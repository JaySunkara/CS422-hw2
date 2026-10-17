# Q1/Q2 report notes

These notes describe the preserved measurements. Reproduction commands and
handout question/page references are in [README.md](README.md).

## Measurement method (Q1(c), Q2(a))

The OS default is read once, applied to every data socket before connecting, and
queried afterward. Every successful saved run used **cubic**. The Python client
implements the iPerf3 exchange; the kernel implements TCP and CUBIC.

TCP_INFO uses native byte order with explicit byte offsets: `=I` is an unsigned
32-bit value and `=Q` an unsigned 64-bit value. We request 256 bytes and require
at least 128 for `bytes_acked`; unavailable optional values are null/blank.
The kernel, byte order, layout, and actual returned length are recorded with runs.

| Field | Offset | Format | Unit |
| --- | ---: | --- | --- |
| snd_mss | 16 | `=I` | bytes |
| rtt | 68 | `=I` | microseconds, already unscaled |
| rttvar | 72 | `=I` | microseconds |
| snd_cwnd | 80 | `=I` | segments |
| total_retrans | 100 | `=I` | cumulative segments |
| pacing_rate | 104 | `=Q` | bytes/s |
| bytes_acked | 120 | `=Q` | cumulative bytes |
| delivery_rate | 160 | `=Q` | bytes/s, optional |

Layout reference: [Linux TCP_INFO](https://github.com/torvalds/linux/blob/v6.8/include/uapi/linux/tcp.h).
Unlimited pacing values and an unavailable zero delivery-rate estimate become null.
JSON retains any additional fields recorded by earlier versions of the sampler.

```text
payload_acked = max(0, bytes_acked - pre_cookie_bytes_acked - 37)
dt = current_monotonic_time - previous_monotonic_time
goodput_bps = 8 * delta(payload_acked) / dt
loss_proxy = delta(total_retrans)              # retransmitted segments / interval
```

The 37-byte iPerf3 cookie is excluded even if its ACK arrives late. Baseline,
periodic, and final snapshots use the live upload socket. The baseline has no
interval rate; all subsequent intervals, including startup, zeros, and the final
partial interval, are included. No drain period is measured after sending ends.
Timestamp is UTC; `_seconds`, `_us`, `_bps`, and byte/segment field names give units.
RTT/cwnd are endpoint snapshots; goodput/loss describe the preceding interval.

`summary.csv` groups successful intervals by destination, port, and actual
algorithm. Mean is the unweighted mean of interval rates; p95 interpolates at
`0.95*(N-1)` in sorted rates. Overall goodput uses total acknowledged bytes divided
by total measured time. Failed/interrupted attempts are excluded from summaries.
Rates are decimal Mbit/s. This Q1/Q2 run plan has one repetition per destination.

## Metric meanings and expected effects (Q2(c))

- **cwnd:** sender congestion allowance in segments. When window limited, a larger
  window can raise goodput; the rough bound is `8*cwnd*MSS/RTT_seconds`. It is an
  allowance, not the amount currently in flight.
- **RTT:** smoothed round-trip time. At fixed cwnd, longer RTT slows ACK feedback
  and lowers the window-limited rate. Rising RTT with flat goodput can suggest queues.
- **Loss proxy:** retransmitted segments per interval. Recovery can delay delivery
  and reduce cwnd. Retransmissions can be repeated or spurious; this is not a loss
  percentage, and loss detection can lag its effects.
- **Goodput:** newly acknowledged useful payload per actual elapsed second.
  Retransmitted payload counts once when acknowledged. Local `send()` acceptance
  and the kernel's latest delivery-rate estimate are different measurements.

## Preserved results and observations

**Q1:** [goodput plots](results/q1/goodput.pdf), [summary table](results/q1/summary.csv).
Ten destinations completed in 12 attempts, with 3-second uploads and 0.2-second
sampling: 150 successful intervals. A busy rejection and a premature disconnect
were retained and replaced; the requested destination count had no shortfall.
These short runs verify coverage and interoperability, but do not characterize
steady congestion avoidance.

**Q2:** [time series](results/q2/q2-timeseries.pdf), [scatter plots](results/q2/q2-scatter.pdf).
Representative destination: `speedtest.lax12.us.leaseweb.net:5207`;
run `bb4f212f-f6f9-4aaf-ab06-371c6ff9bffe`, **cubic**, 99 intervals over 20.003 s.
Overall goodput was **219.140 Mbit/s**. Every Q2 figure and observation uses this run.

| Metric | Minimum | Median | Maximum |
| --- | ---: | ---: | ---: |
| cwnd (segments) | 40 | 40 | 40 |
| RTT (ms) | 0.193 | 0.780 | 16.068 |
| Retransmitted segments / interval | 0 | 0 | 0 |
| Goodput (Mbit/s) | 58.319 | 225.041 | 338.180 |

cwnd stayed at 40 while goodput varied, so window changes do not explain the
variation. The zero loss proxy cannot demonstrate a loss response or a loss/goodput
correlation. The highest RTT was 16.068 ms at 0.203 s. The largest adjacent goodput
drop was 332.692 to 121.411 Mbit/s at 16.817 s: cwnd remained 40, RTT rose from
0.810 to 1.944 ms, and no retransmissions were recorded. ACK timing, buffering,
pacing, or receiver/application limits are possible explanations, not established causes.

Both saved datasets used Docker Desktop, kernel **6.10.14-linuxkit**, Python
**3.12.3**. Q2 reported MSS **65483 bytes**; forwarding through the VM can affect
MSS, RTT, and ACK timing, so these are development measurements. Final experiments
must use Linux or WSL2 as required on p. 3. No extra kernel configuration was used.
Scatter associations do not establish causation, and these samples do not identify
TCP phases or prove fairness, repeatability, or controller superiority.

For the final PDF, embed the corresponding plots and table, include the repository
and relevant function/line links, and update observations if measurements change.
AI assisted implementation, checking, and cleanup.
