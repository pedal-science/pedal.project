# O5: rigpa follows the pedal

2026-11-09. rigpa `129f178` and `f32bb2a`, pedald `47013fe` (autosave on), on the Mac and on vip.

## On the Mac

All 29 of rigpa's test suites pass against a real `namchaind` and `pedald`. The new ones:

- **`tst_follow_live`:** another app's edit reaches rigpa's document in under 100 ms, from the request going out.
  The play line says "Ljoss: …", and a press shows as "Rig up → Lead". rigpa undoes another app's edit through
  pedald and redoes it, and picking a rig goes through `PUT /running` ("Rigpa → Clean"). A Low Cut added from the
  pedal's templates is named "Low Cut" and edited with its own controls, which reach the engine's `low_cut` and
  `low_slope`.
- **`tst_engineevents`, `tst_pedaldevents`, `tst_templates`, `tst_banks`:** the engine's pushed frames, pedald's event
  stream, the 27 templates and their transforms, and moving rigs between banks.
- **The lane-gain case in `tst_edits`:** a Gain block placed last in a lane stays a block.

`screenshots/` holds both layouts against a dev pedal:

- **Compact:** play, with the cause line after a press (`compact-play-cause.png`), rigs, banks, and the palette of
  templates.
- **Wide:** the rig view, and banks.

## On vip

rigpa `f32bb2a` is installed and pedald's `autosave` is true (`check-vip.py`, `run/check-vip.json`):

- **Saving:** a named app's edit to Bob was in `Bob.json` 1.1 s later.
- **Undo:** it showed as one undo step, and `POST /undo` put Bob back, in the file too.

## Found on the way

- **Saving stopped on a first start (pedald, `2282b09`).** With no record to trust, pedald took the engine's copy of a
  rig differing from its file as a structural change, and stopped saving. The engine writes defaults out, so every
  real rig differed. It now keeps the engine's shape and treats only differing values as a performance.
- **rigpa's own edits looked stale.** A change of rigpa's still on its way made its next whole-document apply look
  stale. rigpa now sends `if_seq` only when nothing of its own is in flight.
- **The first deploy didn't install rigpa.** The image build's container has no `pedal.project` beside rigpa, so
  `tst_templates` failed and rigpa wasn't installed. For about 20 minutes vip ran the old rigpa beside pedald with
  autosave on, and both saved. The test now skips there (`f32bb2a`), and the second deploy installed it.

## What this doesn't cover

- **rigpa on vip's panel:** nobody has looked at it on the screen, so the screenshots are from the Mac.
- **The Banks page on vip:** it hasn't been used there; it's covered by tests on the Mac.
- **Bank tabs:** the Banks page opens from Rigs (compact) and from the header (wide), rather than a tab in Rigs and a
  panel beside the rig list as the plan put it.
- **Old rigs:** blocks made before templates carry no `meta`, so they show and edit as before, by their engine nodes.
