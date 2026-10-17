"""Selection, unit conversion, sample pairing, and observation edge cases."""

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import q2_reporting as q2
import reporting


def trace(run_id="fixture", algorithm="cubic", loss=False):
    samples = [{"goodput_bps": None, "sample_kind": "baseline"}]
    for elapsed, dt, acked, cwnd, rtt, retrans in (
            (0.2, 0.2, 250000, 10, 20000, 0), (0.5, 0.3, 500000, 12, 30000, 2),
            (0.8, 0.3, 0, 12, 60000, 0)):
        samples.append({"sample_kind": "interval", "elapsed_seconds": elapsed,
                        "interval_seconds": dt, "acked_delta_bytes": acked,
                        "goodput_bps": 8 * acked / dt, "snd_cwnd_segments": cwnd,
                        "rtt_us": rtt, "retrans_delta_segments": retrans if loss else 0,
                        "snd_mss_bytes": 1460})
    return {"run_id": run_id, "actual_algorithm": algorithm, "status": "success",
            "host": "example.invalid", "port": 5201, "samples": samples,
            "platform": "fixture", "tcp_info_decoding": {"kernel_release": "fixture"}}


class SelectionTests(unittest.TestCase):
    def test_first_success_and_explicit_override_keep_one_run(self):
        failed = {**trace("failed"), "status": "failed"}
        first, second = trace("first"), trace("second")
        self.assertIs(q2.select_representative([failed, first, second], "cubic"), first)
        self.assertIs(q2.select_representative([failed, first, second], "cubic", "second"), second)
        self.assertIsNone(q2.select_representative([failed]))
        for requested in ("failed", "missing"):
            with self.subTest(requested=requested), self.assertRaisesRegex(ValueError, "not a completed run"):
                q2.select_representative([failed, first], "cubic", requested)

    def test_baseline_mismatch_and_missing_metrics_fail_explicitly(self):
        with self.assertRaisesRegex(ValueError, "baseline algorithm"):
            q2.select_representative([trace(algorithm="reno")], "cubic")
        for field, value in (("rtt_us", None), ("goodput_bps", float("nan")),
                             ("interval_seconds", 0), ("retrans_delta_segments", -1)):
            with self.subTest(field=field), self.assertRaises(ValueError):
                run = trace()
                run["samples"][1][field] = value
                q2.select_representative([run])


class PlotTests(unittest.TestCase):
    def test_all_seven_axes_use_correct_units_and_same_intervals(self):
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt

        run = trace(loss=True)
        captured = {}

        def inspect(fig, path, **kwargs):
            if Path(path).name == "q2-timeseries.pdf":
                captured["time"] = [list(ax.lines[0].get_ydata()) for ax in
                                    (fig.axes[0], fig.axes[1], fig.axes[3])]
                captured["loss"] = [bar.get_height() for bar in fig.axes[2].patches]
                captured["widths"] = [bar.get_width() for bar in fig.axes[2].patches]
            if Path(path).name == "q2-scatter.pdf":
                captured["scatter"] = [ax.collections[0].get_offsets().tolist() for ax in fig.axes[:3]]

        with tempfile.TemporaryDirectory() as temporary, patch.object(plt.Figure, "savefig", inspect):
            q2.plot_tcp_metrics(Path(temporary), run, q2.measured_samples(run))
        rates = [10, 8 * 500000 / 0.3 / 1e6, 0]
        self.assertEqual(captured["time"], [[10, 12, 12], [20, 30, 60], rates])
        self.assertEqual(captured["loss"], [0, 2, 0])
        for actual, expected in zip(captured["widths"], (0.2, 0.3, 0.3)):
            self.assertAlmostEqual(actual, expected)
        for pairs, values in zip(captured["scatter"], ([10, 12, 12], [20, 30, 60], [0, 2, 0])):
            self.assertEqual(pairs, [list(pair) for pair in zip(rates, values)])

    def test_zero_loss_observations_do_not_invent_loss_response(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary)
            run = trace()
            q2.write_observations(path, run, q2.measured_samples(run))
            text = (path / "q2-observations.md").read_text()
        self.assertIn("No retransmissions were recorded", text)
        self.assertIn("correlation is undefined", text)
        self.assertIn("7.500 Mbit/s", text)  # 750000 acknowledged bytes / 0.8 s.
        self.assertIn("payload bytes: **1**", text)
        self.assertIn("cannot demonstrate how the algorithm responds to loss", text)

    def test_nonzero_loss_observations_report_actual_event(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary)
            run = trace(loss=True)
            q2.write_observations(path, run, q2.measured_samples(run))
            text = (path / "q2-observations.md").read_text()
        self.assertIn("2 retransmitted segments", text)
        self.assertIn("largest count was 2 at 0.500 s", text)
        self.assertNotIn("No retransmissions were recorded", text)

    def test_constant_window_does_not_imply_rate_is_constant(self):
        run = trace()
        for sample in q2.measured_samples(run):
            sample["snd_cwnd_segments"] = 40
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary)
            q2.write_observations(path, run, q2.measured_samples(run))
            text = (path / "q2-observations.md").read_text()
        self.assertIn("cwnd stayed at 40 segments", text)
        self.assertIn("cannot establish a cwnd/goodput correlation", text)

    def test_no_success_does_not_leave_stale_plots(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary)
            for name in ("q2-timeseries.pdf", "q2-scatter.pdf"):
                (path / name).write_bytes(b"stale")
            q2.generate_q2_reports(path, None)
            self.assertFalse((path / "q2-timeseries.pdf").exists())
            self.assertFalse((path / "q2-scatter.pdf").exists())
            self.assertEqual(json.loads((path / "q2-selection.json").read_text())["status"], "unavailable")

    def test_saved_report_pipeline_records_explicit_selection(self):
        import matplotlib.pyplot as plt

        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary)
            attempts = []
            for run in (trace("first"), trace("second")):
                filename = run["run_id"] + ".json"
                (path / filename).write_text(json.dumps(run))
                attempts.append({"result_file": filename})
            (path / "experiment.json").write_text(json.dumps({
                "attempts": attempts, "baseline_algorithm": "cubic",
                "successful_destinations": 2, "requested_destinations": 2}))
            with patch.object(plt.Figure, "savefig"), patch.object(reporting, "plot_goodput"):
                reporting.generate_reports(path, representative_run="second")
            selection = json.loads((path / "q2-selection.json").read_text())
            self.assertEqual(selection["run_id"], "second")
            self.assertEqual(selection["selection_rule"], "explicit run ID")
            self.assertEqual(selection["intervals"], 3)
            self.assertIn("Run ID: `second`", (path / "q2-observations.md").read_text())


if __name__ == "__main__":
    unittest.main()
