# T11: the full-load hour (launched 2026-10-09 21:52Z)

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
