"""Q2(b,c): seven plots and trace-based observations for one saved upload."""

import json
import math
import statistics
from pathlib import Path


def measured_samples(run):
    """Keep startup, zero rates, and the final interval; omit only the baseline."""
    samples = [sample for sample in run.get("samples", [])
               if sample.get("goodput_bps") is not None]
    for sample in samples:
        for field in ("elapsed_seconds", "interval_seconds", "acked_delta_bytes", "goodput_bps",
                      "snd_cwnd_segments", "rtt_us", "retrans_delta_segments"):
            value = sample.get(field)
            if not isinstance(value, (int, float)) or not math.isfinite(value) or value < 0:
                raise ValueError(f"Invalid Q2 field {field} in run {run['run_id']}")
        if sample["interval_seconds"] == 0:
            raise ValueError("Q2 intervals must have positive duration")
    return samples


def select_representative(runs, baseline_algorithm=None, run_id=None):
    """Use attempt order, rather than selecting a run for an interesting curve."""
    completed = [run for run in runs if run["status"] == "success"]
    if run_id is not None:
        completed = [run for run in completed if run["run_id"] == run_id]
        if not completed:
            raise ValueError(f"Representative run {run_id!r} is not a completed run")
    if not completed:
        return None
    run = completed[0]
    algorithm = run.get("actual_algorithm")
    if not algorithm or (baseline_algorithm is not None and algorithm != baseline_algorithm):
        raise ValueError("Representative run does not match the recorded Q2 baseline algorithm")
    if not measured_samples(run):
        raise ValueError("Representative run has no measured intervals")
    return run


def plot_tcp_metrics(directory, run, samples):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.ticker import MaxNLocator

    elapsed = [sample["elapsed_seconds"] for sample in samples]
    goodput = [sample["goodput_bps"] / 1e6 for sample in samples]
    metrics = [
        ("Congestion window", "snd_cwnd (segments)", [s["snd_cwnd_segments"] for s in samples]),
        ("Smoothed RTT", "RTT (ms)", [s["rtt_us"] / 1000 for s in samples]),
        ("Retransmission loss proxy", "Retransmitted segments / interval",
         [s["retrans_delta_segments"] for s in samples]),
    ]
    identity = f"{run['host']}:{run['port']} | {run['actual_algorithm']} | run {run['run_id'][:8]}"
    colors = ("#176b91", "#ad661d", "#b14242", "#3c7b50")
    with plt.rc_context({"font.size": 10, "axes.spines.top": False, "axes.spines.right": False,
                         "pdf.fonttype": 42}):
        fig, axes = plt.subplots(2, 2, figsize=(11.7, 8.3), sharex=True)
        for index, (ax, (title, label, values)) in enumerate(zip(
                axes.flat, metrics + [("Acknowledged throughput", "Goodput (Mbit/s)", goodput)])):
            if index == 2:
                ax.bar([s["elapsed_seconds"] - s["interval_seconds"] for s in samples], values,
                       width=[s["interval_seconds"] for s in samples], align="edge",
                       color=colors[index], alpha=0.8)
                ax.yaxis.set_major_locator(MaxNLocator(integer=True))
            else:
                ax.plot(elapsed, values, marker=".", linewidth=1.3, color=colors[index])
            if not any(values):
                ax.set_ylim(0, 1)
                ax.text(0.5, 0.5, "No retransmissions observed" if index == 2 else "All values are zero",
                        transform=ax.transAxes, ha="center", color="#555555")
            else:
                ax.set_ylim(bottom=0)
            ax.set_title(title, loc="left", fontsize=11)
            ax.set_ylabel(label)
            ax.set_xlabel("Elapsed sending time (s)")
            ax.set_xlim(0, elapsed[-1])
            ax.grid(alpha=0.2)
        fig.suptitle(f"TCP statistics during upload\n{identity}", fontsize=13)
        fig.text(0.5, 0.025,
                 "cwnd/RTT are endpoint snapshots; goodput and loss cover the preceding actual interval.\n"
                 "Startup, zeros, and the final partial interval are included; the baseline has no rate.",
                 ha="center", fontsize=9)
        fig.tight_layout(rect=(0, 0.075, 1, 0.91))
        fig.savefig(directory / "q2-timeseries.pdf")
        fig.savefig(directory / "q2-timeseries-preview.png", dpi=130)
        plt.close(fig)

        fig, axes = plt.subplots(1, 3, figsize=(13.5, 5), sharex=True)
        for index, (ax, (title, label, values)) in enumerate(zip(axes, metrics)):
            points = ax.scatter(goodput, values, c=elapsed, cmap="viridis", s=32,
                                vmin=0, vmax=elapsed[-1], edgecolors="white", linewidths=0.3)
            ax.set_title(title + " vs goodput", fontsize=10)
            ax.set_xlabel("Acknowledged goodput (Mbit/s)")
            ax.set_ylabel(label)
            ax.set_xlim(left=0)
            ax.set_ylim(bottom=0)
            ax.grid(alpha=0.2)
            if index == 2:
                ax.yaxis.set_major_locator(MaxNLocator(integer=True))
                if not any(values):
                    ax.set_ylim(-0.1, 1)
                    ax.text(0.5, 0.7, "Loss proxy is constant at zero", transform=ax.transAxes,
                            ha="center", fontsize=9, color="#555555")
        fig.suptitle(f"TCP metrics and acknowledged goodput\n{identity}", fontsize=13)
        fig.text(0.5, 0.025,
                 "Each point pairs one endpoint snapshot/loss count with that interval's goodput.\n"
                 "Color shows elapsed sending time. Correlation does not establish causation.",
                 ha="center", fontsize=9)
        fig.tight_layout(rect=(0, 0.12, 0.92, 0.87))
        color_axis = fig.add_axes((0.935, 0.28, 0.012, 0.4))
        fig.colorbar(points, cax=color_axis, label="Elapsed time (s)")
        fig.savefig(directory / "q2-scatter.pdf")
        fig.savefig(directory / "q2-scatter-preview.png", dpi=130)
        plt.close(fig)


def write_observations(directory, run, samples):
    """Describe computed facts separately from TCP expectations and hypotheses."""
    rates = [sample["goodput_bps"] / 1e6 for sample in samples]
    cwnd = [sample["snd_cwnd_segments"] for sample in samples]
    rtt = [sample["rtt_us"] / 1000 for sample in samples]
    loss = [sample["retrans_delta_segments"] for sample in samples]
    seconds = sum(sample["interval_seconds"] for sample in samples)
    overall = 8 * sum(sample["acked_delta_bytes"] for sample in samples) / seconds / 1e6
    peak = max(samples, key=lambda sample: sample["rtt_us"])
    kernel = (run.get("tcp_info_decoding") or {}).get("kernel_release", run.get("platform", "unknown"))
    lines = [
        "# Question 2(c): TCP metrics and observations", "",
        f"Destination: `{run['host']}:{run['port']}`. Actual algorithm: **{run['actual_algorithm']}**.",
        f"Run ID: `{run['run_id']}`. Kernel: `{kernel}`.",
        f"Selected trace: {len(samples)} measured intervals over {seconds:.3f} seconds.",
        "Plots: [time series](q2-timeseries.pdf) and [scatter plots](q2-scatter.pdf).", "",
        "## Metric meanings and expected influence in congestion avoidance", "",
        "- **snd_cwnd** is the sender's congestion allowance in segments, not actual flight size. "
        "A larger window can permit more useful data per RTT when the flow is window limited. "
        "The rough rate model is `8 * cwnd_segments * snd_mss_bytes / RTT_seconds`; "
        "receiver limits, pacing, application supply, and bottleneck capacity can make achieved goodput lower.",
        "- **RTT** is the kernel's smoothed round-trip estimate, converted from microseconds to milliseconds. "
        "At a fixed window, a longer RTT reduces how quickly ACKs permit new data. Rising RTT alongside "
        "flat goodput can suggest queue buildup, but RTT alone cannot distinguish queues, path changes, "
        "receiver behavior, or virtualization. RTT variation is a delay variation estimate, not squared variance.",
        "- **Loss proxy** is the increase in cumulative retransmitted segments over the interval. "
        "Loss recovery can delay useful delivery and cause a congestion-window reduction. Retransmissions "
        "may be spurious or repeated, so this count is not a loss probability. Detection and its goodput "
        "effect may appear in different intervals; zero retransmissions do not prove a loss-free path.",
        "- **Goodput** is newly acknowledged payload bytes times eight divided by actual interval seconds. "
        "It measures useful delivery visible to this sender, rather than local send acceptance or the "
        "kernel's latest delivery-rate estimate. A retransmitted byte contributes useful delivery once.", "",
    ]
    if run["actual_algorithm"] == "cubic":
        lines.extend(["For CUBIC, congestion-avoidance growth depends on time since the last congestion "
                      "event and the previous window maximum, with a Reno-friendly region. Its usual "
                      "multiplicative decrease factor is about 0.7 after congestion; timeout recovery differs. "
                      "These are expectations from [RFC 9438](https://www.rfc-editor.org/rfc/rfc9438.html), "
                      "not proof that a sampled plateau or decrease is a particular CUBIC phase.", ""])
    lines.extend(["## Measured trace", "",
                  "| Quantity | Minimum | Median | Maximum |", "| --- | ---: | ---: | ---: |"])
    for name, values in (("snd_cwnd (segments)", cwnd), ("RTT (ms)", rtt),
                         ("Retransmitted segments / interval", loss), ("Goodput (Mbit/s)", rates)):
        lines.append(f"| {name} | {min(values):.3f} | {statistics.median(values):.3f} | {max(values):.3f} |")
    lines.extend(["", f"Overall goodput was **{overall:.3f} Mbit/s**, using total acknowledged-byte "
                  "deltas divided by total measured time (rather than an unweighted mean of rates).",
                  f"The sampled cwnd changed from {cwnd[0]} to {cwnd[-1]} segments. "
                  "A wider allowance by itself does not establish that cwnd limited the transfer.", "",
                  "## Notable behavior in this trace", "",
                  f"- The highest sampled RTT was **{peak['rtt_us'] / 1000:.3f} ms** at "
                  f"{peak['elapsed_seconds']:.3f} s, with goodput {peak['goodput_bps'] / 1e6:.3f} Mbit/s "
                  f"and cwnd {peak['snd_cwnd_segments']} segments. The lowest sampled RTT was "
                  f"{min(rtt):.3f} ms. These endpoints describe variability; they do not establish its cause."])
    if min(cwnd) == max(cwnd):
        lines.append(f"- **cwnd stayed at {cwnd[0]} segments** while goodput ranged from "
                     f"{min(rates):.3f} to {max(rates):.3f} Mbit/s. Window changes therefore do not "
                     "explain this trace's rate variation, and the constant cwnd cannot establish a "
                     "cwnd/goodput correlation. It does not show CUBIC window-growth cycles.")
    if sum(loss) == 0:
        lines.append("- **No retransmissions were recorded in the measured intervals.** The loss scatter "
                     "therefore has a constant zero signal: a loss/goodput correlation is undefined, and "
                     "this run cannot demonstrate how the algorithm responds to loss.")
    else:
        event = max(samples, key=lambda sample: sample["retrans_delta_segments"])
        lines.append(f"- The trace recorded **{sum(loss)} retransmitted segments** in "
                     f"{sum(value > 0 for value in loss)} intervals. The largest count was "
                     f"{event['retrans_delta_segments']} at {event['elapsed_seconds']:.3f} s, with goodput "
                     f"{event['goodput_bps'] / 1e6:.3f} Mbit/s. This identifies a retransmission event, "
                     "not its cause or a packet-loss percentage.")
    drops = [(previous, current) for previous, current in zip(samples, samples[1:])
             if previous["goodput_bps"] > current["goodput_bps"]]
    if drops:
        previous, current = max(drops, key=lambda pair: pair[0]["goodput_bps"] - pair[1]["goodput_bps"])
        lines.append(f"- The largest adjacent goodput decrease was from "
                     f"{previous['goodput_bps'] / 1e6:.3f} to {current['goodput_bps'] / 1e6:.3f} Mbit/s "
                     f"at {current['elapsed_seconds']:.3f} s. Endpoint cwnd changed from "
                     f"{previous['snd_cwnd_segments']} to {current['snd_cwnd_segments']} segments, "
                     f"RTT from {previous['rtt_us'] / 1000:.3f} to {current['rtt_us'] / 1000:.3f} ms, "
                     f"and that interval recorded {current['retrans_delta_segments']} retransmitted segments. "
                     "ACK timing, buffering, pacing, or application/receiver limits are possible influences; "
                     "these samples cannot isolate one explanation.")
    else:
        lines.append("- No adjacent goodput decrease was observed among the measured intervals.")
    zeros = sum(value == 0 for value in rates)
    if zeros:
        lines.append(f"- Intervals with zero newly acknowledged payload bytes: **{zeros}**. This is an observed "
                     "ACK-counter stall; it does not by itself prove that no data was sent or that packets were lost.")
    mss = [sample["snd_mss_bytes"] for sample in samples if sample.get("snd_mss_bytes") is not None]
    if mss:
        lines.append(f"- The kernel reported an MSS range of {min(mss)} to {max(mss)} bytes. "
                     "Use this reported MSS when converting cwnd to a byte allowance; these samples "
                     "do not measure physical wire-packet sizes.")
    if "linuxkit" in kernel.lower():
        lines.append("- This trace used Docker Desktop's Linux VM. Its forwarding and host networking "
                     "can affect local ACK timing, RTT, and MSS, so these values should not be treated "
                     "as a verified direct end-to-end view of the remote Internet path. See "
                     "[Docker Desktop networking](https://docs.docker.com/desktop/features/networking/).")
    lines.extend(["", "## Interpretation limits", "",
                  "Every plot and number above uses the same successful run and actual algorithm. "
                  "Startup, zero rates, and the final partial interval are retained; only the initial "
                  "baseline is omitted because its interval goodput/loss is undefined. Snapshot cwnd/RTT "
                  "are paired with the preceding interval's goodput, so feedback can have a lag. Scatter "
                  "associations do not establish causation. A constant metric supplies no correlation evidence.", "",
                  "The saved fields do not identify slow start versus congestion avoidance, so no phase "
                  "is inferred from the shape alone. A single run cannot establish repeatability, fairness, "
                  "or algorithm superiority. Public paths and competing traffic change. No post-send drain "
                  "is measured, so ACKs arriving after the final snapshot are excluded.", ""])
    if seconds < 10:
        lines.extend(["This is a short development trace (under 10 seconds), which is insufficient to "
                      "characterize steady-state congestion avoidance or repeated congestion cycles. "
                      "Use a longer run on the handout's Linux/WSL2 execution host for final observations.", ""])
    lines.extend(["TCP terminology: [RFC 5681](https://www.rfc-editor.org/rfc/rfc5681.html). "
                  "Linux field definitions: [TCP_INFO UAPI](https://github.com/torvalds/linux/blob/v6.8/include/uapi/linux/tcp.h).", "",
                  "AI assistance was used to implement the plotting and observation generator. "
                  "Measured values come from the saved trace; possible explanations are hypotheses.", ""])
    (directory / "q2-observations.md").write_text("\n".join(lines), encoding="utf-8")


def generate_q2_reports(directory, run, explicit_selection=False):
    directory = Path(directory)
    if run is None:
        selection = {"status": "unavailable", "reason": "No completed measurement runs"}
        for name in ("q2-timeseries.pdf", "q2-scatter.pdf", "q2-timeseries-preview.png", "q2-scatter-preview.png"):
            (directory / name).unlink(missing_ok=True)
        (directory / "q2-observations.md").write_text(
            "# Question 2(c)\n\nNo completed measurement runs; no TCP observations or Q2 plots generated.\n",
            encoding="utf-8")
    else:
        samples = measured_samples(run)
        selection = {"status": "selected", "run_id": run["run_id"], "host": run["host"],
                     "port": run["port"], "actual_algorithm": run["actual_algorithm"],
                     "selection_rule": "explicit run ID" if explicit_selection else "first successful run in attempt order",
                     "intervals": len(samples), "baseline_included": False}
        plot_tcp_metrics(directory, run, samples)
        write_observations(directory, run, samples)
    (directory / "q2-selection.json").write_text(json.dumps(selection, indent=2) + "\n", encoding="utf-8")
