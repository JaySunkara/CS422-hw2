| Destination | Algorithm | Min | Median | Mean | p95 | Overall |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| speedtest.hkg12.hk.leaseweb.net:5209 | cubic | 0.000 | 44.878 | 54.501 | 135.463 | 54.515 |
| speedtest.lax12.us.leaseweb.net:5207 | cubic | 86.892 | 302.384 | 288.533 | 381.639 | 287.961 |

All rates are Mbit/s (1 Mbit/s = 1,000,000 bit/s).
Min/median/mean/p95 use all valid sending intervals of successful runs,
including startup, zeros, and the final partial interval. Mean is the
unweighted arithmetic mean; p95 uses linear interpolation at 0.95*(N-1).
Overall = 8*sum(acknowledged byte deltas)/sum(actual interval seconds).
Failed/interrupted runs are logged but excluded from this table.
