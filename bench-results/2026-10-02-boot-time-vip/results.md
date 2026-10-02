# vip's power-on, from the debug UART (plan 1.7)

2026-10-02. The half of plan step 1.7 that was still unmeasured: the Pi's own time before the
kernel. One boot, captured on the Mac through the Debug Probe while the console also went to
vip's own journal, so the wire and the kernel timestamp the same boot.

**This boot came from the power button, not a plug pull** — the bootloader reports
`POWER_OFF_ON_HALT: 0` and `power-on-reset 0`, so the PMIC went to standby and came back, which
is not quite the pedal's "unplugged and plugged in again". A plug-pull repeat is in
[plug-pull/](plug-pull/).

## Method

- vip's EEPROM config has `BOOT_UART=1`, read from Linux through the device tree
  (`/proc/device-tree/aliases/blconfig` → `/sys/bus/nvmem/devices/rmem4/nvmem`), so the
  bootloader logs on UART10 — the dedicated debug connector, which is where vip's console
  already is (`console=ttyAMA10,115200`).
- Debug Probe **U** port to vip's debug connector: GND, and probe RX (yellow) ← vip TXD. Probe
  TX was left off, since a getty is running on that port and nothing should be typed into it.
  The bridge is `/dev/cu.usbmodem1302` on the Mac; `/dev/cu.usbmodem1401` is the Pico's own
  console.
- The cable was proved *before* the reboot by writing a marker into `/dev/ttyAMA10` on vip: it
  appeared on 1302 as `BOOT-CABLE-MARKER-A`. No reboot needed to test the wiring.
- `tools/measure-boot.py` opened every `/dev/cu.usbmodem*` and logged each line with the Mac's
  monotonic clock (`serial-button-poweroff.log`).
- The kernel half is vip's own: `sudo dmesg` and
  `sudo journalctl -b -o short-monotonic -u namchaind`.

## The boot

`T+` is seconds on the capture's clock. The second column is what the line says about itself,
where it says anything.

| stage | `T+` | self-reported |
|---|---|---|
| previous boot's `reboot: Power down` | 75.893 | kernel |
| first byte from the bootloader | **77.030** | |
| `RPi: BOOTSYS release` (EEPROM bootloader) | 77.037 | firmware clock 1.13 s |
| `RPi: BOOTLOADER release` (second stage) | 83.182 | firmware clock 7.27 s |
| `Boot mode: SD (01) order f4` | 83.415 | firmware clock 7.17 s |
| `SD HOST: … 400000 Hz` (card comes up) | 88.081 | firmware clock 12.17 s |
| start.elf logging (`*** Restart logging`) | 88.502 | firmware clock 12.60 s |
| `Read a/initrd.img bytes 52770103` | 91.028 | 2.20 s to read 52.8 MB |
| `Read a/vmlinuz bytes 14703885` | 92.184 | 0.61 s to read 14.7 MB |
| `Starting OS 17644 ms` | 93.542 | firmware: OS start at 17.644 s |
| `BL31` (ARM Trusted Firmware) | 93.571 | |
| kernel `[    0.000000]` | **93.667** | kernel |
| `Starting namchaind.service` | — | kernel 5.160 s |
| `[namchaind] published … (generation 1)` | — | kernel 6.524 s |
| `Ubuntu 26.04.1 LTS vip ttyAMA10` (getty) | 105.310 | kernel ~11.6 s |

## Numbers

- **First bootloader byte → kernel: 16.63 s** on the Mac's clock (77.037 → 93.667).
- The **firmware's own counter agrees**: the OS started at 17.644 s on its clock and its first
  logged line is at 1.13 s, so 16.51 s. The 0.12 s difference is the wire's own cost — line
  serialisation at 115200 plus the 10 ms read cycle. Two independent clocks agreeing to ~0.1 s
  over 16.6 s is the accuracy this method has.
- **Kernel → rig published: 6.52 s** (namchaind started at 5.16 s, the rig published at 6.52 s).
  piv, for contrast, was 13.2–14.2 s from kernel start to a running rig.
- **First bootloader byte → rig published: 23.15 s.**
- Power-on itself is still unanchored: the wire cannot show it, and this boot's off→on gap was
  the owner's button presses, not a timestamp. So the total is 23.2 s **plus** the PMIC and
  boot-ROM time before the firmware's first byte.
- **The plan's "~20 s power-on to sound" was therefore if anything optimistic, not
  pessimistic.** The bypass relay (3.6) keeps its justification.

## Where the 16.6 s goes

| span | Mac delta | what |
|---|---|---|
| first byte → second stage | 6.15 s | EEPROM bootloader: SDRAM init, PCIe, RP1 firmware load, USB-PD negotiation, SD probe begins |
| second stage → start.elf | 5.32 s | SD and boot mode — and **4.67 s of it is one gap**, `Boot mode: SD` (83.415) to `SD HOST` init (88.081) |
| start.elf → `Starting OS` | 5.04 s | config.txt and DTBs, 52.8 MB initrd (2.20 s), 14.7 MB vmlinuz (0.61 s), AVS, HDMI probe |
| `Starting OS` → kernel | 0.13 s | BL31 to the kernel |

Two leads for Phase 4's boot item, both from this table: the **52.8 MB initrd is 2.2 s** of the
pre-kernel time (rtpi's slimming work owns that size), and the **4.7 s SD gap** wants explaining
before it is accepted, since it is the single largest wait in the boot.

## Caveats

- A button/standby boot, not a plug pull: the PMIC and boot-ROM part of the anchor may differ.
  See `plug-pull/`.
- The firmware wraps or truncates long `MESS:` lines on the wire (the command line arrived cut
  mid-argument). Trust the arrival times, not the completeness of long lines.
- `T+` is the capture's clock, so it includes the cable's and the USB bridge's few milliseconds
  per line; the firmware counter cross-check above bounds that at about a tenth of a second,
  not per line.

## Evidence

- `serial-button-poweroff.log` — the capture, every line, both ports.
- `plug-pull/` — the repeat, if it ran.
- vip's journal and `dmesg` for this boot, quoted above.
