# Q2(a) validation - October 17, 2026

Implemented TCP statistics tracing during the existing upload loop. One
TCP_INFO read supplies both endpoint TCP metrics and the raw counters for the
preceding interval's goodput and retransmission proxy. Measurements use the live
data socket. The experiment reads the OS default algorithm once and selects it
on each data socket before connecting, then verifies the actual selection.

## Saved fields and interpretation

- Required: UTC timestamp, monotonic/elapsed time, `snd_cwnd_segments`, `rtt_us`,
  `lost_segments`, cumulative `total_retrans_segments`, interval
  `retrans_delta_segments`, and acknowledged `goodput_bps` on each measured row.
- Recommended: `rttvar_us`, `pacing_rate_bytes_per_second`,
  `delivery_rate_bytes_per_second`, cumulative `bytes_acked`, `bytes_received`,
  `bytes_sent`, and `bytes_retrans` when exposed by the kernel.
- `retrans_rate_segments_per_second` accounts for unequal interval durations.
  The count/rate is a retransmission proxy, not a measured loss probability.
  `lost_segments` is a gauge; it is not differenced as a cumulative counter.
- Run JSON contains destination/port, resolved peer, run ID, requested/actual
  algorithm, and `tcp_info_decoding` with kernel, byte order, offsets, widths,
  units, availability rules, and formulas. CSV repeats run/destination/algorithm
  context per row and uses metric names with units.
- Missing optional fields and unlimited/unavailable rate estimates are null in
  JSON and blank in CSV. The initial baseline has no interval rate. The final
  partial sending interval is included; there is no post-transfer ACK drain.
  Protocol cookie ACKs are excluded from payload goodput, including delayed ACKs.

## Executed validation

1. All **43** unit checks passed on macOS and in the rebuilt `cs422-q2a` image,
   including execution as user `65534:65534`. New checks exercise independent
   binary fixtures, 64-bit values, optional-field truncation boundaries, pacing
   sentinels, unavailable delivery estimates, mismatched algorithms, selection
   before connect, data/control socket separation, and CSV compatibility with
   older saved logs. Existing checks cover irregular interval times, delayed
   cookie ACKs, counter resets, backpressure, protocol framing, and cleanup.
2. The existing `FROM ubuntu:24.04` Dockerfile built successfully. Compiler
   packages were installed only in a disposable check container. The independent
   `check_tcp_info_layout.c` compiled against Ubuntu's installed Linux UAPI
   headers. All **12** decoded field offsets and the 64-bit ACK-counter width
   matched Python's decoder; output is `q2a-tcp-info-layout.json`. The versioned
   layout reference is Linux v6.8's stable TCP_INFO prefix; the execution kernel
   below returned 248 bytes, with later unused fields ignored.
3. A real three-second upload to public server
   `speedtest.lax12.us.leaseweb.net:5207` completed the full iPerf3 exchange ending
   in `IPERF_DONE`. Both requested and actual data-socket algorithms were
   **cubic**. The trace contains **16** snapshots: one baseline and **15**
   measured intervals at a requested 0.2 seconds. Every recommended field was
   available during sending. This was the first candidate from the bundled
   server list with seed 422; no replacement was needed.
4. An independent audit recomputed every goodput interval, retransmission delta,
   and retransmission rate from saved raw counters and actual monotonic times.
   Every value matched. All decoded CSV field values matched JSON, run context
   was present, and baseline/final samples were retained. Results are in
   `q2a-linux-smoke/independent-checks.json`; raw traces are
   `q2a-linux-smoke/attempt-001.json` and `q2a-linux-smoke/samples.csv`.

The live validation used Ubuntu 24.04 user space, Python 3.12.3, and Docker
Desktop's Linux kernel `6.10.14-linuxkit`. Docker Desktop forwarding can change
the observed ACK path, MSS, RTT, and rates. These are development validation
measurements; use the required Linux/WSL2 host for final experiment observations.
No final measurement campaign, Q2(b) visualization, Q2(c) interpretation, or Q3
comparison was performed for this implementation request.

## Reproduce

From the assignment directory on Linux/WSL2:

```sh
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s . -v
python3 experiment.py run --servers servers.csv --output results/q2a -n 1 -t 60 --interval 0.2 --max-attempts 2 --seed 422
```

The normal entry point writes per-attempt JSON and `samples.csv`; it also
continues generating the existing Q1 goodput plots and summaries. The short
validation above saved JSON/CSV with `run_test()`, `write_tables()`, and
`summary_rows()` directly and did not generate additional plots.
