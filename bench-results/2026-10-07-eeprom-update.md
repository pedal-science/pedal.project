# The bootloader EEPROM: off the package, onto a pinned image

**Status: done, 2026-10-07.** vip went from the factory `66f33f7e` (2026-05-11) to `1accd665`
(2026-09-25) in one staged update and one reboot, with the EEPROM configuration carried across
unchanged, and the `tryboot` path re-verified under the new firmware. The recording is in
`devices/vip/` (`eeprom.lock`, `eeprom-fetch`, `rootfs/usr/local/sbin/vip-eeprom`) and in the
`check` block that diffs it; [docs/vip-image.md](../docs/vip-image.md), "The bootloader EEPROM", is
the design and the reasons.

## Why Ubuntu's package cannot do it

`rpi-eeprom-update` never looks at the network. It compares the running EEPROM's timestamp against
the newest `pieeprom-YYYY-MM-DD.bin` that is exactly 2 MiB in one directory,
`${FIRMWARE_ROOT}-2712/${FIRMWARE_RELEASE_STATUS}` — on vip `/usr/lib/firmware/raspberrypi/bootloader-2712/default`,
which the Ubuntu package fills from the snapshot. That package's images are *older* than the board:

| | newest image | build |
|---|---|---|
| package `default/` | `pieeprom-2025-12-08.bin` | 2025-12-08 |
| package `latest/` | `pieeprom-2026-02-23.bin` | 2026-02-23 |
| the board, from the factory | `pieeprom-2026-05-11.bin` | 2026-05-11 |
| upstream `default/` and `latest/` | `pieeprom-2026-09-25.bin` | 2026-09-25 |

So the tool reports the board as up to date, and switching `FIRMWARE_RELEASE_STATUS` to `latest`
would only offer to go *backwards*. The "Use raspi-config to change the release" line is
`${RPI_EEPROM_UPDATE_CONFIG_TOOL}`, cosmetic, and vip has no raspi-config; the release is a
subdirectory name and the root is a variable, both settable in `/etc/default/rpi-eeprom-update` or
the environment. `FIRMWARE_ROOT` from the environment wins over the packaged tree — proved with a
directory that does not exist:

```
$ FIRMWARE_ROOT=/var/tmp/nope rpi-eeprom-update -l
EEPROM updates directory /var/tmp/nope/default not found.        (exit 2)
```

## What is pinned

`raspberrypi/rpi-eeprom` at `3da76c3b6fe6272d0c54b32ffa4dfe8ed0deddbb` ("pieeprom-2026-09-25:
2712: Promote to the default release", 2026-09-27), `firmware-2712/default/`:

| File | Bytes | sha256 |
|---|---|---|
| `pieeprom-2026-09-25.bin` | 2097152 | `02c4daa25df5af66af50da63ee97dfd03b21a40ac5b495a1c447979a2aa00edd` |
| `recovery.bin` | 104314 | `29bbbbba21b532fbde8943adf6ad1e657c8ac0013b66e6d60f8212894d86b024` |

Its metadata, read from the file rather than taken on trust: `VERSIONINFO 2026/09/25 15:59:09
1accd665 R 2712 MFG02` → `VERSION:1accd665`, `BUILD_TIMESTAMP=1790351949`, `MFG_VER: 2`, and a
`bootsys` section at 0x10008 — the A/B layout that arrived upstream on 2026-05-13. Its embedded
configuration is byte-identical to the one vip runs (`BOOT_UART=1`, `BOOT_ORDER=0xf461`,
`NET_INSTALL_AT_POWER_ON=1`), which is upstream's stock default: nothing here is bespoke. The board's
`rpi-min-boot-ver` is 1, so an `MFG_VER 2` candidate passes the firmware's own check.

## The dry run, before anything was written

A temporary tree at `/var/tmp/rpi-eeprom-dryrun/bootloader-2712/default/`, no root, nothing mounted:

```
$ rpi-eeprom-update                                     # dpkg's tree
BOOTLOADER: up to date
   CURRENT: Mon May 11 11:20:02 UTC 2026 (1778498402)
    LATEST: Mon Dec  8 19:29:54 UTC 2025 (1765222194)

$ FIRMWARE_ROOT=/var/tmp/rpi-eeprom-dryrun/bootloader rpi-eeprom-update
*** UPDATE AVAILABLE ***
BOOTLOADER: update available
   CURRENT: Mon May 11 11:20:02 UTC 2026 (1778498402)
    LATEST: Fri Sep 25 15:59:09 UTC 2026 (1790351949)
   RELEASE: default (/var/tmp/rpi-eeprom-dryrun/bootloader-2712/default)   (exit 1)
```

`-l` resolved to the pinned image, `-b` to `/boot/firmware`, and `rpi-eeprom-config` on the
candidate printed the three keys above. The tree was removed afterwards; nothing was staged.

## The update

`devices/vip/eeprom-fetch` installed the pinned bytes into
`/usr/local/lib/rpi-eeprom/bootloader-2712/default/` (sha256 verified on the Mac *and* read back on
the board), `devices/vip/apply` put `vip-eeprom` and `eeprom.lock` in place and `check` was green,
including the new block:

```
==> bootloader EEPROM: eeprom.lock against what vip carries
  ok    version 66f33f7e, built 2026-05-11 11:20:02
  ok    config 1/0xf461/1
  ok    pinned pieeprom-2026-09-25.bin
  ok    pinned recovery.bin
```

`sudo vip-eeprom apply` then mounted the pedal boot partition, ran the packaged tool with
`FIRMWARE_ROOT` set, and staged into it:

```
    BOOTFS: /boot/firmware
'/tmp/tmp.qboyCCCukr' -> '/boot/firmware/pieeprom.upd'
Copying recovery.bin to /boot/firmware for EEPROM update
EEPROM updates pending. Please reboot to apply the update.
    staged image: 1accd665, BUILD_TIMESTAMP=1790351949
      pieeprom.sig    80 bytes
      pieeprom.upd    2097152 bytes   sha256 6b927c25a0097831229d508bb3bbaa6471edbeba1f300ab8e60fb72e9e482edd
      recovery.bin    104314 bytes    sha256 29bbbbba21b532fbde8943adf6ad1e657c8ac0013b66e6d60f8212894d86b024
```

(`pieeprom.upd` differs from the pinned image because the tool embeds the running configuration and
a fresh timestamp — that is the mechanism that carries the configuration across.)

One reboot later, 50 seconds for the whole two-boot cycle:

| | before | after |
|---|---|---|
| `vcgencmd bootloader_version` | `66f33f7e…`, 2026/05/11 12:20:02, `update-time 0` | `1accd6659983613…`, 2026/09/25 15:59:09, `update-time 1791402967` |
| configuration | `BOOT_UART=1 BOOT_ORDER=0xf461 NET_INSTALL_AT_POWER_ON=1` | the same three, unchanged |
| boot partition | `a/ b/ config.txt profile.txt tryboot.txt` | the same, plus the ROM's `RECOVERY.000` |
| `vip-boot status` | `slot=a profile=tuned tryboot=0 partition=2`, both slots `good`, guard 0 of 3 | identical |
| engine | `namchaind` stopped for the apply | `namchaind` and `pedald` active |

`RECOVERY.000` is the ROM saying it ran `recovery.bin`: it renames the file after a successful write
and resets, which is why Linux never runs that boot and why `bootsel`, the slot markers and the
guard counter are untouched. `sudo vip-eeprom clean` removes the leftovers (`recovery.000`,
`pieeprom.upd`, `pieeprom.sig`) — on Raspberry Pi OS the `rpi-eeprom-update` service does that at
every boot, and it is masked here, so nothing else would.

## The tryboot check, under the new firmware

`autoboot.txt`, `tryboot_a_b`, `os_prefix`, `include` and `reboot "N"` are firmware behaviour, last
proven on the factory image. `vip-boot loose` re-runs the one-shot without touching the slots:

```
running    root=pedal slot=a profile=loose tryboot=1 partition=2 kernel=7.0.0-1017-raspi-realtime-numaemu1-trimmed
default    root=pedal slot=a profile=tuned
slot a *   good     7.0.0-1017-raspi-realtime-numaemu1-trimmed
slot b     good     7.0.0-1017-raspi-realtime
cmdline: … systemd.unit=pedal-maint.target vipboot.root=pedal vipboot.slot=a vipboot.profile=loose
```

`tryboot=1` at boot is the flag having been armed and consumed; `partition=2` is `autoboot.txt` on
partition 1 selecting the pedal partition through its `[tryboot]` section; the `cmdline` shows
`[tryboot] include tryboot.txt` being honoured and `os_prefix=a/` resolving `cmdline-loose.txt`
inside the slot. `pedal-maint.target` was active and `namchaind` inactive, the loose profile doing
what it says; the default stayed `tuned`, both slots stayed `good`, and the guard counter stayed at
0 of 3. Rebooting returned to `tuned` with `tryboot=0` and the engine up. The open upstream issue
for this class of layout ([rpi-eeprom#818](https://github.com/raspberrypi/rpi-eeprom/issues/818),
autoboot+tryboot on GPT, which fails as a boot loop) does not bite this card: its FAT partitions are
contiguous 1/2/3, and `bootsel` is 64 MB FAT32 — the sizes the reporters found fixed it.

## What this does not cover

- **No rollback on the board.** The firmware that came with vip has no A/B EEPROM; the new one does,
  but using it needs newer tooling (`rpi-eeprom-ab`, `AB_EEPROM_FORCE_COMMIT=0`) than the snapshot's
  28.14, and the migration from a non-A/B EEPROM is undocumented. A power cut during the write is
  still the one failure this board cannot fix by itself: Raspberry Pi Imager's
  `Misc utility images → Bootloader → SD Card Boot`, or `rpiboot` over USB-C.
- **The card does not carry the tree.** `eeprom-fetch` installs it on the host from the pin; a fresh
  card has none, and `check` reports that as `--` rather than a failure. Baking it into the image
  build is a separate, deliberate change.
- **The configuration is upstream's default**, so nothing here records a deliberate choice:
  `NET_INSTALL_AT_POWER_ON=1` still spends about a second of cold boot on keyboard and
  network-install probing the pedal does not need. Changing it is `rpi-eeprom-config --apply` — a
  configuration write, not an image update, and still an EEPROM write.
