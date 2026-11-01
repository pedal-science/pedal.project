# pro: what a NAM A2-Full costs on one core, and on five at once

**Date:** 2026-10-31
**Question** ([docs/pro.md](../../docs/pro.md)): `pro` was bought for its L3 cache because several
A2-Full instances in parallel stopped scaling on vip. How many Full models fit per core on pro, and
does that number survive when the other cores are busy too?
**In one line:** one core fits **9** Full models with the engine as vip builds it (0.111 of a core,
the same as vip's row) and **14** with `-march=native` (0.0714); running the same load on five cores
at once costs 13% more time per model on the stock build and **21%** more on the native one, so five
cores hold about 8 and 12 per core. Cost still scales with the number of cores in use, on the
desktop part too.

## Setup

- **Host:** `pro`, i5-9500T (6 cores, no SMT, 9 MiB L3, 1.5 MiB L2 in all), Ubuntu 26.04.1, kernel
  7.0.0-42-generic, 14 GiB. Idle (load 0), nothing else running; wired network down, Wi-Fi up.
- **State changed for the run:** cpufreq governor `performance` on all cores for the runs, put back to
  `powersave` after. No core isolation, no `isolcpus`, no IRQ steering: this is the stock Ubuntu
  Server, so the numbers include whatever the OS does on its own. Test cores 1-5, core 0 left idle.
  Frequency sampled mid-run: 3.43 GHz with five cores loaded, ~3.65 GHz with one.
- **Tool:** `namchain-warm-bench measure --unit nam --slim 1.0 --seconds 15 --quantum 64 --priority 70
  --cpu <c>`, the bench behind vip's cost table, from namchain `efcdae7` (committed tree, with the
  vendored core `d033987` and its Dependencies, built on pro in `~/pedal-build/namchain-efcdae7`).
  namchain's 5 tests pass on pro. Model: `ORNG-V30-421-Center.nam`, input `guitar-di.wav`.
  Two builds: **stock** (`-O3`, no `-march`, so x86-64 baseline SSE2; the A2 planar NEON path is
  Arm-only, so A2 takes the Eigen path) and **native** (`-DCMAKE_CXX_FLAGS=-march=native`, AVX2/FMA).
- 15 s per point, not vip's 30 s, so the figures are less settled than vip's. The bar is vip's:
  p99 under the deadline (1333 us), overruns recorded.
- Run with plain `sudo` and not under `scripts/host-lock`; the lock works against pro unchanged
  (`scripts/host-lock --host pro`), it just wasn't needed with one person on the machine.

## Results

One core (cpu 2), the curve:

| n | stock p99 | stock p99 % deadline | native p99 | native p99 % deadline |
|---|---|---|---|---|
| 1 | 151 us | 11.3 | 105 us | 7.8 |
| 4 | 554 | 41.5 | 366 | 27.5 |
| 8 | 1066 | 80.0 | 694 | 52.1 |
| 9 | 1201 | 90.1 (1 overrun) | | |
| 10 | 1362 | 102.2 | | |
| 12 | | | 1041 | 78.1 |
| 14 | | | 1222 | 91.6 (0 overruns) |
| 15 | | | 1344 | 100.8 |

Stock fits **9** (0.111, as vip's row), native fits **14** (0.0714). Per-model time is flat in n on
one core (133 us stock, 86 us native at the p50), so nothing in the unit itself crowds.

The same n, one core against several at once (every loaded core runs the same bench; p50 per block):

| build | n | cores loaded | p50 | p99 % deadline | overruns of 11250 |
|---|---|---|---|---|---|
| stock | 8 | 1 | 1064 us | 80.0 | 0 (1 max over) |
| stock | 8 | 3 | 1135 (+6.7%) | 86.8-87.7 | 0 |
| stock | 8 | 5 | 1198-1206 (+13%) | 92.5-93.4 | 0-2 |
| native | 12 | 1 | 1036 us | 78.2 | 0 |
| native | 12 | 5 | 1247-1257 (+21%) | 96.7-97.5 | 4-20 |
| native | 14 | 1 | 1212 | 91.5 | 2 |
| native | 14 | 5 | 1481-1488 (+22%) | 130-131 | all |

So with five cores busy: stock holds 8 per core (40 in all) and native 12 per core (60 in all, at
97% p99, so with no margin; 11 was not measured). Native on one core held 14.

## What this does and does not show

- **Something does scale with the cores in use.** The p50 of the very same work rises as cores are
  added, and the native build, which moves more data per instruction, suffers more.
- **It is not shown to be the L3.** Part of it is frequency: with five cores loaded the clock was
  ~6% below the one-core clock, about half of the stock build's 13%. The rest could be the shared L3
  and memory bandwidth, or power limits (the part's PL1 is 35 W, PL2 69 W), or the OS; nothing here
  separates them. A measurement that would: `perf stat` L3 miss counters per run, the same load with
  the clock pinned, a working-set sweep.
- **It was not compared with vip on the same day.** The "cache contention" on vip is the owner's
  observation. `docs/multi-core.md` has vip's multi-core findings; the same five-core arm has not
  been run on vip (vip was not touched).
- Stock-build numbers are what the engine as vip builds it gives on x86; `-march=native` is a pro-only
  choice that ties the binary to this CPU and has not been through the golden/parity tests (the 5
  tests passed on the stock build only).

## Files

`full.json` and `full-native.json` (one-core curves with their fragments), `par-<k>-c<cpu>.{json,txt}`
(stock, k cores loaded, n=8), `nat-<k>-<n>-c<cpu>.txt` (native).
