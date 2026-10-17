"""Offline edge-case checks. Public-server interoperability is checked separately."""

import json
import io
import socket
import struct
import time
import unittest
from contextlib import ExitStack
from unittest.mock import Mock, patch

import iperf_client as client


class FramingTests(unittest.TestCase):
    def test_fragmented_json_prefix_and_utf8_payload(self):
        encoded = '{"message":"caf\u00e9"}'.encode("utf-8")
        wire = struct.pack("!I", len(encoded)) + encoded
        sock = Mock()
        sock.recv.side_effect = [bytes([byte]) for byte in wire]
        self.assertEqual(client.recv_json(sock, time.monotonic() + 1),
                         {"message": "caf\u00e9"})

    def test_json_length_counts_encoded_bytes(self):
        sock = Mock()
        client.send_json(sock, {"message": "caf\u00e9"}, time.monotonic() + 1)
        wire = sock.sendall.call_args.args[0]
        self.assertEqual(struct.unpack("!I", wire[:4])[0], len(wire[4:]))
        self.assertEqual(json.loads(wire[4:]), {"message": "caf\u00e9"})

    def test_eof_in_length_or_body(self):
        for chunks in ([b"\0", b""], [struct.pack("!I", 5), b"{", b""]):
            with self.subTest(chunks=chunks):
                sock = Mock()
                sock.recv.side_effect = chunks
                with self.assertRaisesRegex(client.ClientError, "premature EOF"):
                    client.recv_json(sock, time.monotonic() + 1)

    def test_unreasonable_json_lengths(self):
        for size in (0, client.MAX_JSON_SIZE + 1, 0xffffffff):
            with self.subTest(size=size):
                sock = Mock()
                sock.recv.return_value = struct.pack("!I", size)
                with self.assertRaisesRegex(client.ClientError, "frame length"):
                    client.recv_json(sock, time.monotonic() + 1)
                self.assertEqual(sock.recv.call_count, 1)

    def test_malformed_or_rejected_json(self):
        for body in (b"{", b"\xff", b"[]", b'{"error":"policy rejection"}'):
            with self.subTest(body=body):
                sock = Mock()
                sock.recv.side_effect = [struct.pack("!I", len(body)), body]
                with self.assertRaises(client.ClientError):
                    client.recv_json(sock, time.monotonic() + 1)

    def test_partial_reads_share_one_deadline(self):
        sock = Mock()
        sock.recv.side_effect = [b"a", b"b"]
        with patch.object(client.time, "monotonic", side_effect=[10, 10.4]):
            self.assertEqual(client.recv_exact(sock, 2, 11), b"ab")
        self.assertEqual(sock.settimeout.call_args_list[0].args[0], 1)
        self.assertAlmostEqual(sock.settimeout.call_args_list[1].args[0], 0.6)

    def test_unresponsive_control_has_a_real_timeout(self):
        with ExitStack() as stack:
            receiver, peer = socket.socketpair()
            stack.enter_context(receiver)
            stack.enter_context(peer)
            started = time.monotonic()
            with self.assertRaises(TimeoutError):
                client.recv_exact(receiver, 1, started + 0.03)
            self.assertLess(time.monotonic() - started, 0.5)


class StateTests(unittest.TestCase):
    def test_signed_server_states(self):
        for state, message in ((client.State.ACCESS_DENIED, "busy"),
                               (client.State.SERVER_TERMINATE, "prematurely")):
            with self.subTest(state=state):
                sock = Mock()
                sock.recv.return_value = struct.pack("!b", state)
                with self.assertRaisesRegex(client.ClientError, message):
                    client.recv_state(sock, time.monotonic() + 1)

    def test_server_error_includes_both_network_order_codes(self):
        sock = Mock()
        sock.recv.side_effect = [b"\xfe", struct.pack("!I", 130), struct.pack("!I", 22)]
        with self.assertRaisesRegex(client.ClientError, "error=130, remote errno=22"):
            client.recv_state(sock, time.monotonic() + 1)

    def test_authorization_error_can_omit_errno(self):
        sock = Mock()
        sock.recv.side_effect = [b"\xfe", struct.pack("!I", 142), b""]
        with self.assertRaisesRegex(client.ClientError, "error=142, remote errno=None"):
            client.recv_state(sock, time.monotonic() + 1)

    def test_unknown_state_is_rejected(self):
        sock = Mock()
        sock.recv.return_value = b"\x7f"
        with self.assertRaisesRegex(client.ClientError, "unknown iPerf3 state"):
            client.recv_state(sock, time.monotonic() + 1)


class UploadTests(unittest.TestCase):
    def test_partial_sends_count_only_accepted_bytes(self):
        control, data = Mock(), Mock()
        data.send.side_effect = [3, BlockingIOError(), 2]
        # Start, loop time, check deadline, send progress, repeated for each write,
        # then finish at the configured deadline. No real network transfer here.
        ticks = [0, 0, 0, 0.1, 0.1, 0.1, 0.2, 0.2, 0.3, 1, 1]
        with patch.object(client.time, "monotonic", side_effect=ticks), \
                patch.object(client.select, "select", return_value=([], [data], [])):
            results, elapsed = client.transmit(control, data, 1, 5)
        self.assertEqual(results["streams"][0]["bytes"], 5)
        self.assertEqual(elapsed, 1)
        self.assertEqual(len(data.send.call_args_list[1].args[0]), client.BLOCK_SIZE - 3)
        self.assertEqual(len(data.send.call_args_list[2].args[0]), client.BLOCK_SIZE - 3)

    def test_duration_and_stall_deadlines_under_backpressure(self):
        with ExitStack() as stack:
            control, control_peer = socket.socketpair()
            data, data_peer = socket.socketpair()
            for sock in (control, control_peer, data, data_peer):
                stack.enter_context(sock)
            data.setblocking(False)
            try:
                while True:
                    data.send(b"x" * 65536)
            except BlockingIOError:
                pass
            # A full local socket buffer must not turn send() into an unbounded wait.
            started = time.monotonic()
            results, elapsed = client.transmit(control, data, 0.03, 1)
            self.assertEqual(results["streams"][0]["bytes"], 0)
            self.assertGreaterEqual(elapsed, 0.03)
            self.assertLess(time.monotonic() - started, 0.5)
            with self.assertRaisesRegex(TimeoutError, "no send progress"):
                client.transmit(control, data, 1, 0.03)

    def test_control_rejection_stops_upload_before_another_send(self):
        control, data = Mock(), Mock()
        control.recv.return_value = b"\xff"
        with patch.object(client.select, "select", return_value=([control], [data], [])):
            with self.assertRaisesRegex(client.ClientError, "ACCESS_DENIED"):
                client.transmit(control, data, 1, 1)
        data.send.assert_not_called()

    def test_data_eof_stops_upload(self):
        control, data = Mock(), Mock()
        data.recv.return_value = b""
        with patch.object(client.select, "select", return_value=([data], [data], [])):
            with self.assertRaisesRegex(client.ClientError, "closed before"):
                client.transmit(control, data, 1, 1)
        data.send.assert_not_called()


class ConnectionTests(unittest.TestCase):
    def test_stalled_dns_is_bounded(self):
        def stalled_dns(*args, **kwargs):
            time.sleep(0.1)
            return []

        with patch.object(client.socket, "getaddrinfo", side_effect=stalled_dns):
            started = time.monotonic()
            with self.assertRaisesRegex(TimeoutError, "DNS resolution timed out"):
                client.connect_control("example.invalid", 5201, 0.02)
            self.assertLess(time.monotonic() - started, 0.5)

    def test_refused_connection_closes_socket(self):
        address = (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("192.0.2.1", 5201))
        sock = Mock()
        sock.connect.side_effect = ConnectionRefusedError("refused")
        with patch.object(client.socket, "getaddrinfo", return_value=[address]), \
                patch.object(client.socket, "socket", return_value=sock):
            with self.assertRaisesRegex(client.ClientError, "could not connect"):
                client.connect_control("example.invalid", 5201, 1)
        sock.close.assert_called_once()

    def test_interrupted_connect_closes_unreturned_socket(self):
        address = (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("192.0.2.1", 5201))
        sock = Mock()
        sock.connect.side_effect = KeyboardInterrupt()
        with patch.object(client.socket, "getaddrinfo", return_value=[address]), \
                patch.object(client.socket, "socket", return_value=sock):
            with self.assertRaises(KeyboardInterrupt):
                client.connect_control("example.invalid", 5201, 1)
        sock.close.assert_called_once()

    def test_negotiation_failure_reports_stage_and_cleans_up(self):
        control = Mock()
        control.getpeername.return_value = ("192.0.2.1", 5201)
        control.recv.return_value = b"\xff"
        with patch.object(client, "connect_control", return_value=control):
            with self.assertRaisesRegex(client.ClientError, "parameter negotiation.*busy"):
                client.run_test("example.invalid", duration=1)
        cookie = control.sendall.call_args_list[0].args[0]
        self.assertEqual(len(cookie), 37)
        self.assertTrue(cookie.endswith(b"\0"))
        self.assertEqual(control.sendall.call_args_list[-1].args[0], b"\x0c")
        control.close.assert_called_once()

    def test_invalid_configuration_fails_before_connecting(self):
        cases = ({"port": 0}, {"port": 65536}, {"duration": 0},
                 {"duration": 1.5}, {"timeout": float("nan")},
                 {"timeout": float("inf")}, {"timeout": -1})
        with patch.object(client, "connect_control") as connect:
            for options in cases:
                with self.subTest(options=options), self.assertRaises(ValueError):
                    client.run_test("example.invalid", **options)
            connect.assert_not_called()


class ResultTests(unittest.TestCase):
    def test_missing_or_wrong_stream_cannot_claim_success(self):
        base = {"cpu_util_total": 0, "cpu_util_user": 0, "cpu_util_system": 0,
                "sender_has_retransmits": -1, "streams": [{"id": 1, "bytes": 123}]}
        client.validate_results(base)
        for change in ({"streams": []}, {"streams": [{"id": 2, "bytes": 123}]},
                       {"streams": [{"id": 1, "bytes": -1}]},
                       {"streams": [{"id": 1, "bytes": 10**1000}]},
                       {"cpu_util_total": 10**1000},
                       {"cpu_util_total": float("nan")}, {"cpu_util_user": None}):
            with self.subTest(change=change), self.assertRaises(client.ClientError):
                client.validate_results({**base, **change})


class ExchangeTests(unittest.TestCase):
    """Recorded-format messages through the whole state machine, without a receiver."""

    def exercise(self, wire, upload_error=None):
        control, data = Mock(), Mock()
        control.family = socket.AF_INET
        control.getpeername.return_value = ("192.0.2.1", 5201)
        control.recv.side_effect = io.BytesIO(wire).read
        results = {"streams": [{"id": 1, "bytes": 1000}]}
        with patch.object(client, "connect_control", return_value=control), \
                patch.object(client.socket, "socket", return_value=data), \
                patch.object(client, "transmit", return_value=(results, 1), side_effect=upload_error):
            try:
                return client.run_test("example.invalid", duration=1), control, data
            finally:
                self.control, self.data = control, data

    def test_full_exchange_sends_matching_cookie_and_ends_with_done(self):
        server_results = {"cpu_util_total": 0, "cpu_util_user": 0, "cpu_util_system": 0,
                          "sender_has_retransmits": -1, "streams": [{"id": 1, "bytes": 1000}]}
        encoded = json.dumps(server_results).encode()
        result, control, data = self.exercise(
            b"\x09\x0a\x01\x02\x0d" + struct.pack("!I", len(encoded)) + encoded + b"\x0e")
        self.assertEqual(result["status"], "success")
        writes = [call.args[0] for call in control.sendall.call_args_list]
        self.assertEqual(data.sendall.call_args.args[0], writes[0])
        data.connect.assert_called_once_with(("192.0.2.1", 5201))
        self.assertEqual(json.loads(writes[1][4:])["parallel"], 1)
        self.assertEqual(writes[2], b"\x04")
        self.assertEqual(json.loads(writes[3][4:])["streams"][0]["bytes"], 1000)
        self.assertEqual(writes[-1], b"\x10")
        data.close.assert_called_once()
        control.close.assert_called_once()

    def test_missing_display_results_is_failure_and_closes_both_sockets(self):
        encoded = json.dumps({"cpu_util_total": 0, "cpu_util_user": 0, "cpu_util_system": 0,
                              "sender_has_retransmits": -1, "streams": [{"id": 1, "bytes": 10}]}).encode()
        with self.assertRaisesRegex(client.ClientError, "result exchange.*EOF"):
            self.exercise(b"\x09\x0a\x01\x02\x0d" + struct.pack("!I", len(encoded)) + encoded)
        self.data.close.assert_called_once()
        self.control.close.assert_called_once()
        self.assertEqual(self.control.sendall.call_args.args[0], b"\x0c")

    def test_invalid_state_order_cannot_claim_success(self):
        with self.assertRaisesRegex(client.ClientError, "expected CREATE_STREAMS"):
            self.exercise(b"\x09\x01")
        self.control.close.assert_called_once()

    def test_interrupted_upload_closes_both_sockets_and_notifies_server(self):
        with self.assertRaises(KeyboardInterrupt):
            self.exercise(b"\x09\x0a\x01\x02", upload_error=KeyboardInterrupt())
        self.assertEqual(self.control.sendall.call_args.args[0], b"\x0c")
        self.control.close.assert_called_once()
        self.data.close.assert_called_once()


if __name__ == "__main__":
    unittest.main()
