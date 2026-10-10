# P8's catch-up on the pedal: the replay that never ran, and why (2026-10-10)

**The defect, found and fixed.** T9's run two hours earlier
(`../2026-10-10-t9-lite-first/`) found that every `lite_first` publish on the pedal ended in
`catch_up.replay: no_input` with `catch_up.blocks: 0`, so the Full was crossfaded in **cold** — the
~170 ms of wrong audio P8 exists to remove. The cause was not the history ring, although that was the
suspicion and it was the reason the ring had no counters. There were **two** faults, and the second was
only visible once the first was fixed:

1. **The render thread's patience was shorter than the window.** A covering window is filled at the
   speed of the audio clock: the ring holds the newest `frames` of input, so the catch-up thread
   reaches one `frames` after the plans exist. vip's model needs **14539 frames (303 ms)**; the patience
   was a flat **12000 (250 ms)**. The render thread gave up first, took the Full over cold, and the
   replay then found every plan abandoned. Fixed by making the bound per chain — its own memory plus a
   quarter second, floored at the old constant (`PlanSlot::catch_up_hold_frames`,
   `catch_up.hold_frames` in the report).
2. **The hand-over could not be won.** With the patience fixed, the replay ran and was exact, but the
   render thread still took the plan over on the *bound* rather than because the replay was ready
   (`hold.abandoned: 1`, `hold.exact: 0`). Two reasons, both measured on the board:
   * the history was written to the ring **before** the block's plans ran, so the ring's newest block
     was the one being rendered: the catch-up thread, feeding the plan from it as fast as blocks are
     published, was always one block *past* the state the render thread's check asked for. Measured:
     the comparison saw `lag = -1` on **every check of a whole catch-up** (see `lag-probe.txt`);
   * the check compared the sequence the catch-up thread writes **after executing** a block and asked
     for equality, which on an unpaced producer (the `file` backend of the daemon's own end-to-end
     test) can never hold, because the device renders blocks far faster than the replay is fed.

   Fixed by writing the history at the end of the block, and by deciding the hand-over on a
   **"fed through" high-water mark** (`PlanSlot::catch_up_ready`) with `>=` rather than `==`. A read
   that races the store can then only be told "not yet" for a block that is already there, never
   "ready" for one that is not.

**After the fix, on the board, three runs** (`scripts/measure-lite-first --host vip --runs 3
--engine-only --rig t9-base.json --base last.json`):

| run | Lite audible | Full audible | `catch_up.replay` | `catch_up.blocks` | `catch_up.hold` | frames held at the hand-over |
|---|---|---|---|---|---|---|
| 1 | 40.7 ms | 351.0 ms | **exact** | **247** | `exact: 1, abandoned: 0` | 13888 |
| 2 | 40.2 ms | 355.6 ms | **exact** | **248** | `exact: 2, abandoned: 0` | 14016 |
| 3 | 39.6 ms | 349.3 ms | **exact** | **248** | `exact: 3, abandoned: 0` | 14016 |

`catch_up.frames` is 14539 in every run (the model's memory, 303 ms), `hold_frames` 26560,
`window: {held: 228–229, contiguous: 228, need: 228}`, `ring.dropped: 0`,
`period_mismatch: 0`, `fill: need_met`, `progress: done`, `seq: {fed: executed}` — the hand-over reads
what has been fed and it is one block ahead of the state, as it should be. The window needs 228 blocks
and the plan was held for 13888–14016 frames (217–219 blocks) **plus the arm-to-Full window**: the
patience is 553 ms and the hand-over happened 322 ms in, i.e. the moment the window covered, not at the
bound. The poll grid is 6.9–7.7 ms, so that is inside one poll of "the window covered". The replay is
228 blocks (the window) plus ~20 mirrored while the crossfade ran, which is what `blocks` counts.

The Full is audible at **~351 ms** against **~320 ms** in the earlier run (`before-lite-first.json`).
That is not a regression: the earlier number was a *cold* Full arriving, and the extra ~30 ms is the
replay's own hand-over. P8's promise is sound at the press (40 ms) and the rig the player asked for
inside a second; the point is that the Full is now *right* when it arrives.

Every number above is from the shipped commit (`eba5eef`), measured after the container suite on
that commit came back 5/5.

The rig is unchanged from the previous run (`last.json` → `t9-base.json`: the Ampeg WaveNet into the
YA AMPG 410 HS mix), and the Lite's own numbers are identical (`cost` 0.07112, `full_cost` 0.14882,
`NAM.WaveNet.lite`, `adopted: true`).

**Nothing disturbed what was playing.** `render.over_deadline` 0 and `xruns` 0 before and after every
run, `guard_trips` 0, worst block 218.5 µs of the 1333.3 µs deadline (16.4%).

## What the counters show, which is the other half of this

`engine.status.catch_up` now carries the history's own account: the ring's `armed`, `written`,
`consumed`, `dropped`, `head`, `tail` and the sequences at each end; the window's `held`,
`contiguous`, `blocks` and `need`; the catch-up thread's `progress` and why its fill stopped (`fill`);
`hold_frames`, and `hold` with which way the hand-over went. It is what turned "`no_input`" into "the
window covered, the replay was exact, and the render thread had already given up" — a sentence no
debugger could have produced on a board with neither `gdb` nor ptrace. The fields, and what each one
means, are in `namchain/docs/daemon.md` under "Lite-first publishes".

## Commands

On the board, holding the host lock, one at a time:

```sh
cd pedal.project
scripts/t9-rigs --host vip setup                      # stage t9-base.json and t9-lstm.json
scripts/measure-lite-first --host vip --runs 3 --engine-only \
    --rig t9-base.json --base last.json               # the table above
scripts/t9-rigs --host vip restore                    # put the pedal back
```

Raw: `after-lite-first.json` (every poll of all six runs after the fix, including the ring, window and
hold fields), `before-lite-first.json` (the same harness before it: `no_input`/`blocks: 0`), and
`lag-probe.txt` (the `previous_block - catch_up_seq` probe that found the ordering fault).

Engine: `namchain` `eba5eef` — the counters `141a3f3`, the hold budget `1983083`, the end-of-block
history `3b694bd`, the "fed through" hand-over `b496f52`, the sequence report `07b929c` and its
counter fix `eba5eef`, plus the de-flaked `levels_first_frame` case `c5b93b1` that was failing in the
container and blocking deploys from there. The container suite
(`devices/common/image/build-namchain`, snapshot `20260929T000000Z`) is 5/5 on that commit, and the
suite is green on the Mac (369/369 cases, 272812 assertions).

## What this does not claim

* **The bit-identity of the blocks after the hand-over on the pedal.** That is asserted by
  `tests/test_catch_up.cpp` and by the daemon's end-to-end case on the `file` backend, not measured at
  the pedal's output: nothing here captured the codec's audio during a press.
* **A press through the service.** This is the engine arm; pedald's `rig_up`/`rig_select` are the
  handover arms measured in the earlier run and are unchanged.
* **A heavier Full.** One model, one cab. A Full whose compile outruns the ring's slack is still the
  documented `gap` case, and the counters now show it rather than hiding it.
