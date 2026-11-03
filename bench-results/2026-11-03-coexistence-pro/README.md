# pro with the other cores busy: the planar kernels' coexistence cost

**Date:** 2026-11-03
**Question** ([docs/pro.md](../../docs/pro.md),
[2026-10-31](../2026-10-31-cost-pro/README.md), [2026-11-02](../2026-11-02-cost-table-pro/README.md)):
every row of pro's cost table is measured on one core with the other render cores idle, so the table
is an upper bound on what fits. 10-31 measured the correction on the Eigen builds — 13% on the stock
one, 21% on `-march=native` — and left two things open: the arm had **not** been re-run with the
planar AVX2 kernels the table was eventually measured with, and it could not say whether the cost
was the clock or the shared L3 ("It is not shown to be the L3"). What does a unit really cost on pro
when the pedal is rendering on every core, and what is the cost made of?
**In one line:** the planar build suffers **four times** what the Eigen build did — **+86%** on a
Full model's p50 with five cores busy, against 10-31's +21% — and it is **the shared L3, not the
clock**: with every core pinned to one speed, +68.4% of the 86% survives, which is what the IPC drop
alone implies. Only 14 Full models fit per core with the other four busy, against 25 alone, so pro's
table now carries a `coexistence` block for the first time (factors 1.24 and 1.71). The run also
re-measured the table's three real rows independently and **confirmed two of them exactly**, finding
the third (`lite`) one copy optimistic.

Evidence: `fixed/`, `bisect/`, `lite-k23/` and `pinned/`, each with the arms it was given, its
`reading.txt`, the bench's own log per arm, `perf` counters per core and the `/proc/stat` pair that
shows which cores were loaded. 23 arms, 136 measured points, 3h 51m of host time under the lock.

## Setup

- **Host:** `pro`, i5-9500T (6 cores, no SMT, 9 MiB L3), kernel **7.0.0-38-realtime**, tuned as
  `devices/pro/` declares it: core 0 housekeeping, 1-5 isolated (`isolcpus`/`nohz_full`/`rcu_nocbs`),
  governor `performance`, turbo on. `namchaind` stopped for every arm, the host's lock held
  throughout, and the run detached on the host so a dropped ssh session could not take it with it.
- **Engine:** namchain `ae6f853` built `-march=skylake`, vendored core `97d7cd4` — **the exact
  commit and flags the table was measured with**, taken from the host's own
  `/opt/namchain/current`, so the bench and the engine cannot disagree.
- **Input:** `guitar-di.wav`, sha256 `1afd0ba…4dac3f517`, checked on the host before the run: the
  signal the table's `input` block names.
- **Tool:** [scripts/measure-coexistence](../../scripts/measure-coexistence), new here, read by
  [scripts/src/coexistence-read.py](../../scripts/src/coexistence-read.py). One core is the
  *subject* (cpu 2, the core `measure-core` uses); k-1 of the others are *neighbours*, each carrying
  **a full core's worth** of the same unit at the table's own fitted n, relaunched until the arm
  ends so a long bisection cannot outlive its load. Two arm kinds: `fixed` holds n constant across k
  so the arms are the identical job, and `bisect` runs the bench's own search *under* load so the
  fitted n is measured rather than inferred.
- Two measurement traps this harness had to work around, both pro-specific and both worth knowing:
  - **`nproc` returns 1** in an ssh session, because `devices/pro` narrows `user.slice` to the
    housekeeping core. Anything deriving a core list from it watches one core of six.
  - **`scaling_cur_freq` is useless on the isolated cores**: it cannot IPI a `nohz_full` core and
    reads the 800 MHz floor however busy the core is. Every clock below is **aperf/mperf × TSC**
    through `perf stat -A`, which is the frequency the core ran at while it was running.

## 1. The same work, more cores busy

n held at the table's own fitted n, so every arm of a unit is the identical job. 120 s a point. The
perf columns are the subject core's, over a 65 s window inside the arm.

| arm | cores busy | p50 | vs alone | p99 %dl | clock | IPC | L3 miss rate |
|---|---|---|---|---|---|---|---|
| `NAM.WaveNet.full`, n=25 | 1 | 1040.6 us | — | 97.9 | 3.366 GHz | 1.93 | 25.7% |
| | 2 | 1168.4 | +12.3% | 111.1 | 3.413 | 1.69 | 50.4% |
| | 3 | 1308.5 | +25.7% | 131.1 | 3.391 | 1.52 | 60.9% |
| | 4 | 1586.7 | +52.4% | 160.1 | 3.183 | 1.33 | 67.8% |
| | 5 | 1935.9 | **+86.0%** | 193.1 | 3.052 | 1.14 | 73.0% |
| `NAM.WaveNet.lite`, n=95 | 1 | 919.8 | — | 101.0 | 3.272 | 1.28 | 57.3% |
| | 5 | 2295.5 | **+149.6%** | 266.4 | 3.225 | 0.52 | 89.2% |
| `IR.8192`, n=55 | 1 | 336.2 | — | 99.2 | 3.145 | 2.64 | 12.8% |
| | 5 | 306.6 | **−8.8%** | 100.7 | 3.413 | 2.46 | 56.3% |
| `NAM.WaveNet.full`, n=25, **repeated last** | 1 | 1040.9 | +0.03% | 98.0 | 3.369 | 1.92 | 26.2% |

**The drift control passed.** The first arm and the last are the same arm, 29 minutes apart:
1040.6 us and 1040.9 us, 0.03% apart. Nothing above is session drift.

**The planar build is four times as sensitive as the Eigen build.** 10-31 measured +13% (x86-64
baseline) and +21% (`-march=native`) for five cores busy, and reasoned that the native build, moving
more data per instruction, "might suffer more". With the planar AVX2 kernels it is **+86%**. The
guess was right and badly understated.

**The penalty is strongly unit-dependent**, which is the part no earlier run saw:

- `lite` is worst (+150%). A lite submodel is small enough that a quiet 9 MiB L3 holds the working
  set — its miss rate alone is 57% and its IPC 1.28, both already poor — and five busy cores take
  that away: IPC collapses to **0.52**, worse than one instruction every other cycle.
- `IR.8192` barely cares, and its p50 actually **fell** 8.8%. A partitioned FFT is already
  memory-bound and streaming, so it has little cache residency to lose; its cost is set by the
  periodic large block rather than by what stays in L3. Its tail did degrade (72 overruns → 10775,
  p99 99.2% → 100.7%), which is what takes it over the bar, but the *median* is untouched.

## 2. It is the L3, not the clock — and this time it is shown

10-31 could not separate the two. This run separates them twice over, by arithmetic and then by
construction.

**By arithmetic.** Over the five-core arm the clock falls 3.366 → 3.052 GHz, −9.3%, which on its own
would cost +10.3% of time. IPC falls 1.93 → 1.14, −41%, which on its own would cost +69%. Together
1.103 × 1.693 = **1.868**, against the **1.860** measured. The decomposition closes to 0.4%, and the
L3 miss rate going 26% → 73% says what the IPC drop is.

**By construction.** The same two arms with `scaling_max_freq` held at 3.0 GHz on every core — below
the 3.052 GHz the part settles to with five cores busy, so both arms demonstrably ran at one speed
(3.011 GHz measured, both):

| arm | clock | p50 | vs alone | IPC | L3 miss rate |
|---|---|---|---|---|---|
| Full, n=25, 1 core busy | 3.011 GHz | 1144.7 us | — | 1.96 | 26.2% |
| Full, n=25, 5 cores busy | 3.011 GHz | 1927.6 | **+68.4%** | 1.17 | 72.4% |

With frequency removed by construction, **+68.4%** of the 86% remains, against the +69% the IPC drop
predicts. So of the 86%: about a tenth is the clock and the rest is the shared L3 and memory. The
cache explanation pro was bought on is now measured rather than assumed — and it is also the reason
the box's advantage over vip is narrower in practice than the single-core table suggests.

(The pinned k=1 arm *misses* the deadline at n=25, p99 105.3%. That is not a fault: the table's row
of 25 depends on the part's full 3.37 GHz, and 3.0 GHz is not enough for it. It is a useful warning
that the row has no frequency margin in it.)

## 3. What actually fits, and the factors

The bench's own bisection, run *under* load. 90 s a point. Every unit gets its own one-core arm here
rather than borrowing the table's n, so each factor is a ratio of two measurements taken the same way
in the same session.

| unit | alone | 1 nbr | 2 nbr | 3 nbr | 4 nbr |
|---|---|---|---|---|---|
| `NAM.WaveNet.full` | **25** | 22 | 19 | 16 | 14 |
| `NAM.WaveNet.lite` | **94** | 76 | 55 | — | 41 |
| `IR.8192` | **55** | — | — | — | 51 |

| unit | factor at 1 nbr | 2 nbr | 3 nbr | 4 nbr |
|---|---|---|---|---|
| `NAM.WaveNet.full` | 1.136 | 1.316 | 1.562 | 1.786 |
| `NAM.WaveNet.lite` | **1.237** | **1.709** | — | 2.293 |
| `IR.8192` | — | — | — | 1.078 |

**The block installed** in [devices/pro/rootfs/etc/namchain/cost.json](../../devices/pro/rootfs/etc/namchain/cost.json)
is `{"1": 1.24, "2": 1.71}`: the **worst** row's factor at each key, rounded up, because the factor
multiplies a whole rig and a rig is a mixture of units. `IR.8192` was deliberately not re-run at one
or two neighbours — its factor at *four* is 1.078, and a factor cannot fall as cores are added, so
IR is at most 1.078 anywhere and can never be the binding row. That reasoning saved 35 minutes of
host time to change nothing.

**The table's own rows come out of this confirmed.** These one-core arms are an independent
re-measurement at three times the point length the table used (90 s against 30 s):

| row | table (30 s) | here (90 s) | |
|---|---|---|---|
| `NAM.WaveNet.full` | 25 | **25** | exact |
| `IR.8192` | 55 | **55** | exact |
| `NAM.WaveNet.lite` | 95 | **94** | one copy optimistic |

The `lite` row is the one soft spot, and §1 agrees with §3 about it: at n=95 and 120 s the arm
*misses*, p99 101.0% with 1177 overruns. The row is left at 95 rather than quietly corrected, because
a row measured by one harness should not be overwritten from another's arm — and it does not matter
in practice: with `headroom` 0.8 admission seats 76 lite submodels per core, nowhere near 94. It is
recorded here and in `docs/pro.md` so the next `measure-core` run fixes it properly.

## 4. The engine applies it

Installed with `devices/pro/apply` (`namchaind` stopped for it and restarted, under the lock);
`devices/pro/check` reports **`pro matches devices/pro and it is in force`** and
`devices/pro/components.lock` records the new tree. The engine then loaded it — 14 rows, `table_ok`,
`issues: []` — and reported the factor **not** applied, exactly as it should:

```
coexistence 1.0   coexistence_warm_documents 0   cost 0.07382   effective 0.07382
```

That proves it parsed, not that it reaches admission. So one document was warmed from a file
(`namchainctl warm --document`, nothing added to the pedal's library) and the engine re-read:

```
coexistence 1.24  coexistence_warm_documents 1   cost 0.07382   effective 0.0915368   verdict fits
```

0.07382 × 1.24 = 0.0915368. The number in the file reaches the charge. The document was cooled, the
probe file removed, and pro left playing its own rig with 0 xruns, 0 guard trips and the lock free.

## Limits of this measurement

- **The factors are an upper bound, and not the same quantity vip's block holds.** A neighbour here
  is a *saturated* core — 25 Full models, 100% busy. vip's T5 neighbour was one real warm document,
  which is far lighter. So pro's 1.24 and vip's 1.25 agree by coincidence, not because the hosts
  behave alike, and pro's block will refuse some warms pro could actually afford. That is the safe
  direction (D8 refuses rather than glitches), but the honest refinement is vip's T5 on pro, which
  needs **pedald**, which pro has not got.
- **Nothing is charged on pro today.** `coexistence_factor` returns 1.0 for zero warm documents and
  nothing warms one without pedald, so the block is correct and inert. It was still worth installing
  and measuring now: §1 is a property of the host and the engine, not of pedald.
- **Only three rows were measured.** The eight floor rows (the seven node types, IR.512/1024/2048)
  were not: they are `at_most` values at the `--max 128` ceiling, so a coexistence factor read
  against them would be a ratio of two floors.
- **k is cores busy, not warm documents.** The engine holds at most one warm document
  (`kMaxDocuments` is 2), so only the `"1"` key can arise today; `"2"` is measured against the day
  D4's two-neighbour arrangement exists, as vip's is.
- **Still no signal through pro's audio interface.** Every figure here is the bench pacing offline.
  The table's bar still says "the live soak confirms zero xruns", which on pro remains inherited
  wording. A pro equivalent of vip's T10 is the outstanding gap, unchanged by this run.
- **The 10-31 comparison crosses two setups.** That run was on the generic kernel with no isolation,
  15 s a point, governor forced to `performance`; this one is the RT kernel with 1-5 isolated at
  90-120 s. The direction (+21% → +86%) is far too large to be setup, but the exact multiple is not
  a controlled comparison.

## Files

| Path | What it is |
|---|---|
| `fixed/` | §1: ten fixed-n arms, 120 s, with per-core perf. `arms`, `reading.txt`, `session.log`, `fragments.jsonl`, `out/` |
| `bisect/` | §3: nine bisection arms under load, 90 s |
| `lite-k23/` | §3: the lite row at one and two neighbours, which decide the two factors |
| `pinned/` | §2: the two clock-pinned arms, plus `out/maxfreq.before` — what the clock was put back to |
| `*/out/<arm>-c2.txt` | the bench's own output for that arm, curve and all |
| `*/out/<arm>.perf` | `perf stat -A` for every core over that arm's window |
| `*/out/<arm>.cpustat.{before,after}` | the `/proc/stat` pair: which cores were loaded, and how much |
