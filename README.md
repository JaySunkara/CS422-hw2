# Assignment 2: Questions 1–3

Python implements one iPerf3 upload stream. Linux supplies TCP reliability and
congestion control. `experiment.py` runs the measurements and generates the plots,
for the OS default (Q1/Q2) or for CUBIC, Reno, and BBR with repetitions (Q3).

## Requirements in the handout

Page numbers refer to [assignment-2.pdf](assignment-2.pdf).

| Location | Required work and reporting |
| --- | --- |
| Q1(a), p. 1 | Python socket client: control connection, JSON negotiation, data connection, configurable upload duration, proper iPerf3 termination; handle rejection, timeout, and premature closure. Use public standard servers; do not invoke the iPerf3 binary or use a custom receiver. |
| Q1(b), p. 1 | Random configurable destination count; record addresses/ports, failed attempts, bounded replacements, and any shortfall. |
| Q1(c), pp. 1-2 | Goodput from acknowledged-byte deltas and actual elapsed time, using data-socket `getsockopt()`; plot every destination and tabulate minimum, median, mean, and p95 per destination/algorithm. |
| Q2 introduction, p. 2 | Use CUBIC or the OS default. “Record the algorithm actually used and use it for all measurements, plots, and observations in this question.” |
| Q2(a), p. 2 | Sample timestamp, cwnd, RTT, loss signal, and goodput together on the live data socket. Save CSV/JSON with units, destination, algorithm, run ID; document decoding and interval/loss calculations. RTT variation, pacing, cumulative counters, and delivery rate are recommended. |
| Q2(b), p. 2 | Automatically generate PDF time series of cwnd, RTT, loss, goodput, and three scatter relationships against goodput for one representative destination. |
| Q2(c), p. 2 | “Explain what each of the above TCP metrics (in the visualizations) means and how you expect it to influence goodput in congestion avoidance, and describe any anomalous behavior observed in your traces.” |
| Q3(a), p. 2 | Repeat Q1/Q2 with CUBIC, Reno, BBR selected before connecting; record the actual algorithm; same destinations, duration, interval; multiple runs with reported count and order; Q2(b) plots per algorithm on one destination with consistent axes; regimes via cwnd, RTT, queueing, loss, BDP; variability and limits of public paths. |
| Q3(b), p. 3 | Pseudocode for a congestion controller using RTT, loss proxy, and throughput; design choices; fairness and convergence; assumptions and limitations. |
| Report, p. 3 | One experiment/plotting entry point; server-list input; documented options, dependencies, commands, raw data, PDF plots, and summary tables. Include an Ubuntu 24.04 Dockerfile, kernel/configuration details, and execute on Linux or WSL2. Submit one PDF with repository/function links, embedded plots, interpretations, plotting-code pointers, and an AI acknowledgement; explain the work orally. |

The PDF requires successful TCP experiments and verification of generated code;
it does **not** require a test suite or submitted test cases. Q3(b) is pseudocode
and analysis in [REPORT.md](REPORT.md); it is not implemented in the kernel.

## Run

Use Linux or Windows WSL2, Python 3.10+, and Matplotlib. From this directory:

```sh
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
# Q3: CUBIC, Reno, and BBR, three repetitions each (the defaults)
.venv/bin/python experiment.py run --servers servers.csv --output results/q3 -n 5 -t 30 --interval 0.2 --repetitions 3 --seed 422
# Q1/Q2: OS default only, one upload per destination
.venv/bin/python experiment.py run --servers servers.csv --output results/new -n 10 -t 60 --interval 0.2 --max-attempts 20 --seed 422 --algorithms default --repetitions 1
```

| Option | Meaning (default) |
| --- | --- |
| `--servers` | `host,port` CSV (`servers.csv` beside the script); inclusive port ranges such as `5201-5210` are accepted |
| `--output` | New output directory; required |
| `-n`, `--count` | Successful distinct server hostnames requested (`10`) |
| `-t`, `--duration` | Whole seconds per upload, 1-86400 (`60`) |
| `--interval` | Sampling interval in seconds (`0.2`) |
| `--timeout` | Connection, protocol, and send-stall timeout in seconds (`10`) |
| `--max-attempts` | Total destinations tried, including replacements (`2*n`) |
| `--algorithms` | Comma-separated algorithms, or `default` for the OS default only (`cubic,reno,bbr`) |
| `-r`, `--repetitions` | Runs per destination and algorithm (`3`) |
| `--pause` | Seconds to wait before each test; public servers often reset a test that starts right after the previous one (`5`) |
| `--retries` | Extra tries of the same server after a failed test, each saved as its own attempt (`1`) |
| `--seed` | Random selection seed (generated and recorded if omitted) |

The input list comes from [iperf3serverlist.net](https://iperf3serverlist.net/);
its retrieval time is recorded in `servers.csv`. Hosts are shuffled without
replacement, with one listed port chosen per host. Failed attempts are saved.
Exit status is 0 for completion, 1 for a shortfall/error, or 130 for interruption.

**Q3 test order.** Repetition 1 admits destinations: a server counts only if it
completes a test with every algorithm (otherwise it is logged and replaced), so all
algorithms are compared on the same destinations. Each repetition rotates the
algorithm order (Latin square: cubic,reno,bbr / reno,bbr,cubic / bbr,cubic,reno), and
repetitions 2..R sweep all admitted destinations in turn, so repeats of one
destination/algorithm pair are minutes apart. Later failures are recorded as missing
runs, not retried. `experiment.json` records every run's `repetition` and `order_index`.

Regenerate tables and PDFs from saved data without network traffic (also on macOS):

```sh
python3 experiment.py plot results/q1
python3 experiment.py plot results/q2
```

Docker on a Linux/WSL2 host:

```sh
docker build -t cs422-a2 .
docker run --rm --network host --user "$(id -u):$(id -g)" -v "$PWD:/app" cs422-a2 run --servers /app/servers.csv --output /app/results/q3 -n 5 -t 30 --interval 0.2 --repetitions 3 --seed 422
```

Q1/Q2 use the OS default read once at experiment start, selected before each data
connection and verified afterward. No kernel configuration change is needed for
that baseline. The manifest records the kernel and available/allowed/default algorithms.

**Q3 host setup.** A container uses the host kernel, so BBR must be available on the
host (Docker Desktop's macOS VM offered only `reno cubic`). On the Linux/WSL2 host:

```sh
cat /proc/sys/net/ipv4/tcp_available_congestion_control   # must list bbr
cat /proc/sys/net/ipv4/tcp_allowed_congestion_control     # non-root users may only select these
# If either lacks bbr (needs root, e.g. ask the lab admin):
sudo modprobe tcp_bbr
sudo sysctl -w net.ipv4.tcp_allowed_congestion_control="reno cubic bbr"
```

`run` checks every requested algorithm on a throwaway socket before sending any traffic.
If Docker is unavailable (common on lab machines), run natively with the venv commands above.

## Files and execution flow

| File | Purpose |
| --- | --- |
| `experiment.py` | Read CLI/servers, shuffle destinations, run bounded attempts, save results, call plotting |
| `iperf_client.py` | Control handshake, continuous upload, result exchange, and cleanup |
| `tcp_stats.py` | Decode Linux TCP_INFO and calculate intervals from data-socket snapshots |
| `reporting.py` | Read saved runs, write CSV tables, generate Q1 and Q2 PDFs; dispatch Q3 directories |
| `comparison.py` | Q3 per-run metrics (queueing delay, BDP), variability/algorithm tables, Q3 PDFs |
| `REPORT.md` | Measurement definitions, metric explanations, and findings for the final report |
| `results/q1/`, `results/q2/` | Preserved Q1 multi-destination measurements and the longer Q2 trace |
| `results/q3/` | Q3 run: 5 destinations × CUBIC/Reno/BBR × 3 repetitions (native Ubuntu VM, kernel 7.0.0) |
| `servers.csv`, `requirements.txt`, `Dockerfile` | Input destinations and reproducible environment |

Each result directory contains `experiment.json` (settings, selection, attempts,
shortfall, host metadata), the input `servers.csv`, `runs/attempt-NNN.json` (raw
snapshots and protocol results), `samples.csv`, `summary.csv`, and three PDFs:
`goodput.pdf`, `q2-timeseries.pdf`, `q2-scatter.pdf`. Q2 always uses the first
successful attempt, whose destination, actual algorithm, and run ID label the plots.

Q3 directories (more than one algorithm or repetition) instead contain:

| Output | Content |
| --- | --- |
| `goodput.pdf` | One panel per destination; one curve per algorithm, first repetition bold |
| `q3-timeseries.pdf` | Representative destination: rows = algorithms, columns = cwnd, RTT, loss, goodput; one y-scale per column |
| `q3-scatter.pdf` | Representative destination: cwnd, RTT, loss vs goodput per algorithm; shared axes |
| `q3-compare.pdf` | All destinations, one point per run: goodput, queueing delay, cwnd·MSS/BDP, goodput vs base RTT |
| `summary.csv` | Min/median/mean/p95 goodput per destination × algorithm (admitted destinations only) |
| `q3-runs.csv` | Per run: goodput, min/median/p95 RTT, queueing delay, retransmits, cwnd, BDP estimate |
| `q3-variability.csv` | Per destination × algorithm: mean, stdev, coefficient of variation across repetitions |
| `q3-algorithms.csv` | Per algorithm: medians across runs, and destinations where it had the best goodput / lowest RTT |

The representative destination is the first admitted destination with every
algorithm × repetition run completed. Queueing delay is median sRTT minus the
kernel's `tcpi_min_rtt`; the BDP estimate is the highest kernel delivery rate × that
minimum RTT.

[Report notes](REPORT.md) document the saved Q1/Q2 runs' Docker Desktop limitation,
the Q3 method and results, and the congestion-control design.
After collecting final Linux/WSL2 measurements, update those observations and
include the corresponding plots and table in the submission PDF. The notes are
not the final submission. AI assisted implementation, review, and cleanup.
