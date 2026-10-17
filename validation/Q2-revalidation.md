# Question 2 revalidation - October 17, 2026

**Result: Q2(a-c)'s implementation passed the practical checks below. No code
changes or additional tests/features were needed.** Final submission measurements
still need the handout's Linux/WSL2 execution environment; these local retests
used Docker Desktop's Linux VM.

| Part | Result | Evidence |
| --- | --- | --- |
| Q2 baseline | Pass | Fresh data socket reported `cubic`, matching the selected OS default; logs, PDFs, and observations all identify the same algorithm and run |
| Q2(a) live sampling | Pass | Code and existing socket-selection test confirm reads from the upload data socket; timestamp, cwnd, RTT, loss proxy, and goodput are logged together |
| Q2(a) saved format and decoding | Pass | CSV/JSON include destination, port, algorithm, run ID, units, execution kernel, and decoding offsets; current offsets match the saved independent Linux C-header check |
| Q2(a) interval calculations | Pass | Every new goodput and retransmission delta/rate was recomputed independently using raw counters and actual elapsed times; cookie-byte exclusion and baseline/final handling matched |
| Q2(b) visualization | Pass | All four time series and three scatter relationships are generated automatically from one representative run, with correct units and same-interval pairing; both rendered PDF pages were inspected |
| Q2(c) observations | Pass | Metric meanings and expected influence are explained; reported statistics and event times match the trace; zero loss and possible causes are described without invented loss events or causal claims |
| Offline reproduction | Pass | Normal `plot` command succeeded with container networking disabled; hashes confirmed the manifest and raw run JSON were unchanged |

## Checks actually rerun

- Rebuilt the existing Ubuntu 24.04 image from the current project files.
- All **51 existing tests passed** in Linux as user `65534:65534`, with network
  access disabled. No new edge-case tests were added.
- Ran one new **10-second** public upload to
  `speedtest.lax12.us.leaseweb.net:5207`. The first candidate completed; no
  replacement was needed. The protocol ended normally with `IPERF_DONE`.
- Audited **51 snapshots**: one baseline plus **50 measured intervals**, over
  10.000575 seconds. Overall goodput was **260.608 Mbit/s**. The actual algorithm
  was **cubic**, and the execution kernel was **6.10.14-linuxkit**.
- Independently checked each CSV sample against JSON, all required fields/units,
  all interval formulas, observation minimum/median/maximum values, overall
  goodput, peak RTT/time, and the presence of all seven labeled PDF panels.
- Regenerated reports without network access, then rendered and visually checked
  both final PDF pages for readable labels, units, legends, and layout.

Raw results, regenerated plots/observations, and the machine-readable audit are
in `q2-retest/`; the audit is `q2-retest/revalidation.json`. Original example
measurements under `../output/pdf/q2/` were preserved.

The new trace recorded zero retransmissions. That is a valid value for the
required loss proxy; Q2 does not require artificially inducing loss. Its zero
loss plot and the absence of loss-response evidence are explicitly documented.

## Submission distinction

The implementation meets the Q2(a-c) requirements inspected in the handout.
Docker Desktop forwarding can affect the measured TCP path, so local validation
is not a replacement for final measurements on Linux or Windows WSL2. Include
those plots and their corresponding observations in the final report PDF. No
other Q2 implementation gap was identified.

The decoder and CUBIC explanation were also rechecked against the
[Linux TCP_INFO declaration](https://github.com/torvalds/linux/blob/v6.8/include/uapi/linux/tcp.h)
and [RFC 9438](https://www.rfc-editor.org/rfc/rfc9438.html).
