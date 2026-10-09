# T5: one housekeeping core, and what a warm document costs the audible one (2026-10-09)

T5 asks whether one housekeeping core (0) can carry `pedald`, the engine's control side, WiFi, the SD
card and a compile without moving the cores that render. It also, as it turns out, measures something
the cost table does not model: **what a warm document rendering on another core costs the rig the
player is hearing.**

The harness is [`scripts/measure-housekeeping`](../../scripts/measure-housekeeping). Two arms: quiet,
then loaded on core 0 (a CPU spinner, a 200 MB SD write, a 200 MB WiFi upload — repeated until the arm
ends — and a compile burst: `namchainctl cost` over the active rig in a loop, which the engine runs on
the control thread pinned to core 0). The active rig is built for the test: the document the pedal
plays, its chains repeated with fresh ids until `rig.cost` puts it just under the headroom (7 chains,
**0.735**, verdict `fits`, one model trimmed), and a second rig of the same document as the neighbour.
The run was done twice with the *same* rigs and the same load, once with the neighbour held warm on
core 1 and once with `pedald` stopped so nothing is warm. 120 s an arm, `vip`, engine `fee0440`.

## The four arms

| | worst block | of the deadline | blocks over it (Δ in the arm) | blocks over 90% (Δ) |
|---|---|---|---|---|
| **nothing warm**, after the load | 1342.3 µs | 100.7% | 1 | 42 |
| nothing warm, arm A (quiet) | 1342.3 µs | 100.7% | 1 (**+0**) | 44 (+2) |
| nothing warm, arm B (loaded) | 1435.6 µs | 107.7% | 2 (**+1**) | 82 (+33) |
| **warm on core 1**, after the load | 1667.2 µs | 125.0% | 27 | 36 |
| warm on core 1, arm A (quiet) | 1667.2 µs | 125.0% | 34 (**+7**) | 56 (+20) |
| warm on core 1, arm B (loaded) | 2024.1 µs | 151.8% | 100 (**+61**) | 1018 (+947) |

Both runs, both arms: `xruns` 0, guard trips 0.

| | quiet, cpu3 | loaded, cpu0 / cpu3 | IRQ wait to run | temperature |
|---|---|---|---|---|
| nothing warm | 41.8% | 99.3% / 54.3% | 6.5 → 435.6 ns/wake | 68.3 → 72.2 °C |
| warm on core 1 | 51.1% (cpu1 28.7%) | 99.2% / 67.1% (cpu1 40.0%) | 12.0 → 696.4 ns/wake | 67.2 → 77.1 °C |

The warm document itself stayed current throughout: `behind_blocks` 0, worst 2, **0 dropped blocks**,
in both arms of the warm run. Nothing was starved on core 1 — D5's arrangement held for the warm work.

## What it says

1. **The housekeeping load moves the render tail, and on a rig this close to the table's limit it
   breaks the deadline.** With nothing warm: worst block 100.7% → 107.7%, blocks over 90% 51 → 82, and
   **one block over the deadline in 120 s**. On the lighter rig the first (accidental) run used — 3
   chains, cost 0.41 — the same load produced **0 overruns** and a worst block of 63%. So the load's
   cost is real but bounded, and whether it *fails* depends on how close the rig is to the top of the
   table. T5's falsifier fires, at the top end.
2. **The warm document is the bigger cost, and the table does not model it at all.** The same rig,
   same load, with a 0.41 document rendering beside it on another core: **7 overruns/120 s quiet
   against 0**, and **61 against 1 loaded**, with the worst block 125% against 100.7% and 151.8%
   against 107.7%. The cost table charges units as if a core were alone with them; it is not, once a
   warm rig is rendering, and the interference (shared L3/DRAM) is what T5's own *Expected* paragraph
   predicted: "this is where the headroom may prove too thin — the two-amp work measured another
   core's traffic doubling a rig's median".
3. **So `fits` is not sufficient when warming is on.** A document the engine admits at 0.735 — under
   D3's 0.8 headroom, with one model already trimmed — is effectively clean alone and misses the
   deadline beside a warm document. Nothing in D3, D4 or the table reflects that.
4. **The interrupt degrades with core 0 loaded** — 12.0 → 696.4 ns of wait-to-run per wake with the
   warm set (6.5 → 435.6 without). It is delivered to core 1, which is also where the warm thread
   runs, so this is the shared-core cost D5 accepted; the warm work was not starved (0 drops), and
   the audible rig's overruns are not scheduling (no xruns, no queue loss) but time.

## The sweep: where the knee is

The same harness, the same warm neighbour (0.41 on core 1), the active rig rebuilt at several costs —
and, at two of them, the same run again with nothing warm. 120 s an arm, engine `fee0440`.

| active rig | warm? | quiet arm, blocks over the deadline | loaded arm, blocks over the deadline | worst block (loaded) |
|---|---|---|---|---|
| 0.410 (3 chains) | warm | +0 | **+1** | 117.5% |
| 0.410 (3 chains) | none | +0 | **+0** | 63.0% |
| 0.559 (4 chains) | warm | +0 | **+1** | 139.0% |
| 0.685 (5 chains) | warm | **+4** | **+72** | 122.6% |
| 0.685 (5 chains) | none | **+0** | **+0** | 99.7% |
| 0.735 (7 chains) | warm | **+7** | **+61** | 151.8% |
| 0.735 (7 chains) | none | **+0** | **+1** | 107.7% |

`xruns` 0 and no guard trips anywhere; the warm document stayed within 2 blocks and dropped nothing.

**The knee is at about 0.6.** With nothing warm, a rig the table admits at 0.735 holds the deadline
through a saturated housekeeping core (0-1 blocks over in 120 s, worst 107.7%) — the admission model
is doing its job. With a warm document rendering beside it, the *same rig* is four to seventy-two
blocks over in the same two minutes, and even a 0.41 rig gives up a block now and then. So while a
neighbour is warm the figure that holds is nearer **0.6 than 0.8**, and the coexistence cost grows
with the rig's cost rather than being a constant.

Two smaller readings worth keeping: the *first* seconds after a heavy rig is made audible are the
worst of all (the load-time transient — 6 blocks over at 0.685, 27 at 0.735 — while the new document
is compiled, paged in and its models touched), and the quiet arm is not clean either above 0.6, so
this is not only about the housekeeping load.

## What follows (a decision, and a measurement to make it)

The knee is measured; the choice of what to do with it is the owner's, because each option changes
what the pedal promises:

* **Charge the coexistence.** Measure, per unit or per rig class, the cost of rendering *beside* a
  warm document, and add it to the admission sum when the warm set is not empty. Most faithful, most
  measurement — and the sweep above says the term is not a constant (0.41 barely notices, 0.685 does
  not hold), so it needs the curve, not a fudge factor.
* **Lower the headroom while warming is on**: the sweep puts the figure near **0.6** (0.559 held, 0.685
  did not). Cheap, conservative, and it costs capacity only while a neighbour is warm.
* **Let the service decide** (D9's boundary), which is the cheapest thing that ships today: `pedald`
  already costs every rig in the bank and chooses the warm rig, so it can hold a neighbour warm only
  while the audible rig is under the figure, and cool it above that. The engine keeps enforcing what
  it was given, and nothing in the cost model has to change.
* **Do nothing about it and record the promise**: `fits` means "fits alone"; a rig above 0.6 may miss
  blocks while a neighbour is warm. That is a decision too, and D3 has to say it.

To choose between the first two properly the next measurement is the same sweep with more points and
longer arms (T10's hour, not two minutes), and on a rig whose chains are *different* rather than
repeats.

## Caveats

* One rig shape (chains repeated), one warm document (0.41), one board, one hour of the day. The
  numbers above are one point, not a curve.
* The arm's load is deliberately heavy (core 0 at 99%): a synth, an SD write and a WiFi upload
  sustained for the whole arm. A quieter core 0 is the load T10 measured, and it passed there.
* `runs` are 120 s an arm here; T10's hour is the acceptance test, and it ran a 0.41 rig.
* The warm document is the *same* document as the audible one (a copy), so the interference it causes
  is from a second render thread's traffic, not from a second *different* set of weights.

## Reproducing it

```sh
scripts/host-lock -- scripts/measure-housekeeping --seconds 120 --mb 200 \
    --out bench-results/2026-10-09-housekeeping-vip/warm
scripts/host-lock -- scripts/measure-housekeeping --seconds 120 --mb 200 --no-warm \
    --out bench-results/2026-10-09-housekeeping-vip/nowarm
```

The harness restarts `namchaind` for fresh counters, builds its rigs from the one the pedal plays,
backs up and restores `last.json`/`last.prev.json` (pedald rewrites them whenever the playing rig
changes — a measurement that skips this leaves the pedal playing the test rig), copies both rigs into
`--out/rigs/`, and stops `pedald` for `--no-warm`.
