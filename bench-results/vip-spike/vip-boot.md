# vip-boot on vip: step 2's smoke test, 2026-09-29

rtpi's `vip-boot` (`devices/vip/`), run on the spike card in vip ahead of the real image, to find
what the unit tests can't: the initramfs, the units' ordering, FAT written in place across reboots.
Not step 6's rehearsal: that runs on the real card, with the real rescue root and the RT kernel.

**Setup.** On the spike root: rtpi's vip files, `/etc/rtpi/device.env` with
`PEDAL_ROOT_LABEL=spike-root` and the stock kernel, `python3-minimal`, the initramfs rebuilt with
`vip-guard`. Partition 2 and bootsel rebuilt by `vip-boot init-pedal-boot` / `init-bootsel`, as
the image build will. Partition 3 stayed the spike's, standing in for rescue (so `root=?` there).
Spike-only: `pedal-guard` clears without waiting for `namchaind` (there is none), and a stand-in
`pedal-maint.target`. Console: `console-vipboot.log`.

## Results

| # | Did | Came back | Result |
|---|---|---|---|
| 1 | boot the new layout | slot a, tuned, isolation args on | **pass** |
| 2 | `pedal-guard` off, reboot ×4 | count 1, 2, 3; the 4th boot's initramfs made rescue the default and rebooted into partition 3 (35 s) | **pass** |
| 3 | reboot in rescue | partition 3 again | **pass**: sticky |
| 4 | `vip-boot default pedal` | slot a, guard 0 | **pass** |
| 5 | `try-kernel` | slot b validated (sshd, wlan0, route, release) and promoted; stays default after a plain reboot | **pass** (second attempt, see 2 below) |
| 6 | `try-args '… root=LABEL=nope'` | 129 s: dracut gave up, rebooted, back on slot b; `settle` marked slot a bad with the reason | **pass** |
| 7 | `vip-boot loose` without `pedal-maint.target` | refused | **pass** |
| 8 | `vip-boot loose` | one boot to `pedal-maint.target`, no isolation; the next plain boot tuned | **pass** |
| 9 | `default loose`, reboot ×2, `default tuned` | loose until switched back; `pedal-guard-maint` clears the count | **pass** |
| 10 | `vip-boot rescue` | partition 3 once, then the pedal | **pass** |

Boots take 22-27 s to ssh.

## Found, and fixed in rtpi

1. **The initramfs counter ran before the card appeared.** dracut's hooks run under systemd here,
   and pre-mount came at 1.4 s, the card's partitions at 2.2 s, so every boot went uncounted.
   Counting later (pre-pivot) would miss the boots that matter most, the ones whose root never
   mounts, so the hook now waits up to 30 s for `BOOTSEL` to appear.
2. **Validation queued behind `network-online.target`**, which with no cable in `eth0` waits up to
   2 minutes. The test rebooted before validation ran, and `settle` marked a good candidate bad
   (the safe direction, and exactly its job). The unit no longer waits for it; the hook waits for
   sshd and an address itself. The image must also set `RequiredForOnline=no` on `eth0`.
3. **`wc`, `head` and `sleep` weren't in the initramfs** (resolute's coreutils are uutils; its
   `dd conv=notrunc,fsync` does the in-place write correctly).
4. **A loose boot with no `pedal-maint.target`** would drop systemd to emergency mode, with no
   network until a power cycle. `vip-boot loose` and `default loose` now refuse.

## For the image (step 4)

- `ca-certificates` in both roots: without it apt can't reach the https snapshot.
- `eth0`: `RequiredForOnline=no`.
- The root needs room for dracut's work directory (~150 MB): the spike's 850 MB root ran out.
