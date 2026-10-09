# Managing processing power and optimising for fast switching

**Status:** rules and decisions D1–D9 agreed 2026-10-07, **amended 2026-10-09** (the core rules and
D5). **Implemented and measured**, item by item below: P1, P2, P3, P5, P6, P7 and P9 are done;
**P4 and P8 are not**, and both were waiting on P6's inactive core, which now exists with a defined
owner. vip's cost table was measured 2026-10-08
([bench-results/2026-10-08-cost-table-vip](bench-results/2026-10-08-cost-table-vip/README.md): 14 rows,
E2 reproduced, T2 not falsified over 16 rigs), and the core rules, T6, P6 and T10's second hour are
measured in
[bench-results/2026-10-09-core-rules-vip](bench-results/2026-10-09-core-rules-vip/README.md). T1, T2,
T3 (three of its four), T6 and T10 have been run — T10 twice, the second time on the amended rules
with the warm set live and a warm document rendering beside the audible one for the whole hour (gate
PASS: 0 xruns, 0 overruns, worst block 78.4%); T4's three paths are unit tests; T8's falsifier and
T7's live half are measured (8 switches, 0 xruns, warm lag ≤ 1 block) while T7's offline harness runs
but does not yet give a trustworthy verdict (see that document, §4); T5, T9 and T11 have not been
run. The measurements it leans on are E1, E2 and the two-amp work, cited per item.

The goal is a Core device that plays quite large rigs **and** switches between rigs one press away
in under 50 ms (D10). Those two goals compete for the same resource — a warm rig costs CPU that a
big active rig cannot have — and the rules below settle the competition in favour of switching.

## Rules

* **Measure every Core device before using it.** A device's numbers are measured, not assumed, and
  stored with it. New models, IRs and node types are added to the measurements as they are seen for
  the first time.
* **A rig renders on one core, all of its chains.** Rigs are atomic. A rig that does not fit one
  core is trimmed (Full → Lite), and if it still does not fit it is refused and skipped over.
* **All but one core is a render core** (amended 2026-10-09). Every core but the housekeeping one
  exists to render: exactly one of them at a time is the *active* render core, playing the rig the
  player is hearing, and the rest are *inactive render cores* — keeping other rigs warm, or running
  a catch-up.
* **The non-render core handles everything except interrupts**: `pedald`, the engine's control side,
  the service's compiles, the OS, WiFi, the SD card, backups.
* **The audio interrupt is delivered to a render core** (amended 2026-10-09), one designated for it
  and never the active one. It is the highest-priority realtime thread on the box (SCHED_FIFO 85,
  above the render thread's 80) and always preempts whatever it lands on; on the active core that
  preemption is a missed deadline, on an inactive one it is a warm rig falling a block behind, which
  is what warm work is for. It also keeps the interrupt's own tail off the one core that has to
  carry everything else.
* **The interrupt's core never becomes the active render core.** A rig warm there becomes audible by
  handing its execution to the active core, not by that core becoming active.
* **Warm rigs are packed by cost into the inactive cores**, not assigned one rig per core: a core
  holds as many warm rigs as its budget allows.
* **Catch-up is a real path, not an afterthought.** Where a rig cannot be kept warm, switching to it
  is a catch-up (replay of recent input into a cold instance), which is allowed to take longer than a
  warm switch, and is measured.

### Example: a 4-core device

Measured (illustrative values):

```json
{
  "core_percent": {
    "NAM": { "A2": { "full": 0.5, "lite": 0.2 } },
    "IR":  { "8192": 0.4, "4096": 0.2, "2048": 0.1, "1024": 0.05, "512": 0.025 }
  }
}
```

* **Rig 1:** 5 × A2-Lite, nothing else → 5 × 0.2 = 1.0. Fits exactly, cannot be trimmed (already Lite).
* Rig 2, 3, 4: the same.

```
Core 0: housekeeping — pedald, control, WiFi, the SD card, the OS
Core 1: render — takes the audio interrupt; warm rigs only, never the audible one
Core 2: render — warm rigs, packed by cost
Core 3: ACTIVE — the rig being heard; no interrupt is delivered here
```

With Rig 2 active on core 3 and Rigs 1 and 3 adjacent, cores 1 and 2 hold Rigs 1 and 3 warm. Press
"next" and the incoming rig's execution hands over to the active core, whose rig becomes warm on the
core the incoming one leaves; the newly-adjacent rig (Rig 4) is loaded and warmed on an inactive
core. What makes the switch fast is that the incoming rig was already rendering and its state is
current — no load, no parse, no allocation on a render thread — not that a particular core stays with
a particular rig. A rig's *execution* may move cores; a rig's *state* is never rebuilt.

For comparison, vip's real measured numbers (E2, 2026-10-06) are **8 A2-Full or 30 A2-Lite per core**
without cabs, so `full: 0.125`, `lite: 0.033`; E1 measured **5 rigs per core** when each rig is a
model plus an 8192-tap cab, which is what the IR rows are for.

## Decision records

**D1 — Rigs are atomic; chains are not split across cores (2026-10-07).** A chain cannot be split
across cores without a block of latency, so the chain is the hard unit; making the rig the *policy*
unit is stricter and simpler, and it keeps a whole core free for warmth instead of spending two on
one rig. Multi-core rendering (namchain M4) stays in the engine, off, and the policy does not use it.
*Ruled out:* spreading one rig over several cores; `render_threads > 1` in the shipped
configuration. *Evidence:* `docs/multi-core.md` Axis 1/2, and the fact that the heaviest rig measured
(`bench-results/2026-10-02-two-amp-tail-vip/two-amp.json`) is **one chain with two NAM models in
series**, which no form of parallel rendering can help.

**D2 — Cost is measured per unit, per device, by bisection, and stored** (2026-10-07). For each
unit — a NAM model at a given submodel size, an IR at a given tap count, a node type — the cost is
`1/n`, where `n` is the largest number of that unit that renders on one core with no block over the
deadline (procedure below). Costs add. *Evidence:* vip: 8 Full, 30 Lite (E2); piv: 5 model+cab rigs
(E1). *Note:* 1/n measured at the fit point already includes the cache crowding that makes the
eighth model dearer than the first (measured: first Full 6.6% of a quantum, eighth 11.1%).

**D3 — Admission leaves 20% headroom: a rig fits if its cost ≤ 0.8** (2026-10-07). The fit point is
a cliff, not a plateau — vip: 8 Full at 89% of a quantum, 10 at 113%, 12 with the warm thread 2,621
blocks (3.5 s) behind and never recovering — and the transition itself briefly runs two rigs
(Lite and Full during a handover). *Ruled out:* admitting a rig that scores exactly 1.0.
**And a failsafe, because the charge is a measurement** (2026-10-09). The engine watches the render
load's own histogram: if a window of blocks has *any* block over the deadline — D7's own bar — or a
twentieth of them past 95% of it, the warm set is cooled and no new warm is accepted for ten seconds —
`warm_pressure`, with `pressure_cools` and `pressure_holding` in `engine.status.warm`. The cost of
being wrong is the right way round: a press costs a cold switch instead of the audible rig missing
deadlines. This is the half of "charge the coexistence" that covers a table measured on one board
being asked about another, a rig nobody measured, and material nobody played.

**Charged since 2026-10-09 (T5), instead of a smaller headroom.** The rows are measured on a quiet
core and a rig does not get one while a warm document renders beside it, so the table now carries what
that costs and the rig is admitted for the way it will run: `coexistence.factors` maps warm documents
held to a multiplier on the audible rig's cost (vip: 1.25 for one, 1.4 for two), trimming targets
`headroom / factor`, `over` is decided on `cost * factor`, and `rig.warm` is refused when the rig that
is playing could not afford another warm document beside it. A table with no such block charges nothing
and admits exactly as it always did. The factors come from T5's sweep: with nothing warm 0.735 holds the
deadline; with one warm document 0.559 holds and 0.685 breaks; with two, 0.559 holds and 0.685 breaks
fifty times worse. T5 below has the arms, and the runtime failsafe -- cool the warm set when the audible
core's own blocks approach the deadline -- is what covers the cases the pre-calculation gets wrong.

**D4 — Warm rigs are packed by cost into the inactive cores, up to the same 0.8** (2026-10-07;
scoped 2026-10-09). One rig per core wastes the resource the whole scheme exists to protect: a core
holds ~8 Full or ~30 Lite *models* warm, i.e. several rigs' worth. **What ships is the rigs a
footswitch reaches next, one per inactive core**: `rig.warm` and the packing rule are built to take
more than one per core, but filling the core is optimisation and is left until after the pedal is
gig-ready (2026-10-09). *Ruled out:* one warm rig per core as a **limit**; and, for now, warming the
whole bank.

**D5 — The audio IRQ lives on a render core that is never the active one** (2026-10-07; **reversed
2026-10-09**). It is the highest-priority realtime thread on the box (SCHED_FIFO 85, above the render
thread's 80) and always preempts whatever it lands on, so the question is only *where that costs
least*. An **inactive** render core is the answer: the only thing it can preempt there is a warm rig,
which falls a block behind and catches up, and it keeps the interrupt's ~2% of a core and its
wake-to-completion tail off the one core that carries `pedald`, the control side, WiFi and the SD
card. Its *delivery* therefore goes to **core 1** on vip — a render core, and never the active one
(core 3) — with `AUDIO_IRQ_CPU="1"` and `AUDIO_IRQ_PRIO="85"` in
`devices/vip/rootfs/etc/pedal/tune.conf`, and `pedal-tune check` asserting that its core is *inside*
`ISOLATED_CPUS` and is *not* `RT_CPUS`. *Evidence:* `docs/audio-dma-irq.md`; T6 measured both
placements and found no difference to the interrupt or to the render (7.4 ns wait-to-run on a render
core against 7.7 ns on the housekeeping core, identical render distributions, zero xruns either arm)
— so the interrupt is not what decides this and the core layout is; and piv has run this shape since
2026-09-25, its SSL 2+ interrupt pinned to isolated core 2 while the engine renders on core 3.
*Ruled out:* the IRQ on the active core; and the IRQ on the housekeeping core, which is what P7
chose and what this reverses. **Measured live 2026-10-09**: with a warm document rendering on core 1
beside it, the warm rig's lag was 0 or 1 block (1.33 ms) across eight switches with 0 dropped blocks,
so the preemption the rule sends there is visible exactly where it costs nothing. *Caveat that stands:* only the interrupt's **delivery** can be pinned.
Its handler thread carries `0-3` on this kernel (`PF_NO_SETAFFINITY`), it is observed on core 1, and
`isolcpus=domain` rather than the mask is what keeps it off the other render cores — so `pedal-tune
check` reports the thread's actual core and fails if it is ever seen on the active one.

**D6 — Trimming is Full → Lite, applied only as far as it needs to be, and it is visible**
(2026-10-07). Lite and Full are two separately trained networks, measured 9 to 40 dB apart (E2), so a
trimmed rig is a different-sounding rig. It is the capacity tool, but the player must be able to see
that a rig is playing trimmed (the engine already reports `model_slimmed`; ljoss must show it).
**Sharpened 2026-10-09 by the owner's listening verdict** (`bench-results/2026-10-06-e2-listening`):
a Lite standing in for a Full, crossfaded with E2's compensated shape, is *not audible* on the six
models the test used — so the rule's teeth are its **visibility**, not its sound. That is what makes
P8's Lite-first catch-up acceptable, and it is why a temporary Lite must be *shown*: the difference
is real in the networks even where it is not audible in the room.

**D7 — One bar for "fits"** (2026-10-07): every block within the deadline, zero overruns, on a
paced offline run, confirmed by a live soak with the device's `xruns` at zero. A looser bar for warm
work (E1: a candidate running a block or two late does no harm) is a possible later refinement and
would need its own table; it is not assumed now.

**D8 — An unmeasured unit is treated as expensive, never as free** (2026-10-07). A model or node seen
for the first time is assigned a conservative class default until it is measured, so admission can
never wave something through on the grounds that nobody had measured it.

**D9 — Ownership: the engine measures and enforces; the service packs; the app displays**
(2026-10-07, agreed). namchain owns the cost table, the per-document fit check and the refusal
(it is the thing that renders, and it already owns `model_budget_kb` and `model_slimmed`). `pedald`
owns the bank, so it owns the warm-set packing and the skip-when-stepping behaviour. ljoss shows the
indicator and refuses to make an unusable rig active.

The boundary, because "own the cost table" could be read two ways: **namchain owns what a unit is and
what a cost means** — the row types, the bar, the headroom, how a rig's cost is summed, and the fit
verdict. **The measured values are per-device configuration** and live in that device's tree
(`devices/<host>/cost.json`, P2), produced by namchain's own bench (P1) and versioned with the engine
commit and the kernel they were measured against. The format is the engine's; the numbers are the
device's; there is one of each.

*Why it matters:* without this said, both ends grow a cost model.

## The cost table

One file per Core device, in that device's tree, so it is configuration as code and it is versioned
with the kernel and engine commits it was measured against.

The implemented format is `devices/common/cost.schema.json`; vip's own table is
`devices/vip/rootfs/etc/namchain/cost.json` (and `devices/vip/cost.json` is a symlink to it, the path
this document names), installed at `/etc/namchain/cost.json`. Its shape, with vip's measured numbers:

```json
{
  "host": "vip",
  "measured": "2026-10-08T09:22:07Z",
  "engine_commit": "becd0f2",
  "kernel": "7.0.0-1017-raspi-realtime-numaemu1-trimmed",
  "rate": 48000,
  "quantum": 64,
  "deadline_us": 1333.333,
  "headroom": 0.8,
  "bar": "p99 under the deadline, overruns recorded, paced offline; the live soak confirms zero xruns",
  "core_percent": {
    "NAM": {
      "WaveNet": { "full": 0.111, "lite": 0.0333 }
    },
    "IR": {
      "8192": 0.0222, "4096": 0.0222, "2048": 0.01, "1024": 0.00781, "512": 0.00781
    },
    "node": {
      "nc.input": 0.00781, "nc.output": 0.00781, "nc.gain": 0.00781,
      "nc.eq.biquad": 0.00781, "nc.delay": 0.00781, "nc.mix": 0.00781, "nc.split": 0.00781
    }
  },
  "unknown": {
    "NAM": 0.25, "IR": 0.1, "node": 0.05
  },
  "sources": {
    "NAM.WaveNet.full": {
      "n": 9, "p99_at_n": 0.974, "overruns_at_n": 153,
      "p99_at_n_plus_1": 1.109, "overruns_at_n_plus_1": 1185, "blocks_behind_at_n_plus_1": 1
    }
  }
}
```

* Every unit carries the `n` it came from and what happened one past it, so the cliff is recorded
  with the number rather than folklore. A row whose bisection stopped at the bench's own ceiling
  carries `at_most: true` and a `why`, and is an upper bound rather than a cliff — vip's node rows and
  its two shortest IR rows are all of that kind, because no node type reaches a whole core at 128
  copies.
* **The unit keys are the engine's** (D9): a NAM row is keyed by the architecture the file declares —
  `NAM.<family>.<full|lite>` — and for a `SlimmableContainer`, which is a wrapper and not a network,
  by its submodels' architecture. Vip's library is all containers of WaveNets, so it has one NAM row;
  this document's earlier `NAM.A2` was the pedal's name for that family, which no file says.
* IRs are not free and are not one row: an IR is charged the cheapest row that is not shorter than it,
  so a 6000-tap cab pays the 8192 row. Measured on vip a cab is **a fifth** of a Full model
  (0.0222 against 0.111), not the half E1 guessed from a rig's cost on piv.
* `unknown` is D8: what admission charges for something not yet measured, and `cost-check` fails a
  table whose `unknown` is cheaper than any measured row of its kind.

## Measuring a Core

`namchain-warm-bench measure` is the procedure below, and `scripts/measure-core` runs it for a device:
it builds the bench in the image's container, takes the host lock, stops `namchaind`, measures each
unit detached (a dropped ssh must not take an hour of measurements with it), and writes one JSON
fragment per unit, which `devices/common/cost-merge` folds into the table and `cost-check` validates.

For each unit (a `.nam` at a submodel size, an IR at N taps, a node type with a given parameter set):

1. Build a chain of `n` copies of the unit on **one core**, no other work on that core, `namchaind`
   stopped, the host lock held.
2. Render paced to the wall clock at the device's quantum, for long enough to be meaningful (E2 used
   30 s; the cliff shows within that).
3. Record p50, p99, p99.9, max, blocks over the deadline, and (for warm work) the worst lag.
4. `n` is the largest count with **p99 < deadline**. Bisect: start at 1, double until it fails, then
   narrow. **Record `n+1` and `n+2` as well** — the cliff's shape is part of the measurement, not a
   by-product (E2's Full curve: 6.6%, 13.9%, 30.4%, 56.7%, 89.1%, 112.9%).
   *Amended 2026-10-08, from the measurement.* This read "p99 < deadline **and zero overruns**", and
   D7 said the same. Measured, the overrun count at the fit point is not monotone in `n`: one Lite
   model on vip's core 2 overran twice at n = 22, never at 23, three times at 24 and never again at
   25, while p99 climbed smoothly through 64.5, 67.5, 72.7 and 76.4 per cent over the same four
   points. A bar that one late block in 22,500 decides is a bar the environment decides, and it moved
   the answer by three when nothing about the unit changed. So the bisection fits on p99, and the
   overruns, the max and the worst lag are recorded as the curve's shape
   (`namchain-warm-bench measure --bar strict` asks for D7's reading and prints both). D7's "every
   block within the deadline, zero overruns" is what the **live soak** (T10) confirms.
5. Store the fraction `1/n` with its provenance.

Three things this procedure has to get right, all of which have bitten:

* **The core matters.** The housekeeping core and the audio-IRQ core are not equivalent to a clean
  render core. Measure on the core the unit will actually run on, and say which (E1/E2 both noted
  core 2 runs harsher than core 3).
* **The offline bar is a proxy.** A paced offline run has no ALSA, no queue, no IRQ. The table is
  built offline and **validated live**: the same rig played through the device for an hour with
  `xruns` at zero (T10).
* **Measure the mixture, not just the units.** The additive model is an assumption (T2 tests it, and
  P3's first-sight measurement is what keeps it honest).

**First-sight measurement (D8).** When a unit appears that is not in the table, it is measured
opportunistically: on an inactive core, at low priority, and never on the active render core while
the player is playing. Until then it costs the `unknown` value. If the warm cores are full, the
measurement waits — an unmeasured unit is a candidate for refusal, which is the safe direction.

## Runtime

1. **Cost every rig in the bank** from the table (sum of its units). Cache it; recompute when the rig
   or the table changes.
2. **Admit the active rig** if its cost ≤ 0.8 (D3). If not, trim Full → Lite on as few NAM nodes as
   it takes, largest first, and re-check. If it still does not fit, mark the rig unusable: ljoss shows
   it (editable, not selectable), and the pedal's mapping skips it — pressing "next" lands on the next
   usable rig, and if there is none the press does nothing. **Implemented** (P3 in the engine, P5 in
   the service and the app): the refusal is `over_budget` with the total and every node's row, the
   service asks `rig.cost` for each rig in the bank, and ljoss marks a rig it will not publish.
3. **An edit that pushes the live rig over budget is refused at publish**, with the reason reported
   (the engine already refuses a publish over its model budget). The player must not be able to wedge
   themselves by editing the rig they are hearing.
4. **Pack the warm set** (D4): fill the inactive cores' 0.8 with the rigs one interaction away — the
   footswitch neighbours and any rig MIDI can jump to — dearest first, and prefer that rigs inside the
   *bank* are warm over rigs outside it. Whatever does not fit is left for catch-up. **Not
   implemented** (P6).
5. **Switch**: the incoming rig's core becomes the active one; the outgoing rig stays warm where it
   is; the warm set slides and the newly-adjacent rig is loaded and warmed. No rig migrates between
   cores, and nothing is loaded, parsed or allocated on a render thread. **Not implemented** (P6): a
   switch today is a publish, which compiles the incoming rig and crossfades to it.
6. **Catch-up** where warmth is not available: replay recent input into the target (Lite first, in the
   background, then Full), staged by chain depth. Measured: 170 ms of replay per model is
   bit-exact at depths 1–4, and on vip it costs 9.8 ms (depth 1), 29.4 (2), 58.8 (3), 98.2 (4) at low
   priority; a Lite catch-up is roughly a third of that. The catch-up runs on an inactive core, never
   on the active one.
7. **The transition needs headroom of its own**: during a Lite→Full handover both run, so the switch
   window costs about 1.2× the rig. This is what the 0.8 is for. **The 0.8 is in force** (the table's
   `headroom`, applied by the engine); the handover it pays for is P6's and P8's.

## Plan

Ordered, so each item is useful on its own. Repos: **nc** = `namchain`, **pp** = `pedal.project`,
**lj** = `ljoss`, **rt** = `rtpi`.

**P1 — the measurement bench (nc). DONE 2026-10-08.** A `measure` mode for `namchain-warm-bench`: bisect a unit to
`n`, print the curve, and emit the table's JSON fragment. Reuse what is already there — the mode
already builds N candidate rigs on a chosen core, paces the render thread, and reports p50/p99/max,
overruns and lag. *Deliverable:* `tools/warm/namchain-warm-bench.cpp`, a new mode.
*Verification:* reproduce E2's 8 Full and 30 Lite within ±1 on vip, and E1's 5 model+cab rigs on piv.
**Measured: 9 Full and 30 Lite** on vip (the p99 bar D2 step 4 now names), and the E1 shape is the
`rig` mode's one-model-plus-cab rig rather than a piv run: piv is a version behind and was not
disturbed. See [bench-results/2026-10-08-cost-table-vip](bench-results/2026-10-08-cost-table-vip/README.md).

**P2 — the table and its plumbing (pp, nc). DONE 2026-10-08.** `devices/<host>/cost.json`, a schema in
`devices/common`, the same file installed on the pedal where the engine reads it.
*Verification:* `devices/<host>/check` fails if the file is missing, malformed, or measured against a
different engine commit than the one installed; `pedal-device status` prints it.
**Both do**, through `devices/common/cost-check` (the schema plus the invariants a JSON schema cannot
state: every row's provenance, the cost is 1/n, n+1 missed, `unknown` never cheaper than a measured
row, the deadline is quantum/rate). The table lives at `devices/<host>/rootfs/etc/namchain/cost.json`,
so the rootfs install and the file hashes cover it, with `devices/<host>/cost.json` a symlink to it so
the path this document names resolves.

**P3 — cost model, admission and trimming in the engine (nc). DONE 2026-10-08.** Replace the single
`model_budget_kb` with the table's per-unit costs; refuse a publish over 0.8; report the cost, the
verdict and what was trimmed (`model_slimmed` already exists; add the cost to `engine.status`).
*Verification:* the boundary tests (T4) and the service tests.
**Done**: `model_budget_kb` is gone, `cost_table` is read at startup and on SIGHUP, every node is
charged, the dearest models are trimmed Full -> Lite, a client's publish over the headroom is refused
as `over_budget` with the total and every node's row, and `engine.status.cost` carries the cost, the
verdict and the nodes. A new `rig.cost` answers the same question for a rig that is not playing, which
is how the service costs its bank without a second cost model (D9). The boundary itself is T4 below.

**P4 — first-sight measurement (nc). HALF IMPLEMENTED; design settled 2026-10-09.** Unknown units cost
`unknown` (D8) and are measured opportunistically on an inactive core; the result is written to the
table and reported. *Verification:* install a model the table has never seen, play, and watch the cost
resolve without a single xrun (T5).

**In place:** D8's half — an unmeasured unit is charged `unknown`, never nothing, at the dearest value
of its kind, and every node charged that way raises a `cost_unknown` warning naming it and the row it
should have; **the worklist** — `pedald` aggregates those warnings into `/status`'s
`engine.needs_measuring` (one entry per *row*, deduplicated, with a count and one reference to hand the
bench); and **the measurer** — `pedal-measure`, a root oneshot beside `pedal-diag`
(`devices/common/rootfs/usr/local/sbin/pedal-measure`, `pedal-measure.service`), which reads the
worklist, refuses when the pedal is unhappy, runs the deployed bench for one row on a core the player
is not using inside `pedal-bench.slice`, and writes the fragment to
`/var/lib/pedal/cost-fragments/<row>.json`. Twelve tests cover the decision (which row, and when to
refuse); the measurement itself is the bench's, and namchain tests that.

**Settled design for the rest:**

- **The service *says*, the measurer *measures* — and they are different processes** (checked on the
  board, 2026-10-09). `pedald` is `User=pedal`, `CPUAffinity=0`, in `system.slice`, whose cpuset is the
  housekeeping core: it **cannot** pin a bench to an inactive core (the affinity call fails, as it does
  from an ssh session) and it has no privilege to enter `pedal-bench.slice` (which is exactly the slice
  that exists to allow those cores). So the measurement is its own root oneshot — `pedal-measure`,
  beside `pedal-diag` — triggered by a timer: it reads `/status` for `needs_measuring`, checks the
  pedal is happy, runs the deployed bench for one row
  (`namchain-warm-bench measure --units <one line> --input <DI> --seconds N --out DIR`, the invocation
  `scripts/measure-core` already uses) inside `pedal-bench.slice` on a core the player is not using,
  and writes the fragment. D9's boundary holds and is sharpened: the engine measures and enforces, the
  service knows and says, a root oneshot does the privileged part, and the *operator* merges.
- **The result is a fragment, not a table.** The bench prints a `fragment:` line; the service writes it
  to `/var/lib/pedal/cost-fragments/<row>.json` and reports it, and `devices/common/cost-merge` folds
  fragments into the device's table as it already does. The engine cannot write the table — a device's
  numbers are the device's, and `devices/<host>/check` hashes the installed file — so a pedal that
  measured its own row still waits for the operator to accept it. That is deliberate: an unattended
  measurement that rewrote admission would be a machine grading its own homework.
- **Nothing waits for it.** The rig plays at the `unknown` cost meanwhile (D8 charges the dearest
  value of its kind, so admission errs expensive, never permissive), and the measurement only ever
  *frees* capacity.
- **It never runs while the pedal is unhappy**: a measurement is skipped when `xruns` or
  `over_deadline` are non-zero, when the failsafe is holding, or when the audible rig is above the
  charge — a pedal at its limit does not have an inactive core to spare, and T5 is the measurement
  that says so.
- **A row measured with a different signal is not the same row** (found 2026-10-09): the table records
  `bar`, `measured`, `host`, `kernel`, `quantum`, `rate` and its 14 rows, and **not the input it was
  measured with** — the convention (`guitar-di.wav`, which `scripts/measure-core` always uses) lives
  only in the tooling. `pedal-measure` defaults to `/var/lib/pedal/guitar-di.wav` and refuses to run
  without an input, which encodes the convention but does not enforce it. What would: an `input` block
  in the table (name, size, hash) with the measurer checking it before it writes a fragment, so a
  measurement taken with a different signal cannot be merged into a table it does not belong to.
- **What has to be built**: that `input` block and the check, the DI on the device
  (`/var/lib/pedal/guitar-di.wav` — not shipped in the rootfs at 8 MB; the tool says so and takes
  `--input`), the apply that installs the oneshot, the operator's merge step
  (`devices/common/cost-merge`), and T5's verification path: install a model the table has never seen,
  play, run `pedal-measure`, merge the fragment, and watch the row resolve with no xrun.

**P5 — the bank's verdicts and the pedal's mapping (pp, lj). DONE 2026-10-08; the warm half landed
2026-10-09.** `pedald` costs every rig and skips unusable ones when stepping;
ljoss shows the indicator and refuses to activate one. *Verification:* `devices/common/test-pedald`
for the skip logic (it already tests the mapping), plus a manual pass in ljoss with one rig
deliberately made too big.
**Both**: `pedald` asks the engine's `rig.cost` for every rig in the bank (at most two rigs per poll,
re-asked at most once a minute), skips an unusable rig when stepping, refuses to load one, and reports
the verdicts in `/status`; ljoss shows a "Lite: <blocks>" chip while the running rig is trimmed (D6),
refuses to publish a rig the engine would refuse, and marks it too big for the device while keeping it
editable. 244 pedald tests and 507 ljoss assertions, both green. **The warm half (2026-10-09)**: the
service holds the rig the footswitches reach next warm in the engine — `rig.warm` when the neighbour
changes, `rig.cool` with no rig when nothing is one press away, and `rig.switch` on every press, which
hands a warm rig over and publishes a cold one, so a press never ends in silence — and `/status`
carries the engine's own `warm` object rather than a summary of it. 272 pedald tests, green
(`WarmSet` and the switch path in `test_daemon.py`, `Mapping.neighbour` in `test_mapping.py`, the three
calls in `test_engine.py`). **One rig**, as D4 was scoped: packing more of the bank into the inactive
cores is optimisation, and a jump outside the neighbours is P8's catch-up.
`docs/pedal-service.md` ("The ready set, and the split with namchain") is the design.

**P6 — the warm set in the engine (nc).** namchain M3: more than one document resident and rendering
at once, one of them audible, the rest warm; a switch makes a warm rig audible and crossfades to it.
*Verification:* T7, T8, and the switch latency at the jack. **IMPLEMENTED AND ON THE PEDAL
2026-10-09** (engine `a0a9cf0`, `warm_cpus [1, 2]`, `warm_priority 70`, device core 3;
`namchain/docs/warm-set.md` is the engine's design). Measured on vip: eight live switches, each
`handover_blocks: 3` plus the 5 ms fade — about 9 ms from `rig.switch` to fully on the new rig — with
**0 xruns, 0 blocks over the deadline, 0 dropped warm blocks**, and the warm document never more than
one block (1.33 ms) behind while sharing core 1 with the audio IRQ. T7's offline harness runs and
agrees on the load (render p99 8% of the deadline with a warm document beside it, warm lag 0 blocks)
but its glitch verdict is not trusted yet; §4 of the bench-results document says why.
**What is deliberately not here:** D4's packing (several warm rigs per core), P8's catch-up, and more
than two documents — the mechanism generalises and the policy over it is pedald's, which warms the one
rig a press reaches next (P5's warm half, 2026-10-09).

What ships, in order: **one warm document** on an inactive core, rendering the same block the active
one does and publishing its output; then `rig.switch`, which hands the warm rig's *execution* to the
active core at a block boundary and crossfades to it; then the footswitch neighbours, one per
inactive core (D4). A switch to a rig that is not warm **falls back** to today's path — publish,
compile, cold crossfade — rather than refusing, so a press always produces sound. The difference a
warm switch buys is that it does no load, no parse and no allocation on a render thread, which is
what makes it fast and click-free.

The architecture, because namchain has the opposite shape today (one document, one set of plans, the
render thread executing whichever document was published last): per-**document** render state —
chains, bus, transition state — of which one is owned by the device thread and the others by warm
threads pinned to the inactive cores. Ownership moves by **swapping which document a thread owns**,
not by moving a plan in memory, so a rig's state is never rebuilt. The device core is fixed
(`cpu: 3`): the rules make the interrupt core (1) and the warm core (2) ineligible for the active
role, so a switch is a handover between the device thread and a warm one. A rig's *execution* may
therefore move cores; the withdrawn "no rig migrates" reading of the rules is not a constraint
(2026-10-09). P4's inactive core and P8's catch-up both wait on it.

**P7 — the audio IRQ's core (rt, pp). DONE 2026-10-07; MEASURED 2026-10-08; REVERSED 2026-10-09.**
P7 moved the pin to core 0, a housekeeping core, on the reading that the interrupt must not land on a
render core at all; `pedal-tune check` asserted that, and T6 then measured both placements and found
no difference (D5 above carries the numbers). The reversal is not T6's doing: the rules changed on
2026-10-09 so that all but one core renders, which leaves the interrupt with a render core as its
home and makes the *active* core the one thing it must not touch. What P7 added stays — the pin by
name, the priority, `pedal-interface.json`'s `audio_irq_cpu` (which `pedal-diag` reads), and the
check — and the value moves from 0 to 1, with the assertion flipped from "outside `ISOLATED_CPUS`"
to "inside it, and not `RT_CPUS`". *Verification:* T6 (done), the four layout assertions in
`pedal-tune check` (one housekeeping core; the render set is every other core; the IRQ inside the
render set; the IRQ outside `RT_CPUS`), and a re-run of T6's arms on the new placement.

**P8 — catch-up, end to end (nc). NOT IMPLEMENTED; design settled 2026-10-09.** Lite-first
catch-up on an inactive core, staged by depth, with the measured 170 ms per model; the path must be
exercised by a real switch, not only by the bench. *Verification:* T9 and the convergence numbers
re-measured through the live engine.
**What is in place:** the mechanism is measured (E1/E2: 170 ms of replay per model is bit-exact at
depths 1-4, and a Lite catch-up is about a third of that) and the engine's publish path is where a
catch-up would run. **What is missing:** the tiers and the inactive core.

**The question it was waiting on is answered: the owner listened to the fixed E2 audition set on
2026-10-09 and cannot hear a difference when Lite stands in for a Full** (the verdict is recorded in
`bench-results/2026-10-06-e2-listening/README.md`). So the design is the one E2's numbers pointed at,
and it is now settled in this shape:

- **A cold switch becomes two steps instead of one.** The press publishes the rig's **Lite** document
  first — it compiles in about a third of the time, and (the verdict) a Lite standing in for a Full
  is not something the player hears — and the engine then compiles the **Full** in the background and
  crossfades to it with the compensated fade shape E2 measured. The promise becomes: *sound at the
  press, the rig the player asked for within a second or two*, instead of silence or a wrong-sounding
  first 170 ms.
- **The catch-up is the replay, not the fade.** A cold instance starting mid-note is wrong for the
  length of its receptive field; E1/E2 measured that replaying 170 ms per model into it makes it
  bit-exact at depths 1-4. That is what the background step does before the crossfade, and it is why
  the Lite is audible in the meantime rather than the Full being late.
- **It costs one extra compile and one extra document, both off the audible path.** The Lite is
  compiled and published on the control thread (already the case for any publish), the Full's compile
  happens while the Lite plays, and the crossfade is the ordinary transition machinery. Nothing here
  adds work to the render thread, which is what keeps D2's budget honest.
- **It is visible, because D6 says a trimmed rig is a different rig.** While the Lite is standing in,
  the engine reports it (`model_slimmed` and the cost object's `trimmed`/`verdict`), so ljoss and the
  pedal's own UI can say "coming up to full" rather than pretending the rig is what it will be.
- **What still has to be built**: the two-step publish in namchain (`rig.switch`'s cold path, or a
  flag on it: Lite first, Full behind), the replay that catches the Full up, the service's
  willingness to accept a temporary Lite (it already accepts a switch's `switched: cold` answer), and
  T9 measuring press-to-full-rig through the pedal.

**P9 — the level probes as a table row (nc, pp). DECIDED 2026-10-08, BY MEASUREMENT.** The meter costs render-core time and is not free
(publishing per period already recovered 55% of it). Either it appears as a per-node row in the table
or it is excluded from rigs that must fit — decide with a measurement, not by assumption.
**Measured** (128 biquads, 30 s, vip's core 2): 4.5% of a core with the probes off, **10.3%** in the
device's own configuration (`levels_publish_period`), 20.7% with a sample-per-frame probe published on
read. Publishing per period recovered just under half, as the 2026-10-06 switch found. **Decision: the
probes are part of the rows** -- every node row in vip's table was measured with the shipped
configuration, so a rig that must fit pays for the meter it has. Excluding the probes from rigs that
must fit is ruled out because the pedal ships with the meter on.

## Test plan: where the edges and the cliffs are

Each test names what it pushes past the limit. The point is to find the edge *before* a player does,
and to record the shape of the failure rather than a pass/fail.

**Run so far.** 2026-10-08 ([bench-results/2026-10-08-cost-table-vip](bench-results/2026-10-08-cost-table-vip/README.md)):
T1 (**every unit's curve**), T2 (**16 rigs, nothing falsified**), three of T3's four adversaries, T4's
unit paths, and P9's measurement. 2026-10-09 ([bench-results/2026-10-09-core-rules-vip](bench-results/2026-10-09-core-rules-vip/README.md)):
**T6** on both placements, **T10** twice (the second hour with the warm set live), and **T7's live
half with T8's live falsifier** — eight switches through the engine, 0 xruns, warm lag 0–1 block.
**Not run:** T4's "while switching" half, **T5**, **T7's service half** (a press through `pedald`,
which needs an event path), **T8's press storm**, **T9** (it waits on P8) and **T11**. Each says
where it is described what it waits on, and none is claimed.

**T1 — the cliff, per unit.** For each unit, run n−2 … n+4 and record p50/p99/max/overruns/lag.
*Expected:* not linear. E2's Full: 89% at 8, 113% at 10, and at 12 the warm thread 2,621 blocks
behind and never catching up — the failure is not graceful, which is why D3 leaves 20%.
*Recorded as:* the `sources` block in the table.
**Run 2026-10-08**: every row's whole curve is in `vip-fragments.jsonl` and readable in `curves.txt`.
The expectation holds: vip's Full unit goes 82.2% at 8, 97.4% at 9 (the fit point), 110.9% at 10 and
124.9% at 11, with the lag climbing 1, 1, 1, 779 blocks — and Lite goes 39.7% at 16, 76.4% at 25,
106.4% at 32 with 1,184 blocks over the deadline. What the sweeps also showed is the *overrun* count
at the edge being non-monotone in n (section 1 of the bench note), which is why the fit bar is p99.

**T2 — does the cost model predict? (the make-or-break test.)** 12–20 heterogeneous rigs — mixed
Full/Lite, mixed IR lengths, effects-heavy, one rig of each known adversary — costed from the table
alone, then measured. **Run 2026-10-08, and it did not fire**: sixteen heterogeneous rigs — one and two models, cabs at
four lengths, effects-heavy, effects-only, parallel lanes, three chains at once, eight and sixteen
Lite models in series — costed from the table by the engine's own model and measured on vip's core 2.
Every prediction was above its measurement (1.2x to 1.9x), the heaviest rig measuring 64.1% of the
deadline against 74.8% predicted. *Falsifier:* any rig predicted ≤ 0.8 that misses the deadline. If that happens,
the additive model needs a term the table does not have (the working-set sum against L2 is the
obvious candidate: two A2-Full's ~450 KB ring buffers already exceed a 512 KB L2), and the fix is
either a per-class interaction term or more headroom — decided by the size of the error.

**T3 — the known adversaries, re-measured clean.** The two-amp ambient wash (the vip numbers are
flagged unreliable in `docs/multi-core.md` because they ran under load — re-measure under the host
lock first), a 16-model rig, N × 8192-tap IRs, and an effects-only rig (which today's table would
score as nearly free). *Expected:* the two-amp rig is one chain and will be refused unless trimmed to
Lite; the effects-only rig exposes P9.
**Three of the four run 2026-10-08**, under the host lock with `namchaind` stopped: the two-amp rig
(predicted 0.238, measured p99 13.3% — and *not* refused, because D2's table charges two Fulls at
0.222 where the old L2 budget refused them at 587 KiB), the sixteen-model rig (predicted 0.782,
measured 62.3% — inside, and the rig nearest the fit point of the whole set), and the effects-only rig
(predicted 0.078, measured 0.7%, which is P9's answer and D8's conservatism in one line). **N x
8192-tap IRs has not been run**: the IR rows exist (0.0222 each) but a rig of several 8192-tap cabs
has not been measured.

**T4 — the boundary.** Rigs costed at 0.79, 0.81 and 1.00: the first must publish, the second must be
refused, the third must trim. Then the same three *while switching*, because the transition window
costs ~1.2× — the rig that fits at rest may not fit mid-handover.
**Half run:** the three paths are unit tests in namchain (`tests/test_cost_table.cpp`: a rig under the
headroom is admitted as written; one over it with nothing to trim is `over`; one over it with a
slimmable model is trimmed, dearest first, exactly as far as it takes), plus `tests/test_daemon.cpp`
over a real daemon — the publish, the refusal with the total and the rows in the message, and the
configured rig admitted with a `cost_over` warning. **The "while switching" half has not been run**:
it needs two rigs rendering at once, which is P6's dual render. `namchain-warm-bench rig --reps 2`
measures the cost of two copies of one rig, not a real handover.

**T5 — housekeeping starvation.** `dd` on the housekeeping core, a WiFi upload of models and IRs, an
SD write, all while the active rig renders at 0.8 with the warm cores packed. Since 2026-10-09 that
is **one** core (0) carrying `pedald`, the control side, WiFi and the SD card, with the audio
interrupt moved off it (D5) — so the interrupt is not what this measures any more. *Expected:* this
is where the headroom may prove too thin — the two-amp work measured another core's traffic
*doubling* a rig's median, and isolation protects cores, not the memory system. *Falsifier:* a
compile, an upload or a backup on core 0 moves the render cores' tail, or pushes the active rig over
the deadline. *Recorded as:* the headroom and the mitigation it forces (a lower admission figure, or
the memory discipline: `mlockall` for every worker stack and buffer, no new-page churn beside the
engine). **Run 2026-10-09: the falsifier fired, and it found more than the falsifier.**
`scripts/measure-housekeeping`, four arms on vip (engine `fee0440`), the active rig built for the test
at **0.735** — admitted, `fits`, one model trimmed — with a 0.41 neighbour warm on core 1 in two of
them and nothing warm in the other two, the same load (core 0 at 99%: spinner, 200 MB SD write, a
WiFi upload repeated to the end of the arm, and `namchainctl cost` in a loop as the compile burst):

| 120 s arm | over the deadline | worst block | blocks over 90% |
|---|---|---|---|
| quiet, nothing warm | +0 | 100.7% | +2 |
| **loaded, nothing warm** | **+1** | **107.7%** | **+33** |
| quiet, warm on core 1 | **+7** | 125.0% | +20 |
| **loaded, warm on core 1** | **+61** | **151.8%** | **+947** |

`xruns` 0 and no guard trips anywhere; the warm document itself was never more than 2 blocks behind
and dropped nothing.

**Two findings.** (1) The housekeeping load does move the render tail, and on a rig this close to the
table's limit it breaks the deadline — on a 0.41 rig the first run of the same harness saw 0 overruns
and a worst block of 63%, so the load's cost is bounded and what decides is how near the top of the
table the rig is. (2) **The warm document costs more than the load, and the table does not model it
at all**: the *same rig* with a warm neighbour goes from +0 to +7 overruns quiet and from +1 to +61
loaded, worst block 100.7% → 125.0%. The cost model charges units as if a core were alone with them;
with a warm rig rendering beside it, it is not. `fits` at 0.735 is therefore not a promise that the
rig holds the deadline — D3's headroom, D4's per-core independence and the admission verdict all
assume a quiet core. **The sweep puts the knee at about 0.6** (overruns in the loaded 120 s arm, warm against none):
0.410 → +1 against +0; 0.559 → +1; 0.685 → **+72 against +0**; 0.735 → **+61 against +1**.
**Two warm cores is a second, steeper step** — the same rigs with a *second* renderer on the other warm
core (core 2; the engine holds one warm document today, so the second is the bench's `rig` mode pinned
there, labelled as what it is): 0.410 → +1, 0.559 → +3, 0.685 → **+3543** against +72 for one. The
cliff is in the same place; past it the damage is fifty times worse. **Decided and implemented
2026-10-09: the coexistence is charged** (D3 above) rather than the headroom being lowered — warming is
always on, so a lower headroom would cost capacity even with nothing warm — with vip's measured factors
1.25 (one warm document) and 1.4 (two) written into its table, and the *runtime* failsafe (cool the warm
set when the audible core's own blocks approach the deadline) as the thing that catches what the
pre-calculation gets wrong. **Still open:** the engine holds one warm document, so a pedal with two
footswitch neighbours cannot yet keep both warm — `kMaxDocuments` is 2, and the second warm document is
D4's "one per inactive core" arriving as a real change to the warm set with its own measurement.
[bench-results/2026-10-09-housekeeping-vip](bench-results/2026-10-09-housekeeping-vip/README.md) has
the four arms, the sweep, the caveats and the reproduction.

**T6 — the IRQ arm (D5).** The audio IRQ on a render core (where it lives now, core 1) against the
housekeeping core (what P7 chose, core 0), measuring the IRQ thread's tail, the render tail, and the
footswitch-to-sound latency with WiFi and SD busy. *Falsifier:* if the interrupt's latency degrades
on the core it shares with warm work, or a warm rig's lag grows without bound, D5 is wrong and the
interrupt needs a core nothing else uses — which changes how many cores the rules can spend on
rendering.
**Run 2026-10-08** under the *old* split (four minutes an arm, a CPU spinner on core 0, a 200 MB SD
write and a 200 MB WiFi upload, an amp-and-cab rig through the codec): a render core (2) against a
housekeeping core (0). The render's distribution is identical (54% of blocks at 7% of the deadline,
33% at 8%, 13% at 9%), blocks over 10% came to 1,222 against 886, the IRQ thread's wait to run was
7.4 ns per wake against 7.7, and both arms ended with zero xruns, zero guard trips and no block over
the deadline — **the falsifier did not fire**.
**Run again 2026-10-09** on the amended rules (core 1, a render core that is never the active one,
against core 0, with one housekeeping core and a three-chain rig whose worst block is 58.3% of the
deadline): the render distributions are again identical between arms, zero xruns and zero blocks over
the deadline either way, and the wait to run was **16.8 ns per wake on core 1 against 17.0 ns on core
0**. So the interrupt does not care which core it is on, and the reversal rests on the rules (its home
is a render core) and on where the preemption *lands* — which is P6's warm set, measured at 0–1 block
of lag and 0 dropped blocks. **The footswitch-to-sound leg has still not been measured**: it needs
the Pico in the loop (3.5). Both arms, both runs:
[bench-results/2026-10-09-core-rules-vip](bench-results/2026-10-09-core-rules-vip/README.md), §2.

**T7 — rotation and refill.** Switch repeatedly so that every switch also loads and warms a new
neighbour: the warm set slides while the player plays. *Measured:* the active rig's p99 during
refills, the switch latency distribution, and whether a catch-up on an inactive core ever disturbs
the active one.
**Half run 2026-10-09**: eight live switches on the pedal through the *engine*, each
`handover_blocks: 3` plus a 5 ms fade (~9 ms), zero xruns, zero blocks over the deadline, zero
dropped warm blocks, and the warm document never more than a block behind while sharing core 1 with
the audio IRQ. The service half has since landed: `pedald` holds the neighbour warm (`rig.warm`) and
switches with `rig.switch` (P5, `24349e7`), so the set can slide — but nothing has *driven* a press
through it yet, because pedald has no event path a bench can use (a token-authenticated `POST /event`
is the proposed one, and it would also let ljoss and rigpa step rigs without speaking the engine's
protocol). **Still to measure:** a step through the service, the neighbour changing under it, and the
switch latency distribution over a run of presses. The offline arm (`namchain-warm-bench switch`) runs,
pins correctly and agrees on the load (device p99 107 µs = 8% of the deadline with a warm document
beside it, warm lag 0 blocks). Its glitch verdict is **not** evidence for a cross-rig switch, and
after four harness fixes the reason is measured rather than guessed
([bench-results/2026-10-09-warm-bench-switch](bench-results/2026-10-09-warm-bench-switch/README.md)):
on the *same* rig on both sides the handover is an **exact match** — convergence −1000 dBFS (the
detector's sentinel for no difference at all), dropout 0.00 ms, 14 switches, 0 deferred, no block
over the deadline — and on two *different* rigs the convergence reading is the two rigs' own
difference to four digits (−3.0 dBFS against 0.7076 = −3.0 dBFS), which is the comparison deciding
which rig the output should be, not a hole in the handover. What remains is the arm's own timing: it
does not wait for the outgoing block before mixing (56 of ~70 fade blocks in a 30 s run), so its
continuity and high-frequency numbers are the harness's, and the rules themselves are written for
ramped parameter edits — the engine's own suite expects a hard switch to trip the spectral rule. So:
**the arm's load numbers and the same-rig handover are evidence; a cross-rig verdict from it is not,
and T7's offline half is closed as UNPROVEN for that case, with the reason recorded.**

**T8 — faster than a human.** Ten presses a second, newest wins. *Expected:* bounded work, no queue
growth, no xruns, and the refill backlog visible in `engine.status`. *Falsifier:* a press storm that
leaves the warm set permanently behind.
**The falsifier's live half is measured**: over the eight switches of 2026-10-09 the warm document's
`behind_blocks` was 0 or 1 with 0 dropped, and `warm_behind` never appeared. The press storm itself
has not been run: the service now switches, so a storm is a matter of driving it (T7's event path),
and the engine-level storm — many `rig.switch` calls a second — is the cheaper first cut.

**T9 — cold, from nothing.** The first press after boot, nothing warm, SD card cold: the catch-up
path's worst case, measured to the jack. This is the number that justifies D6 and the catch-up rules
being real.

**T10 — the hour.** The whole scheme for an hour: switching between rigs, refills, warm cores at
0.8, catch-ups, `xruns` at zero, guard trips at zero, temperature and throttle recorded. This is the
only test that validates the offline table against the live device (D7).
**Run 2026-10-08**: sixty minutes on the pedal through the WM8960, switching between four admitted
rigs every 30 seconds (118 loads, 2,864,049 blocks, 120 samples), with **`xruns` at zero in every
sample**, no block over the deadline, the worst at 60.1% of it, 51-55 °C, 2400 MHz, never throttled.
**D7 holds for what the table admits.** What the hour does not cover is the rest of the scheme — the
warm set, the refills and the catch-ups are P6's and P8's — and it switched the way the engine
switches today: by publishing.
**Run again 2026-10-09, on the amended rules and with the warm set live**: 359 samples over 60.0 min,
120 transitions, 2,699,756 blocks, p50 12% / p99 29% / p99.9 42%, worst block 1045.5 µs (78.4%),
57.6–63.7 °C, 2400 MHz and `throttled 0x0` throughout, gate **PASS** (xruns 0, deadline overruns 0,
guard trips 0, blocks over 90% 0, render errors 0, device lost 0). This hour is the acceptance test
for the core rules and for P6 together: one housekeeping core, the audio interrupt on core 1, and a
second document rendering on core 1 beside it for the whole hour. The audio path's p99 is six points
worse than the October 8 hour (29% against 23%, worst 78% against 71%, the board 5 °C warmer) — that
is what a warm rig costs the audible one, and it is a fraction of the headroom D3 reserves.
[bench-results/2026-10-09-core-rules-vip](bench-results/2026-10-09-core-rules-vip/README.md) §5 has
the two hours side by side.

**T11 — thermal and clock.** One hour at full load; confirm 2.4 GHz uncapped holds on vip's cooling
(`tune.conf` says unverified on vip) and that no throttle changes the numbers the table was built
from. If it does, the table needs a temperature caveat.
**Run 2026-10-09/10 — an hour of full load across two halves, and nothing throttled the tail.** A
**0.559** rig (admitted with the coexistence charge in force), a stand-in second renderer on the free
warm core and the app's traffic on WiFi; 30 minutes quiet, then 30 with the housekeeping core at
**100.0%** (spinner, SD reads, a compile burst in a loop):

| half | blocks over the deadline | worst block | temperature | clock / low-voltage alarm |
|---|---|---|---|---|
| quiet | **+0** (9 before, 9 after: the setup transient's single spike) | 215.4% at the transient, flat after | 62.2 → 66.7 °C | 2400 MHz / 0 |
| loaded | **+0** | 90.5% | 64.5 → **80.4 °C** | 2400 MHz / 0 |

So the two things this test exists to check hold: **2400 MHz held for the hour** — the frequency is
read at the end of each half and never moved — and **no throttle changed the numbers**, because the
loaded half put nothing over the deadline while the temperature walked 16 °C up to 80.4 °C (first trip
110 °C). One caveat about the *evidence* rather than the result: this kernel exposes no `/dev/vcio`, so
`vcgencmd get_throttled` cannot be read and "uncapped" rests on the clock register, the temperature and
the render tail rather than on the firmware's own flags; the low-voltage alarm via hwmon
(`rpi_volt in0_lcrit_alarm`, which `pedal-diag` reads) is 0 at both ends. Consequence for the table:
**no temperature caveat is needed** at this rig and this cooling.

What this run does *not* settle, and what is owed: it never had the engine's own warm document
(cpu1 ~0.7% in both halves; both setups printed `no warm document is rendering`, most likely the
failsafe cooling it after the setup transient). The interference was present as the stand-in renderer
on core 2 and the load was fully present, so T5's question is answered; "a warm document rendering" is
not. [bench-results/2026-10-10-t11-fullload](bench-results/2026-10-10-t11-fullload/README.md) has both
halves and the harness mistake that made the loaded half a re-run.

## Not doing, and why

* **Splitting one rig across cores** (D1). It would buy the heaviest rig and cost the cores that keep
  switching fast; the heaviest rig is one chain anyway, so it would buy nothing real.
* **One warm rig per core** (D4). It halves the number of rigs kept warm and therefore the fraction of
  the bank a MIDI jump can reach instantly.
* **A separate bar for warm work** (D7). Simpler to have one, and the strict bar is the safe one.
* **IRs longer than 8192 taps.** Not supported; measured as such rather than left undefined.
* **A second cost model in the service.** D9: the engine owns it.

## Open

* **P7 (the IRQ's core)** is the one decision here that a measurement could reverse. It is decided in
  the tree and **T6 has not been taken**, so nothing yet says the IRQ is happy on the busy housekeeping
  core. That measurement is the next thing this scheme owes.
* **What to keep warm is a guess, and knowingly so.** D4 fills the warm set from what the player can
  reach in one action — the footswitch neighbours, the bank, anything MIDI can map to. Nothing here
  can know what a *pointer* will pick: ljoss puts several rigs on screen and a click is as likely as a
  footswitch press. Making the warm set follow the player instead of guessing is a deliberate piece of
  future work, **after the pedal is gig-ready and not a dependency of it** — the `predict` node in
  [diagrams/plan-dependency-graph.html](diagrams/plan-dependency-graph.html) and the "Tracks off the
  critical path" entry in `plan.md`. It would change which rigs are warm, not how warmth works.
* **The bank's size.** These rules cover the current bank and anything MIDI can jump to; the 16 × 16
  case (E2) is 240 instances and fits no scheme in this document — that is a separate decision about
  what the pedal promises.
