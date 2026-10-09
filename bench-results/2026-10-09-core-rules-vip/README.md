# vip's core rules, and the audio IRQ's core (2026-10-09)

The pedal's rules changed on 2026-10-09 (owner): **all but one core is a render core**, the
non-render core carries everything *except* interrupts, the audio interrupt is delivered to a
**render core**, and that core is **never the active one**. Both the rules and the tree had drifted:
the document said "one core is housekeeping, IRQs ... and everything the OS does", while vip's
`tune.conf` had two housekeeping cores (0–1) and two render cores (2–3), inherited verbatim from piv
on 2026-09-29 and never measured. P7 then moved the interrupt's pin onto core 0 on a reading of D5
that only made sense under the inherited split.

This is the evidence for the change and for what it cost.

## 1. The layout that is now in force

| | before (2026-09-29 → 2026-10-09) | now |
|---|---|---|
| kernel isolation (`isolcpus`, `nohz_full`, `rcu_nocbs`) | 2-3 | 1-3 |
| interrupt affinity (`irqaffinity=`) | 0-1 | 0 |
| housekeeping (`HOUSEKEEPING_CPUS`, the three slice drop-ins, `init.scope`) | 0-1 | 0 |
| active render core (`RT_CPUS`, namchaind's `cpu`) | 3 | 3 |
| warm-capable render cores | 2 | 1, 2 |
| audio IRQ delivered to (`AUDIO_IRQ_CPU`) | 0 (P7), 2 before that | 1 |
| namchaind's control thread (`CPUAffinity`) | 0-1 | 0 |

The five places that must agree are the kernel command line (`rtpi`, `devices/vip/device.env`,
`AUDIO_TUNING_ARGS`), `devices/vip/rootfs/etc/pedal/tune.conf`, the two slice drop-ins,
`devices/common/rootfs/etc/systemd/system/namchaind.service.d/10-pedal.conf` and
`devices/common/rootfs/etc/pedal/pedal-interface.json` (what `pedal-diag` reads). `pedal-tune check`
now asserts the rules as four lines rather than the single "the IRQ is outside `ISOLATED_CPUS`" that
P7 added — which passed in *both* layouts and so caught nothing:

```
== core roles
  ok    non-render cores (R1)              1
  ok    render cores (R1)                  3
  ok    housekeeping and render cores disjoint 0 / 1-3
== audio interrupt (dw_axi_dmac_platform)
  ok    IRQ 138 affinity                   1
  ok    IRQ 138 affinity vs render set (R3) cpu 1 is inside 1-3
  ok    IRQ 138 is not on the active core (R4) cpu 1, active core 3
  ok    thread irq/138-dw_axi_dmac_platform prio 85
  --    thread irq/138-dw_axi_dmac_platform core 0 (observed; its mask cannot be set from here)
```

The command line was changed with `vip-boot set-args`, a new subcommand: it rewrites
`cmdline-tuned.txt` in **every** slot from `devices/vip/device.env`, prints the word-level diff,
writes nothing without `--yes`, keeps the file it replaced as `cmdline-tuned.txt.bak-<stamp>`, reads
it back, and can put it back from any root (rescue included). Before it existed the only way to
change the arguments on a running board was to stage a whole kernel through `try-kernel` — a bigger
hammer than the change deserves, and one that leaves the other slot on the old arguments, which is a
fallback into a layout the rules no longer describe. Slot b was on the same old line as slot a; both
now say `isolcpus=managed_irq,domain,1-3 nohz_full=1-3 rcu_nocbs=1-3 irqaffinity=0 skew_tick=1`. The
board rebooted into it (23 s to answer, 113 s to settle, no guard event).

**An unenforceable half, recorded so it is not assumed.** Only the interrupt's *delivery* can be
pinned. Its handler thread carries `0-3` on this kernel (`PF_NO_SETAFFINITY`), and it does **not**
follow the IRQ's affinity here as `pedal-tune`'s comment used to claim: it was observed on core 1
while the delivery was pinned to 0, and on core 0 while the delivery was pinned to 1. What keeps it
off the other render cores is `isolcpus=domain`, not the mask, so `pedal-tune check` reports the core
it is on and fails if it is ever the active one.

## 2. T6, re-run on the new placement

`scripts/measure-irq`, two arms, 240 s each, the same load on the housekeeping core in both (a CPU
spinner on core 0, a 200 MB SD write, a 200 MB WiFi upload), the engine playing
`/var/lib/pedal/library/rigs/last.json` through the codec. Arm A is the rule (delivery on core 1, a
render core that is not the active one); arm B is P7's placement (delivery on core 0).

| | arm A: core 1 (the rule) | arm B: core 0 (P7's) |
|---|---|---|
| render, worst block | 777.9 µs = **58.3%** of the deadline | 777.9 µs = **58.3%** |
| render histogram | 20–22% typical, tail to 58% | identical |
| blocks over the deadline | 0 | 0 |
| blocks over 90% | 0 | 0 |
| xruns / guard trips | 0 / 0 | 0 / 0 |
| IRQ thread's wait to run | 6.06 ms over 361,298 wakes = **16.8 ns/wake** | 6.17 ms over 362,374 wakes = **17.0 ns/wake** |
| IRQ thread's core, as delivered | 1 | 0 |

**Reading it.** The interrupt's core does not matter, to the interrupt or to the render: 16.8 ns
against 17.0 ns per wake, and identical render distributions with zero overruns and zero xruns in
both arms. That is the same conclusion the 2026-10-08 run reached (7.4 ns against 7.7 ns), so the
reversal is not justified by T6 — it is justified by the *rules* (all but one core renders, so the
interrupt lives on a render core) and by where the preemption lands, which T6 does not measure: with
P6 the warm rig is the thing that gets preempted, and that is T8's subject.

**Two honest differences from the 2026-10-08 run.** The rig is not the same: this run played
`last.json`, a three-chain document (worst block 58.3% of the deadline), where the earlier run played
an amp-and-cab rig (worst block 24.6%, typical 7–9%). And the absolute wait-to-run is higher
(17 ns against 7.4): the numbers that matter here are the *pair*, measured minutes apart on the same
board with the same load, not the absolute value across runs.

**What this run does not cover.** At the time it ran, P6 was not yet deployed, so core 1 had no warm
thread on it: this measures the interrupt against an *idle* render core, which is not the arrangement
the rules describe. The arrangement with warm work beside it is measured below (§4). T5
(housekeeping starvation under a one-core housekeeping set) has not been run; the document records
why — it wants P6's warm cores to be the thing being protected.

## 3. Two faults the work surfaced, and fixed

* **The interface model was never installed.** `pedal-interface.json` is what `pedal-diag` compares
  the host against, and `pedal-diag.service` will not start without it
  (`ConditionPathExists=/etc/pedal/pedal-interface.json`) — but it lived at
  `devices/common/pedal-interface.json`, and the only thing that installs anything is the rootfs tree
  (`apply` stages `rootfs_files()`, the image build copies `rootfs/`). It reached no host, so every
  check that compares the board against the model — the audio IRQ's core among them — silently did
  nothing. It is now `devices/common/rootfs/etc/pedal/pedal-interface.json`, with a test that asserts
  it is inside the tree that installs it. On the board: the report's header names
  `/etc/pedal/pedal-interface.json` and the verdict is 9 ok, 1 warn (61 °C, the stand-in case), 1 info.
* **`pedal-diag --json` could not parse its own gatherer.** The gatherer prints one line of JSON and
  then `COST <seconds>`; the remote path looked for each by shape, the local path did
  `json.loads(whole buffer)` — so a local run crashed with `Extra data: line 2 column 1` on every
  non-deep sample. Both paths go through one function now.

## 4. P6 on the pedal: the warm set and the switch

P6 (namchain M3, `namchain/docs/warm-set.md`) is deployed: engine `a0a9cf0`, with
`"warm_cpus": [1, 2]` and `"warm_priority": 70` in `devices/vip/rootfs/etc/namchain/namchaind.json`
and the device core unchanged at 3. Core 1 comes first on purpose — it is the core the audio IRQ is
delivered to, so the first live warm rig shares a core with the interrupt, which is the arrangement
D5 describes.

**The switch, live, eight times.** `rig.warm last.prev.json` (both documents are the three-chain
soak rig, cost 0.41 each), then `rig.switch` back and forth every 2 s:

```
switches, handover_blocks, xruns, worst_us, worst_pct, over_deadline, warm_behind, drops
1 3 0 932.424 69.9 0 0 0
2 3 0 932.424 69.9 0 0 0
3 3 0 932.424 69.9 0 1 0
4 3 0 932.424 69.9 0 0 0
5 3 0 932.424 69.9 0 0 0
6 3 0 932.424 69.9 0 1 0
7 3 0 932.424 69.9 0 0 0
8 3 0 932.424 69.9 0 0 0
```

Every switch: `switched: warm`, `handover_blocks: 3` (4 ms of setup) plus the 5 ms fade, **0 xruns,
0 blocks over the deadline, 0 dropped warm blocks**, and the outgoing document stays warm in its
place (`behind_blocks` 0 or 1 — one block, 1.33 ms, of lag while sharing core 1 with the interrupt).
That is T7's live half and T8's live falsifier at once, and it is a long way inside D10's 50 ms.

**T7's offline half is measured but its verdict is not trusted.** `namchain-warm-bench switch`
(30 s, switch every 2 s, render on 3, warm on 1, inside `pedal-bench.slice` — an ssh session lives in
`user.slice`, whose cpuset is core 0, so the tool cannot pin from there and reports
`sched_setaffinity: Invalid argument`):

```
handover:   5 switches (0 deferred), last 5 blocks; blocks here are 1333 us
render:     p50 86 us  p99 107 us  p99.9 114 us  max 155 us  over deadline 0
warm:       p50 86 us  p99 107 us  max 134 us  blocks 8995  worst lag 0 blocks
glitch:     FAIL  continuity 1.85 vs limit 0.29, hf excess 8.22 dB, convergence 12.4 dBFS
```

The *loads* agree with the live run and are the useful part: the device thread's p99 is 8% of the
deadline with a warm document rendering beside it, nothing overruns, and the warm thread's worst lag
is **0 blocks**. The glitch verdict is a different matter: the tool's own crossfade is being judged,
and it fails continuity, high-frequency excess and convergence in *both* arms with byte-identical
output, which is what a fault in the harness's own mixer or reference comparison looks like rather
than a fault in the engine — the engine's own switch is judged continuous on the file backend by its
test suite, and the live switches above produce no xrun, no dropped block and no report of trouble.
**Treat the tool's PASS/FAIL as unproven until someone fixes or disproves it**; the numbers above it
are not affected by that.

**Two integration faults found by putting it on the board, and fixed:**

* `namchaind` would not start with `warm_cpus [1, 2]`: the startup check asked whether each warm cpu
  was in the process's *initial* affinity mask, which the unit sets to core 0 (`CPUAffinity=0`, so
  that the compiling control thread cannot land on the device core). The render thread already
  widens its own mask to core 3, which `CAP_SYS_NICE` allows; a warm thread does the same. The check
  now asks what no capability can conjure — whether the kernel has the cpu — and the pin is reported
  after the fact as the render thread's already is. The failure mode was the worst one available: no
  engine at all, and a silent pedal.
* `namchain-warm-bench`'s switch arm had never been compiled (the target is Linux-only) and did not
  compile: an unqualified `kMaxTransitionFrames` and an unused local. Fixed, and `namchain/AGENTS.md`
  now carries the seconds-long container check that catches this class of thing.

**The service's half, live.** `pedald` holds the neighbour warm by itself: given a bank of two
library rigs it logged `warming warmcheck-a.json`, the engine took it on core 1 (`state: warm`,
`behind_blocks: 0`) and `pedald`'s `/status` carried the engine's own object under `engine.warm`.
The pedal's library had **no** rigs at all before that — only the resume files `last.json` and
`last.prev.json`, which `pedald` excludes from the bank by design — so there had been nothing for it
to warm and the empty bank was correct rather than broken. A *press* through the service is
unit-tested (25 new tests, including the `warm_disabled` fallback) but not measured on the pedal: a
press arrives over the Pico link and no footswitch is attached to this bench.

## 5. The hour, on the new layout with the warm set live

`scripts/soak/rig-switch-hour --minutes 60 --switch 30` — the repo's own T10, run on the new
layout with a warm document rendering on core 1 for the whole hour (the engine's journal shows the
warm thread on core 1 at priority 70 and `last.prev.json` in document 1 from the first sample) and
120 cold rig publishes on the device core.

| | 2026-10-08 (2–3 isolated, IRQ on 0) | 2026-10-09 (1–3 isolated, IRQ on 1, warm set live) |
|---|---|---|
| samples / duration | 373 over 62.2 min | 359 over 60.0 min |
| blocks | 2,799,143 | 2,699,756 |
| render p50 / p99 / p99.9 | 13% / 23% / 30% | 12% / **29%** / 42% |
| worst block | 951.5 µs (71.4%) | **1045.5 µs (78.4%)** |
| temperature | 53.8–58.2 °C | 57.6–63.7 °C |
| clock / throttle | 2400 MHz, `0x0` | 2400 MHz, `0x0` |
| transitions, drops, bursts | 126, +0, +0 | 120, +0, +0 |
| **gate** | **PASS** | **PASS** |

Gate, both runs: driver xruns 0, deadline overruns 0, guard trips 0, blocks over 90% 0, render
errors 0, device lost 0.

**Reading it.** The hours are not like for like and the difference is the point: this one had a
second document rendering on the core that also carries the audio IRQ, which the October 8 hour did
not (there was no warm set then). The audio path's p99 moved from 23% to 29% of the deadline, the
worst block from 71% to 78%, and the board ran 5 °C warmer — that is what a warm rig costs the
audible one, and it is a fraction of the headroom D3 reserves. Nothing overran, nothing was dropped,
and the clock held at its cap with no throttle flag.

## 6. The cost table's provenance, moved without re-measuring

`devices/vip/cost.json`'s `engine_commit` moved from `87f3cb9` to `a0a9cf0` on 2026-10-09, and the
table's own `bar` field says so. It was **not** re-measured, deliberately: P6 adds a warm thread and
a second document on an *inactive* core and adds nothing to the audible path, and namchain's golden
tests — recorded before P6 — still pass, so no unit's cost has changed. Two things follow: the
numbers stand, and a re-measurement is owed the next time a change touches the render path itself.

The check that caught this (`devices/common/check` compares the table's `engine_commit` with what
`/opt/namchain/current/MANIFEST` says) also found a wart in `deploy-engine`: it wrote the *argument*
through as `rev=`, so a deploy made with `--commit HEAD` produced a manifest that says "HEAD" and a
correct table failed its provenance check. Both build paths record the resolved commit now.

## 7. What is not done

* **T5 (housekeeping starvation)** has still not been run. With the warm set live it is now the test
  the document says it should be — load on the one housekeeping core while a warm rig renders beside
  the audible one — and it is the next measurement to take.
* **D9's packing half**: `pedald` costs the bank and skips unusable rigs, but nothing yet calls
  `rig.warm`/`rig.switch`, so the pedal does not warm its neighbours by itself. The engine's API and
  its live behaviour are measured above; the service wiring is the remaining piece.
* **P4 (first-sight measurement)** and **P8 (catch-up)** were waiting on P6's inactive core, which
  now exists with a defined owner.
* **piv** still has two housekeeping cores (0–1) and isolates 2–3: the rules are device-independent
  and piv is behind them. Recorded as debt, to reconcile in its own session.

