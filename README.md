# Assignment 2: Questions 1 and 2

Python implements one iPerf3 upload stream. Linux supplies TCP reliability and
congestion control. `experiment.py` runs the measurements and generates the plots.

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
| Report, p. 3 | One experiment/plotting entry point; server-list input; documented options, dependencies, commands, raw data, PDF plots, and summary tables. Include an Ubuntu 24.04 Dockerfile, kernel/configuration details, and execute on Linux or WSL2. Submit one PDF with repository/function links, embedded plots, interpretations, plotting-code pointers, and an AI acknowledgement; explain the work orally. |

The PDF requires successful TCP experiments and verification of generated code;
it does **not** require a test suite or submitted test cases. Q3 adds three-algorithm
comparisons, repetitions/test order, and controller pseudocode (pp. 2-3); this
project currently covers Q1/Q2, with one upload per successful destination.

## Run

Use Linux or Windows WSL2, Python 3.10+, and Matplotlib. From this directory:

```sh
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python experiment.py run --servers servers.csv --output results/new -n 10 -t 60 --interval 0.2 --max-attempts 20 --seed 422
```

| Option | Meaning (default) |
| --- | --- |
| `--servers` | `host,port` CSV (`servers.csv` beside the script); inclusive port ranges such as `5201-5210` are accepted |
| `--output` | New output directory; required |
| `-n`, `--count` | Successful distinct server hostnames requested (`10`) |
| `-t`, `--duration` | Whole seconds per upload, 1-86400 (`60`) |
| `--interval` | Sampling interval in seconds (`0.2`) |
| `--timeout` | Connection, protocol, and send-stall timeout in seconds (`10`) |
| `--max-attempts` | Total attempts including replacements (`2*n`) |
| `--seed` | Random selection seed (generated and recorded if omitted) |

The input list comes from [iperf3serverlist.net](https://iperf3serverlist.net/);
its retrieval time is recorded in `servers.csv`. Hosts are shuffled without
replacement, with one listed port chosen per host. Failed attempts are saved.
Exit status is 0 for completion, 1 for a shortfall/error, or 130 for interruption.

Regenerate tables and PDFs from saved data without network traffic (also on macOS):

```sh
python3 experiment.py plot results/q1
python3 experiment.py plot results/q2
```

Docker on a Linux/WSL2 host:

```sh
docker build -t cs422-a2 .
docker run --rm --network host --user "$(id -u):$(id -g)" -v "$PWD:/app" cs422-a2 run --servers /app/servers.csv --output /app/results/new -n 10 -t 60 --interval 0.2 --max-attempts 20 --seed 422
```

Q1/Q2 use the OS default read once at experiment start, selected before each data
connection and verified afterward. No kernel configuration change is needed for
that baseline. The manifest records the kernel and available/default algorithms.

## Files and execution flow

| File | Purpose |
| --- | --- |
| `experiment.py` | Read CLI/servers, shuffle destinations, run bounded attempts, save results, call plotting |
| `iperf_client.py` | Control handshake, continuous upload, result exchange, and cleanup |
| `tcp_stats.py` | Decode Linux TCP_INFO and calculate intervals from data-socket snapshots |
| `reporting.py` | Read saved runs, write CSV tables, generate Q1 and Q2 PDFs |
| `REPORT.md` | Measurement definitions, metric explanations, and findings for the final report |
| `results/q1/`, `results/q2/` | Preserved Q1 multi-destination measurements and the longer Q2 trace |
| `servers.csv`, `requirements.txt`, `Dockerfile` | Input destinations and reproducible environment |

Each result directory contains `experiment.json` (settings, selection, attempts,
shortfall, host metadata), the input `servers.csv`, `runs/attempt-NNN.json` (raw
snapshots and protocol results), `samples.csv`, `summary.csv`, and three PDFs:
`goodput.pdf`, `q2-timeseries.pdf`, `q2-scatter.pdf`. Q2 always uses the first
successful attempt, whose destination, actual algorithm, and run ID label the plots.

[Report notes](REPORT.md) document the saved runs' Docker Desktop limitation.
After collecting final Linux/WSL2 measurements, update those observations and
include the corresponding plots and table in the submission PDF. The notes are
not the final submission. AI assisted implementation, review, and cleanup.
