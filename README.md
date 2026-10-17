# Questions 1 and 2: iPerf3 uploads, TCP statistics, plots, and observations

The client implements the iPerf3 socket protocol in Python. The experiment script
randomly selects public destinations, replaces failed tests within an attempt
limit, records Linux TCP_INFO alongside goodput, and generates Q1/Q2 PDF plots,
summary tables, and trace-based Q2 observations.
No iPerf3 executable, wrapper, or custom receiver is used.

## Run Q1(b,c) on Linux or WSL2

Python 3.10+ and Matplotlib are required. From this assignment directory:

```sh
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python experiment.py run --servers servers.csv --output results/q1 -n 10 -t 60 --interval 0.2 --max-attempts 20 --seed 422
```

The output directory must be new; existing measurements are protected. This
command requests 10 completed destinations, with at most 20 total attempts.
Transfers are sequential. A short check can use `-n 2 -t 2 --max-attempts 4`.
macOS supports regeneration of saved plots, but measurement runs fail clearly
before contacting servers. `experiment.py` is the single command-line entry point;
`iperf_client.py` contains the protocol implementation used by it.

| Option for `experiment.py run` | Meaning | Default |
| --- | --- | --- |
| `--servers` | CSV with `host,port` headers | Bundled `servers.csv` |
| `--output` | New results directory | Required |
| `-n`, `--count` | Number of successfully tested destinations | `10` |
| `-t`, `--duration` | Whole seconds per upload, 1 to 86400 | `60` |
| `--interval` | Requested sampling interval, seconds | `0.2` |
| `--timeout` | Setup/I/O/send-stall timeout, seconds | `10` |
| `--max-attempts` | Total attempts, including initial destinations | `2*n` |
| `--seed` | Reproducible selection/port seed | Generated and saved |
| `-v`, `--verbose` | Print iPerf3 control-state transitions | Off |

Exit codes: `0` means all requested destinations completed; `1` means a shortfall
or operational error; `130` means interrupted. Ctrl-C preserves the interrupted
attempt and previous successful runs. Invalid run configuration fails locally.

## Destination selection and failures

`servers.csv` contains 183 entries retrieved from the
[public directory API](https://iperf3serverlist.net/api/servers) on October 17,
2026. The source and retrieval time are in its comment lines. To refresh it,
copy current addresses and ports from [iperf3serverlist.net](https://iperf3serverlist.net/)
into the same CSV format. Extra columns such as country/provider are accepted.
Port ranges are inclusive; only one randomly chosen port is tested per hostname:

```csv
host,port
speedtest.chi11.us.leaseweb.net,5201-5210
chi.speedtest.clouvider.net,5201-5209
```

`load_servers()` validates ports and merges repeated hostnames and their ports.
`destination_plan()` shuffles distinct hostnames without replacement and picks
one of each host's listed ports using the same seed. The initial `n` choices and
replacement order up to the attempt limit are saved before the first connection. Different aliases
for the same physical machine are not deduplicated by DNS.

`run_experiment()` advances through that order until `n` successes, the attempt
limit, or pool exhaustion. A rejected/busy/rate-limit error, stalled transfer,
timeout, premature EOF, or invalid result is saved as a failed attempt, then a
different destination is tried. Low achieved throughput alone is a valid
measurement, not evidence that negotiation failed. No hostname is retried within
one experiment. Failures retain their reason and any partial samples; successful
measurements alone contribute to plots and summary statistics. The manifest,
terminal output, and exit code report any shortfall, including when `n` exceeds
the available pool.

## Acknowledged goodput

The kernel supplies TCP reliability and congestion control. `tcp_stats.py`
samples the **live data socket** using
`getsockopt(IPPROTO_TCP, TCP_INFO, 256)`. It also queries the data socket's actual
`TCP_CONGESTION` name. For Q1/Q2(a), `check_support()` reads the OS default once
at experiment start. Each data socket selects that same algorithm with
`TCP_CONGESTION` **before connecting**, then verifies the actual selection after
connection. A mismatch fails the attempt. The manifest records `baseline_algorithm`
and every run records both `requested_algorithm` and `actual_algorithm`.
All Q2 measurements therefore use one baseline even if the system default changes
between destinations. This uses the handout's OS-default option; it does not run
the Q3 comparison.

`GoodputSampler` records a baseline immediately before payload transmission,
periodic snapshots during sending, and a final snapshot before `TEST_END` and
socket cleanup. `transmit()` includes the next sampling time in its `select()`
deadline, so a full send buffer does not prevent sampling. Samples stay in
memory during the upload and are saved afterward. When scheduling slips, it
records one real snapshot and schedules the next interval from that snapshot; it does not
invent catch-up samples.

For each pair of snapshots:

```text
dt = current_monotonic_time - previous_monotonic_time
acknowledged_delta = current_payload_bytes_acked - previous_payload_bytes_acked
goodput_bps = 8 * acknowledged_delta / dt
```

The data socket's counter is captured before sending the 37-byte protocol cookie.
`cookie_ack_target` is that counter plus 37. Each snapshot retains the raw
`bytes_acked` and computes `payload_bytes_acked = max(0, bytes_acked - cookie_ack_target)`.
This excludes cookie bytes even if their ACK arrives after payload transmission
starts. Initial TCP sequence-space accounting is removed by the pre-cookie
counter. The baseline has no interval rate. Nonpositive time or decreasing
counters fail explicitly.

The final, possibly shorter interval is included. There is no post-test drain
period: bytes still unacknowledged at the last snapshot are excluded. Setup and
result-exchange time are excluded too. `payload_bytes_sent` and
`application_send_rate_bps` retain their Q1(a) meaning (bytes accepted by local
`send()`); neither is used as a substitute for acknowledged goodput.

### TCP_INFO layout and units

Linux UAPI fields use native byte order, fixed-width unsigned integers, and the
explicit byte offsets below. `struct.unpack_from("=I", ...)` reads 32 bits and
`"=Q"` reads 64 bits; network order is only used for iPerf3 framing. At least 128
returned bytes are required; a shorter structure fails rather than filling
missing counters with zeros. The returned length is saved in every sample.

| Saved field | Offset | Width | Units |
| --- | ---: | ---: | --- |
| `snd_mss_bytes` | 16 | 32 bits | Bytes |
| `lost_segments` | 32 | 32 bits | Current lost segments |
| `rtt_us` | 68 | 32 bits | Microseconds, already unscaled |
| `rttvar_us` | 72 | 32 bits | Microseconds |
| `snd_cwnd_segments` | 80 | 32 bits | Segments |
| `total_retrans_segments` | 100 | 32 bits | Cumulative retransmitted segments |
| `pacing_rate_bytes_per_second` | 104 | 64 bits | Bytes/second |
| `bytes_acked` | 120 | 64 bits | Cumulative acknowledged bytes |
| `bytes_received` | 128 | 64 bits | Cumulative received bytes (optional) |
| `delivery_rate_bytes_per_second` | 160 | 64 bits | Bytes/second (optional) |
| `bytes_sent` | 200 | 64 bits | Cumulative sent bytes, including retransmissions (optional) |
| `bytes_retrans` | 208 | 64 bits | Cumulative retransmitted bytes (optional) |

Each optional field is decoded only when all its bytes are present in the
returned structure. Missing fields are `null` in JSON and blank in CSV; they are
never fabricated zeros. Unlimited pacing (`UINT32_MAX` or `UINT64_MAX`) is saved
as `null`, as is a zero delivery rate (no valid estimate yet). Other reported
zeros remain zeros. Kernel delivery rate is its latest ACK-derived estimate,
which can reflect application-limited sending; it is distinct from our interval
goodput. The decoder ignores any unneeded trailing fields.

`rtt_us` is the exported smoothed RTT, already unscaled: divide by 1000 for
milliseconds. `rttvar_us` is RTT variation, in microseconds, not squared units.
`snd_cwnd_segments` is a congestion allowance in segments, not the amount of data
actually in flight. An approximate byte allowance is `snd_cwnd_segments * snd_mss_bytes`.

These offsets were checked against the
[Linux tcp_info declaration](https://github.com/torvalds/linux/blob/v6.8/include/uapi/linux/tcp.h)
and [tcp_get_info exporter](https://github.com/torvalds/linux/blob/v6.8/net/ipv4/tcp.c).
Every sampled run saves `tcp_info_decoding`: execution kernel release, CPU
architecture, actual byte order, requested/minimum lengths, offsets, unsigned
formats, units, and formulas. Explicit offsets avoid dependence on Python's
implicit native alignment. The returned `tcp_info_length` is also saved per row.
The development Linux kernel returned 248 bytes.

## Question 2(a): tracing during transfer

The same command records all Q2(a) measurements; there is no separate sampling
thread or timer that could misalign goodput and TCP statistics:

```sh
python3 experiment.py run --servers servers.csv --output results/q2a -n 1 -t 60 --interval 0.2 --max-attempts 2 --seed 422
```

For each snapshot, `GoodputSampler.sample()` reads one TCP_INFO structure from
the live upload socket and stores its UTC timestamp, monotonic/elapsed time,
cwnd, smoothed RTT, RTT variation, raw acknowledged-byte and retransmission
counters, pacing rate, and available delivery-rate/sent/received byte fields.
`goodput_bps` and the loss proxy share that snapshot and its preceding actual
interval. The first baseline has `null` interval values because there is no
previous measurement; all following rows, including the final partial interval,
contain goodput and loss values. Snapshot cwnd/RTT describe the interval endpoint,
while goodput averages the preceding interval.

The loss proxy is:

```text
retrans_delta_segments = current_total_retrans_segments - previous_total_retrans_segments
retrans_rate_segments_per_second = retrans_delta_segments / interval_seconds
```

It counts retransmitted segments observed during the interval. It is **not an
exact packet-loss probability**: a segment may be retransmitted more than once,
retransmissions can be spurious, and a loss may be detected in a later interval.
No packet-count denominator is assumed. `lost_segments` is a current outstanding
loss estimate; it is saved as a snapshot and is not differenced as a cumulative
counter. Raw retransmission totals include connection/cookie activity; taking
deltas from the payload baseline excludes earlier activity, though a delayed
cookie retransmission could still appear during sending.

`runs/attempt-NNN.json` stores destination/port, resolved peer, run ID, algorithm,
decoding/units metadata, and every snapshot. `samples.csv` repeats destination,
run ID, actual algorithm, and status on every row, with units in metric names
(`_us`, `_seconds`, `_segments`, `_bytes_per_second`, `_bps`; all `bytes_*`
counters are bytes). Both formats retain raw cumulative counters for recomputing
interval goodput and retransmission deltas. Failed/interrupted attempts keep
partial samples and their status.

## Question 2(b,c): plots and observations

`experiment.py run` automatically generates the Q2 outputs after measurements.
`experiment.py plot` regenerates them from saved JSON without sending traffic:

```sh
python3 experiment.py run --servers servers.csv --output results/q2 -n 1 -t 60 --interval 0.2 --max-attempts 2 --seed 422
python3 experiment.py plot results/q2
```

Q2 uses **one representative run**, selected as the first successful attempt in
the manifest's recorded order. Selection does not depend on throughput or whether
the plot looks interesting. `q2-selection.json` identifies the run ID,
destination/port, actual algorithm, sample count, and selection rule. Every Q2
figure and observation uses that same run. The selected algorithm must match the
manifest's baseline; old Q1 logs without that field use the selected run's actual
algorithm. Failed/interrupted runs are excluded. If no run completed, the script
records that fact and generates no Q2 plots or invented observations.

To choose another completed run, copy its full `run_id` from its JSON and use:

```sh
python3 experiment.py plot results/q2 --representative-run RUN_ID
```

That override applies to this invocation; omitting it selects the first success
again. An unknown/failed run or algorithm mismatch fails clearly.

`q2-timeseries.pdf` contains four panels: cwnd in segments, smoothed RTT in
milliseconds, retransmitted segments per interval, and acknowledged goodput in
decimal Mbit/s. The retransmission bars span their actual intervals. The other
points sit at interval endpoints. `q2-scatter.pdf` contains three panels with
goodput on the x axis and cwnd, RTT, and retransmission count on the y axes.
Color indicates elapsed sending time. Units, destination, actual algorithm, and
run identifier appear on the figures. PNG previews are also generated.

All measured intervals are retained, including startup, zero rates, and the
final partial interval. The initial baseline has no interval rate and is omitted
from these paired plots. Endpoint cwnd/RTT and preceding-interval goodput can
have a feedback lag; a scatter relationship does not establish causation. A
constant zero loss signal is labeled explicitly and is not jittered or replaced
with fabricated events. The loss proxy remains a count, not a loss percentage.

`q2-observations.md` explains each metric and its expected effect in congestion
avoidance, then reports measured ranges/medians, overall goodput, the peak RTT,
retransmission events, and the largest adjacent goodput decrease with its
corresponding cwnd/RTT/loss values. Potential explanations are identified as
hypotheses. It explicitly handles zero-loss and ACK-counter stalls, includes the
reported MSS and Docker Desktop limitation when applicable, and avoids inferring
TCP phase or causation from a curve alone. Copy and review this text for the final
report after collecting measurements on Linux/WSL2.

The implementation follows a short flow: `reporting.generate_reports()` reads
the manifest and run JSON, `q2_reporting.select_representative()` chooses and
validates one run, `plot_tcp_metrics()` generates the seven panels, and
`write_observations()` computes the accompanying trace facts. No additional
dependencies beyond Matplotlib are needed.

`output/pdf/q2/` contains a generated example from a 20-second CUBIC upload,
with its input, manifest, and raw JSON/CSV preserved. Its two PDFs were rendered
and visually checked; observation statistics were independently recomputed.
All **51** checks passed in the final Linux container. See
`validation/Q2bc-validation.md` for the observed behavior and environment limits.

## Saved outputs and regeneration

| File | Contents |
| --- | --- |
| `experiment.json` | Seed, initial selection, candidate order, attempts, statuses, shortfall, settings, kernel/Python/Matplotlib metadata |
| `servers.csv` | Exact input snapshot |
| `runs/attempt-NNN.json` | Run ID, destination/port, actual algorithm, protocol results/events, raw counters, timestamps, and derived intervals; failure details when applicable |
| `samples.csv` | All saved snapshots, including baseline and failed-run samples, with run ID and status |
| `summary.csv`, `summary.md` | Minimum, median, mean, p95, overall rate, and interval/run counts per destination/port/actual algorithm |
| `goodput.pdf` | Goodput over time for every completed destination, up to four panels per page |
| `goodput-preview.png` | First plot page for quick inspection |
| `q2-selection.json` | Representative destination/run/algorithm and selection rule |
| `q2-timeseries.pdf` | Four TCP metric/goodput time series for the representative run |
| `q2-scatter.pdf` | Three relationships against goodput, colored by elapsed time |
| `q2-timeseries-preview.png`, `q2-scatter-preview.png` | Previews of the two Q2 figures |
| `q2-observations.md` | Metric explanations, computed observations, anomalies, and interpretation limits |

The four requested summary statistics use all measured intervals from successful
runs, including startup, zero-goodput intervals, and the final partial interval.
Mean is the unweighted arithmetic mean of interval rates. p95 linearly
interpolates at index `0.95*(N-1)` in sorted rates. The additional `overall` column
uses `8*sum(acked_delta_bytes)/sum(interval_seconds)`, which accounts for unequal
interval lengths. Rates in the summary are decimal Mbit/s. If saved runs include
repetitions, their intervals are pooled within each destination/port/algorithm
group, with the run count shown and separate curves in the plots.

Regenerate plots/tables without network traffic (Linux or macOS):

```sh
python3 experiment.py plot results/q1
```

## Docker

The supplied Dockerfile starts with `FROM ubuntu:24.04` and installs Python and
Matplotlib. On a supported Linux/WSL2 host, from this assignment directory:

```sh
docker build -t cs422-q1 .
docker run --rm --network host --user "$(id -u):$(id -g)" -v "$PWD:/app" cs422-q1 run --servers /app/servers.csv --output /app/results/q1 -n 10 -t 60 --interval 0.2 --max-attempts 20 --seed 422
```

TCP_INFO and congestion control come from the execution kernel, which is recorded
in the manifest. No privileges or kernel configuration changes are needed for
Q1's default algorithm. Docker Desktop was used for a development smoke test;
its VM/network forwarding can change the TCP path and ACK behavior. Use the
handout's Linux/WSL2 environment for the final experiment campaign.

## Verification

```sh
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s . -v
```

The checks cover partial framing, EOF,
deadlines, decoding/truncation, delayed cookie ACKs, actual time differences,
sampling under backpressure, replacement limits, shortfalls, aggregation, the full
control-state exchange, cleanup after interrupted connection setup/upload,
optional-field boundaries, rate sentinels, algorithm pinning, and CSV compatibility
with older logs. Q2 plotting checks cover representative selection, unit
conversion, same-interval pairing, actual loss-bar widths, zero-loss and nonzero-loss
observations, failed runs, and the saved-report pipeline. See
`validation/Q2bc-validation.md` for current Q2(b,c) evidence and
`validation/Q2a-validation.md` for the earlier measurement checks.
Isolated socket pairs/mocks test edge cases; interoperability uses public servers.

The independent C check in `validation/check_tcp_info_layout.c` was compiled
against Linux's installed UAPI header. Every decoded field offset and the 64-bit
acknowledged-byte width matched; see `validation/q2a-tcp-info-layout.json` for
the extended Q2(a) decoder and `validation/tcp-info-layout.json` for the original Q1 check.
The revalidation results and requirement coverage are in `validation/Q1-validation.md`.

For Q2(a), all **43** checks passed on macOS and in the rebuilt Ubuntu container
as an unprivileged user. `validation/q2a-linux-smoke/` contains a completed
three-second public upload using `cubic`, with 16 snapshots and 15 intervals.
All required/recommended fields were available; goodput and retransmission
deltas/rates were independently recomputed, and JSON/CSV values matched. See
`validation/Q2a-validation.md` for details and environment limits.

`validation/q1-retest-10/` contains the latest live check: **10 completed public
destinations in 12 attempts**, three seconds per upload, and 0.2-second sampling.
One busy-server rejection and one premature disconnect were logged and replaced.
All 150 successful goodput intervals and ten summary rows were independently
recomputed, and all three PDF pages were visually checked. See
`validation/Q1-validation.md` for requirement-by-requirement evidence and limits.

`validation/q1-linux-smoke/` contains the earlier two-destination check with seed 422,
two seconds per destination, and 0.2-second sampling. Both selected LeaseWeb
servers (Los Angeles and Hong Kong) completed; both local data sockets reported
`cubic`. Ten intervals per destination and the baseline were saved. Their raw
counter differences and interval rates were independently rechecked, and the
PDF was visually inspected. The image built successfully on Ubuntu 24.04;
the execution kernel was `6.10.14-linuxkit` (Docker Desktop), Python `3.12.3`.
This short check is not the final 10-destination, 60-second campaign.

Earlier Q1(a) protocol success/refusal evidence remains in `validation/`.
Protocol sequencing was checked against official iPerf3 3.17.1
[client states](https://github.com/esnet/iperf/blob/3.17.1/src/iperf_client_api.c),
[parameter/result JSON](https://github.com/esnet/iperf/blob/3.17.1/src/iperf_api.c),
and [TCP cookie handling](https://github.com/esnet/iperf/blob/3.17.1/src/iperf_tcp.c).
AI assistance was used for implementation, protocol/source inspection, and
verification. Q3 algorithm comparisons/design are outside this implementation.
