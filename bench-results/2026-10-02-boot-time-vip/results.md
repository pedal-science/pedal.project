# vip's power-on, from the debug UART (plan 1.7)

2026-10-02. The half of plan step 1.7 that was still unmeasured: the Pi's own time before the
kernel. Three boots, from the power button and from a real USB-C plug pull, each captured on the
Mac through the Debug Probe while the same console also went to vip's own journal — so the wire
and the kernel timestamp the same boot.

**The pedal's case is the plug pull** (`power-on-reset 1`): a rig is playing **20.4 s** after the
bootloader's first byte, plus however long the PMIC and boot ROM take before that first byte.
The plan's "~20 s power-on to sound" holds, so the bypass relay (3.6) keeps its justification.

## Method

- vip's EEPROM config has `BOOT_UART=1`, read from Linux through the device tree
  (`/proc/device-tree/aliases/blconfig` → `/sys/bus/nvmem/devices/rmem4/nvmem`), so the
  bootloader logs on UART10 — the dedicated debug connector, which is where vip's console
  already is (`console=ttyAMA10,115200`).
- Debug Probe **U** port to vip's debug connector: GND, and probe RX (yellow) ← vip TXD. Probe
  TX was left off, since a getty runs on that port and nothing should be typed into it. The
  bridge is `/dev/cu.usbmodem1302` on the Mac; `/dev/cu.usbmodem1401` is the Pico's own console.
- The cable was proved *before* any reboot by writing a marker into `/dev/ttyAMA10` on vip: it
  appeared on 1302 as `BOOT-CABLE-MARKER-A`. No reboot needed to test the wiring.
- `tools/measure-boot.py` opened every `/dev/cu.usbmodem*` and logged each line on the Mac's
  monotonic clock.
- The kernel half is vip's own: `sudo dmesg`, `sudo systemd-analyze`, and
  `sudo journalctl -b -o short-monotonic -u namchaind`.
- The `power-on-reset` field in the bootloader's own log says which kind of boot each one was,
  and a plug pull has no orderly `reboot: Power down` line before it.

## Stage timings, in seconds from the bootloader's first byte

| stage | button (`por 0`) | power-on, incidental | **plug pull (`por 1`)** |
|---|---|---|---|
| first byte | 0.000 | 0.000 | **0.000** |
| `RPi: BOOTSYS release` | 0.007 | 0.006 | 0.007 |
| `Halt: power_off: 0` | 0.042 | 0.028 | 0.028 |
| `PCIEx1: PWR 0 DET_WAKE 0` | **3.720** | 0.042 | 0.042 |
| `RPi: BOOTLOADER release` (2nd stage) | 6.152 | 2.472 | 2.474 |
| `Boot mode: SD (01) order f4` | 6.385 | 2.706 | 2.704 |
| `SD HOST: … 400000 Hz` (card up) | 11.051 | 7.370 | 7.368 |
| start.elf `*** Restart logging` | 11.472 | 7.792 | 7.785 |
| `Read a/initrd.img bytes 52770103` | 13.998 | 10.319 | 10.311 |
| `Read a/vmlinuz bytes 14703885` | 15.154 | 11.473 | 11.467 |
| `Starting OS …` | 16.512 | 12.833 | 12.825 |
| kernel `[    0.000000]` | **16.637** | **12.958** | **12.950** |
| getty banner | +11.64 s of kernel | +12.75 s | +12.27 s |

The two power-on boots agree to about 10 ms at every stage. Everything from the second bootloader
stage onward is identical across all three kinds of boot to within 0.03 s.

## Numbers

- **First bootloader byte → kernel: 12.95 s on a real plug pull**, 12.96 s on the second
  power-on, 16.64 s from the power button.
- The **firmware's own counter agrees every time**: the OS started at 13.881 s on its clock with
  its first logged line at 1.06 s → 12.82 s (plug pull), 12.84 s (second power-on) and 16.51 s
  (button). The 0.12–0.13 s between the two clocks is the wire's own cost — line serialisation at
  115200 plus the 10 ms read cycle. **That is this method's accuracy.**
- **Kernel → rig published: 7.48 s** on the plug pull (namchaind started at 5.80 s), 7.52 s on
  the second power-on, 6.52 s on the button boot. `systemd-analyze` for the plug pull: 707 ms
  kernel + 1.830 s initrd + 13.774 s userspace.
- **First bootloader byte → rig published: 20.43 s** (plug pull), 20.48 s (second power-on),
  23.16 s (button).
- Power-on itself is still unanchored: the wire cannot show it, so the total is 20.4 s **plus**
  the PMIC and boot-ROM time before the firmware's first byte. The earlier ~20 s estimate from
  piv was therefore close, and the relay's case stands.
- The kernel half is no longer the interesting one: piv took 13.2–14.2 s for the same span where
  a plug-pull vip takes 7.5 s.

## Where the time goes

- **The button/standby boot's extra 3.7 s is one silent stall** between `Halt: power_off: 0` and
  `PCIEx1: PWR 0 DET_WAKE 0`, inside the EEPROM bootloader: the firmware's clock goes 1.17 s →
  4.85 s with nothing on the wire. The plug pull runs through the same lines with no stall at all
  (0.028 s → 0.042 s), and its `AON_RESET … PM_RSTS 00001000` differs from the standby boot's
  `00000575`. So it is the standby path, not the pedal's, and it needs no explanation for 1.7.
- **4.66 s of every boot is the SD wait** — `Boot mode: SD (01) order f4` to `SD HOST` at
  400 kHz. It is 4.666, 4.664 and 4.664 s across three boots of two kinds, so it is a fixed wait
  in the bootloader, not contention. The largest single wait in a boot, and a target for Phase 4.
- **2.2 s** reading the **52.8 MB initrd**, **0.6 s** the 14.7 MB kernel. The initrd is rtpi's
  slimming work's; this is what its size costs at power-on.
- USB-PD negotiation is 15 lines and the same in all three boots, so it is not the difference
  between them.

## Caveats

- The anchor: power-on → the firmware's first byte is the one number this method cannot see.
  Quote a total as "20.4 s from the first byte" unless something stamps the power application.
- "Rig published" is the engine's own statement that it is rendering, not a measurement at the
  jack. The codec is opened at namchaind's start (5.8 s of kernel time), so the gap is small, but
  the jack end is still unmeasured.
- The firmware wraps or truncates long `MESS:` lines on the wire (the command line arrives cut
  mid-argument). Trust the arrival times, not the completeness of long lines.
- `T+` in the logs is the capture's clock, which includes the USB bridge's latency; the firmware
  counter cross-check above bounds the whole error at about a tenth of a second, not per line.

## Evidence

- `serial-plug-pull.log` — the real USB-C pull, boot `por 1`.
- `serial-two-boots.log` — a standby boot cut short, then a second `por 1` power-on 10 s later:
  the repeat that agrees with the plug pull to 10 ms.
- `serial-button-poweroff.log` — the power-button boot, `por 0`, with the marker test before it.
- vip's `dmesg`, `systemd-analyze` and journal for each boot, quoted above.
