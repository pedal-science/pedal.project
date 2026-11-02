# pro's cost table, with the planar AVX2 kernels

**Date:** 2026-11-02
**Question** ([docs/pro.md](../../docs/pro.md),
[docs/managing-processing-power-and-optimising-for-fast-switching.md](../../docs/managing-processing-power-and-optimising-for-fast-switching.md)):
`pro` had no cost table, so `namchaind` reported `cost_table_missing` and admission charged every
unit its unknown cost of 0.25 of a core — four units to a core, whatever they were. What does each
unit actually cost on one core of `pro`, now that the host is tuned and the engine has the A2 planar
AVX2 kernels?
**In one line:** 14 rows measured and installed, **one A2-Full costs 0.04 of a core (25 per core,
against vip's 9)** — but the win is NAM-specific: the IR ladder improves only 1.22×, so most of the
2.77× is the planar kernels and the wider ISA rather than the box. The level meter does cost render
time on pro too (+53% on a biquad at 128 nodes, against roughly double on vip), and eight of the 14
rows are **floor values**: the bisection ran out of ladder at `--max 128` without a miss, so those
units cost less than the table says.

Evidence: `pro-fragments.jsonl` (the 15 fragments, each with its whole curve), `curves.txt` (the
same curves, readable), `points/` (the bench's own output per unit), `units` (the unit set),
`session.log`. The table itself is
[devices/pro/rootfs/etc/namchain/cost.json](../../devices/pro/rootfs/etc/namchain/cost.json).

## Setup

- **Host:** `pro`, i5-9500T (6 cores, no SMT, 9 MiB L3), Ubuntu Server 26.04, kernel
  **7.0.0-38-realtime** (the signed amd64 RT flavour), tuned as `devices/pro/` declares it: core 0
  housekeeping, 1-5 isolated for render (`isolcpus`/`nohz_full`/`rcu_nocbs`), 72 units masked,
  xHCI interrupt on core 1. `devices/pro/check` was clean apart from the missing table itself.
- **Engine:** namchain `ae6f853`, built on pro with `-march=skylake -mtune=skylake`, vendored core
  `97d7cd4` (`rikkus/OptimisationWorkOnNeuralAmpModelerCore`, `all-optimisations`). All five ctest
  suites pass on pro, **including the A2 planar parity gate at -O3** — so the AVX2 kernels are
  provably the ones that ran (bit-identical to the Eigen-backed reference for C=3, −133.5 to
  −134.2 dB for C=8; recorded in pedal.project `25f603e`).
- **Tool:** `scripts/measure-core --host pro --seconds 30 --no-build`, which runs
  `namchain-warm-bench measure` on **cpu 2** (an isolated render core, not the active one),
  SCHED_FIFO priority 80, self-paced, quantum 64, deadline 1333 us, 30 s a point — vip's parameters,
  so the two tables are comparable. `namchaind` is stopped for the duration and the host lock is
  held; both were restored on the way out.
- **Input:** `guitar-di.wav`, 8182024 bytes, sha256 `1afd0ba…4dac3f517` — **byte-for-byte the file
  vip's table was measured with**, verified on both ends. Recorded in the table's `input` block, as
  vip's is, because costs are only comparable between units that rendered the same signal.
- `--no-build` because `scripts/measure-core`'s build step sources `devices/<host>/image.env`, which
  pro has not got; pro's own deployed `namchain-warm-bench` from `/opt/namchain/current` was used
  instead, so the bench and the engine are the same commit and the same flags.
- Wall clock: 00:58:53Z to 02:26:29Z, about 88 minutes.

## The table

| unit | vip | n | pro | n | vip/pro |
|---|---|---|---|---|---|
| `NAM.WaveNet.full` | 0.111 | 9 | **0.04** | 25 | **2.77×** |
| `NAM.WaveNet.lite` | 0.0333 | 30 | **0.0105** | 95 | **3.17×** |
| `IR.8192` | 0.0222 | 45 | **0.0182** | 55 | 1.22× |
| `IR.4096` | 0.0222 | 45 | **0.0182** | 55 | 1.22× |
| `IR.2048` | 0.01 | 100 | **0.00781** | ≥128 | ≥1.28× |
| `IR.1024` | 0.00781 | ≥128 | 0.00781 | ≥128 | — |
| `IR.512` | 0.00781 | ≥128 | 0.00781 | ≥128 | — |
| `node.nc.{input,output,gain,eq.biquad,delay,mix,split}` | 0.00781 | ≥128 | 0.00781 | ≥128 | — |

`≥128` means `at_most`: the bisection reached its `--max 128` ceiling with p99 still under the
deadline and zero overruns, so 1/128 = 0.00781 is a **floor, not a measurement**. Eight of pro's 14
rows are floors (the seven node types and IR.512/1024/2048), against six of vip's. IR.2048 is the
one row that moved from a real number on vip (100) to a floor on pro — pro ran out of ladder where
vip did not.

With `headroom` 0.8, admission will seat **20 A2-Full per render core** on pro against 7 on vip.

## What the 2.77× is, and is not

Per-copy p50 at the fitted n, same unit, same input:

| unit | vip | pro |
|---|---|---|
| `NAM.WaveNet.full` | 114.4 us | **41.4 us** |
| `NAM.WaveNet.lite` | 31.7 us | **9.4 us** |
| `IR.8192` | 9.0 us | **6.1 us** |

So the NAM kernels got about 2.8-3.4× faster per copy and the IR convolution about 1.5×. **The
2.77× is mostly the A2 kernels, not the host.** Reading it against
[2026-10-31](../2026-10-31-cost-pro/README.md), which measured the same unit on the same host with
the core at `d033987`, where the planar gate was Arm-only and A2 took the Eigen path:

| build | A2 path | per-copy p50 | fits per core |
|---|---|---|---|
| x86-64 baseline (no `-march`, SSE2) | Eigen | 133 us | 9 |
| `-march=native` (AVX2/FMA) | Eigen | 86 us | 14 |
| `-march=skylake`, core `97d7cd4` | **planar AVX2** | **41 us** | **25** |

Indicatively, the wider ISA buys 9→14 and the planar kernels buy 14→25. That split is **not clean**:
the 10-31 run was on the generic kernel with no core isolation, at 15 s a point and with the governor
forced to `performance`, where this one is on the RT kernel with 1-5 isolated at 30 s a point. The
direction is unambiguous; the exact apportionment is not measured.

**Why the IR row improves so much less than its average.** The IR's distribution is spiky — the
partitioned FFT does a large block periodically — so the fitted n is set by the p99, not the p50. At
pro's fitted n=55 the p50 is 335.9 us against a p99 of 1321 us, a ratio of 3.9 (vip: 3.2 at n=45). A
faster core shortens the average more than it shortens the worst block, so 1.5× per copy becomes
1.22× in the row. Nothing here is wrong; it is what the row is for.

## P9 on pro: the level meter does cost render time

The unit set measures `nc.eq.biquad` twice, which is P9's question. At n=128 (both arms exhausted the
ladder):

| arm | p50 | p99 | p99 % deadline |
|---|---|---|---|
| `--no-levels` | 102.6 us | 108.2 us | 8.1 |
| `--levels-publish-period` | 158.2 us | 165.7 us | 12.4 |

The meter costs about **0.45 us per node per block** — +53% on a biquad's p99 at 128 nodes. On vip
the same arm roughly *doubled* it, so the relative cost is lower here, but it is still real and still
on the render path. Because both arms hit the 128 cap, the table's row is the 0.00781 floor either
way: **the charge the engine makes does not reflect the meter.** That is unchanged from vip and is
P9's open end, not a pro finding.

## The engine reads it

Installed with `devices/pro/apply` (`namchaind` stopped for it and restarted, under the host lock);
`devices/pro/check` then reports **`pro matches devices/pro and it is in force`** and
`devices/pro/components.lock` records `devices=adebe3a`. `namchainctl status` after the restart
(`engine-status-after.json`):

```
"table": "/etc/namchain/cost.json",  "table_ok": true,  "table_detail": "loaded",
"table_rows": 14,  "table_host": "pro",  "table_engine_commit": "ae6f853",
"issues": []
```

`cost_table_missing` is gone. The rig pro happened to have loaded (`last.json`: `in` → NAM Ampeg
GVT52 Full → an 8192-tap Orange 4×12 IR → `out`) is now charged **0.07382 of a core, with all four
nodes `measured: true`** — none of them falling back. The same rig under the unknown costs would have
been charged 0.05 + 0.25 + 0.1 + 0.05 = **0.45**, so admission was over-charging it about sixfold,
and `verdict: fits` now means something.

## Limits of this table

- **Every row is a one-core-busy row.** Each point ran on cpu 2 with the other render cores idle.
  [2026-10-31](../2026-10-31-cost-pro/README.md) measured 13% (Eigen baseline) to 21% (`-march=native`)
  more time per model with five cores loaded, and that arm has **not** been re-run with the planar
  kernels — which move more data per instruction and so, by that run's own reasoning, might suffer
  more. A rig spread across several render cores may therefore be under-charged. vip's table carries a
  `coexistence` block for exactly this reason (its warm-set factors, from T5); **pro's has none**, so
  nothing corrects for it today.
- **No live confirmation.** vip's table was followed by T10 — an hour of real playing and switching,
  zero xruns. pro has a two-hour paced soak ([2026-11-01](../2026-11-01-soak-pro-rt/README.md), both
  arms clean) but **no signal has ever been through its audio interface**, so the table's bar
  ("the live soak confirms zero xruns") is inherited wording on pro, not something measured here.
- **The additive model is untested on pro.** vip's T2 put 16 heterogeneous rigs against the table and
  failed to falsify it. Nothing equivalent has been run here.
- `IR.2048` and the seven node rows are floors, so a rig of many small nodes is charged more than it
  costs. Raising `--max` past 128 would price them; it was not done.
- Two cost figures cannot be compared across hosts as "how good the box is" without saying which
  engine they were measured with. This table is only valid for namchain `ae6f853` built with
  `-march=skylake`; `devices/pro/components.lock` and the table's `engine_commit` both record that.

## Files

| File | What it is |
|---|---|
| `pro-fragments.jsonl` | The 15 fragments `measure-core` produced, each with its full bisection curve |
| `curves.txt` | The same curves as a table per unit |
| `points/unit-N.txt` | `namchain-warm-bench measure`'s own output, one file per unit, in `units` order |
| `units` | The unit set, one bench invocation per line |
| `session.log` | What ran on the host, in order |
| `engine-status-after.json` | `namchainctl status` once the table was installed and `namchaind` restarted |
