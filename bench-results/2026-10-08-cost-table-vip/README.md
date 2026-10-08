# vip's cost table: P1, P2 and what T1/T2/P9 measured

**Date:** 2026-10-08
**Question** (docs/managing-processing-power-and-optimising-for-fast-switching.md, D2/D3/D8/D9): what does
each unit cost on one core of `vip`, does the additive model predict a rig's cost, and does the meter
cost render time?
**In one line:** the measure mode reproduces E2 (9 Full and 30 Lite against its 8 and 30), the table's
14 rows are measured on vip with their provenance, **T2 did not falsify the additive model over 16
heterogeneous rigs** — every rig the table admitted stayed inside the deadline, with the prediction on
the safe side by about 1.7× — and the level probes do cost render time, roughly doubling a biquad's
p99 at 128 nodes when publishing per period.

Evidence: `vip-fragments.jsonl` (the 14 rows, each with its whole curve), `curves.txt` (the same
curves, readable), `t2-rigs.jsonl` (the 16 rigs), `p9-biquad-arms.jsonl` (the meter's three arms).
The table itself is `devices/vip/rootfs/etc/namchain/cost.json`.

## 1. The bar moved, and why (this is the finding that changes D2's step 4 and D7)

D2's step 4 says `n` is "the largest count with p99 < deadline **and zero overruns**", and D7 says the
same. Measured, the overrun count at the fit point is not monotone in `n`. One Lite model on vip's
core 2:

| n | p99 (% of the deadline) | blocks over the deadline |
|---|---|---|
| 19 | 53.3 | 0 |
| 20 | 55.7 | 0 |
| 21 | 59.6 | 0 |
| **22** | 64.5 | **2** |
| **23** | 67.5 | **0** |
| **24** | 72.7 | **3** |
| **25** | 76.4 | **0** |
| 32 | 106.4 | 1184 |

p99 climbs smoothly; the overrun count goes 2, 0, 3, 0 over the same four points. A bar that one late
block in 22,500 decides is a bar the *environment* decides, and the number it produced moved by three
when nothing about the unit changed. So the bisection fits on **p99 under the deadline** — the smooth,
monotone signal, and the bar E2's own 8 and 30 were measured with — and the overruns, the max and the
worst lag are recorded as part of the curve's shape. `namchain-warm-bench measure --bar strict` asks
for D7's reading instead, and prints both `n` when they differ.

D7's "every block within the deadline, zero overruns" is not dropped: it is what the **live soak**
(T10) confirms, and what the headroom in D3 is for. What changed is which bar an *offline bisection*
can use without measuring the box instead of the unit.

## 2. P1's verification: E2 reproduced, and the first-sight of the table

E2 (2026-10-06, `namchain/bench-results/e2-warm-density-vip.txt`) measured **8 Full and 30 Lite** per
core. The same units, measured with the new mode on the same core of the same device:

| unit | E2 | measured | p99 at measured n | p99 at n+1 |
|---|---|---|---|---|
| `NAM.WaveNet.full` | 8 | **9** | 97.4% | 110.9% |
| `NAM.WaveNet.lite` | 30 | **30** | 95.9% | 100.3% |

Both are within the ±1 P1 asks for. The Full unit differs by one because E2 cycled six library models
through its candidates where this run repeats one, and because E2's bar was p99 (its 89.1% at 8 is
this run's 82.2% at 8: the same point, measured with a live rig on the other core and a warmer thread
at priority 70 rather than a self-paced thread at 80).

## 3. The table

Fourteen rows, all measured on vip, all with the `n` they came from:

| row | cost | n | p99 at n | note |
|---|---|---|---|---|
| `NAM.WaveNet.full` | 0.111 | 9 | 97.4% | the family's dearest case: one model repeating |
| `NAM.WaveNet.lite` | 0.0333 | 30 | 95.9% | |
| `IR.8192` | 0.0222 | 45 | 98.7% | |
| `IR.4096` | 0.0222 | 45 | 97.8% | the partitioned FFT's cost is nearly flat here |
| `IR.2048` | 0.010 | 100 | 99.8% | |
| `IR.1024` | 0.00781 | 128 | 95.6% | `at_most`: the bench's `--max 128` was reached |
| `IR.512` | 0.00781 | 128 | 47.9% | `at_most` |
| `node.nc.input` | 0.00781 | 128 | 1.2% | `at_most`, and nowhere near a core |
| `node.nc.output` | 0.00781 | 128 | 1.1% | `at_most` |
| `node.nc.gain` | 0.00781 | 128 | 2.0% | `at_most` |
| `node.nc.mix` | 0.00781 | 128 | 2.5% | `at_most` |
| `node.nc.split` | 0.00781 | 128 | 3.5% | `at_most` |
| `node.nc.delay` | 0.00781 | 128 | 4.1% | `at_most`, at 4800 samples |
| `node.nc.eq.biquad` | 0.00781 | 128 | 10.3% | `at_most`, measured with the shipped level probes |

The node rows are all upper bounds: no node type is dear enough to reach a whole core at 128 copies,
so their cost is what the bench's ceiling allows and the table says so (`at_most` with a `why`). What
distinguishes them is the p99 at that n — 1.2% for an input node against 10.3% for a biquad with its
level probe — which is the shape a finer measurement would resolve. A rig is charged `unknown.node`
(0.05) for a type with no row, which is 6× the dearest bound here: D8's direction, and the reason a
device's node rows are worth measuring even when they look free.

The IR rows say something the document did not assume: **a cab is not half a rig.** E1's "roughly half
a rig's render cost" was a cab against a model *on piv's armv7 NEON build*; on vip an 8192-tap cab is
0.0222 against a Full model's 0.111, a fifth.

## 4. T2: does the cost model predict?

Sixteen rigs, written as documents (so the engine's own compiler, nodes and IR truncation are what
runs), costed from the table by the engine's own model and then measured on vip's core 2 for 30 s
each. The falsifier is "any rig predicted ≤ 0.8 that misses the deadline":

| rig | predicted | measured p99 | measured max |
|---|---|---|---|
| one Full model | 0.127 | 6.4% | 6.9% |
| one Full + an 8192-tap cab | 0.149 | 8.2% | 8.6% |
| two amps in series (T3's ambient wash) | 0.238 | 13.3% | 15.3% |
| two amps + cab | 0.260 | 14.5% | 16.8% |
| pedal + amp + cab | 0.260 | 14.5% | 16.7% |
| amp + 3 effects + cab | 0.172 | 8.4% | 9.2% |
| amp + 5 effects | 0.166 | 6.8% | 8.8% |
| effects only, 8 nodes (T3) | 0.078 | 0.7% | 1.8% |
| **8 Lite models in series** | 0.748 | 64.1% | 89.8% |
| **16 Lite models in series** (T3) | 0.782 | 62.3% | 85.6% |
| three chains at once | 0.410 | 21.8% | 27.1% |
| pedal + amp + cab + 2 effects | 0.275 | 14.7% | 17.9% |
| amp + a 512-tap cab | 0.134 | 6.8% | 8.0% |
| amp + a 2048-tap cab | 0.137 | 7.4% | 7.9% |
| amp + a 4096-tap cab | 0.149 | 8.2% | 8.6% |
| two amps in parallel, mixed (split/mix) | 0.275 | 14.7% | 16.8% |

**Nothing was falsified.** Every prediction is above its measurement — by 1.7× on the light rigs, by
1.2× on the sixteen-model one — so the additive model is conservative wherever it was tested, which is
D2's assumption holding in the direction admission needs. The over-prediction is not noise: a unit's
`1/n` is measured at the *fit point*, where every copy is dearer than it would be alone (E2's own
note: the first Full is 6.6% of a quantum, the eighth 11.1%). Summing those dearest-case rows
therefore charges a small rig as if every unit were crowded. That is the safe direction (a rig that
plays may be refused, never the reverse), and it is the direction D3's headroom is spent in.

What this does **not** show: a rig that reaches the fit point of *mixed* units. The sixteen-model rig
is the closest — 62.3% measured against 78.2% predicted, both inside — and it is all one model.

## 5. P9: does the meter cost render time?

The same biquad unit, measured in three configurations (128 copies, 30 s each):

| configuration | p99 at n = 128 | against levels off |
|---|---|---|
| `--no-levels` | 4.5% | — |
| `--levels-publish-period` (what vip ships) | 10.3% | **+5.8 points, 2.3×** |
| `--levels` (one sample per frame, published on read) | 20.7% | **+16.2 points, 4.6×** |

The meter is not free, and publishing once per period recovered just under half of it — the same
"55% recovered" the 2026-10-06 levels switch measured. **Decision: the probes appear in the table as
part of the node rows** — every node row above is measured with the device's own shipped
configuration (`levels_publish_period: true`), so a rig that must fit is charged for the meter it
actually pays for. Excluding the probes from rigs that must fit is ruled out because the pedal ships
with the meter on, and the cost of that decision is in these three numbers: a rig of 128 biquads pays
10.3% of a core for its meters rather than 4.5%.

## 6. What the table does not cover

- **One row per architecture family.** Every model in vip's library is a `SlimmableContainer` of
  WaveNets, so the family is one row; a different architecture costs `unknown.NAM` (0.25) until it is
  measured (D8).
- **`render_threads > 1` is not part of this.** D1 admits a rig against one core's headroom, and vip
  runs one render thread.
- **Warm work is not measured here.** Every number in this note is a unit's own cost on a quiet core.
  What a warm set costs beside a live rig is E2's contention arm and `docs/multi-core.md`'s subject.
- **The live soak (T10) has not been run.** D7's bar is confirmed live, not offline: nothing here says
  a rig admitted at 0.8 has zero xruns for an hour on the pedal.

## Reproducing it

```sh
pedal.project/scripts/measure-core --host vip --seconds 30            # the 15 units, ~90 min
pedal.project/devices/common/cost-merge --device vip \
    --fragments build/vip/measure/run1/fragments.jsonl \
    --engine-commit "$(git -C namchain rev-parse --short HEAD)" --kernel "$(ssh vip uname -r)"
pedal.project/scripts/measure-rigs --host vip --seconds 30            # T2/T3, ~15 min
```

Both scripts build `namchain-warm-bench` in the image's container, take the host lock, stop
`namchaind` and put it back; both write their raw output under `build/<host>/`. The measurements were
taken on namchain `becd0f2` (P1's measure mode) against vip's kernel
`7.0.0-1017-raspi-realtime-numaemu1-trimmed` at q64, `namchaind` stopped, under
`systemd-run --scope --slice=pedal-bench.slice` so the scope could use the isolated cores 2-3.
