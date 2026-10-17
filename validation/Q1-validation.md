# Q1 revalidation - October 17, 2026

Q1(a-c)'s implementation passed the checks below. Live validation ran in an
Ubuntu 24.04 container using Docker Desktop's Linux kernel `6.10.14-linuxkit`.
This verifies code behavior; it does not replace the final Linux/WSL2 experiment
campaign or guarantee a grade. Public-server availability can change.

| Requirement | Evidence |
| --- | --- |
| Python socket client; no iPerf binary or custom receiver | Protocol implemented in `iperf_client.py`; all live peers came from the saved public directory snapshot |
| Control connection and JSON parameter exchange | Ten completed public tests recorded `PARAM_EXCHANGE` and `CREATE_STREAMS`; fixtures also check cookie matching and length-prefixed JSON |
| Data connection and configurable-duration transmission | Each successful live test sent for at least the requested three seconds; unit checks cover partial writes and a blocked send buffer |
| Proper result exchange and shutdown | Every successful trace ended with `TEST_END`, `EXCHANGE_RESULTS`, `DISPLAY_RESULTS`, and `IPERF_DONE`; missing final state is tested as failure |
| Busy/rejecting/nonresponsive servers, timeouts, premature EOF | Live run recovered from a busy rejection and an upload disconnect; fixtures cover signed errors, negotiation rejection, stalled DNS/data, read timeouts, truncated framing, and cleanup |
| Random configurable destination count, addresses/ports recorded | Default count 10 completed with seed 422; initial selection, bounded candidate order, actual peers/ports, and every attempt are saved |
| Bounded replacement and shortfall reporting | Ten successes in twelve attempts with a maximum of twenty; fixtures also check attempt exhaustion, pool exhaustion, and nonzero shortfall |
| Live data-socket TCP_INFO, acknowledged-byte deltas, actual dt | Independent C-header check confirmed all field offsets and the 64-bit ACK counter; all 150 successful intervals independently recomputed from raw counters and timestamps |
| Exclude protocol bytes; baseline/final behavior | Delayed cookie ACK fixture passes; every live run has a baseline and final snapshot, and ACK deltas telescope to the final payload count |
| Throughput plots for all destinations | Three PDF pages cover all ten completed destinations; every page was rendered and visually checked |
| Min/median/mean/p95 by destination and actual algorithm | All ten summary rows independently matched NumPy calculations; all live data sockets reported `cubic` |
| Reproducibility | Exact server input, seed, options, kernel, Python/Matplotlib versions, run IDs, raw JSON/CSV, failure reasons, and standalone plot regeneration are preserved |

## Executed checks

- All **38** unit checks passed on macOS and Linux, including the rebuilt image
  running as an unprivileged user. Mocks/socket pairs are edge-case fixtures,
  not the interoperability evidence.
- The Docker image built successfully from `ubuntu:24.04`.
- The C layout check and output are `check_tcp_info_layout.c` and
  `tcp-info-layout.json`. Compiler packages were installed only inside a
  disposable validation container, not added to the runtime image.
- `q1-retest-10/experiment.json` records ten successes, two failures, and zero
  shortfall. `q1-retest-10/independent-checks.json` records numeric audit totals:
  **150** goodput intervals, **165** CSV snapshots including failed-run samples,
  **10** summary rows, and **3** PDF pages.
- Three-second uploads and 0.2-second sampling were used for this live retest.
  A 60-second-per-destination campaign was not run. Docker Desktop networking
  can change the TCP path/ACK behavior; final observations should use the
  assignment's Linux/WSL2 execution environment.

## Simplifications and fixes

- Removed the duplicate CLI from `iperf_client.py`; `experiment.py` is now the
  single entry point. The protocol functions remain independently testable.
- Removed redundant input hashing (the exact CSV is already copied), the
  security-oriented random-seed dependency, unused test imports, and candidate
  entries beyond the configured attempt limit.
- Simplified sampling scheduling to the next actual snapshot interval and
  avoided closing an already-closed successful data socket twice.
- Fixed malformed oversized numeric results escaping as `OverflowError` and
  socket cleanup when connection setup is interrupted. Added regression checks
  for both and the full control-state lifecycle.
- Kept framing deadlines, DNS/send-stall limits, failure cleanup, raw counters,
  cwnd/RTT/retransmission fields, actual-algorithm logging, and report regeneration.
  These are necessary for Q1 robustness or useful in Q2/Q3.

Repeat the live retest from the assignment directory on a supported Linux/WSL2
host, using a new output directory:

```sh
python3 experiment.py run --servers servers.csv --output results/retest -t 3 --interval 0.2 --timeout 4 --max-attempts 20 --seed 422 --verbose
```
