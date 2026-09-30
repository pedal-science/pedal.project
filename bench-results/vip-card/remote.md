# Reimaging vip from the Mac: docs/vip-image.md step 7, 2026-09-30

`devices/vip/make-card --remote` (`devices/common/image/remote`), on vip with the pass 2 card. No
card touched, nobody at vip.

| # | Did | Came back | Result |
|---|---|---|---|
| 1 | `make-card --remote` from the lock (pedal 2bf5db4, rtpi 529b648) | 16 min all told (6 of them the build): vip to rescue, rescue the default; 281 MB sent and checked into pedal-data (the old image kept as previous); written over the pedal root, read back to the same hash; booted once as a candidate; the image's commit, namchaind, `vip-boot-validate`; made the default. `check` green, library and rigs intact | **pass** |
| 2 | `--remote --dev` with an unreadable `namchaind.json` | sent and written as in 1; the candidate booted, namchaind failed, `--remote` refused to make it the default | **pass**, but see below |
| 3 | the broken candidate left alone | **didn't return to rescue**: `pedal-guard` had cleared the count, so the deadline rightly left the boot alone, and vip sat on a pedal that wasn't playing (a reboot would have gone to rescue, the default) | **fail, fixed** |
| 4 | `--remote --previous --image <the good build>` | 5 min: to rescue, the previous image written and made the current one on pedal-data, booted once, checked, the default | **pass** |
| 5 | `--remote` again with the fixes (pedal 438a71f, rtpi bae26dc), from a pedal root | as 1; `pedal-guard` cleared at 17.5 s, the engine up 10 s in one run; `check` green | **pass** |

## Found

- **`pedal-guard` counted a pedal that never played as good.** namchaind with a config it can't
  read fails and restarts every second, and is `active` for a moment each time; `guard-clear`
  looked once and caught one. Now the unit must stay active *in one run* (the same
  `InvocationID`) for 10 s (`--settle`), and `--remote` checks the same way. The second card's
  first boot (step 5) got it right only because namchaind had given up before the guard looked.
  A test covers a unit that restarts on every look.
- **`--previous` left the backed-out image as pedal-data's current one**, so a later plain restore
  from rescue would have put it back. It now swaps the two.
- The rescue root is read-only and holds the tools its card was written with, so `--remote` runs
  the image's own `vip-boot` and `vip-reimage` from `/run` on rescue. A kernel change isn't
  handled: `--remote` refuses when the image's kernel isn't the one vip runs (that's `vip-boot
  try-kernel`'s job, from the new root). Neither the rescue root nor the boot partitions change.
