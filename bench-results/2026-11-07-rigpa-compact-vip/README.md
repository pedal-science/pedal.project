# C3: rigpa's compact layout on the box's 4.3″ panel, beside the render core — PASS

**rigpa on the 800×480 DSI panel costs the render core nothing the gate can see.** Five ten-minute
arms on vip (2026-11-07 23:50 to 2026-11-08 00:42 UTC), the same heavy rig in all of them (0.569 of
the render core, two chains), and in every arm: **0 xruns, 0 blocks over the deadline, 0 over 90%,
0 guard trips**. rigpa ran as its real unit, on eglfs on `drm-rp1-dsi` (the panel's DSI-1, 800×480 at
60 Hz, nothing forced), in the compact layout (`docs/pedal-owns-state.md`, C3).

| arm | gate | xruns / over deadline / over 90% / guard | load p50 / p99 / p99.9 / worst | blocks >= 40% | core 0 / 1 / 2 / 3 busy | rigpa CPU | rigpa PSS | MemAvailable | temp |
|---|---|---|---|---|---|---|---|---|---|
| off | PASS | 0 / 0 / 0 / 0 | 18% / 22% / 38% / 56% | 343 | 6.7% / 9.8% / 0.0% / 20.1% | — | — | 763 MB | 68.1..71.4 °C |
| idle | PASS | 0 / 0 / 0 / 0 | 18% / 25% / 39% / 56% | 431 | 8.4% / 9.9% / 0.0% / 20.2% | 0.5% of a core | 137 MB | 717 MB | 68.1..70.8 °C |
| meters | PASS | 0 / 0 / 0 / 0 | 18% / 30% / 49% / 65% | 795 | 10.5% / 10.0% / 0.0% / 21.0% | 2.5% of a core | 137 MB | 716 MB | 68.1..70.3 °C |
| animate | PASS | 0 / 0 / 0 / 0 | 20% / 31% / 42% / 61% | 585 | 22.2% / 10.5% / 0.0% / 22.7% | 12.9% of a core | 139 MB | 712 MB | 68.1..71.9 °C |
| off2 | PASS | 0 / 0 / 0 / 0 | 18% / 22% / 38% / 56% | 300 | 5.2% / 9.8% / 0.0% / 20.0% | — | — | 762 MB | 68.6..71.4 °C |

- **off / off2** agree (p99 22% both): nothing drifted over the hour.
- **idle** (the play view, static): 0.5% of core 0 and three points of render-core p99, against
  the bar's 0.4% and two (bench-results/2026-10-10-rigpa-soak-vip).
- **meters** (Settings, the one compact view that draws the meters, about ten redraws a second):
  2.5% of core 0, eight points of p99, and the worst block of the run at 65%, still well inside the
  90% the gate allows. The tail spreads with small frequent redraws, as on the bar.
- **animate** (`--demo-animate`, a tile swept through the chain editor every frame): 12.9% of core 0,
  against the bar's 18.6% for more than twice the pixels.
- rigpa's memory is 137–139 MB PSS, a little under the bar's 141–143 MB, inside `MemoryMax=256M`.
- vip ran warm throughout (68–72 °C, against 56–64 °C in October): the box's case, not rigpa; off
  and animate span the same range.

## How it ran

`run-c3` is the October harness (`run-v2`) with three changes: the panel is real, so no connector is
forced and the run stops if DSI-1 isn't connected; rigpa runs `"layout": "compact"`; and the meters
arm starts with `--view=settings`. Everything else is as before: the heavy rig built from the playing
rig's chains just under a cost of 0.70 (`run/c3-heavy.json`), `scripts/soak/soak-monitor.sh` every
10 s and `soak-summary.py` on each arm, `/proc/stat`, MemAvailable and rigpa's `smaps_rollup` before
and after, and `analyse.py run` for the table. Put back by its own cleanup: pedald's resume files and
the rig they name, the test rig removed, rigpa's runtime drop-in removed and its real unit started.

The engine was namchain `70a6e3f` and rigpa `f5a6825`, both deployed that evening for C3
(`run/env.txt`; its `namchain`/`rigpa` lines are the card image's, the `bin` lines are what ran).

## What this doesn't cover

Whether the panel is the right way up in the case, whether touches land where they are made, and
whether the play view reads from standing: those are looked at on the pedal, not measured here.
