| Destination | Algorithm | Min | Median | Mean | p95 | Overall |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| 154.81.51.4:5201 | cubic | 0.000 | 57.338 | 71.750 | 144.397 | 71.183 |
| 185.180.12.40:5201 | cubic | 15.464 | 247.128 | 191.278 | 269.040 | 190.211 |
| 213.158.175.240:5201 | cubic | 2.642 | 167.536 | 128.924 | 201.933 | 127.884 |
| 49.205.75.2:5018 | cubic | 0.000 | 0.000 | 5.696 | 37.581 | 5.764 |
| iperf.pendc.com:5202 | cubic | 7.832 | 163.861 | 119.472 | 189.781 | 119.223 |
| iperf3.moji.fr:5204 | cubic | 13.144 | 186.211 | 170.351 | 252.952 | 170.691 |
| speedtest.lax12.us.leaseweb.net:5207 | cubic | 24.369 | 223.617 | 219.786 | 328.848 | 219.604 |
| speedtest.wtnet.de:5209 | cubic | 11.494 | 203.516 | 171.480 | 248.878 | 170.548 |
| speedtest.xmission.com:5205 | cubic | 32.050 | 273.092 | 255.772 | 337.625 | 255.587 |
| speedtest1.cwpanama.net:5506 | cubic | 2.654 | 181.707 | 177.274 | 313.234 | 174.750 |

All rates are Mbit/s (1 Mbit/s = 1,000,000 bit/s).
Min/median/mean/p95 use all valid sending intervals of successful runs,
including startup, zeros, and the final partial interval. Mean is the
unweighted arithmetic mean; p95 uses linear interpolation at 0.95*(N-1).
Overall = 8*sum(acknowledged byte deltas)/sum(actual interval seconds).
Failed/interrupted runs are logged but excluded from this table.
