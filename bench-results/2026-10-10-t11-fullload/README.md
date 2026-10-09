# T11: the full-load hour — its quiet half, and a mistake worth recording

**Arm A (quiet, 30 minutes) completed; arm B never ran, because the harness was edited while it was
running.** Bash reads a script as it executes it, so the rewrite landed mid-flight and the shell
stopped at a line that had moved (line 382, the app-traffic report) the moment arm A ended. The
cleanup did not run either, so the stand-in renderer, three test rigs and the resume files were put
back by hand afterwards. The lesson is cheap and now written down: **edit a running harness and bash
will read your edit**. Arm B is owed, and a re-run must be started from a file nobody touches.

## Arm A: thirty quiet minutes at full rig load

The rig is 0.559 (five chains, admitted with the coexistence charge in force), a warm document on
core 1, a stand-in second renderer on core 2, and the app's traffic — 3,472 library requests over
WiFi during the half:

| | before arm A | after arm A (30 min) |
|---|---|---|
| blocks over the deadline | 9 | **9** (all from the setup transient: **none added in half an hour**) |
| worst block | 2871.7 µs = 215.4% | unchanged (a load-time spike, not a steady one) |
| xruns / guard trips | 0 / 0 | **0 / 0** |
| blocks rendered | 26,481 | 1,376,690 |
| temperature | 62.2 °C | 66.7 °C |
| clock | — | **2400 MHz**, low-voltage alarm **0** |
| per-core busy | — | cpu0 6.8%, cpu1 0.6%, cpu2 25.5%, cpu3 37.4% |
| IRQ thread | — | 8.4 ns of wait to run per wake over 2.7 M wakes |

That is T11's question answered for the *quiet* half at this rig: half an hour of rendering beside a
warm document and a second renderer costs nothing — no block over the deadline, no xrun, the clock at
2400 MHz and the rail unflagged — and the only fault in the run is the spike when the heavy rig was
first published (215% for one block, during the load, not after it). The loaded half is the one that
says whether a busy housekeeping core changes that, and it is still owed.

## The original note

**This run is in progress.** `scripts/measure-housekeeping` was launched at 21:52:03Z under the
host lock and writes its report to `t5.txt` beside this file when it finishes (about 22:55Z): thirty
minutes quiet, then thirty minutes with the housekeeping core loaded, a second renderer on the free
warm core (2) throughout, the app's traffic on the WiFi leg, and both rigs copied into `rigs/`.

What it is asking is T11's question: over an hour at full load, does the render tail move, does the
clock stay at 2400 MHz, does the temperature walk, and does the low-voltage alarm ever assert — the
things a two-minute arm cannot answer and that the cost table's numbers assume.

**One thing this run does not have, by a harness bug that is already fixed:** the engine's own warm
document. The watch that waits for pedald to hold a neighbour warm gave up after 20 seconds, and a
fresh pedald can take longer than that to poll its status and ask for the warm, so the run started
without one — the arm counts it in the `WARNING: no warm document is rendering` line. The watch is 90
seconds now, so a re-run would include it. What the hour *does* include is the second renderer (the
bench's `rig` mode pinned to core 2), so the coexistence interference T5 measured is present; what is
missing is the engine's own warm thread on core 1.

To collect it: read `t5.txt`'s two arms (the before/after lines per arm), check the `clock` and
`low-voltage alarm` lines each arm now prints, then write the result into the document's T11 block and
decide whether the missing warm document is worth a second hour.

The harness fixes that came out of launching this are committed (`scripts/measure-housekeeping`: no
bulk writes, the app's traffic instead of a synthetic upload, `--extra renderer`, and the 90-second
warm watch).
