# Q2(b,c) validation - October 17, 2026

Q2 plotting and observations now run automatically through the existing
`experiment.py run` and `experiment.py plot` commands. Raw Q2(a) measurements
remain the source of every plotted and reported value.

## Implementation and coverage

| Requirement | Implementation/evidence |
| --- | --- |
| One representative destination and actual algorithm | First successful attempt by default; optional `plot --representative-run RUN_ID`; selection saved in `q2-selection.json` and checked against the manifest's baseline algorithm |
| cwnd, RTT, loss, throughput time series | Four labeled panels in `q2-timeseries.pdf`; cwnd in segments, RTT in ms, loss in retransmitted segments per actual interval, goodput in Mbit/s |
| Three scatter relationships | `q2-scatter.pdf` shows cwnd, RTT, and retransmission count against the same-interval goodput; elapsed time is indicated by color |
| Phase/sample treatment | Includes startup, zeros, and the final partial interval; omits the initial undefined-rate baseline; endpoint snapshots are paired with the preceding interval and labeled accordingly |
| Metric explanations and expected effects | `q2-observations.md` explains cwnd/RTT/retransmissions/goodput and congestion-avoidance expectations, with primary TCP/CUBIC references |
| Actual observations/anomalies | Computed ranges/medians, overall goodput, constant-window behavior, peak RTT, retransmission events, and the largest adjacent goodput decrease with accompanying TCP metrics |
| Honest interpretation | Explicit zero-loss/constant-signal handling; no fabricated events, phase labels, causal conclusions, or loss percentage; Docker Desktop limits are identified |
| Reproduction | One entry point, existing dependencies, complete saved input/manifest/raw traces, regeneration without network traffic, and documented representative-run override |

The reporting flow is `reporting.generate_reports()` ->
`q2_reporting.select_representative()` -> `generate_q2_reports()` ->
`plot_tcp_metrics()` and `write_observations()`.

## Executed checks

- All **51** tests passed in the final Ubuntu image as unprivileged user
  `65534:65534`, with container networking disabled. The earlier 50-test suite
  and all eight final Q2-specific checks also passed on macOS.
- New checks inspect the actual Matplotlib axis data: RTT conversion, goodput
  conversion, loss-bar heights and widths, and the exact same-interval scatter
  pairs. Tests also cover failed/missing selections, algorithm mismatch,
  invalid metrics, weighted overall goodput, zero and nonzero loss observations,
  a constant window with variable rate, and stale-plot removal when no run
  completed. Synthetic test fixtures are not presented as measurements.
- The final Docker image built successfully using the existing
  `FROM ubuntu:24.04` Dockerfile. No additional dependencies were introduced.
- One **20-second** upload to public server
  `speedtest.lax12.us.leaseweb.net:5207` completed with **cubic**, the recorded OS
  default. It was the first candidate with seed 422; no replacement was needed.
  The full iPerf3 exchange ended with `IPERF_DONE`.
- The run produced **100 snapshots** (one baseline plus **99 intervals**) over
  20.003 measured seconds. Scheduling uses actual intervals, so exactly 100
  intervals are not assumed from the requested 0.2-second period.
- Every goodput and retransmission delta was independently recomputed from raw
  acknowledged-byte/retransmission counters and monotonic times. CSV values and
  all reported minimum/median/maximum statistics matched the raw JSON. The
  independent audit is saved in `../output/pdf/q2/independent-checks.json`.
- The normal `plot` command regenerated both figures and observations in a
  container using `--network none`. SHA-256 checks confirmed the manifest and
  raw per-attempt JSON were unchanged.
- Both final Q2 PDFs have one page each. Their rendered pages were visually
  inspected: all seven panels, axis units, destination/algorithm/run labels,
  constant-zero loss labels, time-color scale, and captions are legible without
  clipping or overlap.

## Observed behavior and limitations

The example figures and observations are in `../output/pdf/q2/`. The selected
run ID is `bb4f212f-f6f9-4aaf-ab06-371c6ff9bffe`.

- Cwnd stayed at **40 segments**, while interval goodput ranged from
  **58.319 to 338.180 Mbit/s**. The trace therefore does not demonstrate CUBIC
  window-growth cycles or establish a cwnd/goodput correlation.
- RTT ranged from **0.193 to 16.068 ms**. Its highest sample occurred at
  **0.203 s**, during startup.
- There were **zero recorded retransmissions** in the measured intervals.
  The loss scatter is a horizontal zero signal and supplies no loss-response
  evidence. Goodput still varied, so observed rate changes cannot simply be
  attributed to a recorded retransmission event.
- Overall acknowledged goodput was **219.140 Mbit/s**. The largest adjacent
  decrease was **332.692 to 121.411 Mbit/s**, at **16.817 s**, while endpoint
  cwnd remained 40 and RTT changed from 0.810 to 1.944 ms. Its cause is not
  identifiable from these samples alone.

This validation used Ubuntu 24.04 user space, Python 3.12.3, and Docker Desktop's
`6.10.14-linuxkit` kernel. Its forwarding can affect which ACK path and timing
the local socket observes. The reported MSS was 65,483 bytes; no assumption of
1460 bytes or direct physical wire-packet size was made. Use the handout's
Linux/WSL2 execution environment and review the newly generated observations for
the final report. The saved fields do not identify slow start versus congestion
avoidance, and this one run does not establish steady-state behavior or causes.
Q3 comparisons/design and assembly of the final submission PDF are outside this
request.

## Commands

From the assignment directory:

```sh
docker build -t cs422-q2 .
docker run --rm --network none --user 65534:65534 --entrypoint python3 cs422-q2 -m unittest discover -s /app -q
docker run --rm --user "$(id -u):$(id -g)" -v "$PWD:/app" cs422-q2 run --servers /app/servers.csv --output /app/results/q2-new -n 1 -t 20 --interval 0.2 --timeout 5 --max-attempts 2 --seed 422
docker run --rm --network none --user "$(id -u):$(id -g)" -v "$PWD:/app" cs422-q2 plot /app/output/pdf/q2
```

The new-run output directory must not already exist. Regenerating the existing
example is read-only with respect to raw measurements and overwrites only
derived reports. For final measurements on Linux/WSL2, use the README's run
command with the desired transfer duration and destination count.
