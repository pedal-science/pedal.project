# STREAM memory bandwidth: vip vs piv, and why vip is slower

**Date:** 2026-10-03
**Question:** why does vip's RAM measure slower than piv's in STREAM, and how much of the
gap is hardware (DRAM) vs live load?

## Method

- Same STREAM 5.10 binaries on both boards, verified byte-identical by SHA-256:
  - `stream_omp`  `b2ef8ce60a1b6bce339c59b5fdb63d598d6be6e0142e70135b822230d2887db2`
  - `streamomp.10M` `447781d2c5f53a2bc68ac5967fc90aa5e3c3878615cdb8789c30a5c94b76bbd8`
  - `streamomp.10M` (fixed 10M-element arrays, ~229 MiB) is the one used below; no `OMP_*`
    env vars, so the 2 OpenMP threads come from the cpuset (both shells see CPUs 0-1).
- Both boards run the same kernel `7.0.0-1017-raspi-realtime` at 2.4 GHz, `performance`
  governor, and the same tuning args (`isolcpus=managed_irq,domain,2-3 nohz_full=2-3
  rcu_nocbs=2-3 irqaffinity=0-1 skew_tick=1`), so IRQ placement is not a confound.
- vip's run was done under `scripts/host-lock`; the "quiet" leg was measured with
  `namchaind` stopped, then restarted (it returned to `running`/`ok`, xruns 0).
- vip thermal 51.25 °C, all cores 2.4 GHz during the run — no throttling.

The decisive hardware fact (device tree, `/proc/device-tree/chosen/`):

| | vip (Pi 5, 1 GB) | piv (Pi 500, 8 GB) |
|---|---|---|
| `rpi-sdram-size-gbit` | 8 | 64 |
| `rpi-dual-rank` | **0 (single rank)** | dual rank (8 GB = two dies) |

## Results (MB/s, best-of-10 per run; three runs each)

**piv — quiet, dual-rank 8 GB:**

| run | Copy | Scale | Add | Triad |
|---|---|---|---|---|
| 1 | 8570.4 | 8598.8 | 7944.1 | 7825.2 |
| 2 | 8474.9 | 8598.8 | 7875.6 | 7709.4 |
| 3 | 8476.3 | 8514.3 | 7898.9 | 7727.9 |

**vip — quiet (namchaind stopped), single-rank 1 GB:**

| run | Copy | Scale | Add | Triad |
|---|---|---|---|---|
| 1 | 6779.6 | 6962.6 | 5970.0 | 5808.2 |
| 2 | 6939.0 | 6809.1 | 5728.6 | 6083.8 |
| 3 | 6823.6 | 6524.5 | 5931.8 | 6099.6 |

**vip — contended (namchaind running):**

| run | Copy | Scale | Add | Triad |
|---|---|---|---|---|
| 1 | 6052.8 | 5938.9 | 5313.6 | 5139.2 |
| 2 | 5970.2 | 6042.1 | 5338.7 | 5186.0 |
| 3 | 5920.7 | 5889.9 | 5075.7 | 5338.7 |

## The two effects, quantified

Averages:

| kernel | piv quiet | vip quiet | vip contended | hardware gap (vip quiet vs piv) | contention gap (quiet vs contended) |
|---|---|---|---|---|---|
| Copy | 8507 | 6847 | 5981 | −19.5% | −12.7% |
| Scale | 8571 | 6765 | 5957 | −21.1% | −12.0% |
| Add | 7906 | 5877 | 5243 | −25.7% | −10.8% |
| Triad | 7754 | 5997 | 5221 | −22.7% | −12.9% |

## Conclusion

1. **Hardware — single-rank DRAM (~20–26%).** vip's 1 GB Pi 5 is single-rank LPDDR4X
   (`rpi-dual-rank=0`); piv's 8 GB Pi 500 is dual-rank. Rank interleaving is what lifts
   dual-rank's achievable bandwidth, and the penalty is largest on the three-access
   kernels (Add, Triad). This is a property of the 1 GB SKU, not a fault, and it can't be
   tuned away in software.
2. **Live load — namchaind (~11–13%).** Rendering the rig plus the resulting DMA/interrupt
   traffic costs vip another ~11–13% of bandwidth on the shared cores 0-1. This is the
   inherent cost of vip being the Core host, and it's the part that *is* under your control.
3. Combined, vip-as-it-runs delivers ~67–70% of piv's bandwidth.

The earlier single-run number that prompted this (vip Triad 4858, vs its own Add 6962) was
an interference artifact: the run's `Max time` column had ~2× spikes (e.g. Add 0.067 s vs
0.034 s min), and under clean conditions Triad and Add come back into line (vip quiet:
Add 5877 vs Triad 5997).
