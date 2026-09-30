# vip's fallbacks rehearsed: docs/vip-image.md step 6, 2026-09-30

On the card from image 20260930T135950Z (namchain f422dd0), with vip-boot as built, the Debug Probe
on the UART header. Pass 1 is everything that doesn't break the pedal root on purpose; pass 2 (a
broken pedal root reaching rescue by itself, vip-reimage, power pulled) needs the next image.

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
  reaches `multi-user.target`, so the timeout doesn't touch a pedal at a gig.
