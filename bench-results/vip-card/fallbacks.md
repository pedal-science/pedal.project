# vip's fallbacks rehearsed: docs/vip-image.md step 6, 2026-09-30

Pass 1 on the card from image 20260930T135950Z (namchain f422dd0), pass 2 on 20260930T151625Z
(rtpi 8601757: vip-reimage in rescue), the Debug Probe on the UART header. Pass 1 is everything
that doesn't break the pedal root on purpose; pass 2 breaks it, restores it, and pulls the power.
Console logs: `console-step6-pass1.log`, `console-step6-pass2.log`. **All pass.**

## Pass 1

| # | Did | Came back | Result |
|---|---|---|---|
| 1 | `vip-boot loose` | one boot to `pedal-maint.target`: **nobody could log in** ("System is booting up", `/run/nologin`), so vip was unreachable until a power cycle | **fail, fixed**: the target wants `systemd-user-sessions.service` |
| 1b | `vip-boot loose`, fixed | 27 s; no isolation, engine and tuning off, ssh works, guard 0; the next plain boot tuned | **pass** |
| 2 | `vip-boot default loose`, reboot x2, `default tuned` | loose both times, then tuned | **pass** |
| 3 | `vip-boot rescue` | 22 s: the rescue root, read-only, plain kernel, `running`, no failed units. `vip-boot status` crashed there: it made `/boot/firmware`, and the root is read-only | **pass, and a fix**: vip-boot mounts under `/run/vip-boot` when it can't make the mount point; the image makes it |
| 4 | `vip-boot stay`, reboot, `vip-boot default pedal` | rescue again, then the pedal | **pass** |
| 5 | `try-kernel 7.0.0-1020-raspi-realtime` (installed from the snapshot, initramfs by dracut as the build makes it) | 24 s: validated (sshd, WiFi address, release, PREEMPT_RT) and promoted to slot b; engine and tuning fine on 1020 | **pass** |
| 6 | `try-kernel` a candidate whose initramfs lacks `mmc_block` and `sdhci-brcmstb` | 124 s: dracut gave up, rebooted, back on 1020; `settle` marked it bad: "never validated" | **pass** |
| 7 | `try-args` with `modprobe.blacklist=brcmfmac` (boots, no WiFi) | 176 s: validation found no address, marked it bad and rebooted | **pass** |
| 8 | `try-kernel 7.0.0-1017-raspi-realtime` back, 1020 purged, `try-args` with the normal arguments to refill the other slot | both slots 1017, good; `check` green | **pass** |
| 9 | a boot with no network (WiFi masked for that boot only) | stayed on the pedal root, `namchaind` playing (178,000 blocks in 4 min), guard cleared, `multi-user.target` reached; nothing waited for the network. `step6-no-network.txt` | **pass** |

Boots take 21-27 s to ssh.

## Found

- **The loose profile locked everyone out** (1). `pedal-maint.target` replaces `multi-user.target`,
  which is what pulls in `systemd-user-sessions.service`, the unit that removes `/run/nologin`.
  The spike's stand-in target didn't show it. `test-offline-apply` now checks for it.
- **OpenSSH 10 penalises an address** whose connections close before logging in, refusing it for
  up to ten minutes ("Not allowed at this time"). Waiting for a boot looks exactly like that, and
  it kept the Mac out after (1). With keys only there's nothing to guess, so local networks are
  exempt (`PerSourcePenaltyExemptList`). IPv6 got in meanwhile: the penalty is per address.
- **A slot can be "good" with its kernel's modules gone** (8): purging 1020 left slot b good and
  unbootable in practice. vip-boot doesn't check `/lib/modules/<release>`; removing a kernel
  means refilling its slot first, as here.
- **A pedal root that hangs, or lands in emergency mode, never reboots**: PID 1 keeps feeding the
  watchdog, and there's no root password. So the boot counter never moves and the fallback to
  rescue never comes. For pass 2: emergency and rescue mode reboot, and a boot that hasn't
  reached its target in five minutes reboots (rtpi 3c55314). (9) shows a boot with no network
  reaches `multi-user.target`, so the timeout doesn't touch a pedal at a gig. **Replaced in pass
  2**, below: the timeout was the wrong test.

## Pass 2

The target timeouts were checked against the first test before running it, and were wrong: a
unit that hangs *beside* the engine blocks `multi-user.target` while `namchaind` plays and
`pedal-guard` clears the count, so the timeout would reboot a playing pedal every five minutes,
for ever, and the count would never climb. **`vip-boot deadline`** (rtpi 91bb324) replaces them:
five minutes into a pedal boot, if the boot counter still isn't cleared, it reboots so the boot
counts; a boot that reached the engine is never touched, whatever else hangs. It sleeps before
taking vip-boot's lock (held through the sleep, it would have blocked `pedal-guard` and rebooted a
healthy pedal: a test covers it). It was installed on vip by hand from rtpi 91bb324 for these
tests, and reinstalled after each `vip-reimage`; the next image carries it.

| # | Did | Came back | Result |
|---|---|---|---|
| 10 | a healthy boot with the deadline | past 5 min uptime, count 0, the deadline exited without acting | **pass** |
| 11 | a unit that hangs before `namchaind` | each boot rebooted by the deadline at 300 s with the reason written, count 1, 2, 3; the fourth boot's initramfs made rescue the default: **rescue in 16.5 min**, by itself (`step6-hang-watch.txt`) | **pass** |
| 12 | `vip-reimage pedal` from rescue | checked the image's hash, wrote 3 GB to the pedal partition, read it back to the same hash, fsck clean, pedal the default; the pedal booted without the hang, playing, library intact on pedal-data | **pass** |
| 13 | an fstab entry for a disk that isn't there | each boot waited 90 s for it, emergency mode rebooted 10 s later (the drop-in); **rescue in 6.5 min**, unreachable over the network meanwhile (`step6-fstab-watch.txt`) | **pass** |
| 14 | `vip-reimage pedal --reboot` | as 12, and straight into the pedal | **pass** |
| 15 | power pulled while pedal-resume was saving `last.json` every 3 s (two rigs applied in turn) | `last.json` whole and one of the two, no temp file left, resumed at boot; both filesystems clean (the root's orphan cleanup only) | **pass** |
| 16 | power pulled at 5 s (in the firmware, before Linux) and at 15 s (after the kernel started), then left on | count 0 and the pedal default after the third boot; the bootsel files at their exact lengths (65, 16, 256 bytes); both FAT partitions check clean | **pass** |

- The emergency drop-in's message goes to `/dev/console`, which is tty1 (HDMI), the last `console=`:
  the serial console doesn't show it. The timing does (90 s + 10 s a boot, not 300 s).
- `vip-reimage` takes about 10 minutes (two passes over the image to check it, then the write and
  the read-back).
- Debt: a restore puts back the image's pedal root, so anything applied since (here, the
  deadline) has to be applied again. That's what `devices/vip/apply` is for; rtpi files, like the
  deadline, have no such path to vip yet except the image.
