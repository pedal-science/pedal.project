# Rig switch strategies

A performer can have one or more 'rigs' available - that they can switch between.
A rig - in namchain - can have one or more chains
Each chain can have zero or more nodes that contain NAM models
Each instance of a NAM model in a rig must be treated separately for the purposes of considering switching, as even if the same underlying model is the same, except in the discardable case of the same model being used in the first node either side of an exactly-duplicating fork in a chain, and in the - also discardable because we can't rely on luck - case that the input audio happens to be exactly the same.

The performer can switch instances in a rig on and off using various types of controller.
They can also switch rigs - again, using various types of controller.

Technically speaking:
The number of NAM models that the user has access to could be millions
The number of instances configured in a rig could also be millions 
The number of rigs that the user has set up could be millions

In the real world:
We shouldn't have to worry about how many NAM models the user has access to
The number of  instances configured in a rig will be limited by how many are actually practical, given a few factors:
Too much complexity in a rig is unusable for a player
The number of types of NAM model (amp+cab, amp only, pedals (of various types that work - mainly 'dirt' pedals)) that are actually useful to have in a chain - an in a switchable branch of a chain -  is limited by practical usefulness
However many rigs the user has set up, it's impractical to switch between more than a handful with instant access.

I'm going to make some assumptions for us to start with:

The maximum number of different model instances  that we should expect to exist in one rig is 16
The maximum number of different rigs that can be quickly accessed by a player - with entirely disjoint sets of models from each other - is 16

These shouldn't be used as hard limits on anything. I'm just stating them to help us do some maths.

Some hardware constraints:
We can run 5 NAM full instances per core
Given what we've seen in testing, we can run around 5 times the number of lite instances as full instances per core, which means we should be able to run something like 20 lite  instances per core
We have 4 cores, but we need at least one core to be dedicated to non-namchain activities. (I know that namchain / namchaind don't take advantage of multiple cores flexibly yet. I'm just stating hardware constraints here).

Now let's look at catch-up and always-warm:

Catch-up:
When a switch occurs, every instance we want to switch in needs to be caught up.
It will cost a fixed  replay CPU per model (which we need to have available).
It will cost a fixed time per instance (27ms for full, likely ~6ms for lite). 
The total time required before the switch is complete depends on whether any are processed in parallel 

Always-warm: 
When a switch occurs, there is no rendering to perform - just a switch.
Every  instance that we could potentially have to switch in needs to be kept warm. Each has a fixed CPU cost (the amount depends on if it's using full or lite)
The time required for a switch - that's due to instance swapping - is not significant (to be analysed in more detail perhaps)

There are probably many strategies which we could design for switching, where each will optimise for particular attributes, such as:
Amount of processing that has to occur all the time in order to enable the strategy to work
Amount of processing that has to occur between a switch being triggered and it having completed
Amount of time that has to occur between a switch being triggered and it having completed

Some ideas we haven't yet considered may be useful to bring into the thinking, such as:
Could we use lite models for always-warm and/or catch-up processing to optimise for available CPU and/or switch time (let's call that latency) - and automatically switch back to full models (where instances are configured to use full) after the lite models are live, perhaps sequentially in order to avoid running out of CPU?


## What a NAM model can be

A capture is just input and output: NAM doesn't know what was recorded. The common kinds are:
- **Amp only** (a "head"): usually followed by an IR in the rig.
- **Amp and cab**: the cabinet is inside the model. It costs the same as an amp-only model of the
  same architecture, because the cost depends only on the architecture. It doesn't need an IR.
- **Pedals**: fuzz, distortion, overdrive. Time-based pedals have been captured, but don't
  work well and are uncommon.
- **Other devices**, such as console-style vocal preamps.

Model files carry a `gear_type` in their metadata. The 52 models in the library (all A2
`SlimmableContainer`, 2026-09-26):

| `gear_type` | count |
|---|---|
| `full-rig` | 20 |
| `amp_cab` | 15 |
| `pedal` | 9 |
| `amp` | 8 |

So 35 of 52 already include a cab. IRs go with amps, and more than 4 amps in one rig would be very
unusual. A rig will have far fewer IR instances than NAM instances. Unlikely rigs still need
thought: we only rule something out when it's impossible, or when we choose to set a limit (see
"Limits" below).

## Notes on the measured numbers

These are from E1 on piv (`plan.md` 3.8; namchain `bench-results/e1-warm-candidates-piv.txt`).
- **"5 full per core"** was measured on rigs of **one A2-Full model plus an 8192-tap IR**. On the
  render core the IR is about half the cost: 7.3% of the deadline for the model alone, 15.4% with
  the IR. A model with no IR after it should fit roughly **10 per core**. That's an estimate, and
  E2 measures it.
- **Lite** costs about 1/5.8 of Full on piv (RTF 0.0086 against 0.0500 at q64), so roughly
  **50 per core** without IRs. That's also an estimate: the cache crowds as the count grows. E1
  saw each warm rig go from 7% of a quantum alone to 12% each with 8 on one core.
- **"27 ms catch-up"** was for one model plus an IR, replaying 340 ms, at low priority on a
  housekeeping core. For a model alone, estimate **~13 ms** for Full and **~2.5 ms** for Lite.
- **The switch itself** (a warm model taking over) takes **~11 ms** from the event to the jack:
  - up to one block (1.3 ms at q64)
  - a 5 ms equal-power crossfade
  - ~5 ms of output path (queue and converters; the loopback round trip is 8.7 ms)

  A MIDI message adds ~1 ms, and the Pico-to-Core UART hop about the same.
- **Footswitch debounce counts against the 50 ms.** Acting on the first edge and ignoring bounces
  afterwards costs ~0 ms. Waiting out a 10–20 ms debounce window before acting spends a third of
  the budget.

## Four things that change the maths

### 1. Catch-up cost grows with chain depth, not just instance count

Each model in series needs ~340 ms of *correct* input to reach the right state. The second
model's input is only correct once the first has caught up. So a chain of d models in series
needs about d × 340 ms of input history, and the total work is about d(d+1)/2 single-model
replays. Models side by side (a stereo split) don't add depth.

| depth d | replays | Full, one core | Lite, one core |
|---|---|---|---|
| 1 | 1 | ~13 ms | ~2.5 ms |
| 2 | 3 | ~39 ms | ~7.5 ms |
| 3 | 6 | ~78 ms | ~15 ms |
| 4 | 10 | ~130 ms | ~25 ms |
| 16 | 136 | ~1.8 s | ~340 ms |

Pipelining block by block across two cores roughly halves these. The d × 340 ms is reasoning:
E1 only measured a depth of one model plus an IR. A replay shorter than 340 ms may be enough if
we accept an error of about −60 dB rather than −114 dB. E2 measures both.

### 2. Toggling an instance inside the live rig can be free

A rig has to fit on the CPU with every instance switched on, because the player can switch them
all on. That capacity is reserved anyway. So bypassed instances keep running on whatever signal
reaches their position, and toggling one is only a crossfade.

Downstream models see their input change suddenly. That's what a real amp sees when a pedal is
kicked on, so it's the correct sound, not a glitch.

The exception is a "pick one of N" branch (A/B amp select). There, keeping the unpicked branches
running costs extra.

### 3. An IR can be kept warm as a record of its input

`nam::Linear` is a direct convolution: its entire state is its last 8192 input samples. A warm rig
therefore doesn't need to run its IRs, only record what goes into them. At the switch, the
convolver is filled from that record. The model before the IR still has to run.

This only matters for rigs with separate IRs, which (above) is fewer than it first seemed. It
needs a small change to namchain.

### 4. The one-press candidate set is smaller than "all rigs"

With the planned footswitches (preset down, preset up, one assignable), one press reaches two
neighbouring rigs and one assigned target. The set gets large only when:
- MIDI jumps straight to a rig (a controller with a switch per rig)
- the footswitches are changed to work that way
- someone switches in ljoss.

When the player moves on, the new neighbour needs its state brought up to date. A catch-up
burst does that in tens of ms, so a quick double press rarely finds it cold. Warm work doesn't
need an isolated core: E1 showed a warm candidate running a block or two late does no harm,
because the switch waits it out. It can run on a housekeeping core, as long as one core stays
free for everything else.

## Rapid switching: the newest request wins

Switching fast enough means switching faster than a human can. Cases like scrolling through the
rig list in ljoss are handled simply, without trying to support very fast switching between many
rigs:
- **No queue.** One switch is in flight at a time, plus at most one pending request.
- **A new request replaces the pending one.** When the current switch finishes, the engine goes
  to the newest pending rig, crossfading from whatever is playing.
- A scroll through 20 rigs therefore makes at most a few switches, not 20.

## Strategy tiers

Every rig gets the highest tier the budget allows, in this order.

| Tier | What | How | Switch time | Always-on cost |
|---|---|---|---|---|
| 0 | Toggles in the live rig | All instances always run, bypassed or not | crossfade only | none beyond the rig's all-on budget |
| 1 | One-press candidates (neighbours, assignable target) | Full always warm; IRs kept as input records | ~11 ms, exact | one Full model per instance |
| 2 | The rest of the bank, MIDI jumps | A Lite copy always warm. At the switch it takes over at once; Full catches up in the background, then a 5 ms crossfade to Full | ~11 ms, then Full within tens of ms | one Lite model per instance |
| 3 | Everything else (ljoss) | Loaded in RAM, not running. At the switch: Lite catch-up, then Full as in tier 2 | ~11 ms + the Lite catch-up (~15 ms at depth 3) | RAM only |

Notes:
- **Lite and Full are separate submodels** in a `SlimmableContainer`, not one network at two
  widths. Their states can't be copied from one to the other. **E2 measured this on 2026-10-06 and
  the change is not small**: two separately trained networks, 9 to 40 dB apart, level-matched and
  time-aligned, so handing over substitutes a different rig's tone rather than a narrower version of
  the same one. The 5 ms crossfade does stop it *clicking* (102 of 104 model-directions passed every
  glitch rule), and whether the change itself is acceptable is the one measurement E2 left to a
  listening test — see the results below.
- **Upgrading from Lite to Full:** the simplest way is the whole rig at once, one crossfade. For
  those 5 ms both run on the render core. That needs about 1.2× the rig's Full cost, since Lite
  is ~1/5. If that doesn't fit, upgrade one instance at a time, upstream first.
- **Anything not warm uses catch-up**, never the silent prewarm. E1 showed silent prewarm is the
  wrong sound for 170–340 ms.
- **Limits.** The pedal service works out a rig's all-on cost when it's saved. It refuses a rig
  that can't run all-on (namchain's M2, admission control), and drops candidates to a lower tier
  when the budget is full. At your 16 × 16 numbers even the live rig (16 Full ≈ 1.6 cores) needs
  either Lite or rendering on two cores (namchain M4).

## Worked numbers

Estimated per core: ~10 Full or ~50 Lite models (no IRs). There are 2 cores for warm work.

| Case | Candidates | Tier 1 for all (Full) | Tier 2 for all (Lite) |
|---|---|---|---|
| Your upper bound: 16 rigs × 16 models | 240 models | ~24 cores | ~5 cores |
| A large bank: 8 rigs × 3 models | 21 models | ~2 cores (none left for catch-up) | ~0.5 core |
| Footswitch neighbours + assignable, 3 models each | 9 models | ~1 core | ~0.2 core |

So for a typical rig, the footswitch candidates in tier 1 and the rest of an 8-rig bank in
tier 2 fit on one core. The 16 × 16 case doesn't fit any always-warm scheme. It gets tier 1 for
the neighbours, tier 2 for as many as fit, and tier 3 for the rest.

## E2: what has to be measured before building this

In `plan.md` 3.8, after E1.
1. **Lite against Full** for every library model: how far apart the two outputs are (the null
   level), and whether a 5 ms crossfade from one to the other can be heard, in either direction.
   Listening, plus the glitch detector.
2. **Catch-up convergence for chains** of 1–4 models in series, against replay length (85, 170,
   340 and 680 ms per model): does depth d need d × 340 ms, and does −60 dB sound the same as
   −114 dB?
3. **Warm density without IRs**: how many Full and how many Lite models keep up on one core, and
   on a housekeeping core under load; the render core's tail with them running.
4. **IRs as input records**: fill a convolver from recorded input and check it matches one that
   ran all along.

**Measured 2026-10-06, all four** (namchain `083de32`; the tables are in its `bench-results/` as
`e2-lite-vs-full.txt`, `e2-chains-and-irs.txt` and `e2-warm-density-vip.txt`, and the reading is
[bench-results/2026-10-06-e2-tiers.md](../bench-results/2026-10-06-e2-tiers.md)):

1. **Lite and Full are 9 to 40 dB apart** (median 21.7 below the signal), level-matched and
   time-aligned, because each `SlimmableContainer` holds two separately trained networks. The
   crossfade between them is clean — 102 of 104 model-directions passed every glitch rule — so the
   handover does not click, it *changes the sound*. Tier 2's "a Lite takes over at once" therefore
   plays a different rig until the Full catches up, and the sentence below is the live question.
2. **170 ms of replay per model is bit-exact at depths 1–4**; 85 ms fails at depth 3–4. A series
   chain's memory is the *sum* of its stages', so the per-model replay does not grow with depth, and
   the work is the `d(d+1)/2` replays estimated here: 29.4 ms at depth 2, 58.8 at depth 3, 98.2 at
   depth 4 on vip.
3. **8 Full or 30 Lite models stay warm on one core** (p99 of the warm thread under one quantum:
   89.1% and 97.4%; 10 and 40 do not), not the ~10 and ~50 estimated above. The render core's p99
   moves 8.08% → 10.60% with 8 Full warm and there were no overruns; a lower-priority spinner on the
   warm core changes nothing measurable.
4. **An IR can be kept as a record**: filling the convolver from the last 8192 samples of the
   model's output reproduces one that ran all along to −138.5 dBFS, for 1.26 ms at the switch.
