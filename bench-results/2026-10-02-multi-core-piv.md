# Multi-core rendering: what it does, what it does not, and what to do about it

**Report, 2026-10-02.** The plan is [docs/multi-core.md](../docs/multi-core.md); this is what
executing it found. Every number here was taken on **piv** (Raspberry Pi 500, BCM2712, 4 × Cortex-A76,
kernel `7.0.0-1017-raspi-realtime`, cores 2–3 isolated and tickless), with the host otherwise idle,
against namchain `cf7aa84` and NAM core `rikkus/OptimisationWorkOnNeuralAmpModelerCore@all-optimisations`
(`d0339874`).

---

## What to do

**Leave `render_threads` at 1, the default, and turn it on per document — not per pedal.** Set
`render_threads: 2` (with `cpu: 2`, so the render set is cores 2 and 3) when a document has **more than
one chain carrying real work**: two amps on separate chains, a dual-mono rig, a guitar and a bass. That
roughly **halves the per-block load** — measured at p50 11% → 6% and p99 15% → 8% for two A2-Full + cab
chains — and, more importantly, it **halves the exposure to memory pressure from the rest of the
system**: under the same `stress-ng --vm` load the one-thread render missed the deadline four times a
minute where the two-thread render did not.

**Do not expect it to help a one-chain rig, and the pedal's heaviest rig is one chain.** The Ambient
Wash's two amps are **in series on a single chain** (`in → gain → amp₁ → tone → amp₂ → tone → cab →
delay → out`), so there is one chain's worth of work and the second amp cannot start before the first
has finished. Rendering it on two cores measures the same as rendering it on one (p99 13% → 14%), and
the second core is idle. For that rig the lever is the model budget — slim the second amp, or refuse
the document — or a one-block pipeline, which costs latency and is not recommended.

**Do not turn it on to fix a rig that is failing.** On a quiet host the rig that motivated this work
does not fail: it sits at p99 ~14% of the deadline. The failure it was proposed to fix was measured on
a busy host, and the number is withdrawn below.

---

## What was measured

`namchaind`, null backend (paced, so the numbers are real-time; input silent, which the earlier
two-amp work found indistinguishable from played audio), q64, 60 s per arm, `engine.status` read at
the end, one arm at a time, nothing else running. Percentiles come from the daemon's own per-block
load histogram, so they carry its 1% bucket resolution.

| document | `render_threads` | cores | p50 | p99 | worst | over deadline |
|---|---|---|---|---|---|---|
| **two heavy chains** (A2-Full + cab, one per channel) | 1 | 3 | 11% | 15% | 37.8% | 0 |
| | **2** | **2,3** | **6%** | **8%** | 23.1% | 0 |
| one heavy chain | 1 | 3 | 5% | 7% | 13.0% | 0 |
| | 2 | 2,3 | 5% | 7% | 16.8% | 0 |
| **four chains** (A2-Full, no cab) | 1 | 3 | 22% | 25% | 74.5% | 0 |
| | **2** | **2,3** | **11%** | **15%** | 39.0% | 0 |
| **Ambient Wash** (two amps in series + cab + delay + vocal chain) | 1 | 3 | 11% | 13% | 26.4% | 0 |
| | 2 | 2,3 | 11% | 14% | 34.2% | 0 |
| the serial guitar chain alone | 1 | 3 | 11% | 13% | 35.9% | 0 |
| | 2 | 2,3 | 11% | 14% | 31.5% | 0 |

Every arm: **0 driver xruns, 0 deadline overruns, 0 guard trips**, `mlockall` granted, every
participant `SCHED_FIFO` 80, and the cores each participant got **read back from the kernel** (the
`render_cores` bitmask) rather than taken from the configuration.

**Reading it.** Where there are chains to share, the load roughly halves — that is the whole feature,
and it works. Where there is one chain, the two arms are the same to within the bucket resolution,
and the differences in the worst block (13.0% vs 16.8%, 26.4% vs 34.2%) are single blocks in a 45,000
block run, not a signal. Nothing anywhere got worse in a way that matters, which is what makes the
default-off position safe.

---

## The record this corrects

`bench-results/2026-10-02-two-amp-tail-vip` reported the two-amp rig at **p99 59–76%** and a **worst
block of 107–144%** of the deadline, and that figure was used to choose the model budget's default and
to justify this work. That run was taken while **vip was busy with other processing**; the same rig,
same library models and IR, re-measured on a verified-idle piv:

| arm (60 s, q64, null backend) | p50 | p99 | worst | over deadline |
|---|---|---|---|---|
| two-amp rig, core 3, three runs | 11.5–11.6% | 13.9–16.4% | 24.2–39.1% | 0 |
| two-amp rig, core 2 (which carries the xHCI interrupt), three runs | 11.6% | 13.8–18.5% | 22.8–43.0% | 0 |
| two-amp rig, core 0 (a housekeeping core) | 11.6% | 14.0% | 24.0% | 0 |
| two-amp rig, flat out (`--no-pacing`) | 11.5% | 13.0% | 24.9% | 0 |
| GVT amp alone | 5.1% | 5.6% | 11.2% | 0 |
| SVT amp alone | 5.1% | 5.6% | 10.9% | 0 |

The rig has no headroom problem on this class of host. What survives is the **shape**: one amp is p99
5.6% and two are 13.9%, which is the capacity cliff of two working sets larger than one core's L2 —
just not a cliff that reaches the deadline. The withdrawn figure has been removed from
`namchain/docs/daemon.md` where it was load-bearing.

**Why this matters beyond one number:** the earlier run was not marked as taken on a busy host. The
lesson is in the report format below — a measurement now carries whether its host was verified idle,
because a number without that is a number that cannot be defended.

---

## Interference on the housekeeping cores

The loads go on cores 0–1; the render runs on cores 2–3 (two participants) or core 3 (one). Two heavy
chains, 60 s per arm, one arm at a time in a single session.

| load on cores 0–1 | `render_threads` | p50 | p99 | worst | over 90% | **over deadline** |
|---|---|---|---|---|---|---|
| none | 2 | 6% | 8% | 23.1% | 0 | 0 |
| `stress-ng --cpu 2` | 2 | 6% | 9% | 22.6% | 0 | 0 |
| `stress-ng --vm 1 --vm-bytes 128M` (churn) | 2 | 10% | 37% | 52.2% | 0 | 0 |
| `stress-ng --vm 1 --vm-bytes 128M --vm-keep` | 2 | 9% | 37% | 53.6% | 0 | 0 |
| `stress-ng --vm 1 --vm-bytes 128M --vm-keep` | **1** | 14% | **64%** | **119.6%** | 13 | **4** |

**Pure CPU load on the housekeeping cores is free** (6%/8% → 6%/9%), which is the isolation doing its
job. **Memory pressure is not free — and this is where two cores earn their place.** Under identical
pressure, the one-thread render misses the deadline four times in a minute and spends thirteen blocks
over 90%; the two-thread render does neither, with a p99 of 37% against 64%. The mechanism is the one
the plan predicted: a chain rendered on its own core keeps its working set in **its own private L2**,
so it is not competing for the shared L3 and DRAM that the stress load is saturating. Two chains on
one core are two working sets through one cache; two chains on two cores are one each.

Two caveats, both of which matter:

- **The magnitudes are not reproducible; the ordering is.** `namchain/docs/tuning.md` records the same
  memory-load flags giving 0 xruns at one time and 562 at another, 3.5 h apart. This is one balanced
  session. What it supports is "two participants tolerate memory pressure better than one", not
  "p99 is 37%".
- **The `dd` arm produced no status and is missing** (the arm failed to report, twice). It is not
  counted either way.

---

## Against a real device

The SSL 2+ is card `II` on piv, and its controller's interrupt is irq 139 — which the device tree
parks on **core 2**, a core that renders when `render_threads: 2`. These arms use the pedal's own
interface settings (8 capture channels, 6 playback, period 64, 6 periods, the 4/2 output queue), 30 s
each.

| arm | `render_threads` | cores | audio IRQ | p50 | p99 | worst | over deadline | driver xruns |
|---|---|---|---|---|---|---|---|---|
| two heavy chains (control) | 1 | 3 | core 2 | 13% | 16% | 39.2% | 0 | 0 |
| two heavy chains | 2 | 2,3 | **core 2 (a render core)** | 7% | 9% | 21.6% | 0 | 0 |
| two heavy chains | 2 | 2,3 | **core 1 (housekeeping)** | 7% | 9% | 19.4% | 0 | 0 |
| Ambient Wash (series chain) | 2 | 2,3 | core 2 | 12% | 15% | 31.9% | 0 | 0 |

Three things this settles:

- **The pooled render works on the pedal's own interface**, with **0 driver xruns** — better than the
  loopback card managed — and each run rendered exactly the blocks its wall time allows (22,547–22,603
  in 30 s), so the SSL was pacing them.
- **The two-chain gain holds on real hardware**: 13%/16% → 7%/9%.
- **The audio-IRQ question is answered, and the answer is "leave it".** Moving the SSL's interrupt off
  a render core changed the worst block from 21.6% to 19.4% — within the noise of a 30 s arm, with zero
  overruns either way. At this load the interrupt on a render core costs nothing measurable. The
  caveat is the load: this was measured with the render at ~7% of the deadline, and a rig pressed
  against the deadline would be the place to look again.

The kernel's **loopback** card was used before the SSL was known to be attached. It is kept here only
for the one thing it adds — a device measurement of the *series* rig with two threads — and because
the xrun it shows is instructive:

| document | `render_threads` | p50 | p99 | worst | over deadline | driver xruns |
|---|---|---|---|---|---|---|
| two heavy chains | 1 | 12% | 16% | 33.2% | 0 | 1 |
| two heavy chains | 2 | 6% | 9% | 25.0% | 0 | 1 |
| Ambient Wash (series chain) | 2 | 11% | 14% | 31.5% | 0 | 1 |

Its single driver xrun appears in **every** arm including the single-threaded control, so it belongs to
that card, not to the pool; the SSL, in the table above, shows none.

---

## The edit-storm soak

The recorded ljoss session (4 structural rebuilds and 150 ramped knob patches in the window replayed),
replayed by namchain's own `namchain-session-replay` against `namchaind` for 10 minutes per arm, one
arm per `render_threads` value.

| `render_threads` | blocks | p50 | p99 | worst | over deadline | xruns | guard trips | `local_base_mismatches` | requests answered |
|---|---|---|---|---|---|---|---|---|---|
| 1 | 451,737 | 5% | 11% | 36.2% | 0 | 0 | 0 | 0 | 1,358, none refused |
| 2 | 451,733 | 6% | 11% | 37.3% | 0 | 0 | 0 | 0 | 1,358, none refused |

Both arms: **0 overruns, 0 xruns, 0 guard trips, 0 `local_base_mismatches`** (the counter that would
move if two participants ever touched one chain's state), 166 parameter ramps applied and none stale,
5 transitions started. `rig.apply` answered in p50 17 ms / max 19.7 ms, `rig.patch` in p50 0.19 ms, and
the replay itself kept up (send lag p50 1.0 ms, 0 unanswered).

This is the acceptance the engine's own M4 asks for — transitions and edits under a parallel render —
and the two arms are the same to within the histogram's 1% bucket. The soak does not exercise the
*two-chain gain*: this session's rig is the single serial chain, which is exactly the rig parallelism
cannot help, and that is why its two arms match.



---

## Trade-offs, stated plainly

- **It costs a core.** On a four-core Pi, `render_threads: 2` leaves two cores for the kernel, WiFi,
  the control thread (which compiles and prewarms a rig in ~20 ms on a switch) and the pedal service.
  That is a real cost paid for a document that has the chains to use it, and it is why the default
  stays 1 rather than being raised per pedal.
- **It creates no memory bandwidth.** The L3 and DRAM are shared by every core; parallel rendering
  moves work, not bytes. The interference section above is the measurement of what that means.
- **It is more machinery on the render path.** A block-synchronous barrier is, in namchain's own
  words, the largest reliability risk in the design. Here it is bounded by: a chain still being
  executed by one thread in its original order, a bit-identity test that compares two threads against
  one sample by sample, TSan on the pool, and a single-owner rule for everything except the plans.
  The first version of it deadlocked on the daemon (see below) and no unit test could have caught
  that, which is the honest measure of the risk.
- **Thermal is not measured here.** These arms are 30–60 s. A multi-core thermal soak (an hour, inside
  the enclosure, on vip later) is outstanding.
- **The audio IRQ is left where it is, on evidence.** With `render_threads: 2`, core 2 renders *and*
  carries the SSL's interrupt. Moving it to a housekeeping core changed the worst block from 21.6% to
  19.4% — noise — with zero overruns either way, so the configuration need not change. That is measured
  with the render at ~7% of the deadline; a rig pressed against the deadline is the place to revisit it.

## What went wrong on the way

The pool's first version started its workers **after** the render thread had pinned itself to one core.
A thread inherits its creator's affinity mask, so each worker was born confined to the coordinator's
core — and the coordinator, `SCHED_FIFO` 80, was spinning there waiting for the worker to report
itself. The daemon hung at startup with `render_threads: 2` and rendered no block at all. The unit
tests could not see it: they run with `rt_priority: 0`, so the coordinator never becomes `SCHED_FIFO`
and never starves anything. It was found by running the daemon, and fixed by giving each worker its
affinity at creation (`pthread_attr_setaffinity_np`), with the render thread now starting the pool
before it promotes itself as well. A second defect in the same code path — the start record freed by
the creating scope as well as by the worker — would have been a double free on the second worker.

## Rejected, and why

- **Splitting a chain across cores (node-level parallelism).** The rigs that need help most are series
  chains, where there is nothing to overlap; for the rest it would mean partitioning the compiler's
  buffer colouring per parallel section and accepting a tolerance test instead of bit-identity. Not
  built: nothing measured here asks for it.
- **A one-block pipeline** (stage A on block *n*, stage B on block *n−1*). The only way to parallelise
  a series chain, and it adds a block of latency (1.33 ms at q64) to a path whose whole design is
  zero-latency nodes. Declined in the plan and still declined.
- **Splitting one model's work across cores.** A model's ~450 KiB working set is already near one
  core's L2; splitting it would thrash two L2s. Rejected on the arithmetic, not measured.
- **L3 way-locking (DSU-110).** Left as a gated, unverified research track. It remains plausible for
  protecting the render cores' L3 residency under memory pressure, and it is untouched here: nothing
  measured so far says the render cores are L3-starved on a quiet host.
