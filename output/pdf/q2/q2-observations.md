# Question 2(c): TCP metrics and observations

Destination: `speedtest.lax12.us.leaseweb.net:5207`. Actual algorithm: **cubic**.
Run ID: `bb4f212f-f6f9-4aaf-ab06-371c6ff9bffe`. Kernel: `6.10.14-linuxkit`.
Selected trace: 99 measured intervals over 20.003 seconds.
Plots: [time series](q2-timeseries.pdf) and [scatter plots](q2-scatter.pdf).

## Metric meanings and expected influence in congestion avoidance

- **snd_cwnd** is the sender's congestion allowance in segments, not actual flight size. A larger window can permit more useful data per RTT when the flow is window limited. The rough rate model is `8 * cwnd_segments * snd_mss_bytes / RTT_seconds`; receiver limits, pacing, application supply, and bottleneck capacity can make achieved goodput lower.
- **RTT** is the kernel's smoothed round-trip estimate, converted from microseconds to milliseconds. At a fixed window, a longer RTT reduces how quickly ACKs permit new data. Rising RTT alongside flat goodput can suggest queue buildup, but RTT alone cannot distinguish queues, path changes, receiver behavior, or virtualization. RTT variation is a delay variation estimate, not squared variance.
- **Loss proxy** is the increase in cumulative retransmitted segments over the interval. Loss recovery can delay useful delivery and cause a congestion-window reduction. Retransmissions may be spurious or repeated, so this count is not a loss probability. Detection and its goodput effect may appear in different intervals; zero retransmissions do not prove a loss-free path.
- **Goodput** is newly acknowledged payload bytes times eight divided by actual interval seconds. It measures useful delivery visible to this sender, rather than local send acceptance or the kernel's latest delivery-rate estimate. A retransmitted byte contributes useful delivery once.

For CUBIC, congestion-avoidance growth depends on time since the last congestion event and the previous window maximum, with a Reno-friendly region. Its usual multiplicative decrease factor is about 0.7 after congestion; timeout recovery differs. These are expectations from [RFC 9438](https://www.rfc-editor.org/rfc/rfc9438.html), not proof that a sampled plateau or decrease is a particular CUBIC phase.

## Measured trace

| Quantity | Minimum | Median | Maximum |
| --- | ---: | ---: | ---: |
| snd_cwnd (segments) | 40.000 | 40.000 | 40.000 |
| RTT (ms) | 0.193 | 0.780 | 16.068 |
| Retransmitted segments / interval | 0.000 | 0.000 | 0.000 |
| Goodput (Mbit/s) | 58.319 | 225.041 | 338.180 |

Overall goodput was **219.140 Mbit/s**, using total acknowledged-byte deltas divided by total measured time (rather than an unweighted mean of rates).
The sampled cwnd changed from 40 to 40 segments. A wider allowance by itself does not establish that cwnd limited the transfer.

## Notable behavior in this trace

- The highest sampled RTT was **16.068 ms** at 0.203 s, with goodput 87.911 Mbit/s and cwnd 40 segments. The lowest sampled RTT was 0.193 ms. These endpoints describe variability; they do not establish its cause.
- **cwnd stayed at 40 segments** while goodput ranged from 58.319 to 338.180 Mbit/s. Window changes therefore do not explain this trace's rate variation, and the constant cwnd cannot establish a cwnd/goodput correlation. It does not show CUBIC window-growth cycles.
- **No retransmissions were recorded in the measured intervals.** The loss scatter therefore has a constant zero signal: a loss/goodput correlation is undefined, and this run cannot demonstrate how the algorithm responds to loss.
- The largest adjacent goodput decrease was from 332.692 to 121.411 Mbit/s at 16.817 s. Endpoint cwnd changed from 40 to 40 segments, RTT from 0.810 to 1.944 ms, and that interval recorded 0 retransmitted segments. ACK timing, buffering, pacing, or application/receiver limits are possible influences; these samples cannot isolate one explanation.
- The kernel reported an MSS range of 65483 to 65483 bytes. Use this reported MSS when converting cwnd to a byte allowance; these samples do not measure physical wire-packet sizes.
- This trace used Docker Desktop's Linux VM. Its forwarding and host networking can affect local ACK timing, RTT, and MSS, so these values should not be treated as a verified direct end-to-end view of the remote Internet path. See [Docker Desktop networking](https://docs.docker.com/desktop/features/networking/).

## Interpretation limits

Every plot and number above uses the same successful run and actual algorithm. Startup, zero rates, and the final partial interval are retained; only the initial baseline is omitted because its interval goodput/loss is undefined. Snapshot cwnd/RTT are paired with the preceding interval's goodput, so feedback can have a lag. Scatter associations do not establish causation. A constant metric supplies no correlation evidence.

The saved fields do not identify slow start versus congestion avoidance, so no phase is inferred from the shape alone. A single run cannot establish repeatability, fairness, or algorithm superiority. Public paths and competing traffic change. No post-send drain is measured, so ACKs arriving after the final snapshot are excluded.

TCP terminology: [RFC 5681](https://www.rfc-editor.org/rfc/rfc5681.html). Linux field definitions: [TCP_INFO UAPI](https://github.com/torvalds/linux/blob/v6.8/include/uapi/linux/tcp.h).

AI assistance was used to implement the plotting and observation generator. Measured values come from the saved trace; possible explanations are hypotheses.
