# What measuring audio levels costs namchaind

**Measured:** 2026-10-06, on **vip** (Raspberry Pi 5, 1 GB, Cortex-A76). Engine `f00714d`
(`f00714d` is where `--levels`/`--no-levels` landed; the daemon reported `f00714d` for every run).
**Instrument:** [`poll-levels.py`](poll-levels.py) — a TCP `engine.levels` client, the same shape as
the meter in ljoss. **Campaign:** [`run-campaign.sh`](run-campaign.sh). **Arithmetic:**
[`analyse.py`](analyse.py). **Raw results:** [`results.jsonl`](results.jsonl),
[`stability.jsonl`](stability.jsonl).

## Why this was measured

`engine.levels` folds a peak, a sum, a frame count and a clip count into a probe **per sample**, in
the loop the non-finite guard already walks. That is the price of a level meter, and it is paid on
the render core whether or not any client is watching. `f00714d` adds the switch to stop paying it:
`--no-levels` builds no probes at all, so the render path does no level work rather than a little
less work.

These numbers are what that switch buys, and what a client polling the levels costs on top.

## Method

Two series, because the switch has two costs and they are not visible in the same place.

| Series | Rig | What it isolates |
|---|---|---|
| **A** | `input → output` (2 nodes) | The cost of **answering**: the levels JSON is built and sent once per poll. There is almost nothing inside the rig to measure. |
| **B** | 32 × `nc.gain` (34 nodes) | The cost of **measuring**: every node's probe folds a sample. The rig's own cost is one multiply per node, so the probes dominate rather than the audio. |

Both rigs are generated ([`make-rig.py`](make-rig.py)) and passed as absolute paths with `--rig`, so
every condition ran the same document. Series B is a synthetic upper bound, not a realistic rig: a
rig with an A2 model in it would show a smaller *share*, because an inference swamps a probe. The
real saving for a real rig sits between the two series.

- **CPU** is the daemon process's own `utime + stime` from `/proc/<pid>/stat`, every thread included,
  read immediately before and after the window. It is the kernel's accounting, not a sampled estimate.
  `CLK_TCK` is 100, so one tick is 10 ms of CPU time; over a 120 s window one tick is 0.83 ms of CPU
  per second of wall clock, which is the resolution every figure below is quoted to.
- **Windows** are 120 s for the campaign, 60 s for the stability re-runs. Every condition used the
  same window and the same 8 s settle after the daemon reported `running`.
- Percentages are a share of **one** core. vip has four; the render thread is pinned to core 3.
- Each run was gated before it started: the daemon had to report `running`, `engine.levels` had to
  answer with the rig's expected node count when measuring, and had to be **refused** when not. A run
  that failed either gate wrote an error instead of a number — which is why the "off" rows are
  trustworthy rather than merely labelled.
- Level measuring was **on** unless the condition says `off`, so it stays the product default and the
  switch is what is under test.

## Results

### Series A — a minimal rig (2 nodes)

| # | Levels | Client polling | Window | CPU ticks | CPU (one core) | ms/s | vs baseline |
|---|---|---|---|---|---|---|---|
| 1 | **off** | — | 120 s | 249 | 2.08% | 20.8 | baseline |
| 2 | on | — | 120 s | 286 | 2.38% | 23.8 | +0.31 pp (+3.1 ms/s) |
| 3 | on | 20 Hz | 120 s | 300 | 2.50% | 25.0 | +0.42 pp (+4.2 ms/s) |
| 4 | on | 10 Hz | 120 s | 292 | 2.43% | 24.3 | +0.36 pp (+3.6 ms/s) |
| 5 | on | 5 Hz | 120 s | 290 | 2.42% | 24.2 | +0.34 pp (+3.4 ms/s) |
| 6 | on | 4 Hz | 120 s | 290 | 2.42% | 24.2 | +0.34 pp (+3.4 ms/s) |
| 7 | on | 3 Hz | 120 s | 289 | 2.41% | 24.1 | +0.33 pp (+3.3 ms/s) |
| 8 | on | 2 Hz | 120 s | 290 | 2.42% | 24.2 | +0.34 pp (+3.4 ms/s) |
| 9 | on | 1 Hz | 120 s | 287 | 2.39% | 23.9 | +0.32 pp (+3.2 ms/s) |

### Series B — a 32-gain rig (34 nodes)

| # | Levels | Client polling | Window | CPU ticks | CPU (one core) | ms/s | vs baseline |
|---|---|---|---|---|---|---|---|
| 10 | **off** | — | 120 s | 268 | 2.23% | 22.3 | baseline |
| 11 | on | — | 120 s | 541 | 4.51% | 45.1 | +2.28 pp (+22.8 ms/s) |
| 12 | on | 20 Hz | 120 s | 578 | 4.82% | 48.2 | +2.58 pp (+25.8 ms/s) |
| 13 | on | 10 Hz | 120 s | 560 | 4.67% | 46.7 | +2.43 pp (+24.3 ms/s) |
| 14 | on | 5 Hz | 120 s | 554 | 4.62% | 46.2 | +2.38 pp (+23.8 ms/s) |
| 15 | on | 4 Hz | 120 s | 552 | 4.60% | 46.0 | +2.37 pp (+23.7 ms/s) |
| 16 | on | 3 Hz | 120 s | 549 | 4.58% | 45.8 | +2.34 pp (+23.4 ms/s) |
| 17 | on | 2 Hz | 120 s | 547 | 4.56% | 45.6 | +2.33 pp (+23.3 ms/s) |
| 18 | on | 1 Hz | 120 s | 546 | 4.55% | 45.5 | +2.32 pp (+23.2 ms/s) |

## What the numbers say

**1. The switch is worth having, and its worth is set by the rig.** With the switch off, a 34-node
rig costs 2.23% of a core; with it on, 4.51% — **measuring more than doubles the engine's cost on a
light rig**, because a gain node is nearly free and the probe is not. On the 2-node rig the same
switch moves 2.08% → 2.38%.

Per node, from the two off/on pairs: Series B's 32 extra nodes cost 22.8 ms/s, so **0.71 ms/s of one
core per measured node** — and Series A's 2 nodes cost 3.1 ms/s, which is 1.5 ms/s each. Those two
figures are the same quantity measured at different chain lengths and they differ by more than the
tick resolution, so the honest reading is **0.7–1.5 ms/s per node, call it ~1 ms/s**, with the
smaller-chain figure noisier because it is a difference of only 37 ticks. In the currency a pedal is
judged in, that is **0.07–0.15% of one core per node**, and roughly **0.6–1.2% of one core for a
nine-block rig**.

**2. Polling a client is cheap, and linear in the rate.** The marginal cost of one poll is the
difference between adjacent rates, where the tick resolution is not the limit:

| Difference | Polls added | Extra ticks | Extra CPU | Per poll |
|---|---|---|---|---|
| 20 Hz → 10 Hz, Series B | 1,200 | 18 | 0.15% of a core | **0.125 ms** |
| 20 Hz → 10 Hz, Series A | 1,200 | 8 | 0.07% of a core | **0.056 ms** |
| 10 Hz → 5 Hz, Series B | 600 | 6 | 0.05% | 0.125 ms |
| 10 Hz → 5 Hz, Series A | 600 | 2 | 0.02% | 0.028 ms |

The counts double cleanly and the cost follows: **the reply, not the rate, is what a poll costs**, so
a 20 Hz meter costs twice a 10 Hz one and eleven times a 1 Hz one, and all of them together are a
rounding error beside the per-sample cost of measuring.

**3. The reply's size is most of a poll's cost.** A poll of the 2-node rig costs ~0.06 ms and of the
34-node rig ~0.125 ms — the difference is the JSON for 32 more nodes (mean reply 3.6 kB against
0.6 kB). At 20 Hz that is ~2.5 ms/s on the small rig and ~5 ms/s on the big one.

**4. Nothing here is close to a limit.** The heaviest condition in the whole campaign — measuring a
34-node rig while a client polls at 20 Hz — costs **4.82% of one core**, on a board with four. The
engine's own render work, not the meters, is what a rig's cost is made of.

**5. One caveat, and it is about clocks not code.** The two empty windows (conditions 5 and 6, and
one in condition 12) are the documented read-and-reset behaviour: a poll that lands between two
rendered periods gets `frames: 0` everywhere. ljoss holds its display through those rather than
drawing the floor, which is why they are reported here rather than treated as failures.

## Stability

The two baselines and the "measuring, nobody polling" condition were re-run at the end of the
campaign, after ~40 minutes of load, with a **60 s** window. The 60 s figures reproduce the 120 s
ones almost exactly, which is the check that the campaign measured a steady state rather than a
warming board:

| Condition | 120 s window | 60 s re-run | Agreement |
|---|---|---|---|
| Series A, off | 2.08% | 2.07% (124 ticks / 60 s) | 0.5% |
| Series B, off | 2.23% | 2.23% (134 ticks / 60 s) | ~0% |
| Series B, on | 4.51% | 4.52% (271 ticks / 60 s) | 0.2% |

## Conditions worth knowing about

- **Do not run this campaign against a daemon nobody has checked.** The first attempt measured
  whatever `pedald seed` had resumed (`/var/lib/pedal/library/rigs/last.json`) instead of the rig the
  campaign asked for, and the CPU numbers looked entirely plausible. Every condition now gates on the
  node count the daemon reports before its window opens.
- The campaign's `--rig` is always an **absolute path**. A bare name resolves under the pedal's own
  rig library, which is the owner's, and a measurement has no business writing there.
- The campaign changes the unit through a drop-in
  (`/etc/systemd/system/namchaind.service.d/50-levels-campaign.conf`) and **removes it on exit**,
  including on failure, so `namchaind` is always left starting the way `devices/vip` says it starts.
  The rig documents it installs under `/etc/namchain/rigs/` stay behind by default
  (`KEEP_INSTRUMENT=0` removes them) so the campaign can be re-run without reinstalling.
- Everything above ran under the Core host's lock (`scripts/host-lock`), and the host was left with
  the lock free, `namchaind` active, and no campaign drop-in.

## Reproducing it

```sh
scripts/host-lock --host vip -- env SECONDS_PER_RUN=120 SETTLE_SECONDS=8 \
  bench-results/2026-10-06-levels-switch/run-campaign.sh
python3 bench-results/2026-10-06-levels-switch/analyse.py \
  bench-results/2026-10-06-levels-switch/results.jsonl
```

`--only 1,2,3` runs a subset, and `SECONDS_PER_RUN` shortens the window for a smoke test.
