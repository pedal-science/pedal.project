# T9 — Lite first, then the Full, through the pedal (2026-10-10)

**State: NOT YET RUN ON THE HARDWARE.** This directory holds T9's instrumentation, the one blocking
finding that stopped the run, and the exact numbers it produced. The measurement tables below are
filled in by `scripts/measure-lite-first`; where a table has no numbers it is because the board is
not running the engine they would describe. Nothing here is claimed as measured that was not.

T9 is *cold, from nothing*: the first press after boot, nothing warm, and the question is **how long
from a press being accepted to a rig playing at all, and how long to the Full**
(`docs/managing-processing-power-and-optimising-for-fast-switching.md`, "T9", and "P8" above it).

## The engine the run needs, and the one the board has

| | |
|---|---|
| Board (`vip`) runs | **`ee4c53d`** — predates every commit T9 measures |
| T9 needs | `89193f5` (`7d9cbbd` the two-step publish, `810a1fd` the replay, `ea453c0` the compile off the control thread, `74ebd08`/`2830f5d` the allocation and supersede handling, `89193f5` per-chain memory) |
| Deployment | **blocked**: `scripts/deploy-engine --host vip --commit 89193f5` fails its test run, twice, identically |

So the numbers in this file are all still to be taken. The reason they are not is a genuine failure
and not a flake, and it is recorded here because it is the first thing T9 found.

## 0. The blocker: `unit` fails in the build container, in one case, deterministically

`scripts/deploy-engine` builds in the image's container (`devices/common/image/build-namchain`,
snapshot `20260929T000000Z`, `-march=armv8-a -mtune=cortex-a76`, GCC 15.2.0) and runs `ctest`
serially. Two attempts, one after the other:

| attempt | `unit` | failing case | symptom |
|---|---|---|---|
| 1 (`build/engine/89193f5/logs/namchain-test.log`) | FAILED 11.20 s | `test_catch_up.cpp:148` | 5 × `memcmp != 0`, blocks 3,4,5,6,7 |
| 2 (same path, rebuild) | FAILED 11.62 s | `test_catch_up.cpp:148` | 5 × `memcmp != 0`, blocks 3,4,5,6,7 |

The other four ctest cases pass (`soak_cli`, `ctl_cli`, `golden_setup`, `golden_a2_lite`). There is
**no segfault**: this is not the known intermittent `unit` crash (~4% of full-suite runs, 0/300
single-case) — that is a different symptom, and the distinction matters because this one is
deterministic and triage-able.

The case is `"a replayed plan is bit-identical to one that has been running"` — the test that asserts
the exact claim P8 and T9 rest on: that replaying the recorded input into a cold Full makes it the
same plan as one that has been rendering all along, bit for bit, which is what makes crossfading it
in mid-note legitimate. It fails on blocks 3–7 after the hand-over; blocks 0–2 pass.

What was ruled out by measurement, not by reading:

* **It passes alone, in the same image, with the same flags.** `namchain-tests --test-case="a
  replayed plan is bit-identical to one that has been running"` — 17/17 assertions, twice, in a
  container built from the same source and flags the deploy used. So it is a suite-context effect.
* **It passes on the Mac.** The whole suite: 367/367 cases, 271,479/271,479 assertions. The
  container runs 372 cases; the difference is the platform-conditional ones (`test_coreaudio_*` on
  Darwin, plus the cases Linux adds).
* **The falsifier in the same case passes** where it runs: a plan that was *not* replayed does differ
  from the running plan, so the comparison is not vacuous.

What that leaves is an interaction between the case and whatever the rest of the suite leaves behind
in the container build, and it is being chased as an engine bug: a suite that cannot go green is a
board that cannot be updated, which is the correct state to leave it in, and the fix belongs in the
engine rather than in the deploy script's willingness to skip it. Consequence worth writing down:
`deploy-engine` is fail-closed on `ctest`, so **any** failing case — the 4% crash or a deterministic
assertion like this one — now blocks every deploy of that commit, and a red suite is discovered at
deploy time rather than at commit time.

## 1. What was driven, and how

Two documents, both the pedal's own, built by `scripts/t9-rigs` out of models already in the
board's library (nothing is uploaded; the one asset it writes is the 2.3 KB LSTM below):

| rig | what it is | why |
|---|---|---|
| `t9-base.json` | one `nc.nam` (a WaveNet the table has a row for) into the cab `last.json` already names | an ordinary Full, so the switch to the target is a two-step publish with a real Full to compile |
| `t9-lstm.json` | the same shape on `lstm.nam` | a family vip's table has **no row** for — `unknown.NAM`, 0.25 charged — and the case the replay must refuse (`Unbounded`) |

Three arms, all with the press driven through software rather than a footswitch (T9's physical
press is 3.8's and is not claimed here):

| arm | how the press is made | what it is |
|---|---|---|
| `engine-no-lite` | `rig.switch` with `lite_first: false` on the control socket | the single-step cold publish the service asked for until 2026-10-10 — **what a press measured before the wiring**, and the control |
| `engine-lite` | `rig.switch` with `lite_first: true` | P8's two-step publish, straight at the engine |
| `service` | `POST /event` on pedald (`127.0.0.1:47820`, bearer token from `/etc/namchain/token`), kind 1 = `rig_up` | a real press through the service, which now asks for the Lite itself |

`measure-switch`'s approach is reused rather than reinvented: `POST /event` carries the Pico's own
vocabulary and the route hands it to the same `on_event` the UART reader calls. The service arm now
exists as a *comparison* because of a gap found while wiring this up: pedald's `engine.py` sent only
`{rig, fallback}`, so the two-step publish was not reachable from a press at all — the engine had it
and the service never asked. That was fixed on 2026-10-10 (`pedal.project` `877b8c4`).

### The clock, and the resolution of every number here

Every time is this process's `time.monotonic()`. "Accepted" is the request **leaving** the measuring
process, so the engine arms carry one control round trip and the service arm carries the HTTP round
trip as well; neither is subtracted, and neither is claimed to be zero.

"Audible" is the first `engine.status` poll that saw `audible_generation` reach that document with
its transition finished. The document becomes audible somewhere between the last poll that still
showed the old generation and the first that showed the new one, so **the poll interval is the
resolution of every number in this file** and is reported with each run. The engine's generation
changes once per fade (5 ms here), so the catching poll is the first after the crossfade *began*, not
after it ended. Nothing below is finer than one poll and nothing implies it is.

## 2. The numbers

*(to be filled by `scripts/measure-lite-first` on a board running `89193f5`)*

| arm | accepted → Lite audible (ms) | accepted → Full audible (ms) | poll interval (ms) | reply |
|---|---|---|---|---|
| `engine-no-lite` | — | — | — | — |
| `engine-lite` | — | — | — | — |
| `service` | — | — | — | — |

## 3. What the engine reported in between

*(from the same runs: `catch_up.state` / `catch_up.full` / `catch_up.replay`, `cost.lite_first`,
`chains[i].audible_generation`)*

| arm | `catch_up.state` | `catch_up.full` transitions | `catch_up.replay` | `cost.lite_first` | chain `audible_generation` |
|---|---|---|---|---|---|
| `engine-no-lite` | — | — | — | — | — |
| `engine-lite` | — | — | — | — | — |
| `service` | — | — | — | — | — |

The transitions to look for, and what each would mean: `full` `compiling` → `published` is the Full
landing; `replay` `running` → `exact` is the replay having been applied (anything else —
`gap`, `no_input`, `abandoned`, `busy` — is a promise the engine did not keep, and is the shape of
failure D6's visibility exists to surface); `cost.lite_first` true is the Lite standing in, and it
must clear only once the Full is what is playing. **If `catch_up.full` never reaches `published`, or
the Lite is never audible, or the audible rig is disturbed, that is the finding** and goes here
rather than in a footnote.

## 4. The audible rig, and whether the publish disturbed it

`render.over_deadline`, `render.worst_us`, `xruns` and `guard_trips` before and after every run:

*(to be filled)*

## 5. The refusal path, on the pedal

`lstm.nam` (`namchain/vendor/NeuralAmpModelerCore/example_models/lstm.nam`) has unbounded memory, so
`nam/lookback.cpp` answers `Unbounded` — no replay can be exact. The engine must therefore **refuse
the replay with the node named and still publish the Full**, rather than silently handing over a cold
Full as if it had been caught up. This is the half of P8 that can only be tested on the pedal.

What the run checks, via `scripts/t9-rigs`:

1. `rig.load t9-base.json` — playing, an ordinary Full.
2. `rig.switch t9-lstm.json` with `lite_first: true`.
3. `engine.status.catch_up` must say `state: unbounded` with `detail` **naming the node** (`amp0`,
   `nc.nam`) and the reason, and `frames: 0`; the reply's `full` must still end at `published` — the
   Full plays, cold, and says so.
4. `chains[0].audible_generation` must reach the Full's generation, so the refusal did not leave the
   Lite standing.
5. `scripts/t9-rigs restore` — both rigs and the model removed, `last.json` reloaded, pedald
   restarted, library back to `last.json last.prev.json`.

*(result to be filled)*

## 6. What this does not settle

* **The physical footswitch press.** Everything here is driven through the service or the control
  socket; the press through the Pico's own UART path is **3.8's**, and T9's "to the jack" reading
  needs it plus a capture at the output. Not claimed.
* **A heavier Full.** One model into one cab, on vip. A two-model or multi-chain Full has a longer
  compile, and whether the Lite-first promise holds there is a different measurement.
* **The first press after a real boot** with the card cold. These runs load the base rig first, so
  the page cache is warm; T9's literal "after boot, SD card cold" reading is not what was measured.
* **Whether the bit-identity claim itself holds.** That is §0, and it is currently failing in the
  container build.
