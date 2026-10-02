# Multi-core rendering for namchain / namchaind

**Written:** 2026-10-02. This is the plan for namchain's **M4** (optional parallel rendering),
which its own `plan.md` §12 has carried since the start as "off by default, admitted only if soak
and glitch tests pass". It exists because the pedal's heaviest rig cannot run in real time on one
core: the two-amp Ambient Wash fails the gate on vip by itself at q64.

**Where the work happens (decided 2026-10-02).** Development *and* testing happen on **piv**
(Raspberry Pi 500, BCM2712, 4 × Cortex-A76), reached over ssh. vip stays free for the separate
hardware-pedal work. piv already isolates cores 2–3 and runs the SSL 2+, so the two-core
experiment needs no new kernel work — only the audio IRQ moved off core 2.

**The vendored NAM core is `rikkus/OptimisationWorkOnNeuralAmpModelerCore@all-optimisations`**
(`d0339874`), which carries both the planar kernels (the `apple-silicon-a2-planar` work) and the
IR optimisations (the `ir-optimisation` work). This supersedes namchain's current
`sdatkinson` submodule + `0001-a2-planar-neon-kernels.patch` arrangement, and it supersedes
`namchain/AGENTS.md`'s "`nc.cab.ir` convolves with `nam::Linear`; the fork is deprecated" note.

---

## Goal and success criteria

Make the number of cores `namchaind` renders on **configurable**, with today's single-core
behaviour remaining the default and remaining **bit-identical** when parallelism is off.

- Single-core runs remain bit-identical (`max|diff| = 0` against the reference interpreter and
  `namchain-render`), and the default config stays `render_threads: 1`.
- The config knob is honoured end-to-end: namchain's config, the device's tuning and the kernel's
  isolation all describe the same set of cores, and the engine reports the cores it actually got.
- **Withdrawn (2026-10-02, Phase A):** "the two-amp Ambient Wash passes the soak gate with multi-core
  where it fails single-core". The re-baseline found the rig does not fail single-core on a quiet box,
  and that its two amps are in series on one chain, so no form of parallel rendering can help it. See
  [Phase A](#phase-a--re-baseline--done-2026-10-02-and-it-changed-the-plan). The criterion that
  replaces it is the honest one: **multi-core must demonstrably help a document with more than one
  chain's worth of work, must not measurably hurt anything, and must be reported with what it does not
  help**.

---

## Data-reliability caveat

The vip tests of 2026-10-02 that produced the failing gates — the two-amp steady FAIL and the
`bench-results/2026-10-02-two-amp-tail-vip` memory findings — ran while **heavy processing was
already running on vip**. They are **not reliable** and are re-measured on piv before any of them
is used to justify a decision. Every vip-specific number below is a **hypothesis to re-verify**,
not an established fact. The architecture argument (two × ~450 KiB models against one 512 KiB L2)
stands on its own; its supporting measurements are re-established fresh.

---

## Strategy: the three axes, and which one ships

### Axis 1 — chain-level parallelism (ship this first; low risk, bit-identical)

A document is up to `kMaxChains = 8` independent chains (`daemon.h` L169), each a separate
`PlanSlot` + arena, each with its own transition state (`ChainRuntime`). Assign each chain to a
pinned worker core; the coordinator (the existing render thread) keeps all I/O, the crossfade mix
and the bus sum. Each chain still executes on **exactly one thread in its original node order**,
so the output is **bit-identical** to today — only *which* thread runs a chain changes, and chains
never share a buffer. This is what the debt register already anticipated ("Two chains on two
isolated cores") and what `devices/*/tune.conf` reserves core 2 for.

**The decisive insight — cache partitioning, not CPU throughput.** The two-amp rig's problem is
that two A2-Full (~450 KiB each) **do not fit one core's 512 KiB L2**, so each block streams
through the shared L3/DRAM. Run them on **two different cores** and each amp's working set fits
**its own private L2**. The residual limit is the shared L3 and DRAM. The `all-optimisations` IR
changes the cab half of that working set (a partitioned-FFT cab reads less per block than
`nam::Linear`), which is why the re-baseline is against the new core.

### Axis 2 — within-chain (node-DAG) parallelism (defer; measure before building)

Split one chain's topological order into "parallel sections" (nodes with no data dependency, e.g.
two parallel amps under an `nc.split`, mixed by an `nc.mix`). This is the *only* way to
parallelise a single chain with parallel branches. Riskier:

- The compiler's liveness/colour memory plan reuses buffers across the whole graph
  (`plan.cpp` L724–780); concurrent sections must never share a buffer, so the colouring must be
  **partitioned per parallel section**.
- Block-delay (feedback) nodes and `nc.input` sampling timing depend on a precise topological
  order (`plan.cpp` L246–285); parallelism must preserve "block-delay runs first".
- Reordering may change float summation order in `nc.mix`, so bit-identity degrades to a
  **tolerance** test (the partitioned-FFT precedent: 136–138 dB).

**Amdahl applies to both axes.** Post-amp serial tails (feedback delay, reverb, final mix) still
run on one core. If the target rig's amps are **in series**, neither axis helps the same block —
only across-block pipelining would (and it adds a block of latency, so it is not recommended);
the answer there is admission control / Lite.

### Axis 3 — sample-level splitting of a single node (reject)

Splitting one A2-Full's channels across cores would worsen cache behaviour: a ~450 KiB working set
is already near one core's L2, so splitting thrashes two L2s. The kernels are already NEON
optimised. Rejected, recorded so it is not re-derived.

### Synchronisation model

- **Coordinator** = the existing render thread, `SCHED_FIFO` 80 on the first core: capture read,
  command drain, per-chain input decode, dispatch, crossfade mix, bus sum, encode, write.
- **Workers** = one pinned `SCHED_FIFO` thread per extra core, each owning a static subset of
  chains (chain `c` → worker `c mod N`), blocked on a per-worker SPSC "go" word; the coordinator
  publishes input pointer + frame count, the worker executes, then flips a per-block completion
  flag. No allocation, lock or syscall on any render thread; every worker stack and buffer is
  pre-faulted before the clock (`namchain/plan.md` §3.3).
- **Ownership is unchanged.** Only the coordinator mutates `ChainRuntime` transition state;
  workers only `execute()` immutable plan pointers. The `failed_`/`guard_trips` atomics stay atomic
  and single-chain-owned. This is what keeps §3.3's invariants intact.

---

## Shielding from non-audio cores

### CPU isolation (must scale with N)

`isolcpus=managed_irq,domain,… nohz_full=… rcu_nocbs=… irqaffinity=0-1` plus cpuset confinement.
The places that describe the reserved set must all agree — the repo already warns about this in
`devices/vip/rootfs/etc/pedal/tune.conf`:

1. Kernel command line (rtpi `devices/<host>/device.env`, `AUDIO_TUNING_ARGS`).
2. `devices/<host>/rootfs/etc/pedal/tune.conf` — `ISOLATED_CPUS`, `RT_CPUS`.
3. `system.slice.d` / `user.slice.d` drop-ins — `AllowedCPUs` on the complement.
4. `pedal-rt.slice` — `AllowedCPUs`, the only cpuset that may reach the render cores.
5. `namchaind.service.d/10-pedal.conf` — `CPUAffinity=0-1` for the control thread (must stay, or
   the unit's own `SCHED_FIFO` puts the compiling control thread on a render core).

`pedal-tune check` is extended to verify **N** isolated, tickless render cores.

### Interrupt placement

On **piv** the audio IRQ is the SSL 2+'s xHCI controller, currently core 2 at prio 85. If core 2
becomes a render core, the IRQ moves to a housekeeping core (or a dedicated non-DSP core). That is
a benchmark arm, not a default. vip's WM8960 DMA IRQ decision is a later, separate step.

### Memory (the binding constraint)

Measured on piv in earlier sessions (`namchain/docs/tuning.md` "The limit nobody expects"):

- Isolation protects cores, not the memory system; housekeeping traffic reaches every render core
  through the shared L3/DRAM.
- **New-page churn, not RSS, is what hurts** — alloc/free/mmap/page-zeroing beside the engine.
- `mlockall(MCL_CURRENT)` already applies; for N cores it must also cover every worker stack and
  buffer, faulted in before the clock.
- **The budget becomes per-core, not per-document.** Today `model_budget_kb` is one core's L2 for
  the whole document. With N render cores the invariant is a **packing** constraint: no single
  chain's models (chain-level) or single parallel section's models (within-chain) may exceed one
  core's L2 budget — a model is never split across cores. This is a real semantic change to
  `apply_model_budget` and `docs/daemon.md`, and the cab's share of it changes under the new IR.

### L3 way-locking via DSU-110 (unverified research; gated, separate track)

The shared L3 lives in the DynamIQ Shared Unit (DSU-110) the Cortex-A76 cluster is built into, and
the DSU has a hardware **way-lock**: whole L3 ways can be locked to a core or small group,
configured via DSU_CFG registers, typically before the cores are released from reset.

Caveats, any of which decides whether it is worth pursuing:

1. **Coarse** — full ways only (a 2 MiB / 10-way L3 ≈ 200 KiB per way).
2. **It does not remove L2-miss traffic** — it reduces eviction by others, not the traffic itself.
3. **Boot-time and board-wide** — an rtpi/boot-path change, not a namchaind knob.
4. **Unverified on BCM2712** — whether DSU_CFG is reachable on this boot path is unknown.

It is a **gated Phase F**, run only after the axis-1 result and only if the mechanism is confirmed
accessible. It is never a dependency of shipping axis-1 multi-core.

---

## Configuration surface

- `namchain` `Config`: add `unsigned render_threads = 1` (`render_threads` / `--render-threads`).
  Keep `cpu` as the **first core**; workers pin to `cpu .. cpu + render_threads - 1`. (Rejected: an
  explicit `cpus` list — the isolated cores are contiguous, so first+count suffices.)
- `rt_priority` applies to the coordinator and every worker.
- `model_budget_kb` becomes **per render core**, subject to the packing constraint above.
- `engine.status` gains `render_threads` and per-core load/affinity, with `apply_scheduling`'s
  read-back discipline so a refused pin is reported rather than assumed.
- `rt::apply_scheduling` gains a multi-core form.

---

## Phases

### Phase 0 — Environment prep, and the `all-optimisations` core — **DONE 2026-10-02**

1. piv up, idle and ssh-reachable. ✔
2. The latest `namchain` on piv (`66f8dda`), transferred as a bundle rather than pushed. ✔
3. Vendored `rikkus/OptimisationWorkOnNeuralAmpModelerCore@all-optimisations` (`d0339874`). The IR
   optimisation is the core's own `NAM/linear.*` — which is exactly what `nc.cab.ir` already uses, so
   no port and no AudioDSPTools resurrection: `Linear`'s `implementation` argument defaults to `Auto`
   (direct to 512 taps, partitioned FFT above). The planar vendor patch was deleted: the branch
   contains it (its `NAM/` portion reverse-applies cleanly), and it no longer applied verbatim only
   because the core's own `tools/CMakeLists.txt` moved upstream.
4. **Gate passed.** namchain `f5c48d1`. Build green; the full suite is **309 cases / 269,229
   assertions**, planar parity **bit-identical** (7 cases, 188 assertions), the cab path passes its
   `-110 dB` direct-convolution tolerance test at 2/512/513/2048/8192 taps and quantum 32/64/37, and
   the soak runs end to end. Evidence: `namchain/bench-results/2026-10-02-phase0-all-optimisations.txt`.

### Phase A — Re-baseline — **DONE 2026-10-02, and it changed the plan**

The re-baseline did what Phase A existed to do: it killed the reason the plan was written.

**Finding 1 — the heavy rig is one series chain, so no form of parallel rendering can help it.**
The Ambient Wash's Guitar chain is

```
in → gain → nc.nam (Ampeg GVT52, A2-Full) → tonestack → nc.nam (Ampeg SVT, A2-Full)
   → tonestack → nc.cab.ir → fx.delay.feedback → out
```

and the document's other chain is `in → gain → out`. So there is **one chain's worth of work**, and the
two amps are **serially dependent** — the second one's input is the first one's output *in the same
block*. Sharing chains over cores would put the whole rig on one core and a gain node on the other
(axis 1 gains nothing); the two amps cannot run at once in a block (axis 2 gains nothing). Only a
one-block pipeline would, and that costs latency, which the plan already declined to pay.

**Finding 2 — the failing numbers that motivated the plan do not reproduce on a quiet box.** The
2026-10-02 vip run that showed the two-amp rig at p99 59–76% and worst 107–144% of the deadline was
taken while that host was busy with other work. The same rig, same library models and IR, re-measured
on a verified-idle piv against the `all-optimisations` core (null backend, paced, q64, 60 s per arm,
`namchain-soak --graph`):

| arm (60 s, q64, null backend) | p50 | p99 | worst | over deadline |
|---|---|---|---|---|
| two-amp rig, core 3, ×3 | 11.5–11.6 | 13.9–16.4 | 24.2–39.1 | **0** |
| two-amp rig, core 2 (with the xHCI IRQ), ×3 | 11.6 | 13.8–18.5 | 22.8–43.0 | **0** |
| two-amp rig, core 0 (housekeeping) | 11.6 | 14.0 | 24.0 | **0** |
| two-amp rig, flat out (`--no-pacing`) | 11.5 | 13.0 | 24.9 | **0** |
| GVT amp alone | 5.1 | 5.6 | 11.2 | 0 |
| SVT amp alone | 5.1 | 5.6 | 10.9 | 0 |
| both amps, no cab and no delay | 10.6 | 12.0 | 24.5 | 0 |
| one amp + cab + delay | 6.0 | 7.5 | 12.8 | 0 |

The two-amp rig has **no headroom problem on a quiet Pi-5-class host**: p99 is a fifth of the
deadline, worst a quarter to two fifths, and nothing goes past it. The earlier figure is withdrawn
from `namchain/docs/daemon.md` where it had been used to justify the model budget's default.

What survives from the earlier work: the *shape* of the cost is still a capacity cliff (one amp p99
5.6%, two 13.9%, not 11.2%), and two A2-Full working sets still do not fit one core's 512 KiB L2. What
does not survive is the magnitude, and with it the plan's stated success criterion ("the two-amp rig
passes with `render_threads: 2` where it fails with `1`") — there is no failure to fix.

**Consequence for the plan.** The engine change (Phase B) was still worth building and was built: a
configurable `render_threads` is a capability the engine was specified to have (its own M4), it is
free when off, and it is the right shape for a document with more than one chain of work. But the
report has to say plainly that it does **not** fix the rig it was proposed for, and that the pedal's
heaviest rig is a single series chain. The measurement of what it does help is Phase D, below.

### Phase B — Engine change (axis 1) — **DONE 2026-10-02**

1. `render_threads` config + CLI. ✔ (`namchain` `69b5b54`)
2. Worker pool: N participants, static chain→participant assignment, SPSC go-signal and per-block
   completion, all stacks pre-faulted, no allocation or lock on any render path. Workers are **born on
   their own core** (`pthread_attr_setaffinity_np`), because a worker that inherits the coordinator's
   single-core mask cannot run to pin itself once the coordinator is `SCHED_FIFO` on that core — a
   deadlock found by running the daemon, fixed, and now impossible by construction.
3. Refactored `render_loop`: the coordinator keeps the device, the input decode, the crossfade mixes,
   the transition bookkeeping, the reclaimer and the output bus; workers execute their chains' plans,
   both plans of a dual-render on the same participant. ✔
4. Default 1 → **bit-identical**, asserted sample by sample in `tests/test_daemon.cpp` (2 chains on
   2 participants; 5 chains on 3; a structural transition under 2). TSan clean. ✔
5. Per-core model budget: two ceilings — one core's for any single chain, one core's per core the
   chains can be spread over for the document (`namchain` `6ca4324`). ✔

### Phase A steps not done, and why

- **The cache-partitioning prototype (A3) is moot for this rig**: with the amps in series there is no
  configuration in which they run at the same time, so "each amp in its own L2" cannot be arranged
  without a pipeline.
- **The serial-tail bound (A4)** is implicit in the table above: the two amps together are ~2.4× one
  amp at the median and ~2.5× at p99, so the chain is essentially all one serial stage.


Axis 2 is built only if Phase A says the heavy rig is a single parallel chain; its own flag, off by
default.

### Phase C — Shielding plumbing — **measured, and nothing needed changing**

piv already isolates cores 2–3, which is the whole render set for `render_threads: 2`, so nothing had
to change on piv to measure it: `pedal-rt.slice` already allows 0–3 and the system/user slices are
already confined to 0–1.

- **The audio IRQ on a render core — measured, and left alone.** The SSL 2+ is card `II` and its
  controller's interrupt (irq 139) is parked on core 2, which renders with `render_threads: 2`. Moving
  it to core 1 changed the worst block from 21.6% to 19.4% — within the noise of a 30 s arm, 0 driver
  xruns either way. So the plan's fear was not borne out at this load and **the configuration stays as
  it is**; the caveat, recorded in the report, is that this was measured with the render at ~7% of the
  deadline.
- **`pedal-tune check` for N cores — still open, and nobody needs it yet.** It verifies cores 2–3 are
  isolated and tickless, which is the right assertion for N = 2. An N > 2 configuration needs the five
  files in §4.1 changed together (kernel command line, `ISOLATED_CPUS`, the two slice drop-ins,
  `pedal-rt.slice`) and the check extended.

### Phase D — Tests, benches, soak — **DONE 2026-10-02**

- **Tests**, all in `namchain` and all passing: bit-identity of 2 threads against 1 (sample by sample),
  a 5-chain document over 3 participants, a structural transition under 2, the pool started from a
  pinned caller, and the two config refusals. **TSan clean**; **RTSan clean** (clang-20,
  `-fsanitize=realtime`). Evidence: `namchain/bench-results/2026-10-02-render-threads-piv.txt`.
- **Benchmarks**: ten arms over five documents, four interference arms with a one-thread control under
  memory pressure, four arms on the **real SSL 2+** (including the audio-IRQ move), and three on the
  loopback card. The headline: two heavy chains p99 15% → 8%; the series rig unchanged; under
  `stress-ng --vm` the one-thread render missed the deadline 4 times a minute where the two-thread
  render did not; the pooled render on the SSL had **0 driver xruns**.
- **The edit-storm soak is done**: the recorded ljoss session replayed for ten minutes per arm, one and
  two threads, both clean — 0 overruns, 0 xruns, 0 guard trips, **0 `local_base_mismatches`**, 166 ramps
  applied and none stale. The two arms match because that session's rig is the single series chain.
- **Still outstanding: thermal.** These arms are 30–60 s; a multi-core hour at temperature, inside the
  enclosure, on vip, is not measured.

### Phase E — Report — **DONE 2026-10-02**

[bench-results/2026-10-02-multi-core-piv.md](../bench-results/2026-10-02-multi-core-piv.md): what to
do, the matrix, the corrected record, the interference result, the live-device arms, the trade-offs,
what went wrong on the way, and the rejected options.

### Phase F (gated) — L3 way-locking — **closed, with the reason recorded**

Not pursued, and now with a reason rather than an absence: nothing measured here shows the render cores
starved of L3. On a quiet host the render is nowhere near the deadline, and under deliberate memory
pressure the two-core configuration *holds* the deadline — the per-core L2 placement that the feature
provides is doing the work that way-locking was imagined to do.

The board's own numbers, read from `/sys` on piv rather than assumed, also shrink the idea: **L2 is
512 KiB, 8-way, private per core; L3 is 2 MiB, 16-way, shared by all four** (`shared_cpu_list=0-3`), so
one locked way is **128 KiB** — around one A2-Lite's working set and well under an A2-Full's 293.8 KiB.
Locking is therefore a coarse instrument against a working set that is several ways wide, and it takes
L3 away from everything else on the board to do it. No interface to it is exposed by the running system
either: there is no partitioning knob under `/sys/devices/system/cpu/*/cache`, and no `resctrl` (which
is x86-only). Anyone reopening this should start by confirming DSU_CFG is writable on the BCM2712 boot
path at all, and should treat "protect L3 residency" as a hypothesis with a measurement attached, not a
fix.


---

## Test and benchmark design

**Correctness, before any performance claim:**

- **Core parity (Phase 0):** planar kernels bit-identical; IR validated by tolerance (state the dB).
- **Single-core bit-identity:** `render_threads: 1` reproduces the serial output exactly.
- **Multi-core determinism:** chain-level parallelism is bit-identical to serial.
- **RT-safety:** `NAMCHAIN_RT_CHECK`/RTSan/TSan and the alloc/pthread interposers extended to the
  **worker threads** — no allocation, lock or syscall on any render thread.
- **Race/single-owner:** transitions plus param ramps stormed while `render_threads > 1`, asserting
  `local_base_mismatches == 0`, 0 guard trips and correct output.

**Benchmark matrix** — on a verified-idle piv, one measurement at a time, balanced arms in one
session, after the post-boot storm. For each `render_threads ∈ {1, 2}` and each rig (one-amp,
two-amp Ambient Wash, the E1 ready-set):

| interference arm | what it proves |
|---|---|
| quiet (verified nothing on 0–1) | the ceiling and the cache-partitioning win |
| `stress-ng --cpu 2` on 0–1 | CPU isolation still holds |
| `stress-ng --vm 1 --vm-bytes 128M` with and without `--vm-keep` | residual L3/DRAM sensitivity; churn vs steady set |

Report per arm: driver xruns, deadline overruns, worst block, blocks ≥ 90%, p50/p99/p99.9,
per-core load, temperature and throttle state, and each worker's achieved affinity (read back).
Also an IRQ-placement arm (audio IRQ on a housekeeping core vs a render core).

**Acceptance gates** (mirroring the Phase 1 step-8 soak):

- One-amp: 0 xruns, overruns, guard trips; worst block ≤ 90%; on **both** `render_threads` values.
- Two-amp: passes with `render_threads: 2` where it fails with `1`.
- The edit-storm replay soak passes with `render_threads: 2`.
- Thermal unchanged with N cores active.
- **M4's own gate: parallel mode passes every test or it stays off.**

---

## Reporting results and trade-offs

**Advice first, evidence second:**

1. **One-paragraph recommendation up front** — a prescriptive default. The reader must not have to
   extract the advice.
2. **The decision rule as a cost rule** — when to use N cores, with the measured thresholds, so
   admission control can apply it without re-deriving numbers.
3. **The gate table** — rows = rig, columns = gate, pass/fail visible at a glance.
4. **Trade-offs per option, explicit** — fewer housekeeping cores, the IRQ core has to move, more
   RAM for worker stacks, the shared-L3 residual, and the extra RT-synchronisation risk.

**Clarity rules:**

- **Provenance on every number**: host, namchain commit, **NAM-core commit/branch**, kernel, RT or
  not, isolated/tickless or not, memory-quiet or loaded, quantum, and **whether the box was verified
  idle**. "A number you cannot rebuild is a number you cannot defend."
- **Ranges, not points**, for memory-sensitive arms (the same `stress-ng` flags have given 0 vs 562
  xruns), with the balanced-arm caveat.
- **Separate advice from evidence.** Advice is prescriptive and carries a default; evidence is
  descriptive and carries its uncertainty.
- **Name the rejected options and why** (series pipelining, sample-level splitting, an explicit
  `cpus` list, and with caveats L3 way-locking).
- **Say what the default is and what changes it.**

Evidence goes in `namchain/bench-results/`, never `/tmp`.

---

## Edge cases and failure modes

- **piv unreachable** — Phase 0 does not start; no work is silently done elsewhere.
- **A worker refused its pin** — reported as "not as requested"; the run does not count as a
  multi-core result.
- **Fewer chains than workers** — idle workers block on their go-signal; no busy-wait (it would
  steal L3/DRAM).
- **A chain transitions while parallel** — both plans on the *same* worker; the coordinator mixes.
- **Device loss/reopen** — the coordinator drives recovery; workers resume on the new stream.
- **`mlockall` refusal** — reported (`memory_not_locked`); not a valid memory-shielding result.
- **Guard trip on a worker** — per-node atomic flags, read by the coordinator off the RT scope;
  re-verified under TSan.
- **`render_threads` > isolated cores, or non-contiguous** — refused at startup, never a partial
  pin.
- **Measurement contamination** — every run records box idleness as part of its own evidence.
- **Core-branch drift** — the vendored core's commit is recorded with every result and pinned in
  `components.lock`.

---

## Definition of done

- Phase 0 gate passes on piv against `all-optimisations`.
- `render_threads` exists in config and CLI, default 1, single-core bit-identical (CI parity gate).
- RTSan/TSan/allocation-interposer clean with `render_threads > 1`.
- The re-baseline and the benchmark matrix are recorded in `namchain/bench-results/`; the two-amp
  rig passes the gate multi-core.
- The edit-storm replay soak passes with parallelism on.
- `pedal-tune check` verifies the N-core isolation on piv; `components.lock` names the engine, the
  core branch and the device tree.
- The report states a single, actionable default and the measured trade-offs, with provenance.

---

## Assumptions and open questions

- **Operational:** piv is the dev and test host for this work; vip is untouched.
- **Assumption (re-verified):** the two-amp failure and the "two Fulls don't fit one L2" conclusion
  reproduce on a quiet piv with the new core.
- **Assumption:** the heavy rig's two amps are parallel. Phase A verifies; if they are in series,
  the answer is admission control / Lite, stated explicitly rather than claimed as a win.
- **Assumption:** isolated cores remain contiguous, so `cpu` + `render_threads` suffices.
- **Open (Phase 0):** the exact integration surface of the IR optimisation.
- **Open (measured):** audio-IRQ placement once core 2 renders.
- **Open (Phase A data):** whether axis 2 is needed at all.
- **Open (unverified, gated):** DSU-110 L3 way-locking on BCM2712.
- **Dependency order:** core (`all-optimisations`) → engine (namchain) → device config
  (pedal.project) → kernel command line (rtpi); each commit green on its own.
