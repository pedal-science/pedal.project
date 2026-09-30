# vip's first cards: docs/vip-image.md step 5, 2026-09-30

The 32 GB card, written with `devices/common/write-card` from `make-card`'s image, put in vip with
the Debug Probe on the UART header. Console logs: `console-first-card-firstboot-hang.log`,
`console-second-card.log`.

## The first card (image 20260929T232637Z): hung at systemd-firstboot

The firmware read `autoboot.txt`, `config.txt`, `profile.txt` and `a/cmdline-tuned.txt`, and
started the RT kernel; the initramfs mounted the pedal root. Then nothing: no login prompt on the
UART, no network, for ten minutes. `/etc/machine-id` said `uninitialized`, which makes it a first
boot, so `systemd-firstboot` asked for a locale, a keymap, a timezone and a root password on tty1
(HDMI) with the other consoles muted, and nothing after `sysinit.target` started. The spike
didn't hit it: mmdebstrap leaves machine-id empty, which isn't a first boot. Rescue wouldn't have
(the unit needs a writable `/etc`).

Fixed in the build: machine-id empty, `systemd-firstboot` masked in both roots. Also
`dtparam=audio=off` is gone: the firmware said "Unknown dtparam 'audio' - ignored".

## The second card (image 20260930T124711Z)

| Check | Seen | Result |
|---|---|---|
| boots onto the network with no other step | `ssh vip`, `vip.local` (mDNS) and `vip.fritz.box`, 16.6 s to `graphical.target` | **pass** |
| the host key is 1Password's | `ssh-keyscan` matches `fx/vip-ssh-host`'s public key | **pass** |
| pedal root, RT kernel, tuned | `7.0.0-1017-raspi-realtime`, slot a, isolation arguments on | **pass** |
| pedal-data grows to fill the card | `systemd-repart` grew partition 6 on first boot; `x-systemd.growfs`: 23 GB | **pass** |
| the codec | `pedal-codec` loaded the overlay at 5.9 s | **pass** |
| `devices/vip/check` green | one FAIL, a false one: IRQ 138's `effective_affinity_list` is empty on the RP1's chained chip, while `smp_affinity_list` is 2 and every count is on CPU 2. `pedal-tune check` now falls back (b9a7751), applied with `devices/vip/apply`: green | **pass after a fix to the check** |
| `namchaind` running the default rig | failed at boot: pedal-data has no library, and the default rig's model isn't there. After the library was copied: running, 52 models, `failed_nodes` 0 | **fail as built** |
| `components.lock` matches the manifest | it records one Core host, piv; `devices/vip/apply` overwrote it with vip's (restored: step 8 moves the Core host) | **deferred to step 8** |
| memory | 179 MB used of 965 MB with `namchaind` running | — |

## What it means

- **A missing library sends the pedal to rescue.** `namchaind` exits when the rig names a model
  that isn't there, systemd gives up after five restarts, `pedal-guard` doesn't clear the count,
  and three such boots would make rescue the default. This boot got to 1 of 3. A data problem
  (the library, a rig) then looks the same as a broken system, which isn't what the guard is for.
- **The card has no library of its own.** vip has no `rsync`, which `sync-library` needs (added to
  `devices/vip/packages` for the next image). The library went over with tar through ssh. The
  Mac's copy is in iCloud Drive and mostly evicted, so the 1,901 IRs came down from iCloud first:
  slow (about a minute for 60 files).

## Decided, 2026-09-30

- **The card doesn't carry the library.** It's synced after first boot (`scripts/sync-library
  --host vip`); `rsync` is in the next image for it.
- **A missing model or IR plays as a bypass**, and ljoss shows the block as not configured.
  namchain f422dd0: the block is stood in for by `nc.bypass` on the compiled copy, reported as an
  `asset_missing` issue keyed by the block's element, and a library rescan (what `sync-library`
  sends) republishes the rig so the block comes in by itself. ljoss 5da4ea6 draws it. So a fresh
  card boots to a running engine playing the default rig's blocks as bypasses, `pedal-guard`
  clears, and the sync brings the rig in.
