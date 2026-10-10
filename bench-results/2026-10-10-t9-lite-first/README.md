# T9 — Lite first, then the Full, through the pedal (2026-10-10)

**Run on the hardware, and it found a defect.** The board runs `894b67c` (the Lite-first publish, the
catch-up replay and its per-chain memory, with the test fix that unblocked the deploy). The two-step
publish works and the numbers are below. **What does not work on the board is the replay**: the
engine reports `catch_up.state: exact` and a 14,539-frame window, then finishes with
`catch_up.replay: no_input` and `catch_up.blocks: 0` on every run — the Full is published but it was
never caught up, so it is crossfaded in from a cold start, which is the thing P8 exists to prevent.
The engine's own test proves `exact` on the test backend, so this is specific to the board and its
ALSA path. §4 is the finding; it is the most important thing in this file.

What the numbers are worth is bounded by the poll grid, which is **6.5–8.7 ms** per run (measured,
not assumed) — see §1 for what "accepted" and "audible" each do and do not include.

T9 is *cold, from nothing*: the first press after boot, nothing warm, and the question is **how long
from a press being accepted to a rig playing at all, and how long to the Full**
(`docs/managing-processing-power-and-optimising-for-fast-switching.md`, "T9", and "P8" above it).

| | |
|---|---|
| Board (`vip`) runs | **`894b67c`** — `7d9cbbd` the two-step publish, `810a1fd` the replay, `ea453c0` the compile off the control thread, `74ebd08`/`2830f5d` the allocation and supersede handling, `89193f5` per-chain memory, `894b67c` the test fix |
| Deployed by | `scripts/deploy-engine --host vip --commit 894b67c` — 5/5 ctest, `unit` 372/372 in the board's own container build |
| Cost table | `devices/vip/cost.json` names `894b67c` (bumped without re-measuring, reason in `bar`), applied, `devices/vip/check` green |
| Settings | 48 kHz, period 64, `warm_cpus [1, 2]`, active core 3, `fade_ms` 5, headroom 0.8 |

## 0. The blocker that opened this run, and its resolution

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

**Resolved: it was the test, not the engine** (namchain `894b67c`). The case generated exactly
`kBlocks` of input and then compared the blocks *after* the signal by reading
`x.data() + (kBlocks + b) * kQuantum` — 512 floats (2 KB) **past the end of the vector**, into live
heap where the two plans' own buffers sat. So the reference plan's run wrote the bytes the replayed
plan then read: the two plans were fed different audio, and the case measured that instead of the
replay. Deterministic in the board's build and nowhere else because the A2 planar parity case, which
runs first in file order, leaves the heap shaped so the catch-up plans' buffers land immediately
behind `x`. ASan names it exactly — a 256-byte read at `x+51200`, 0 bytes after the 51200-byte region
`signal()` allocated — and digesting the out-of-bounds bytes before and after each run shows the
correlation: blocks 0–2 unchanged (the plans agree) and blocks 3–7 changed by the reference's own run
(so they differ). `execute()` reads exactly `frames` samples from the pointer it is given, which is
its contract, so **the engine was never at fault and the bit-identity claim was never falsified** —
the honest reading of the evidence above was "the test disagrees with itself in this environment",
which is what it turned out to be. The suite is green on the fixed commit both on the Mac (367/367)
and in the board's own container build (5/5 ctest, `unit` 372/372).

Two consequences are worth keeping, because they are about the pipeline rather than this test.
`deploy-engine` is fail-closed on `ctest`, so a red suite — the 4% crash or a deterministic
assertion like this one — blocks every deploy of that commit, and a red suite is now discovered at
deploy time rather than at commit time. And the way this one hid is instructive: it passed alone in
the same image and passed on the Mac, so the two facts that made it tractable were "it is
suite-context" and "the falsifiable prediction is that ordering matters", not a reading of the code.
A second, unrelated finding from the same sweep (a heap-use-after-free in `test_daemon.cpp`, found
under randomised ordering) does not affect this suite.

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

The poll interval was measured against the board rather than assumed: `engine.status` over TCP from
the Mac to `vip` takes **9.62 ms** on average over 20 calls. So every time this measurement produces
is only as good as a ~10 ms grid, and the script prints the interval it actually got with each run.
Times quoted to a tenth of a millisecond would be a lie; they are reported to the grid the run had.

## 2. The numbers

Three runs an arm, the `last.json` → `t9-base.json` cold switch, on the board running `894b67c`. The
engine runs (cold publishes) had the **warm set verified empty at the press** — the service holds the
rig a press would reach next warm, so the harness empties it and re-checks before every run, and the
run is retried if the service refilled it. **Every time is bounded by that run's poll grid**, in the
last column: a rig became audible between the last poll that showed the old generation and the first
that showed the new one.

| arm | accepted → Lite audible (ms) | accepted → Full audible (ms) | reply (ms) | poll grid (ms) |
|---|---|---|---|---|
| `engine-no-lite` (the control) | **32** (30.1 / 30.8 / 38.7 across runs) | n/a — one publish, no Full behind it | 23–29 | 10.7–11.6 |
| `engine-lite` | **41** (40.9 / 40.9 / 42.6) | **320** (319.5 / 321.2; run 2's Full landed after its poll budget) | 32–34 | 7.7–11.0 |
| `service` — press, `rig_up` (handover) | **108** (105.7 / 108.3 / 121.0) | n/a — the rig was already warm | HTTP 98–108 press→accepted | 8.3–10.0 |
| `service` — press, `rig_select` (handover) | **110** (108.2 / 109.6 / 115.8) | n/a | HTTP 98–107 | 7.5–8.6 |

Raw: `raw/lite-first-polls.json` (the polls kept around every state change of all 12 runs) and
`raw/t9.txt`. Reproduce with
`scripts/measure-lite-first --host vip --runs 3 --rig t9-base.json --base last.json`.

**What these say.** The two-step publish gives sound at the press — **41 ms median** — and the Full
**320 ms** later. P8's promise ("sound at the press, the rig the player asked for within a second or
two") holds with room: the 320 ms is not a compile the player waits through, it is the window the
engine spends getting the Full ready while the Lite plays. The control — one publish, no Lite and no
Full behind it — was audible in **32 ms**, so the Lite's own cost at the press is about 9 ms here:
one compile plus the settle-wait, against one compile.

**The pre-wiring number, said plainly.** `engine-no-lite` is what a press measured before `877b8c4`:
pedald sent `{rig, fallback}`, the engine did one publish, and the player heard the Full when it
landed. On this rig that is 32 ms, because this Full is small (0.14882 of a core — one WaveNet and one
8192-tap cab). **The Lite's advantage is a property of the rig, not a constant**: it is roughly the
difference between a Lite compile and a Full compile, and it grows with the Full. This run did not
measure a heavy rig, so read the 41-against-32 as "the two-step costs about 9 ms more when there is
almost nothing to wait for, and buys the difference when there is". The same 320 ms Full window would
be the whole wait without it.

**Both service presses were handovers, and that is the honest result.** pedald holds the rig a press
would reach next warm (D10), so in this bank every press lands on a compiled document: the engine
answers `switched: warm`, no generation moves, and the press is a crossfade. Measured through
`POST /event` that is **108–110 ms** end to end, of which the HTTP round trip is 98–108 ms — so the
service's own overhead is about a tenth of a second and the audio work inside it is a fade shorter
than the poll grid. **A cold press through the service was not obtained**: in a two-rig bank the rig a
`rig_up` reaches is the warm one, and `rig_select` into the other slot reaches the same rig, so there
is no press this bank can make that is not a handover. What the service adds to a *cold* publish is
therefore not measured here. What is measured is that its overhead is ~100 ms, well over twice the
41 ms a Lite-first publish needs — so on this service the press's cost is the service, not the engine.

## 3. What the engine reported in between

From the same runs, the transitions the polls caught:

| arm | `catch_up.state` | `catch_up.full` | `catch_up.replay` | `cost.lite_first` | chain `audible_generation` |
|---|---|---|---|---|---|
| `engine-no-lite` | previous job's, stale (no catch-up is armed: see §6) | `nothing_to_trim` | `no_input` | false throughout | tracked the single publish |
| `engine-lite` | `exact`, all 3 runs | `compiling` → `published` **16 ms later** | `no_input` → **`running`** → **`no_input`** | true → false when the Full landed | the Lite's, then the Full's |
| `service` (both presses) | `exact` | `published` | `exact` (the previous cold publish's, left behind) | false | the handover's document |

The reply to the Lite-first request is the shape P8 describes: `lite.trimmed: true`,
`lite.slimmed_models` naming `amp0` at the `NAM.WaveNet.lite` row with `full_cost` 0.111 against its
`cost` 0.0333, `lite.adopted: true` (the render thread had settled on the Lite, so it really was
audible and not coalesced away), and `full.state: "compiling"` with `catch_up.state: "exact"` and
`frames: 14539` (303 ms of input — the model's receptive field). `cost.lite_first` was true while the
Lite stood in and cleared when the Full became what was playing, which is D6's visibility working.

**`catch_up.full` reached `published` in every run**, so the design's second step landed. What did
not happen is the replay, in the one arm that should have done one: see §4.

Two readings in this table are stale values rather than this run's state, and both are the same
mechanism — `catch_up_report_` is only rewritten by the paths that arm a catch-up: an ordinary
publish (`engine-no-lite`) and a handover (the service presses) leave `catch_up.state` and
`catch_up.replay` carrying whatever the last two-step publish left. So `replay` cannot be read on its
own; `catch_up.blocks`, `frames` and `full` move with each job and are the fields that mean something.
That is a reporting wrinkle, not a behaviour, and it is recorded because a panel would show it.

## 4. The finding: the replay ran and there was no input in it

**The engine says `exact` and then does no replay.** In all three `engine-lite` runs the sequence is
identical:

```
  catch_up state=exact  full=compiling  replay=running  running=true   blocks=0  frames=14539
  ... 264-279 ms later ...
  catch_up state=exact  full=published  replay=no_input running=false  blocks=0  frames=14539
```

(Those two lines are the two distinct states the polls caught in each of the three runs; the gap is
the time between the `running` poll and the `no_input` poll, 264, 276 and 279 ms.)

`catch_up.blocks` is set only where a replay was actually applied (`replay_window`'s result, "exact"
being claimed only when every chain was covered), so **`blocks: 0` means no input was ever replayed**
— not "a little", none. `catch_up.replay: no_input` is the outcome code the daemon sets when the
window it built never covered what the chain needs. The engine then publishes the Full anyway and the
render thread fades it in, which is why the timing looks healthy: **the Full arrives at ~315 ms and
arrives cold.** P8's whole reason for the Lite standing in — that the Full is *right*, not merely
present, before it is heard — is not holding on this board.

Against the engine's own evidence this is board-specific, not a design failure: the daemon test
`"a model with unbounded memory is refused a catch-up"` and the file-backend two-step test both assert
`replay == "exact"` and `blocks > 1` and pass in the container. The difference on the board is the
producer: the history ring is filled by `write_input_history()` on the render path, from the ALSA
capture, and the catch-up thread drained a ring that never had enough contiguous blocks in it. The
input it needs is 303 ms; the ring held it for ~270 ms of wall clock and had 14,539 frames of
requirement against it. This needs the engine's own instrumentation (the ring's `dropped` counter and
its head/tail are not exposed in `engine.status`) and is **handed to the engine**: no `gdb` and no
debug symbols' worth of introspection exist on the board, and guessing at it from outside is not
worth the board time.

**What this run does not claim**: that the bit-identity property is broken. The engine's tests achieve
it. What is measured here is that on the pedal, at every press, the replay that is supposed to
establish it did not run.

## 5. The audible rig, and whether the publish disturbed it

`render.over_deadline` did not move across any run — **0 before and 0 after** — and `xruns` stayed
**0**, `guard_trips` 0. The worst block seen during the whole session was 245.9 µs against the
1333.3 µs deadline (18.4%), and the arms' own `worst_us` before/after pairs are identical, so nothing
in the publish path pushed the render thread. The warm set moved correctly around the presses and the
`audible_generation` of the chain tracked each document as it landed.

## 6. The refusal path, on the pedal

**Confirmed, and exactly as designed.** The LSTM rig alone is not the case — an LSTM document has
nothing slimmable in it, so a Lite-first publish of it answers `nothing_to_trim` and never has a Full
behind it to be refused (that is its own correct behaviour, and it is worth knowing that this is what
`t9-lstm.json` on its own produces). The case the design is about is a chain with **a slimmable model
*and* the LSTM**, which is what the engine's own test uses; `scripts/t9-rigs mixed` builds it and
`build/vip/lite-first/refusal-mixed.json` is the record.

`rig.switch` to that rig with `lite_first: true`, from `t9-base.json`:

```
reply.lite  {"trimmed": true, "verdict": "trimmed", "cost": 0.32112, "full_cost": 0.39882,
             "generation": 30, "slimmed_models": [{"node": "amp0", "row": "NAM.WaveNet.lite", ...}]}
reply.full  {"state": "compiling", "catch_up": {
                "state": "unbounded", "replay": "none", "frames": 0, "blocks": 0, "running": false,
                "detail": "node 'amp1' (nc.nam): '/var/lib/pedal/library/models/t9-lstm.nam':
                           unbounded -- LSTM has unbounded memory; replay cannot be exact"}}
```

and then, polled:

```
    10 ms  gen=30 aud=30 trans=False  state=unbounded  full=compiling   lite_first=True
    50 ms  gen=31 aud=30 trans=True   state=unbounded  full=published   lite_first=True
    84 ms  gen=31 aud=31 trans=False  state=unbounded  full=published   lite_first=False
```

So: **the refusal names the node** (`amp1`, `nc.nam`), the file, and the reason (`LSTM has unbounded
memory; replay cannot be exact`); `frames` is 0, so nothing was recorded for a replay that cannot be
exact; **the Full is still published** (`full: published`, generation 31, and the chain's and the
engine's `audible_generation` both reach 31) rather than the press ending in silence or the Lite being
left standing; and `cost.lite_first` clears once the Full plays. The Lite was audible at 30 and the
Full at 31, 84 ms after the press. That is P8's rule for the `Unbounded` case holding on the pedal:
refuse to *promise*, never refuse to publish, and never a silent cold Full.

One reporting wrinkle worth recording because a panel would show it: in the settled status the LSTM
rig reads `catch_up.replay: "no_input"`, not `"none"` as the reply said. That is the *previous* job's
replay state still in `catch_up_report_` — the unbounded path never arms a catch-up, so nothing
clears the field — and it is cosmetic (the `state`, `blocks` and `detail` are all correct) but it
means `replay` cannot be read on its own.

`scripts/t9-rigs restore` then put the pedal back: the three test rigs and `t9-lstm.nam` removed,
`last.json`/`last.prev.json` restored and reloaded, pedald restarted, library back to
`last.json last.prev.json`, `namchaind` and `pedald` active, `xruns` 0.

## 7. What this does not settle

* **The physical footswitch press.** Everything here is driven through the service or the control
  socket; the press through the Pico's own UART path is **3.8's**, and T9's "to the jack" reading
  needs it plus a capture at the output. Not claimed.
* **A heavier Full.** One model into one cab, on vip. A two-model or multi-chain Full has a longer
  compile, and whether the Lite-first promise holds there is a different measurement.
* **The first press after a real boot** with the card cold. These runs load the base rig first, so
  the page cache is warm; T9's literal "after boot, SD card cold" reading is not what was measured.
* **Whether the Full was actually correct when it became audible.** It was not: §4. The bit-identity
  *property* is proven by the engine's own tests; that the pedal's publish path achieves it is not,
  and this run says it does not.
* **A cold press through the service.** Every press the service made was a handover; §2 says why and
  what it would take to force one.
