# Managing processing power and optimising for fast switching

**Status:** rules and decisions D1–D9 agreed 2026-10-07. **Implemented and measured 2026-10-08**, item
by item below: P1, P2, P3, P5, P7 and P9 are done, with vip's cost table measured on vip
([bench-results/2026-10-08-cost-table-vip](bench-results/2026-10-08-cost-table-vip/README.md): 14 rows,
E2 reproduced, T2 not falsified over 16 rigs); **P4, P6 and P8 are not** — each says what it waits on,
and P6 is the one the rest of the warm-set scheme depends on. The measurements it leans on are E1, E2
and the two-amp work, cited per item. The one decision a measurement could still reverse is D5 (the
audio IRQ's core) — P7 is in the tree and T6 is the measurement that confirms or reverses it.

The goal is a Core device that plays quite large rigs **and** switches between rigs one press away
in under 50 ms (D10). Those two goals compete for the same resource — a warm rig costs CPU that a
big active rig cannot have — and the rules below settle the competition in favour of switching.

## Rules

* **Measure every Core device before using it.** A device's numbers are measured, not assumed, and
  stored with it. New models, IRs and node types are added to the measurements as they are seen for
  the first time.
* **A rig renders on one core, all of its chains.** Rigs are atomic. A rig that does not fit one
  core is trimmed (Full → Lite), and if it still does not fit it is refused and skipped over.
* **One core is housekeeping**, always: IRQs (highest priority on the box), `pedald`, the engine's
  control side, and everything the OS does.
* **Every other real-time core exists to keep rigs warm.** Exactly one render core at a time is the
  *active* render core, playing the rig the player is hearing. The rest are *inactive render cores*
  — free to keep other rigs warm, or to run a catch-up.
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
Core 0: housekeeping (IRQs, pedald, control)
Core 1: ACTIVE   — the rig being heard
Core 2: inactive — warm rigs, packed by cost
Core 3: inactive — warm rigs, packed by cost
```

With Rig 2 active and Rigs 1 and 3 adjacent, cores 2 and 3 hold Rigs 1 and 3 warm. Press "next" and
the roles rotate: the incoming rig's core becomes the active one, the outgoing rig stays warm, and
the newly-adjacent rig (Rig 4) is loaded and warmed. **No rig ever migrates between cores** — the
only thing that changes on a switch is which core's output is audible.

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

**D4 — Warm rigs are packed by cost into the inactive cores, up to the same 0.8** (2026-10-07). One
rig per core wastes the resource the whole scheme exists to protect: a core holds ~8 Full or ~30 Lite
*models* warm, i.e. several rigs' worth. Packing is what lets the whole bank stay warm (D10 asks for
the current bank plus anything MIDI can jump to), rather than only the two immediate neighbours.
*Ruled out:* one warm rig per core.

**D5 — The audio IRQ lives on the housekeeping core** (2026-10-07, decided in P7 — the pins are in
the tree; T6 is the measurement that confirms or reverses it). It is the highest-priority realtime
thread on the box (SCHED_FIFO 85, above the render thread's 80) and must always preempt whatever it
lands on, so it must not land on a render core. Its *delivery* therefore goes to core 0 — a
housekeeping core that the kernel's own `irqaffinity=0-1` already allows — not to core 2, which is
a render core under these rules. *Evidence:* `docs/audio-dma-irq.md`; `AUDIO_IRQ_CPU="0"` and
`AUDIO_IRQ_PRIO="85"` in `devices/vip/rootfs/etc/pedal/tune.conf`, with `pedal-tune check` failing
if the core it finds is inside `ISOLATED_CPUS`; `pedal-interface.json` (`audio_irq_cpu`), which is
what `pedal-diag` reads to report a wrong placement. *Ruled out:* leaving the pin at core 2.
*Open question the measurement answers:* whether the interrupt's tail survives sharing a core with
WiFi and the SD card — if it does not, D5 is wrong and the IRQ needs a core of its own (T6).

**D6 — Trimming is Full → Lite, applied only as far as it needs to be, and it is visible**
(2026-10-07). Lite and Full are two separately trained networks, measured 9 to 40 dB apart (E2), so a
trimmed rig is a different-sounding rig. It is the capacity tool, but the player must be able to see
that a rig is playing trimmed (the engine already reports `model_slimmed`; ljoss must show it).

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

**P4 — first-sight measurement (nc). NOT IMPLEMENTED.** Unknown units cost `unknown` (D8) and are measured
opportunistically on an inactive core; the result is written to the table and reported.
*Verification:* install a model the table has never seen, play, and watch the cost resolve without a
single xrun (T5).
**What is in place:** D8's half -- an unmeasured unit is charged `unknown`, never nothing, at the
dearest value of its kind, and every node charged that way raises a `cost_unknown` warning naming it
and the row it should have. **What is not:** the measurement itself. It needs a core the player is not
using to bisect on, which is P6's inactive core; without one it would run beside the live render, and
T5 is exactly the test that says how bad that is. The engine also cannot rewrite `cost.json` --
`devices/<host>/check` compares the installed file's hash with the tree's -- so a first-sight
measurement has to land as a fragment the operator merges (`cost-merge`), a deliberate difference from
"written to the table".

**P5 — the bank's verdicts and the pedal's mapping (pp, lj). DONE 2026-10-08.** `pedald` costs every rig, packs the
warm set, and skips unusable rigs when stepping; ljoss shows the indicator and refuses to activate
one. *Verification:* `devices/common/test-pedald` for the skip logic (it already tests the mapping),
plus a manual pass in ljoss with one rig deliberately made too big.
**Both**: `pedald` asks the engine's `rig.cost` for every rig in the bank (at most two rigs per poll,
re-asked at most once a minute), skips an unusable rig when stepping, refuses to load one, and reports
the verdicts in `/status`; ljoss shows a "Lite: <blocks>" chip while the running rig is trimmed (D6),
refuses to publish a rig the engine would refuse, and marks it too big for the device while keeping it
editable. 244 pedald tests and 507 ljoss assertions, both green.

**P6 — the warm set and role rotation in the engine (nc).** namchain M3: several documents resident
and rendering at once, one of them audible, the rest warm; a switch rotates which is audible and
crossfades. Start with exactly one warm rig (two documents), then N packed by cost. This is the
biggest item and M3 is already on the plan's critical path. *Verification:* T7, T8, and the switch
latency at the jack. **NOT IMPLEMENTED, and this is the item everything else warm waits on.**
The rules say no rig migrates between cores: each core renders its own rig, and a switch changes
*which core's output is audible*. namchain has the opposite shape today -- one document, one set of
plans, the render thread executing whichever document was published last, and a publish that compiles
the incoming rig and crossfades to it. A faithful P6 is therefore not an addition to the render path
but a change of it: one render thread per core, each with its own resident document and its own bus
buffer, and the device-owning thread mixing the selected one (one block behind, well inside D10's
50 ms). P4's inactive core and P8's catch-up both wait on it.

**P7 — move the audio IRQ to the housekeeping core (rt, pp). DONE IN THE TREE 2026-10-07; T6 PENDING.**
`AUDIO_IRQ_CPU=0` in
`devices/vip/rootfs/etc/pedal/tune.conf`, with the other four places that describe the reserved set
updated to agree (cmdline, slice drop-ins, `pedal-rt.slice`, `namchaind.service`'s `CPUAffinity`),
and `pedal-tune check` extended to assert it. Those four already agreed on 0-1 for housekeeping and
2-3 for the render set, so the only value that moved is the pin itself: `AUDIO_IRQ_CPU` and its
twin in `pedal-interface.json`, which is what `pedal-diag` reads to notice a wrong placement.
`pedal-tune check` now fails if the IRQ's core is inside `ISOLATED_CPUS` — the one assertion that
makes D5 checkable. **Done in the tree 2026-10-07**; the measurement is what remains, and it is the
one that could make things *worse*: the IRQ's own wake-to-completion tail, the render tail, and the
footswitch path while WiFi and the SD card are busy (T6). **This is the arm `docs/multi-core.md`
deferred for vip**, and that section now carries the decision. *Verification:* the measurements,
plus a decision recorded either way. **The tree is changed and `devices/vip/apply` has not been run**,
so the board is still on the old pin: T6 has not been taken, and the decision above is the tree's, not
a measurement's, until it is.

**P8 — catch-up, end to end (nc). NOT IMPLEMENTED.** Lite-first catch-up on an inactive core, staged by depth, with
the measured 170 ms per model; the path must be exercised by a real switch, not only by the bench.
*Verification:* T9 and the convergence numbers re-measured through the live engine.
**What is in place:** the mechanism is measured (E1/E2: 170 ms of replay per model is bit-exact at
depths 1-4, and a Lite catch-up is about a third of that) and the engine's publish path is where a
catch-up would run. **What is missing:** the tiers and the inactive core. "Lite first, in the
background, then Full" needs a second instance playing while the first catches up, which is P6's
machinery -- and E2 left the question that decides whether that design survives: whether a Lite
standing in for a Full is audible (they are 9 to 40 dB apart, and the listening test is the owner's).

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

**Run so far** (2026-10-08, [bench-results/2026-10-08-cost-table-vip](bench-results/2026-10-08-cost-table-vip/README.md)):
T1 (**every unit's curve**), T2 (**16 rigs, nothing falsified**), three of T3's four adversaries, and
P9's measurement. **Not run:** T4 beyond its unit tests, T5, T6, T7-T11 — each needs either the live
engine's warm set (P6) or a soak on the device, and none is claimed.

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
SD write, all while the active rig renders at 0.8 with the warm cores packed. *Expected:* this is
where the headroom may prove too thin — the two-amp work measured another core's traffic *doubling*
a rig's median, and isolation protects cores, not the memory system. *Recorded as:* the headroom and
the mitigation it forces (a lower admission figure, or the memory discipline: `mlockall` for every
worker stack and buffer, no new-page churn beside the engine).

**T6 — the IRQ arm (P7).** The audio IRQ on the housekeeping core vs on core 2, measuring the IRQ
thread's tail, the render tail, and the footswitch-to-sound latency with WiFi and SD busy.
*Falsifier:* if the IRQ's latency degrades on the busy housekeeping core, D5 is wrong and the IRQ
needs a core of its own — which changes how many cores the rules can spend on rendering.
*Result:* <!-- parent: P7's change is in the tree; fill this in with the result in
`pedal.project/bench-results/` and say what D5 becomes. -->

**T7 — rotation and refill.** Switch repeatedly so that every switch also loads and warms a new
neighbour: the warm set slides while the player plays. *Measured:* the active rig's p99 during
refills, the switch latency distribution, and whether a catch-up on an inactive core ever disturbs
the active one.

**T8 — faster than a human.** Ten presses a second, newest wins. *Expected:* bounded work, no queue
growth, no xruns, and the refill backlog visible in `engine.status`. *Falsifier:* a press storm that
leaves the warm set permanently behind.

**T9 — cold, from nothing.** The first press after boot, nothing warm, SD card cold: the catch-up
path's worst case, measured to the jack. This is the number that justifies D6 and the catch-up rules
being real.

**T10 — the hour.** The whole scheme for an hour: switching between rigs, refills, warm cores at
0.8, catch-ups, `xruns` at zero, guard trips at zero, temperature and throttle recorded. This is the
only test that validates the offline table against the live device (D7).
**Not run, and it is the one that matters most:** nothing here yet says a rig admitted at 0.8 has zero
xruns for an hour on the pedal. The table's bar is an offline p99 (D2 step 4 as amended), so D7's
"zero overruns, confirmed live" is exactly what T10 is for.

**T11 — thermal and clock.** One hour at full load; confirm 2.4 GHz uncapped holds on vip's cooling
(`tune.conf` says unverified on vip) and that no throttle changes the numbers the table was built
from. If it does, the table needs a temperature caveat.

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
