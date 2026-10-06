# What measuring audio levels costs namchaind

**Measured:** 2026-10-06, on **vip** (Raspberry Pi 5, 1 GB, Cortex-A76). Engine `dd8d480`, where
`--levels`, `--levels-rate-hz`, `--levels-first-frame` and `--levels-publish-period` all landed; the
daemon reported it for every run. Parts 1–3 were measured on `5eff47e` and are quoted as they were
taken; Part 4 on `dd8d480`, and its two controls were re-measured on the day so that no comparison
crosses a commit.
**Instrument:** [`poll-levels.py`](poll-levels.py) — a TCP `engine.levels` client, the same shape as
the meter in ljoss. **Campaign:** [`run-campaign.sh`](run-campaign.sh). **Arithmetic:**
[`analyse.py`](analyse.py). **Charts:** [`charts.py`](charts.py). **Raw results:**
[`results.jsonl`](results.jsonl), [`stability.jsonl`](stability.jsonl).

![What each way of measuring costs, parts 1–3](overhead-by-mode-part3.svg)

![What a client polling costs, by rate and by rig](overhead-by-poll-rate.svg)

## Why this was measured

`engine.levels` folds a peak, a sum, a frame count and a clip count into a probe **per sample**, in
the loop the non-finite guard already walks. That is the price of a level meter, and the render
thread pays it whether or not any client is watching.

The question that started this was narrower: the conversion — the square root, the logarithms, the
JSON — happens on the control thread, which is only useful if the control thread is somewhere the
render thread is not. If it shares the audio core, it is eating the headroom the audio work needs.
So this campaign answers three things: **where the conversion runs** (Part 1), **what the switches
cost** (Part 2), and **what changing the sampling and the read rate buys** (Part 3).

## Method

Two rigs, generated ([`make-rig.py`](make-rig.py)) and passed as absolute paths with `--rig` so every
condition ran the same document:

| Series | Rig | What it isolates |
|---|---|---|
| **A** | `input → output` (2 nodes) | The cost of **answering**: the levels JSON is built and sent once per poll. There is almost nothing inside the rig to measure. |
| **B** | 32 × `nc.gain` (34 nodes) | The cost of **measuring**: every node's probe folds a sample. The rig's own cost is one multiply per node, so the probes dominate rather than the audio. |

Series B is a synthetic **upper bound**, not a realistic rig: a rig with an A2 model in it would show
a smaller *share*, because an inference swamps a probe. The real saving for a real rig sits between
the two series.

- **CPU** is the daemon process's own `utime + stime` from `/proc/<pid>/stat`, every thread included,
  read immediately before and after the window. It is the kernel's accounting, not a sampled estimate.
  `CLK_TCK` is 100, so one tick is 10 ms of CPU time; over a 120 s window one tick is 0.83 ms of CPU
  per second of wall clock, which is the resolution every figure below is quoted to.
- **Percentages are a share of one core.** vip has four.
- **Windows** are 120 s, after an 8 s settle once the daemon reported `running`.
- Each run was **gated before it started**: the daemon had to report `running`; `engine.levels` had to
  answer with the rig's expected node count when measuring, and to be **refused** when not; and the
  daemon's own reported mode (`cache.rate_hz`, `cache.first_frame`) had to match what the condition
  asked for. A run that failed a gate wrote an error instead of a number. That gate is not ceremony:
  the first attempt at this campaign measured whatever `pedald seed` had resumed — a different
  document — and nothing in the CPU numbers would have said so.
- **Measuring was on** unless a condition says `off`, so the product default is what is under test.

## Part 1 — where the measurement actually runs

**The conversion does not run on the audio core. The audio core is exclusively the render thread's.**

```
$ ps -L -o tid,psr,cls,rtprio,comm -p $(pgrep -x namchaind)
    TID PSR CLS RTPRIO COMMAND
  14423   1  TS      - namchaind     <- control thread: cores 0,1 (taskset), SCHED_OTHER
  14426   3  FF     80 namchaind     <- render thread: core 3, SCHED_FIFO 80
```

Why it is so, in the code:

- `apply_scheduling` pins **the calling thread** (`sched_setaffinity(0, …)`,
  [scheduling.cpp:103](../../../namchain/src/rt/scheduling.cpp#L103)) — not the process.
- Its only daemon call site is `promote_render_thread`
  ([daemon.cpp:2216](../../../namchain/src/daemon/daemon.cpp#L2216)), called from `render_loop`, which
  runs on the thread created at [daemon.cpp:2044](../../../namchain/src/daemon/daemon.cpp#L2044).
- So `CPUAffinity=0-1` from the device's `10-pedal.conf` stays in force for the control thread, and
  the render thread adds core 3 for itself.
- `engine.levels` → `handle_request` → the level build all run on the control thread — the same thread
  as `Daemon::run()`'s poll loop, created in `main` before the render thread exists.
- What is heavy there: the atomic drain per probe, the square root, the logarithms and the JSON. None
  of it touches core 3.
- With `render_threads = 1` (vip's config) `start_render_pool` returns early and the chains run inline
  on the render thread, so **no worker threads exist at all**.

**The one coupling that remains is not the conversion.** It is the per-sample probe write by the
render thread plus the cache-line traffic between the two cores: reading a probe on core 1 while core
3 writes it moves those lines back and forth. That is what the per-node figures in Part 2 measure, and
it is what Part 3's `--levels-first-frame` attacks. The logarithms cost render headroom nothing.

## Part 2 — results, as a share of one core

### Series A — a minimal rig (2 nodes)

| Condition | Mode | Client polling | CPU (one core) | vs `--no-levels` |
|---|---|---|---|---|
| 1 | `--no-levels` | — | **2.07%** | baseline |
| 2 | measuring (default) | — | **2.52%** | +0.45 pp |
| 3 | measuring (default) | 20 Hz | **2.64%** | +0.58 pp |
| 4 | measuring (default) | 10 Hz | **2.58%** | +0.52 pp |
| 5 | measuring (default) | 5 Hz | **2.54%** | +0.47 pp |
| 6 | measuring (default) | 4 Hz | **2.54%** | +0.47 pp |
| 7 | measuring (default) | 3 Hz | **2.52%** | +0.45 pp |
| 8 | measuring (default) | 2 Hz | **2.52%** | +0.45 pp |
| 9 | measuring (default) | 1 Hz | **2.52%** | +0.45 pp |

### Series B — a 32-gain rig (34 nodes)

| Condition | Mode | Client polling | CPU (one core) | vs `--no-levels` |
|---|---|---|---|---|
| 10 | `--no-levels` | — | **2.24%** | baseline |
| 11 | measuring (default) | — | **5.16%** | +2.92 pp |
| 12 | measuring (default) | 20 Hz | **5.62%** | +3.38 pp |
| 13 | measuring (default) | 10 Hz | **5.33%** | +3.09 pp |
| 14 | measuring (default) | 5 Hz | **5.19%** | +2.95 pp |
| 15 | measuring (default) | 4 Hz | **5.18%** | +2.94 pp |
| 16 | measuring (default) | 3 Hz | **5.21%** | +2.97 pp |
| 17 | measuring (default) | 2 Hz | **5.12%** | +2.88 pp |
| 18 | measuring (default) | 1 Hz | **5.10%** | +2.86 pp |

**What the first two parts say.** With the switch off, a 34-node rig costs 2.24% of one core; with it
on, 5.16% — **measuring more than doubles the engine's cost on a light rig**, because a gain node is
nearly free and its probe is not. Per measured node that is **0.7–1.5 ms/s of one core** (0.07–0.15%),
so roughly 0.6–1.2% of a core for a nine-block rig. Client polling is cheap and linear in the rate: a
poll costs about **0.06 ms** on the 2-node rig and **0.13 ms** on the 34-node rig, so the reply's size
is most of it, and the heaviest condition in the whole campaign — a 34-node rig with a 20 Hz client —
is **5.62% of one core**, on a board with four.

## Part 3 — the two finer switches, at 1 Hz

The per-sample fold is the render thread's and no poll rate touches it, so the two things that *can*
be turned down are **how much of a window is measured** and **how often it is read**:

| Switch | What it changes | Default |
|---|---|---|
| `--levels-first-frame` | A probe folds the period's first frame and skips the rest: the render path's level work falls by the period length (64× at the pedal's 64-frame period) | off |
| `--levels-rate-hz N` | Probes are drained at most N times a second; a read in between is answered from the held reply. `0` = a real measurement per read | 0 |

At 1 Hz client polling, over the 34-node rig:

| Condition | Mode | CPU (one core) | vs `--no-levels` | What it costs the render path |
|---|---|---|---|---|
| 19 | `--no-levels` | **2.26%** | +0.02 pp | nothing — there are no probes |
| 20 | measuring (default) | **5.12%** | +2.88 pp | a fold per sample, per probe |
| 21 | measuring, `--levels-rate-hz 1` | **4.52%** | +2.28 pp | unchanged: this switch only limits the *reading* |
| 22 | measuring, `--levels-first-frame` | **2.87%** | +0.63 pp | a fold per period instead of per sample |
| 23 | both finer switches | **2.30%** | +0.06 pp | a fold per period, read once a second |

Measured as savings against condition 20:

- **`--levels-rate-hz 1` saves 0.60 pp** (5.12 → 4.52), and it is a saving for the **daemon**, not for
  render headroom: it limits the reading, and the reading is the control thread's. Confirmed in the
  data rather than assumed — condition 21's replies were 251 cache hits and 9 drains against condition
  20's 0 hits and 254 drains, so most of its polls cost a lookup.
- **`--levels-first-frame` saves 2.25 pp** (5.12 → 2.87), which is the render thread's per-sample work
  falling as designed. This is the switch that buys anything at all on the audio core.
- **Together they save 2.82 pp**, and end at **2.30% against the 2.24% of not measuring at all** — so
  with both on, a 34-node rig's meters cost about **0.06 pp of one core**.
- The two are very nearly **additive** (0.60 + 2.25 = 2.85 against 2.82 measured), which says they act
  on different resources rather than on the same one twice: the rate limits control-thread conversion,
  the sparse fold limits render-thread atomics.

**The catch, and it is why these are off by default.** `--levels-first-frame` changes what a meter
reads: one sample per period misses nearly every transient a peak exists to catch, and the reported
`rms` becomes that one sample's magnitude rather than a mean over the window. It is honest about it —
a window reports `frames: 1` per period rather than the period's length, so a client that reads
`frames` (and ljoss does, to tell an empty window from a silent one) can see that it is looking at a
sparse window. `--levels-rate-hz` trades freshness instead: at 1 Hz a meter shows a value up to a
second old, which is legible for a level and not for an edit.

Neither switch changes the audio, and that is pinned by a test rather than argued: two plans differing
only in `levels_first_frame` render identical samples over three quanta.

### Stability

Three conditions were re-run at the end of the campaign, after about an hour of load, with a **60 s**
window ([`stability.jsonl`](stability.jsonl)). They reproduce the 120 s figures, which is the check
that the campaign measured a steady state rather than a warming board:

| Condition | 120 s window | 60 s re-run | Agreement |
|---|---|---|---|
| 10 — `--no-levels` | 2.24% | 2.22% (133 ticks / 60 s) | 0.02 pp |
| 20 — measuring, 1 Hz | 5.12% | 5.12% (307 ticks / 60 s) | 0.00 pp |
| 23 — both finer switches, 1 Hz | 2.30% | 2.30% (138 ticks / 60 s) | 0.00 pp |

## Part 4 — publishing once a period, so the render thread stops sharing cache lines

![What publishing per period buys](overhead-by-mode-part4.svg)

The per-sample fold writes the probe's atomics, and the control thread reads them. The probes are
plain `std::atomic` members with no padding, so they share cache lines; every sample the render
thread stores into one of those lines is a line it may no longer own. That is where a meter's cost
actually is — Part 3's `--levels-first-frame` proved it by recovering 2.25 pp while throwing away 63
of every 64 samples.

`--levels-publish-period` (namchain `dd8d480`) gets the same kind of saving **without measuring
less**: the render thread folds samples into `level::Window`, plain memory no other thread has ever
touched, and adds that window to the probe's atomics **once per period** — the shape
`account_render_time` has always used.

The meter reads the same thing, and that is a property rather than a hope: a publish **adds** (raises
the peak, `fetch_add`s the sum, frame count and clip count) instead of setting. Add and max against
the zeroed reset a reader performs are order-independent, so any interleaving of a publish and a
`take` still answers "the samples since the last read" — no sample lost, none counted twice. Pinned by
tests that fold, publish and read in both orders.

Measured at 1 Hz client polling on the 34-node rig, 90 s windows, with **both controls taken on the
day** so that a slow drift on the board cannot read as an effect of the change:

| Condition | Mode | CPU (one core) | vs `--no-levels` |
|---|---|---|---|
| 28 | `--no-levels` | **2.22%** | baseline |
| 29 | measuring (sample publish — today's control) | **5.40%** | +3.18 pp |
| 30 | `--levels-publish-period` | **3.66%** | +1.43 pp |
| 31 | `--levels-publish-period --levels-rate-hz 1` | **3.06%** | +0.83 pp |

- **Measuring costs 3.18 pp** over not measuring (2.22 → 5.40), which is today's behaviour.
- **Publishing per period recovers 1.74 pp of it — 55%** — and measures **every sample**: same 34
  probes, same 64 frames per period, same peak and same rms. What is left (1.43 pp) is the atomic
  work itself and the fold, which no amount of batching removes.
- **Stacked with the rate limit it recovers 2.34 pp — 74%** of the whole cost of having meters, and
  the two still combine because they act on different resources: the publish mode is the render
  thread's traffic, the rate limit is the control thread's conversions.

**The price, stated plainly:** a reader can see a window that closed up to one period ago — 1.33 ms
at 64 frames and 48 kHz. Nothing meters at that resolution. The switch is **off by default**, so the
shipped behaviour is unchanged until you decide otherwise; the case for turning it on is this table
plus ljoss's display being unaffected, which it is: the reply's shape, `frames`, and the
read-and-reset rule are all as they were, and only `cache.publish` is new.

### Stability

The two controls were re-run at the end of the series with a **60 s** window:

| Condition | 90 s window | 60 s re-run | Agreement |
|---|---|---|---|
| 28 — `--no-levels` | 2.22% | 2.22% (133 ticks / 60 s) | 0.00 pp |
| 29 — measuring (sample) | 5.40% | 5.22% (313 ticks / 60 s) | 0.18 pp |
| 30 — publishing per period | 3.66% | 3.63% (218 ticks / 60 s) | 0.03 pp |

The 1.74 pp effect is ten times the disagreement between the two window lengths, so it is not an
artefact of when the runs happened.

### What a smaller budget would have cost

CPU is counted in 10 ms ticks, so a window resolves `10 ms ÷ window` of one core: **0.83 pp at
120 s**, **0.56 pp at 90 s**, **0.17 pp at 30 s**. The series above fits in about six minutes only
because 90 s still resolves the effects. At the 30 s a five-minute eight-condition sweep would have
allowed, the publish mode's own saving would be about nine ticks but the *rate limit's* 0.60 pp would
be under half a tick — visible as a number, meaningless as a measurement. The budget was spent on
window length rather than on conditions, which is the trade this instrument makes.

## Reproducing it

```sh
scripts/host-lock --host vip -- env SECONDS_PER_RUN=120 SETTLE_SECONDS=8 \
  bench-results/2026-10-06-levels-switch/run-campaign.sh
python3 bench-results/2026-10-06-levels-switch/analyse.py \
  bench-results/2026-10-06-levels-switch/results.jsonl
# The by-mode chart needs one row per mode: point it at the conditions that differ only in the mode.
python3 bench-results/2026-10-06-levels-switch/charts.py \
  bench-results/2026-10-06-levels-switch/results.jsonl --only 19,20,21,22,23   # part 3; and 28,29,30,31 for part 4
# Part 4 on its own, in about six minutes rather than an hour:
scripts/host-lock --host vip -- env SECONDS_PER_RUN=90 SETTLE_SECONDS=5 \
  bench-results/2026-10-06-levels-switch/run-campaign.sh --only 28,29,30,31
```

`--only 19,22` runs a subset and `SECONDS_PER_RUN` shortens the window, both for a smoke test.
`analyse.py --only` needs no special handling for the baseline: it is looked up in the whole run.
`charts.py --only` does: without it the by-mode chart takes whichever row comes first for each mode,
and several conditions share a mode.

## Things that went wrong, and what they cost

Recorded because each one was a trap that produced plausible numbers:

- **The gate exists because the first attempt measured the wrong rig.** `pedald seed` resumes
  `/var/lib/pedal/library/rigs/last.json` at startup, and the campaign's `--rig` and the daemon's own
  startup rig were two different documents. The CPU figures looked entirely reasonable.
- **A background drain moved no counter a client could see.** The rate test first asserted that
  `misses` grew over time, and it never did: `misses` counts reads that cost a drain, and the control
  loop's own drains are not reads. The reply now carries `drains` as well, which is what says the
  cadence is running at all.
- **Two attempts to verify the sampling mode from outside were abandoned, deliberately.** A single
  window's `frames` cannot identify the mode, because with a rate limit the window spans many periods
  and first-frame mode correctly reports one frame *per period*. And the growth between two reads
  cannot either, because the control loop's drains land between them and the interval is therefore
  arbitrary — it measured 8.0 frames per period where the answer should have been 64, and 0.0 where it
  should have been 1. The mode is now gated on the daemon's declared configuration, and the *behaviour*
  is pinned where it can be pinned exactly: in the unit tests.
- **A pre-existing test flaked on the aarch64 build container, three times, for one race in three
  places.** `engine.levels reports the device, the chain and every node` polled for a non-empty window
  with a budget of 200 attempts of (a read + 2 ms) — about 400 ms, which is a deadline in disguise
  whose real length depends on how loaded the machine is. The second and third failures were the same
  race one level down: it waited only for a *node's* window and then asserted the *device's* had
  samples, and later the same for one node against another. Every read takes every probe, so a test
  that polls for one and asserts about another is asserting that nothing else is using the daemon.
  All three now poll for the whole reply they are about to assert on, on a 10 s deadline.
- **The publish mode has one invariant that the design turns on, and it needed writing down.**
  `publish_window` must *add* to the probe's atomics, never *set* them: the reader zeroes them as it
  reads, so a publish that stored would lose whichever period lost the race against that reset. It is
  now the subject of its own test rather than a property of the code that happens to be true.
- **A one-line answer about the periodic-window publish would have been wrong twice.** This started
  as the question "isn't it a memcpy to the control thread?" — and the useful part of the answer was
  not the mechanism (aggregate scalars, no samples cross) but the diagnosis: probes share cache lines
  with each other, so the cost is coherency rather than bandwidth. That is what made the fix
  obvious, and it is the reason `level::Window` exists instead of a lock-free sample ring.

