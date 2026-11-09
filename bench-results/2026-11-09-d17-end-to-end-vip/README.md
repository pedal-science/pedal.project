# D17 end to end on vip (2026-11-09)

The check in [docs/pedal-owns-state.md](../../docs/pedal-owns-state.md), "Verification, end to end",
run after O1–O9 against vip, with ljoss on this Mac (`Tools/run`, ljoss `374ad6d`, then `8b6cd8a`)
and rigpa on this Mac against vip in the compact layout (rigpa `3aff011`). Real footswitches were
pressed by Rik. pedald's event stream for the whole run is [events.sse](events.sse).

**Result: every step passes, after one fix to ljoss** (`8b6cd8a`, below). Three parts were run
in a different way from the plan's wording, and two can't be checked yet; both are listed under
"How each step was run".

| Step | Result | Evidence |
|---|---|---|
| 1. ljoss finds vip and shows it connected | Pass | [1-pedals.png](1-pedals.png) |
| …pro hidden unless "Show disconnected" | Not checkable: pro has no `pedald`, so it isn't a pedal ljoss can meet | — |
| 2. First meeting: both boxes ticked; one file unticked; both ways; a clash renamed; nothing deleted | Pass | [2-compare.png](2-compare.png), [2-compare-after.png](2-compare-after.png) |
| 3. A rig built in ljoss plays, rigpa shows the same blocks, the pedal saved it unasked | Pass | [3-ljoss.png](3-ljoss.png), [3-rigpa-play.png](3-rigpa-play.png), [3-stored.json](3-stored.json) = [3-engine.json](3-engine.json) |
| 4. Footswitch 2 switches and both apps say so | Pass | events.sse |
| …Footswitch 3 toggles a block in every app, the stored rig is unchanged, reloading restores it | Pass | [4-ljoss.png](4-ljoss.png), [4-rigpa.png](4-rigpa.png), [4-stored.json](4-stored.json), [4-ljoss-reloaded.png](4-ljoss-reloaded.png), [4-rigpa-reloaded.png](4-rigpa-reloaded.png) |
| 5. Undo on rigpa reverts ljoss's edit | Pass | [5-rigpa-undo.png](5-rigpa-undo.png), [5-ljoss-after-undo.png](5-ljoss-after-undo.png) |
| …after a restart, undo works and the toggle still plays, unsaved | Pass **after the fix** | below |
| 6. ljoss with no pedal: empty, no editing, Models & IRs works | Pass | [6-offline.png](6-offline.png), [6-offline-models.png](6-offline-models.png) |

## What happened

**1–2.** ljoss, relaunched after it was made to forget that it had compared files with vip,
found vip over DNS-SD and opened the comparison by itself. Five test IRs (one byte apart) were set up
first: one only on the Mac, two only on vip, and one path on both with different content. The sheet
offered 2 files to vip and 3 to ljoss, every box ticked; `E2E unticked.wav` was unticked. After
Copy, by hash:

| File | Mac | vip |
|---|---|---|
| `E2E mac.wav` | had it | got it, same hash |
| `E2E vip.wav` | got it, same hash | had it |
| `E2E clash.wav` | kept its own | kept its own |
| `E2E clash (vip).wav` / `E2E clash (M2).wav` | got vip's | got the Mac's |
| `E2E unticked.wav` | **not copied** | kept |

Nothing on either side was deleted or replaced.

**3.** New Rig in ljoss, then Low Cut, Tilt EQ, Tape Echo and High Cut from the palette. ljoss
said "Saved on the pedal". `GET /library/rigs/New Rig 2` equals the engine's `rig.get` exactly,
each node carrying its template (`eq.lowcut`, `eq.tilt`, `delay.tape`, `eq.highcut`). rigpa's Play
view shows the same four blocks under the same names.

**4.** Footswitch 3 was mapped to the Tape Echo for this step (`state/midi-map.json`,
`{"cc": {"82": {"block": …}}}`, with a backup first; removed afterwards). Rik pressed 2, 1 and 3:

```
footswitch 2 → load Bob (warm)
footswitch 1 → load New Rig 2 (cold)
footswitch 3 → block 8BF86D2A-… bypass true
```

ljoss and rigpa both showed "Footswitch 3 → Tape Echo off" with the block off. The engine had it
bypassed; `/running` listed it under `performance`; the stored rig was byte-for-byte unchanged.
Picking the rig again in ljoss (after step 5) brought the echo back, with `performance` empty.

**5.** Tilt to +4 dB in ljoss: the stored rig had `tilt: 4.0` with nobody pressing Save, and still no
bypass on the echo. Undo in rigpa: the engine, the stored rig and ljoss all went back to 0.0 dB
(undo 5 → 4, redo 0 → 1), and the echo stayed bypassed. **vip was rebooted** (`uptime` 0 min after):
the echo was still bypassed and playing, still a performance and not stored, and the history came
back (undo 4, redo 1).

That is where the fault showed. Undo in ljoss after the reboot worked on the pedal, but ljoss then
said "vip changed while you were editing, so ljoss shows its version and your last change wasn't
made", and a block added in ljoss was refused. **ljoss kept the engine's `seq` as the highest it had
seen**, and the restarted engine counts from 1 again, so every structural edit went with `if_seq`
2217 and was refused until ljoss itself restarted. ljoss `8b6cd8a` forgets the number on each new
connection. Checked with `namchaind` restarted under a running ljoss: a block added in ljoss reached
the engine, and an Undo published once with no conflict. The echo's toggle survived the engine
restart too.

**6.** With `pedald` and `namchaind` stopped on vip, ljoss dropped the rig list and the editor and
said it was trying again, with Try Again; Settings → Models & IRs listed the 593 files and rescanned.
Once the services were started again, ljoss went back to the rig by itself.

## How each step was run, where it differs from the plan

- **"A fresh card"** (step 2): simulated by removing vip's id from ljoss's `pedals.compared`. This
  is the record of a first meeting, and a new card is a new id, so the sheet behaves the same way.
- **pro** (step 1): ljoss knows only pedals it has met through `pedald`, and pro runs `namchaind`
  alone. "Show disconnected" needs a second pedal before it can be checked. While vip itself was
  down it stayed listed, because it is the selected pedal, with its error and Try Again.
- **The panel** (step 3): rigpa ran on this Mac against vip (the same code and events as the unit on
  vip). The panel itself is still to be checked by eye, as `plan.md` says.
- **Undo on rigpa** (step 5): rigpa's Qt view takes no clicks from a background driver, so
  a second rigpa against vip pressed Undo with `--input U` (its Undo key since rigpa `1c6fc8d`),
  through the same code as the button.
- **Off the network** (step 6): this session and vip share the Mac's Wi-Fi, so vip's two services
  were stopped instead. To ljoss, that is the same as a pedal that can't be reached.

## Noted, not changed

- **`/running`'s `modified` is true during a performance.** pedald defines it as "differs from the
  stored copy", and neither app marks the rig unsaved (rigpa's header says "saved"; ljoss "Saved on
  the pedal"). D17's words are "do not mark the rig modified". What the apps show matches D17; the
  field's name doesn't, if anything reads it as "unsaved".
- **Tapping an amp in ljoss's palette** opens its inspector with the model unchosen. The pedal gets
  nothing until a model is picked, and Remove Block leaves nothing behind, so D17's "picker first"
  default holds. The model menu can't be opened by accessibility, so amps weren't part of this run.
- **vip's health is `warn` on rigs from templates:** nodes such as `-tone`, `-cab` and `-cut` have
  no row in `devices/vip/cost.json` and are charged the guessed 0.05 of a core (`cost_unknown`).
  `pedal-measure` can measure them.

vip was left as found: the map file removed, `pedald` restarted, both services active. The test files
and rigs stay; they are test data.
