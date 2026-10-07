# Managing processing power and optimising for fast switching

**Status:** rules and decisions D1–D9 agreed 2026-10-07. Nothing below is implemented yet except
where it says so; the measurements it leans on are E1, E2 and the two-amp work, cited per item. The
one decision a measurement could still reverse is D5 (the audio IRQ's core) — P7 and T6 are how.

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

**D5 — The audio IRQ lives on the housekeeping core** (2026-10-07, to be checked — see P7). It is
the highest-priority realtime thread on the box (SCHED_FIFO 85, above the render thread's 80) and
must always preempt whatever it lands on, so it must not land on a render core. *Evidence:*
`docs/audio-dma-irq.md`; `devices/vip/rootfs/etc/pedal/tune.conf` currently pins its *delivery* to
core 2, which is a render core under these rules. **Open until P7 is run.**

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

```json
{
  "host": "vip",
  "measured": "2026-10-07T15:00:00Z",
  "engine_commit": "c0e3f37",
  "kernel": "7.0.0-1017-raspi-realtime-numaemu1-trimmed",
  "quantum": 64,
  "deadline_us": 1333.3,
  "headroom": 0.8,
  "bar": "p99 under the deadline and zero overruns, paced offline, confirmed live",
  "core_percent": {
    "NAM": {
      "A2": { "full": 0.125, "lite": 0.0333 }
    },
    "IR": {
      "8192": 0.0, "4096": 0.0, "2048": 0.0, "1024": 0.0, "512": 0.0
    },
    "node": {
      "nc.gain": 0.0, "nc.eq.biquad": 0.0, "nc.delay": 0.0,
      "nc.mix": 0.0, "nc.split": 0.0, "level_probe": 0.0
    }
  },
  "unknown": {
    "NAM": 0.25, "IR": 0.1, "node": 0.05
  },
  "sources": {
    "NAM.A2.full": { "n": 8, "p99_at_n": 0.891, "p99_at_n_plus_1": 1.129 },
    "NAM.A2.lite": { "n": 30, "p99_at_n": 0.974, "p99_at_n_plus_1": 1.412 }
  }
}
```

* Every unit carries the `n` it came from and what happened one past it, so the cliff is recorded
  with the number rather than folklore.
* IRs are not free and are not one row: E1 measured a cab at roughly half a rig's render cost, and
  the taps matter (an 8192-tap cab reads more per block than a 512-tap one). The `0.0`s above are
  placeholders for P1/P2 to fill in.
* `unknown` is D8: what admission charges for something not yet measured.

## Measuring a Core

For each unit (a `.nam` at a submodel size, an IR at N taps, a node type with a given parameter set):

1. Build a chain of `n` copies of the unit on **one core**, no other work on that core, `namchaind`
   stopped, the host lock held.
2. Render paced to the wall clock at the device's quantum, for long enough to be meaningful (E2 used
   30 s; the cliff shows within that).
3. Record p50, p99, p99.9, max, blocks over the deadline, and (for warm work) the worst lag.
4. `n` is the largest count with p99 < deadline and zero overruns. Bisect: start at 1, double until
   it fails, then narrow. **Record `n+1` and `n+2` as well** — the cliff's shape is part of the
   measurement, not a by-product (E2's Full curve: 6.6%, 13.9%, 30.4%, 56.7%, 89.1%, 112.9%).
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
   usable rig, and if there is none the press does nothing.
3. **An edit that pushes the live rig over budget is refused at publish**, with the reason reported
   (the engine already refuses a publish over its model budget). The player must not be able to wedge
   themselves by editing the rig they are hearing.
4. **Pack the warm set** (D4): fill the inactive cores' 0.8 with the rigs one interaction away — the
   footswitch neighbours and any rig MIDI can jump to — dearest first, and prefer that rigs inside the
   *bank* are warm over rigs outside it. Whatever does not fit is left for catch-up.
5. **Switch**: the incoming rig's core becomes the active one; the outgoing rig stays warm where it
   is; the warm set slides and the newly-adjacent rig is loaded and warmed. No rig migrates between
   cores, and nothing is loaded, parsed or allocated on a render thread.
6. **Catch-up** where warmth is not available: replay recent input into the target (Lite first, in the
   background, then Full), staged by chain depth. Measured: 170 ms of replay per model is
   bit-exact at depths 1–4, and on vip it costs 9.8 ms (depth 1), 29.4 (2), 58.8 (3), 98.2 (4) at low
   priority; a Lite catch-up is roughly a third of that. The catch-up runs on an inactive core, never
   on the active one.
7. **The transition needs headroom of its own**: during a Lite→Full handover both run, so the switch
   window costs about 1.2× the rig. This is what the 0.8 is for.

## Plan

Ordered, so each item is useful on its own. Repos: **nc** = `namchain`, **pp** = `pedal.project`,
**lj** = `ljoss`, **rt** = `rtpi`.

**P1 — the measurement bench (nc).** A `measure` mode for `namchain-warm-bench`: bisect a unit to
`n`, print the curve, and emit the table's JSON fragment. Reuse what is already there — the mode
already builds N candidate rigs on a chosen core, paces the render thread, and reports p50/p99/max,
overruns and lag. *Deliverable:* `tools/warm/namchain-warm-bench.cpp`, a new mode.
*Verification:* reproduce E2's 8 Full and 30 Lite within ±1 on vip, and E1's 5 model+cab rigs on piv.

**P2 — the table and its plumbing (pp, nc).** `devices/<host>/cost.json`, a schema in
`devices/common`, the same file installed on the pedal where the engine reads it.
*Verification:* `devices/<host>/check` fails if the file is missing, malformed, or measured against a
different engine commit than the one installed; `pedal-device status` prints it.

**P3 — cost model, admission and trimming in the engine (nc).** Replace the single
`model_budget_kb` with the table's per-unit costs; refuse a publish over 0.8; report the cost, the
verdict and what was trimmed (`model_slimmed` already exists; add the cost to `engine.status`).
*Verification:* the boundary tests (T4) and the service tests.

**P4 — first-sight measurement (nc).** Unknown units cost `unknown` (D8) and are measured
opportunistically on an inactive core; the result is written to the table and reported.
*Verification:* install a model the table has never seen, play, and watch the cost resolve without a
single xrun (T5).

**P5 — the bank's verdicts and the pedal's mapping (pp, lj).** `pedald` costs every rig, packs the
warm set, and skips unusable rigs when stepping; ljoss shows the indicator and refuses to activate
one. *Verification:* `devices/common/test-pedald` for the skip logic (it already tests the mapping),
plus a manual pass in ljoss with one rig deliberately made too big.

**P6 — the warm set and role rotation in the engine (nc).** namchain M3: several documents resident
and rendering at once, one of them audible, the rest warm; a switch rotates which is audible and
crossfades. Start with exactly one warm rig (two documents), then N packed by cost. This is the
biggest item and M3 is already on the plan's critical path. *Verification:* T7, T8, and the switch
latency at the jack.

**P7 — move the audio IRQ to the housekeeping core (rt, pp).** `AUDIO_IRQ_CPU=0` in
`devices/vip/rootfs/etc/pedal/tune.conf`, with the other four places that describe the reserved set
updated to agree (cmdline, slice drop-ins, `pedal-rt.slice`, `namchaind.service`'s `CPUAffinity`),
and `pedal-tune check` extended to assert it. Then measure, because this is the one change that could
make things *worse*: the IRQ's own wake-to-completion tail, the render tail, and the footswitch path
while WiFi and the SD card are busy (T6). **This is the arm `docs/multi-core.md` deferred for vip.**
*Verification:* the measurements, plus a decision recorded either way.

**P8 — catch-up, end to end (nc).** Lite-first catch-up on an inactive core, staged by depth, with
the measured 170 ms per model; the path must be exercised by a real switch, not only by the bench.
*Verification:* T9 and the convergence numbers re-measured through the live engine.

**P9 — the level probes as a table row (nc, pp).** The meter costs render-core time and is not free
(publishing per period already recovered 55% of it). Either it appears as a per-node row in the table
or it is excluded from rigs that must fit — decide with a measurement, not by assumption.

## Test plan: where the edges and the cliffs are

Each test names what it pushes past the limit. The point is to find the edge *before* a player does,
and to record the shape of the failure rather than a pass/fail.

**T1 — the cliff, per unit.** For each unit, run n−2 … n+4 and record p50/p99/max/overruns/lag.
*Expected:* not linear. E2's Full: 89% at 8, 113% at 10, and at 12 the warm thread 2,621 blocks
behind and never catching up — the failure is not graceful, which is why D3 leaves 20%.
*Recorded as:* the `sources` block in the table.

**T2 — does the cost model predict? (the make-or-break test.)** 12–20 heterogeneous rigs — mixed
Full/Lite, mixed IR lengths, effects-heavy, one rig of each known adversary — costed from the table
alone, then measured. *Falsifier:* any rig predicted ≤ 0.8 that misses the deadline. If that happens,
the additive model needs a term the table does not have (the working-set sum against L2 is the
obvious candidate: two A2-Full's ~450 KB ring buffers already exceed a 512 KB L2), and the fix is
either a per-class interaction term or more headroom — decided by the size of the error.

**T3 — the known adversaries, re-measured clean.** The two-amp ambient wash (the vip numbers are
flagged unreliable in `docs/multi-core.md` because they ran under load — re-measure under the host
lock first), a 16-model rig, N × 8192-tap IRs, and an effects-only rig (which today's table would
score as nearly free). *Expected:* the two-amp rig is one chain and will be refused unless trimmed to
Lite; the effects-only rig exposes P9.

**T4 — the boundary.** Rigs costed at 0.79, 0.81 and 1.00: the first must publish, the second must be
refused, the third must trim. Then the same three *while switching*, because the transition window
costs ~1.2× — the rig that fits at rest may not fit mid-handover.

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

* **P7 (the IRQ's core)** is the one decision here that a measurement could reverse.
* **The bank's size.** These rules cover the current bank and anything MIDI can jump to; the 16 × 16
  case (E2) is 240 instances and fits no scheme in this document — that is a separate decision about
  what the pedal promises.
