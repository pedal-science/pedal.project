# pro: UMC202HD period sweep and one-hour soak

**Date:** 2026-10-31. **Host:** pro (i5-9500T, kernel 7.0.0-42-generic stock, governor `performance`,
no isolation), namchain `efcdae7` stock-flag tools, `namchaind` stopped for the runs.
**Tool:** `namchain-soak --backend alsa_raw --device hw:CARD=U192k,DEV=0 --channels 2 --periods 6
--model ORNG-V30-421-Center.nam --instances 2 --cpu 5 --rt-priority 80 --max-p99-percent 80`.
Stream mode: capture from the interface with nothing plugged in; **no signal injected, no `namchaind`.**

**In one line:** 32 frames and up held for 45 s; 24 and 16 did not; the hour at 64 frames **failed**
with one burst of slow blocks (4 overruns, 1 playback underrun) 22 min 51 s in.

## Period sweep (45 s each) — `sweep.txt`

| frames | p99 % of deadline | result |
|---|---|---|
| 128 | 15.6 | pass |
| 64 | 16.3 | pass |
| 48 | 18.2 | pass |
| 32 | 21.6 | pass |
| 24 | 30.5 | fail, 1 playback underrun |
| 16 | 30.1 | fail, 3 deadline overruns, 1 playback underrun |

## One hour at 64 frames — `soak-hour.txt`

2 700 000 blocks, RTF 1.0000, block p99 274.8 us (20.6%), 0 allocations. **FAIL:** 4 deadline overruns
and 1 playback underrun, first at block 1028393. The slow blocks cluster at blocks 1028378-1029028
(1371-1380 s); the worst took 2.03 ms. CPU time equals wall time for them (cpu max 2026954 ns, wall max
2026857 ns), so the thread was running, not preempted: the same work took ten times longer. Three further
isolated spikes of about 0.7 ms (blocks 102797, 307723, 1144236) did no harm.

Not established: the cause. Candidates are an SMI, a frequency or power-limit event, and a memory or USB
stall. Nothing was recorded during the run to separate them. The `soak-exit=` line is empty (the
`PIPESTATUS` in the remote command did not survive the shell); the result line above is the verdict.
`namchaind` was restarted afterwards and is active.

Every run, including the sweep, reports `bring-up xruns: 1` before the measured loop; not investigated.
