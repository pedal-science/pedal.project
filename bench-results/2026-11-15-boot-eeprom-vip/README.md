# Cold boot: EEPROM network-install experiment (reverted) and the console cost

**Verdict: the EEPROM change is reverted.** It removed the network-install delay (4.8 s measured
once), but cold boot was then **intermittent**: one attempt stopped at `BOOTSYS`, one booted, and a
later attempt stopped after `Starting OS` and never came up. The original EEPROM config
(`BOOT_ORDER=0xf461`, `NET_INSTALL_AT_POWER_ON=1`, no extra keys) was restored on the matching
2026-09-25 image and the board booted normally. The quiet-console change is kept; the EEPROM result
is a measured but rejected experiment, most likely because `BOOT_ORDER=0xf` removed the SD retry/
fallback path (not isolated).

Two changes measured on vip on 2026-11-15 with the official Pi PSU, same card and image. They are
both about the **pre-kernel** half that the OS cannot change from within Linux.

## 1. The bootloader network-install check cost 4.8 s on a cold boot

A cold power-on capture before the change (Debug Probe on the bootloader UART, firmware clock):

```
1.17 s  BOOTSYS release 1accd665 2026/09/25
1.23 s  uSD voltage 3.3V
2.76 s  SDC start - success
4.18 s  Boot mode: SD (01) order f4
8.68 s  SD HOST ...
9.45 s  Loading 'a/initrd.img'
11.04 s Loading 'a/vmlinuz'
12.98 s Starting OS
```

The warm-reboot capture of the same build reached `Starting OS` at **8.62 s**: the extra **4.3 s**
on a cold boot is the bootloader's network-install UI/check, not SD or kernel work.

I wrote a config-only EEPROM image from the **matching 2026-09-25 bootloader release**
(`rpi-boot-eeprom-recovery-2026-09-25-2712-sd.zip` → `pieeprom.bin`, same hash/version as
installed) with:

```
[all]
BOOT_UART=1
BOOT_ORDER=0xf
NET_INSTALL_AT_POWER_ON=0
NET_INSTALL_ENABLED=0
HDMI_DELAY=0
```

written through the BOOTSEL partition and `rpi-eeprom-update -d -f`, flashed by `recovery.bin` at
the next reboot. The bootloader version stayed `1accd665…` (2026/09/25).

After the change, one cold power-on:

```
1.15 s  BOOTSYS release 1accd665 2026/09/25
6.28 s  Read a/vmlinuz
8.17 s  Starting OS
```

`Starting OS` is **8.17 s instead of 12.98 s: 4.81 s saved**, essentially all the network-install
UI. That one boot's kernel/initrd/userspace:

| Milestone (cold boot, after EEPROM) | Value |
|---|---:|
| firmware `Starting OS` | 8.17 s |
| kernel (`systemd-analyze`) | 0.412 s |
| initrd userspace | 2.942 s |
| userspace | 16.538 s |
| rigpa active (from kernel start) | 7.365 s |
| rigpa first frame (from kernel start) | 9.226 s |
| **power-on → rigpa first frame** | **≈17.4 s** |

Before the EEPROM change the same cold-boot path was **≈21.7 s** to the first frame. The EEPROM
config was **reverted** after the cold stability failures below; the 4.8 s is real but not usable
as-is. A safer retry would keep `BOOT_ORDER=0xf461` (SD first, then USB/NVMe fallback) and only
disable `NET_INSTALL_AT_POWER_ON`/`NET_INSTALL_ENABLED`, then cold-test several times before
keeping it.

Notes:

- `BOOT_ORDER=0xf` means **SD only**: no USB or NVMe boot fallback. `NET_INSTALL_ENABLED=0` also
  removes the network-install UI/recovery route. Recovery from a bad card is reflashing the card,
  not USB/network.
- `BOOT_UART=1` was kept so the Debug Probe still sees the bootloader and `Starting OS`.
- The EEPROM update is **per board**, not in the card image; the image build does not write it.
  The matching image is needed because the installed bootloader (2026-09-25) is newer than the
  package's latest image (2026-02-23) in this snapshot.

## 2. The verbose console cost ~2 s; the serial console itself ~0.5 s

- `quiet loglevel=3 systemd.show_status=0` + serial console + early rigpa:
  first frame **9.399 s** after kernel start (kernel 0.413 s), vs **11.314 s** with the verbose
  console (kernel 2.43 s). **≈1.9 s** comes from not writing thousands of kernel/systemd lines to
  the 115200 UART.
- Same quiet args with **no `console=ttyAMA10`** (`console=tty1` only): first frame **8.853 s**
  (kernel 0.414 s). The serial console itself, once logging is quiet, adds **≈0.55 s**.
- Keeping `console=ttyAMA10` with `quiet` preserves error/panic output and the bootloader log;
  removing it is the last half-second and loses kernel debug on the probe.

The cold measurement used `console=tty1` only; the runtime has since been restored to
`quiet loglevel=3 systemd.show_status=0` **with** `console=ttyAMA10,115200` for debug, and the
EEPROM was reverted. One normal quiet+serial boot with the original EEPROM measured: kernel 0.414 s,
initrd 2.576 s, userspace 16.802 s, rigpa active 7.401 s, first frame 9.218 s after kernel. The
serial console costs ≈0.5 s versus `console=tty1` only.

The final screen target is unchanged: with the original bootloader the cold path is back to
≈13 s firmware + ≈3 s kernel/initrd + ≈9.2 s userspace/rigpa; a 5 s cold boot is not reachable on
this stack.

## Reproduce

```sh
sudo rpi-eeprom-config /tmp/pieeprom-2026-09-25.bin          # confirm the version
sudo rpi-eeprom-config --config /tmp/pieeprom.conf --out /tmp/pieeprom-new.bin /tmp/pieeprom-2026-09-25.bin
sudo mount /dev/mmcblk0p1 /boot/bootsel
sudo BOOTFS=/boot/bootsel rpi-eeprom-update -d -f /tmp/pieeprom-new.bin
# reboot, let recovery.bin run, then verify:
sudo vcgencmd bootloader_version; sudo vcgencmd bootloader_config
```

Cold boot timestamps come from `tools/measure-boot.py`; kernel/initrd/userspace and rigpa's
`startup: first frame` from `systemd-analyze` and the journal.
