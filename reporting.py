"""Recreate Q1(c)/Q2(b,c) reports from saved runs without sending more traffic."""

import csv
import json
import math
import statistics
from collections import defaultdict
from pathlib import Path

from q2_reporting import generate_q2_reports, select_representative


def percentile(values, fraction):
    """Linear interpolation between adjacent sorted observations (inclusive ends)."""
    values = sorted(values)
    position = (len(values) - 1) * fraction
    low = math.floor(position)
    high = math.ceil(position)
    return values[low] + (values[high] - values[low]) * (position - low)


def summary_rows(runs):
    groups = defaultdict(list)
    for run in runs:
        if run["status"] == "success":
            groups[(run["host"], run["port"], run["actual_algorithm"])].append(run)
    rows = []
    for (host, port, algorithm), group in sorted(groups.items()):
        samples = [sample for run in group for sample in run["samples"]
                   if sample["goodput_bps"] is not None]
        if not samples:
            raise ValueError(f"Successful run for {host}:{port} has no goodput intervals")
        rates = [sample["goodput_bps"] / 1e6 for sample in samples]
        seconds = sum(sample["interval_seconds"] for sample in samples)
        acked = sum(sample["acked_delta_bytes"] for sample in samples)
        rows.append({
            "host": host, "port": port, "actual_algorithm": algorithm,
            "runs": len(group), "intervals": len(samples),
            "min_goodput_mbps": min(rates),
            "median_goodput_mbps": statistics.median(rates),
            "mean_goodput_mbps": statistics.mean(rates),
            "p95_goodput_mbps": percentile(rates, 0.95),
            "overall_goodput_mbps": 8 * acked / seconds / 1e6,
            "acknowledged_bytes": acked, "measured_seconds": seconds,
        })
    return rows


SUMMARY_FIELDS = ["host", "port", "actual_algorithm", "runs", "intervals",
                  "min_goodput_mbps", "median_goodput_mbps", "mean_goodput_mbps",
                  "p95_goodput_mbps", "overall_goodput_mbps", "acknowledged_bytes",
                  "measured_seconds"]
SAMPLE_FIELDS = ["run_id", "attempt", "host", "port", "actual_algorithm", "status",
                 "sample_kind", "timestamp_utc", "monotonic_seconds", "elapsed_seconds",
                 "interval_seconds", "bytes_acked", "payload_bytes_acked",
                 "acked_delta_bytes", "goodput_bps", "tcp_info_length",
                 "snd_cwnd_segments", "snd_mss_bytes", "rtt_us", "rttvar_us",
                 "lost_segments", "total_retrans_segments", "retrans_delta_segments",
                 "retrans_rate_segments_per_second", "pacing_rate_bytes_per_second",
                 "delivery_rate_bytes_per_second", "bytes_received", "bytes_sent", "bytes_retrans"]


def write_tables(directory, runs, summaries):
    with (directory / "samples.csv").open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=SAMPLE_FIELDS)
        writer.writeheader()
        for run in runs:
            context = {name: run.get(name) for name in SAMPLE_FIELDS[:6]}
            for sample in run.get("samples", []):
                writer.writerow({**context, **sample})
    with (directory / "summary.csv").open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=SUMMARY_FIELDS)
        writer.writeheader()
        writer.writerows(summaries)
    lines = ["| Destination | Algorithm | Min | Median | Mean | p95 | Overall |",
             "| --- | --- | ---: | ---: | ---: | ---: | ---: |"]
    for row in summaries:
        values = [f"{row[field]:.3f}" for field in SUMMARY_FIELDS[5:10]]
        lines.append(f"| {row['host']}:{row['port']} | {row['actual_algorithm']} | "
                     + " | ".join(values) + " |")
    lines.extend(["", "All rates are Mbit/s (1 Mbit/s = 1,000,000 bit/s).",
                  "Min/median/mean/p95 use all valid sending intervals of successful runs,",
                  "including startup, zeros, and the final partial interval. Mean is the",
                  "unweighted arithmetic mean; p95 uses linear interpolation at 0.95*(N-1).",
                  "Overall = 8*sum(acknowledged byte deltas)/sum(actual interval seconds).",
                  "Failed/interrupted runs are logged but excluded from this table.", ""])
    (directory / "summary.md").write_text("\n".join(lines), encoding="utf-8")


def plot_goodput(directory, runs, manifest):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.backends.backend_pdf import PdfPages

    groups = defaultdict(list)
    for run in runs:
        if run["status"] == "success":
            groups[(run["host"], run["port"], run["actual_algorithm"])].append(run)
    items = sorted(groups.items())
    with PdfPages(directory / "goodput.pdf") as pdf:
        for start in range(0, max(1, len(items)), 4):
            batch = items[start:start + 4]
            columns = min(2, max(1, len(batch)))
            rows = math.ceil(max(1, len(batch)) / columns)
            fig, axes = plt.subplots(rows, columns, figsize=(12, 4 * rows + 1), squeeze=False)
            for ax in axes.flat:
                ax.set_visible(False)
            if not items:
                axes[0, 0].set_visible(True)
                axes[0, 0].axis("off")
                axes[0, 0].text(0, 0.7, "No completed measurement runs.\nSee experiment.json for failures.",
                                transform=axes[0, 0].transAxes)
            for ax, ((host, port, algorithm), group) in zip(axes.flat, batch):
                ax.set_visible(True)
                for run in group:
                    samples = [sample for sample in run["samples"] if sample["goodput_bps"] is not None]
                    ax.plot([sample["elapsed_seconds"] for sample in samples],
                            [sample["goodput_bps"] / 1e6 for sample in samples],
                            marker=".", linewidth=1.3, label=run["run_id"][:8])
                ax.set_title(f"{host}:{port}\n{algorithm}", fontsize=10)
                ax.set_xlabel("Elapsed sending time (s)")
                ax.set_ylabel("Acknowledged goodput (Mbit/s)")
                ax.set_ylim(bottom=0)
                ax.grid(alpha=0.25)
                if len(group) > 1:
                    ax.legend(fontsize=8)
            fig.suptitle(f"TCP acknowledged goodput | {manifest['successful_destinations']}/"
                         f"{manifest['requested_destinations']} destinations completed", fontsize=14)
            fig.text(0.5, 0.015, "Each point averages newly acknowledged payload bytes over the preceding actual interval.",
                     ha="center", fontsize=9)
            fig.tight_layout(rect=(0, 0.04, 1, 0.94))
            pdf.savefig(fig)
            if start == 0:
                fig.savefig(directory / "goodput-preview.png", dpi=130)
            plt.close(fig)


def generate_reports(directory, representative_run=None):
    directory = Path(directory)
    manifest = json.loads((directory / "experiment.json").read_text(encoding="utf-8"))
    runs = [json.loads((directory / attempt["result_file"]).read_text(encoding="utf-8"))
            for attempt in manifest["attempts"]]
    representative = select_representative(runs, manifest.get("baseline_algorithm"), representative_run)
    summaries = summary_rows(runs)
    write_tables(directory, runs, summaries)
    plot_goodput(directory, runs, manifest)
    generate_q2_reports(directory, representative, explicit_selection=representative_run is not None)
    return summaries
