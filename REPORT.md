# Report notes (Q1–Q3)

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
| min_rtt | 148 | `=I` | microseconds, kernel windowed minimum (added for Q3; absent in Q1/Q2 data) |
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


## Q3(a): CUBIC, Reno, and BBR comparison

**Status: method and tooling done; results pending the Linux lab-machine run.**
The saved Q1/Q2 data cannot be used: Docker Desktop's kernel offered only
`reno cubic` and distorted cwnd/MSS. Fill in the bracketed items from `results/q3`.

**Method.** Same destinations, duration, and sampling interval for every algorithm.
The algorithm is set with `TCP_CONGESTION` on the data socket before `connect()` and
read back afterward (`actual_algorithm`). Repetition 1 admits destinations: a server
counts only if it completes a test with all three algorithms; otherwise it is logged
and replaced. Each repetition rotates the order (cubic,reno,bbr / reno,bbr,cubic /
bbr,cubic,reno), so no algorithm always runs first while the path drifts. Repetitions
2..R sweep all admitted destinations, so repeats are minutes apart. Later failures are
reported as missing runs. Run: [n] destinations × 3 algorithms × [R] repetitions,
[t] s each, 0.2 s sampling, seed [422]; host kernel [uname -r]; [Docker or native].

**Derived per-run metrics** (`comparison.py`, `run_metrics`):

```text
min_rtt         = min(tcpi_min_rtt)          # raw kernel minimum; ≈ propagation delay
queueing_delay  = median(srtt) - min_rtt     # standing queue the flow builds
bottleneck_rate = max(tcpi_delivery_rate)    # best delivery rate observed
BDP             = bottleneck_rate × min_rtt  # bytes the path holds without queueing
cwnd_to_bdp     = median(cwnd) × MSS / BDP   # > 1: excess window sits in a queue
```

**Plots to embed:** `q3-timeseries.pdf` and `q3-scatter.pdf` (representative destination
[host:port]), `q3-compare.pdf` (all runs), `goodput.pdf`; tables `summary.csv`,
`q3-algorithms.csv`, `q3-variability.csv`.

**Hypotheses to confirm or refute with the data:**

| | Expected throughput | Expected RTT/queue | Why |
| --- | --- | --- | --- |
| Reno | Lowest on high-BDP (long-RTT, fast) paths; similar on short paths | Fills buffer, sawtooth | +1 MSS per RTT takes BDP/MSS RTTs to fill the pipe; halves on loss |
| CUBIC | High on high-BDP paths | Fills buffer; RTT rises toward a loss | Growth depends on time since loss, not RTT; ×0.7 on loss |
| BBR | High on lossy or shallow-buffer paths | Near min RTT except periodic probes | Paces at measured bottleneck rate × min RTT; ignores isolated loss; may retransmit more |

**Observations:** [Per algorithm, from q3-algorithms.csv: median goodput, queueing delay,
retransmits/s, cwnd/BDP, destinations where it won goodput / RTT. Relate winners to
min RTT and BDP (q3-compare panel d). Point at cwnd sawtooth vs RTT inflation in the
time series.]

**Variability and limitations:** [CoV range from q3-variability.csv.] Public paths share
the bottleneck with unknown cross traffic, routes and server load change between runs,
and some servers may cap rates, so a difference smaller than the run-to-run spread is not
evidence that one algorithm is better. Interleaving and rotation reduce time bias but do
not remove it. One upload stream per test means no algorithm competes with another of
its own kind here, so fairness is not measured.

## Q3(b): DART, a delay-aware, rate-targeting controller

**Idea.** In the Q2 trace, retransmissions were absent while RTT moved before goodput
dropped (e.g. 0.81 → 1.94 ms at the largest goodput drop). Loss is a late and sparse
signal on these paths, so DART uses **queueing delay** as its main signal. It uses
**delivery rate** to size the window against the BDP, and **loss** only for
backoff, scaled by whether the queue was actually full. Every input is a field we
already decode from `TCP_INFO`: `rtt`, `rttvar`, `min_rtt`, `delivery_rate`,
`total_retrans`, `snd_cwnd`. [Confirm the motivation with Q3 retransmission rates.]

```text
constants: α = 2, β = 4 packets (target backlog in the bottleneck queue)
state:     cwnd, mode ∈ {STARTUP, CRUISE, COMPETE}
           min_rtt = windowed min RTT over 10 s
           btl_bw  = windowed max delivery_rate over 10 RTTs

once per RTT:
  bdp    = btl_bw × min_rtt / MSS                    # packets the pipe holds
  queued = cwnd × (1 − min_rtt / srtt)               # packets sitting in the queue
  noisy  = rttvar > 0.5 × (srtt − min_rtt)           # delay too jittery to trust

  STARTUP:
    cwnd = 2 × cwnd
    if btl_bw grew < 25% for 3 rounds or queued > β or loss:
      cwnd = bdp + α;  mode = CRUISE                 # pipe full: drop the startup queue

  CRUISE:
    if   queued < α and btl_bw still rising: cwnd += 2   # throughput says room left
    elif queued < α:                         cwnd += 1
    elif queued > β and not noisy:           cwnd -= 1
    cwnd = min(cwnd, 2 × bdp)                             # bound the standing queue
    if queued > β for 8 RTTs despite decreases:           # a loss-based flow fills the
      mode = COMPETE                                      #   buffer; backing off only starves us

  COMPETE:
    cwnd += 1                                        # Reno-style additive increase
    if queued < α for 4 RTTs: mode = CRUISE          # competitor gone

  if min_rtt not refreshed for 10 s:                 # re-measure the empty-queue RTT
    cwnd = 4 for max(200 ms, 1 RTT)

on a loss episode (once per recovery, from Δtotal_retrans > 0):
  if srtt − min_rtt > 2 × rttvar:  cwnd = max(0.7 × cwnd, 4)     # queue was full: congestion
  else:                            cwnd = max(0.9 × cwnd, bdp)   # queue empty: likely random loss
on retransmission timeout:
  cwnd = 1;  mode = STARTUP
```

**Design choices.**
- *Delay first.* Keeping only α–β packets queued holds RTT near `min_rtt`, which Reno and
  CUBIC cannot do because they grow until the buffer overflows.
- *Throughput sets speed and the ceiling.* Exponential startup exits when the delivery
  rate stops growing (the pipe is full), and the cap `cwnd ≤ 2·BDP` bounds the queue even
  if the delay signal is wrong.
- *Loss is classified by delay.* A loss with an empty queue is probably random
  (wireless, policing), so DART cuts only 10% and never below the BDP. That avoids the
  throughput collapse loss-based algorithms suffer on lossy long paths. A loss with a full
  queue is congestion, so it cuts by 30% like CUBIC.
- *Dead-band and noise guard.* No change inside α–β, and no decrease when `rttvar`
  dominates the queueing signal, to avoid reacting to ACK jitter.
- *COMPETE mode.* Pure delay-based control (Vegas) is starved by CUBIC; a persistent queue
  that does not shrink when DART backs off means someone else is filling it.

**Fairness.** At a shared bottleneck all flows see the same queueing delay *q*. A flow at
rate *x* keeps `queued = x · q` packets in the queue, and CRUISE holds `queued` in [α, β].
So every DART flow settles at a rate in [α/q, β/q], **independent of its RTT**, unlike
Reno, whose share scales as 1/RTT. The dead-band means rates are equal only to within a
factor β/α = 2. A single target (α = β, as in FAST TCP) gives exact proportional fairness
but oscillates more. In COMPETE mode DART is additive-increase/multiplicative-decrease,
which converges to equal shares among DART flows (Chiu–Jain). Against CUBIC or BBR it is
Reno-like and is expected to get *less* than a fair share.

**Convergence and stability.** In CRUISE, ±1 packet per RTT with a dead-band reaches a
fixed point at about BDP + α…β packets and stops moving, with no sawtooth. With N flows the
queue holds about N·α…N·β packets, so delay grows with the number of flows. The 10 s
min-RTT refresh drains the queue briefly; flows that see the new minimum reset their timers
together, which tends to synchronize later refreshes (as in BBR).

**Assumptions.** One FIFO bottleneck; RTT changes come mainly from forward-path queueing;
the kernel delivery-rate estimate is not application-limited (true for a bulk upload);
min RTT changes slowly compared with the 10 s window.

**Limitations.**
- *Base-RTT error:* a flow that starts while a queue already exists measures an inflated
  `min_rtt`, underestimates its backlog, and takes more than its share until the next refresh.
  A route change has the same effect.
- *Reverse-path congestion and ACK compression* inflate RTT without a forward queue, so
  DART backs off unnecessarily.
- *Coexistence:* COMPETE is Reno-like, so DART loses against CUBIC on high-BDP paths and
  against BBR's pacing.
- *Parameters* (α, β, thresholds, 10 s windows) are chosen by reasoning, not tuned.
- *Not implemented or tested.* This is pseudocode; nothing here measures DART. A real test
  would need a kernel module or BPF `struct_ops` controller and a controlled bottleneck
  where competing flows can be measured.

## Final PDF checklist

Embed the plots and tables, include the repository and relevant function/line links
(Q3 code: `experiment.py` `run_experiment`/`algorithm_order`, `tcp_stats.py`
`check_algorithms`, `comparison.py`), and update observations if measurements change.
AI assisted implementation, checking, cleanup, and drafting of the Q3 design write-up.
