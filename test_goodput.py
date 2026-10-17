"""Counter-layout, sampling, destination-replacement, and aggregation edge cases."""

import json
import csv
import io
import socket
import struct
import tempfile
import unittest
from contextlib import ExitStack
from pathlib import Path
from unittest.mock import Mock, call, patch

import experiment
import iperf_client
import reporting
import tcp_stats


def tcp_info_fixture(acked, retrans=7):
    # Independent layout: 8 initial bytes, 24 uint32 fields, then four uint64s.
    integers = [0] * 24
    integers[2] = 1448
    integers[6] = 2
    integers[15:17] = [12345, 3210]
    integers[18] = 31
    integers[23] = retrans
    return struct.pack("=8B24I4Q", *([0] * 8), *integers, 0, 0, acked, 0)


class CounterTests(unittest.TestCase):
    def test_native_layout_and_64_bit_counter(self):
        fields = tcp_stats.decode_tcp_info(tcp_info_fixture(2**45 + 123))
        self.assertEqual(fields, {"tcp_info_length": 136, "snd_mss_bytes": 1448,
                                  "lost_segments": 2, "rtt_us": 12345, "rttvar_us": 3210,
                                  "snd_cwnd_segments": 31, "total_retrans_segments": 7,
                                  "bytes_acked": 2**45 + 123, "bytes_received": 0,
                                  "pacing_rate_bytes_per_second": 0,
                                  "delivery_rate_bytes_per_second": None,
                                  "bytes_sent": None, "bytes_retrans": None})

    def test_extended_layout_and_optional_field_boundaries(self):
        # Four uint64s at 104, six uint32s at 136, four uint64s at 160,
        # two uint32s at 192, then sent/retransmitted uint64 byte counters.
        raw = tcp_info_fixture(2**45 + 123) + struct.pack(
            "=6I4Q2I2Q", *([0] * 6), 2**40 + 321, 0, 0, 0, 0, 0, 2**46 + 99, 9876)
        fields = tcp_stats.decode_tcp_info(raw)
        self.assertEqual(fields["delivery_rate_bytes_per_second"], 2**40 + 321)
        self.assertEqual(fields["bytes_sent"], 2**46 + 99)
        self.assertEqual(fields["bytes_retrans"], 9876)
        for length in (128, 135, 136, 160, 167, 168, 207, 208, 215, 216):
            with self.subTest(length=length):
                decoded = tcp_stats.decode_tcp_info(raw[:length])
                for name, end in (("bytes_received", 136), ("delivery_rate_bytes_per_second", 168),
                                  ("bytes_sent", 208), ("bytes_retrans", 216)):
                    self.assertEqual(decoded[name], fields[name] if length >= end else None)

    def test_rate_sentinels_are_unavailable_instead_of_enormous_rates(self):
        raw = bytearray(tcp_info_fixture(100) + bytes(32))
        for sentinel in (2**32 - 1, 2**64 - 1):
            with self.subTest(sentinel=sentinel):
                struct.pack_into("=Q", raw, 104, sentinel)
                fields = tcp_stats.decode_tcp_info(raw)
                self.assertIsNone(fields["pacing_rate_bytes_per_second"])
                self.assertIsNone(fields["delivery_rate_bytes_per_second"])
        struct.pack_into("=Q", raw, 104, 2**40 + 100)
        self.assertEqual(tcp_stats.decode_tcp_info(raw)["pacing_rate_bytes_per_second"], 2**40 + 100)

    def test_truncated_kernel_structure_is_not_zero_filled(self):
        with self.assertRaisesRegex(tcp_stats.StatsError, "at least 128"):
            tcp_stats.decode_tcp_info(tcp_info_fixture(100)[:104])

    def test_counter_is_read_from_supplied_data_socket(self):
        data = Mock()
        data.getsockopt.return_value = tcp_info_fixture(123)
        tcp_stats.read_tcp_info(data)
        data.getsockopt.assert_called_once_with(socket.IPPROTO_TCP, tcp_stats.LINUX_TCP_INFO, 256)

    def test_delayed_cookie_acks_are_excluded_and_real_dt_used(self):
        data = Mock()
        data.getsockopt.side_effect = [tcp_info_fixture(1), tcp_info_fixture(21),
                                      tcp_info_fixture(138, 9)]
        sampler = tcp_stats.GoodputSampler(data, 0.2, cookie_ack_target=38)
        with patch.object(tcp_stats.time, "monotonic", side_effect=[10, 10.2, 10.5]):
            sampler.sample("baseline")
            sampler.sample()
            sampler.sample("final")
        self.assertIsNone(sampler.samples[0]["goodput_bps"])
        self.assertEqual(sampler.samples[1]["goodput_bps"], 0)
        final = sampler.samples[-1]
        self.assertEqual(final["acked_delta_bytes"], 100)
        self.assertAlmostEqual(final["interval_seconds"], 0.3)
        self.assertAlmostEqual(final["goodput_bps"], 800 / 0.3)
        self.assertEqual(final["retrans_delta_segments"], 2)
        self.assertAlmostEqual(final["retrans_rate_segments_per_second"], 2 / 0.3)

    def test_counter_resets_and_nonpositive_time_fail(self):
        previous = {"monotonic_seconds": 1, "payload_bytes_acked": 20,
                    "bytes_acked": 58, "total_retrans_segments": 2}
        current = {**previous, "monotonic_seconds": 2, "payload_bytes_acked": 40, "bytes_acked": 78}
        for change in ({"monotonic_seconds": 1}, {"monotonic_seconds": 0},
                       {"payload_bytes_acked": 0}, {"bytes_acked": 1},
                       {"total_retrans_segments": 1}):
            with self.subTest(change=change), self.assertRaises(tcp_stats.StatsError):
                tcp_stats.interval_values(previous, {**current, **change})

    def test_sampler_wakes_under_send_backpressure_and_takes_final_snapshot(self):
        with ExitStack() as stack:
            control, peer = socket.socketpair()
            data, data_peer = socket.socketpair()
            for sock in (control, peer, data, data_peer):
                stack.enter_context(sock)
            data.setblocking(False)
            try:
                while True:
                    data.send(b"x" * 65536)
            except BlockingIOError:
                pass
            with patch.object(tcp_stats, "read_tcp_info", return_value=tcp_stats.decode_tcp_info(tcp_info_fixture(38))):
                sampler = tcp_stats.GoodputSampler(data, 0.02, 38)
                iperf_client.transmit(control, data, 0.07, 1, sampler)
            self.assertGreaterEqual(len(sampler.samples), 4)
            self.assertEqual(sampler.samples[0]["sample_kind"], "baseline")
            self.assertEqual(sampler.samples[-1]["sample_kind"], "final")
            self.assertGreaterEqual(sampler.samples[-1]["elapsed_seconds"], 0.07)

    def test_algorithm_mismatch_is_rejected(self):
        data = Mock()
        data.getsockopt.return_value = b"reno\0"
        with self.assertRaisesRegex(tcp_stats.StatsError, "requested.*cubic.*got.*reno"):
            tcp_stats.select_congestion_algorithm(data, "cubic")
        data.setsockopt.assert_called_once_with(socket.IPPROTO_TCP, tcp_stats.LINUX_TCP_CONGESTION, b"cubic")

    def test_sampling_exchange_uses_data_socket_and_selects_before_connect(self):
        control, data = Mock(), Mock()
        control.family = socket.AF_INET
        peer = ("192.0.2.1", 5201)
        control.getpeername.return_value = peer
        server_results = {"cpu_util_total": 0, "cpu_util_user": 0, "cpu_util_system": 0,
                          "sender_has_retransmits": -1, "streams": [{"id": 1, "bytes": 1000}]}
        encoded = json.dumps(server_results).encode()
        control.recv.side_effect = io.BytesIO(
            b"\x09\x0a\x01\x02\x0d" + struct.pack("!I", len(encoded)) + encoded + b"\x0e").read
        counters = iter((1, 38, 1038))

        def getsockopt(level, option, size):
            if option == tcp_stats.LINUX_TCP_CONGESTION:
                return b"cubic\0"
            self.assertEqual(option, tcp_stats.LINUX_TCP_INFO)
            return tcp_info_fixture(next(counters))

        def upload(control_socket, data_socket, duration, timeout, sampler):
            self.assertIs(data_socket, data)
            sampler.sample("baseline")
            sampler.sample("final")
            return {"streams": [{"bytes": 1000}]}, 1

        data.getsockopt.side_effect = getsockopt
        with patch.object(iperf_client, "check_support", return_value="cubic"), \
                patch.object(iperf_client, "connect_control", return_value=control), \
                patch.object(iperf_client.socket, "socket", return_value=data), \
                patch.object(iperf_client, "transmit", side_effect=upload):
            result = iperf_client.run_test("example.invalid", duration=1, interval=0.2)
        control.getsockopt.assert_not_called()
        self.assertLess(data.method_calls.index(call.setsockopt(socket.IPPROTO_TCP, 13, b"cubic")),
                        data.method_calls.index(call.connect(peer)))
        self.assertEqual(result["actual_algorithm"], "cubic")
        self.assertEqual(result["requested_algorithm"], "cubic")
        self.assertEqual(result["samples"][-1]["acked_delta_bytes"], 1000)
        self.assertEqual(result["tcp_info_decoding"]["fields"]["rtt_us"]["unit"], "microseconds")


class SelectionTests(unittest.TestCase):
    def test_duplicate_hosts_ranges_and_seeded_selection(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "servers.csv"
            path.write_text("# public directory subset\nhost,port\na.example,5201-5203\nA.EXAMPLE,5203\nb.example,5201\n")
            servers = experiment.load_servers(path)
        self.assertEqual(len(servers), 2)
        self.assertEqual(servers[0]["ports"], [5201, 5202, 5203])
        first = experiment.destination_plan(servers, 422)
        self.assertEqual(first, experiment.destination_plan(servers, 422))
        self.assertEqual(len({row["host"] for row in first}), 2)

    def test_bad_server_input_is_rejected_before_networking(self):
        for content in ("host,port\na,0\n", "host,port\na,5-2\n", "host,port\na,65536\n",
                        "host,port\n,5201\n", "host,port\n", "address,port\na,5201\n"):
            with self.subTest(content=content), tempfile.TemporaryDirectory() as temporary:
                path = Path(temporary) / "servers.csv"
                path.write_text(content)
                with self.assertRaises(ValueError):
                    experiment.load_servers(path)

    def run_fixture(self, failures, count=2, max_attempts=3):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        path = Path(temporary.name) / "servers.csv"
        path.write_text("host,port\na.example,5201\nb.example,5202\nc.example,5203\n")
        output = Path(temporary.name) / "results"
        success = {"status": "success", "actual_algorithm": "cubic", "samples": []}
        responses = [iperf_client.ClientError("server busy") if fail else dict(success) for fail in failures]
        with patch.object(experiment, "check_support", return_value="cubic"), \
                patch.object(experiment, "run_test", side_effect=responses) as run, \
                patch.object(experiment, "generate_reports"):
            manifest = experiment.run_experiment(path, output, count=count, duration=1,
                                                 max_attempts=max_attempts, seed=422)
        return manifest, output, run

    def test_failure_gets_a_distinct_replacement_and_is_preserved(self):
        manifest, output, run = self.run_fixture([True, False, False])
        self.assertEqual(manifest["status"], "complete")
        self.assertEqual(manifest["successful_destinations"], 2)
        self.assertEqual(manifest["shortfall"], 0)
        self.assertEqual(run.call_count, 3)
        self.assertEqual(len({call.kwargs["host"] for call in run.call_args_list}), 3)
        failed = json.loads((output / "runs/attempt-001.json").read_text())
        self.assertEqual(failed["status"], "failed")
        self.assertIn("busy", failed["error"])
        self.assertEqual(json.loads((output / "experiment.json").read_text())["seed"], 422)
        self.assertEqual(manifest["baseline_algorithm"], "cubic")
        self.assertTrue(all(item.kwargs["algorithm"] == "cubic" for item in run.call_args_list))

    def test_attempt_limit_reports_shortfall_and_stops(self):
        manifest, _, run = self.run_fixture([True, True], max_attempts=2)
        self.assertEqual(run.call_count, 2)
        self.assertEqual(manifest["status"], "shortfall")
        self.assertEqual(manifest["shortfall"], 2)

    def test_small_pool_reports_shortfall_instead_of_reusing_hosts(self):
        manifest, _, run = self.run_fixture([False] * 3, count=4, max_attempts=5)
        self.assertEqual(run.call_count, 3)
        self.assertEqual(manifest["shortfall"], 1)


class SummaryTests(unittest.TestCase):
    def test_csv_keeps_tcp_stats_with_run_context_and_handles_older_logs(self):
        sample = tcp_stats.decode_tcp_info(tcp_info_fixture(1000))
        sample.update({"goodput_bps": 8000, "retrans_delta_segments": 2,
                       "retrans_rate_segments_per_second": 4})
        run = {"host": "a.example", "port": 5201, "actual_algorithm": "cubic",
               "run_id": "fixture", "attempt": 1, "status": "success", "samples": [sample]}
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary)
            reporting.write_tables(path, [run, {**run, "run_id": "old", "samples": [{"rtt_us": 123}]}], [])
            with (path / "samples.csv").open(newline="") as stream:
                rows = list(csv.DictReader(stream))
        self.assertEqual(rows[0]["run_id"], "fixture")
        self.assertEqual(rows[0]["actual_algorithm"], "cubic")
        self.assertEqual(rows[0]["snd_cwnd_segments"], "31")
        self.assertEqual(rows[0]["goodput_bps"], "8000")
        self.assertEqual(rows[0]["retrans_rate_segments_per_second"], "4")
        self.assertEqual(rows[1]["delivery_rate_bytes_per_second"], "")

    def test_zero_startup_final_and_failed_samples_have_explicit_treatment(self):
        def run(status="success", algorithm="cubic"):
            return {"host": "a.example", "port": 5201, "actual_algorithm": algorithm,
                    "status": status, "samples": [{"goodput_bps": None}] + [
                        {"goodput_bps": value * 1e6, "interval_seconds": 1,
                         "acked_delta_bytes": value * 1e6 / 8} for value in (0, 8, 16, 24)]}
        rows = reporting.summary_rows([run(), run("failed"), run(algorithm="reno")])
        self.assertEqual(len(rows), 2)
        for row in rows:
            self.assertEqual(row["runs"], 1)
            self.assertEqual(row["intervals"], 4)
            self.assertEqual(row["min_goodput_mbps"], 0)
            self.assertEqual(row["median_goodput_mbps"], 12)
            self.assertEqual(row["mean_goodput_mbps"], 12)
            self.assertAlmostEqual(row["p95_goodput_mbps"], 22.8)

    def test_overall_rate_weights_actual_interval_durations(self):
        rows = reporting.summary_rows([{"host": "a", "port": 5201,
            "actual_algorithm": "cubic", "status": "success", "samples": [
                {"goodput_bps": 32e6, "acked_delta_bytes": 1e6, "interval_seconds": 0.25},
                {"goodput_bps": 8e6 / 0.75, "acked_delta_bytes": 1e6, "interval_seconds": 0.75}]}])
        self.assertAlmostEqual(rows[0]["mean_goodput_mbps"], (32 + 8 / 0.75) / 2)
        self.assertEqual(rows[0]["overall_goodput_mbps"], 16)


if __name__ == "__main__":
    unittest.main()
