# vip spike card: step 1 results, 2026-09-29

The spike card from `devices/vip/spike/` (build `43e89f92…`, then patched live as noted below) on
vip, a Raspberry Pi 5 1 GB (boardrev `a04171`), Debug Probe on the 3-pin UART header.
Card: the 32 GB, written with `devices/common/write-card`, read back and hash-matched.

**Bootloader:** EEPROM `66f33f7e651cf482a26fb2c931a7587bb14e71db`, built 2026-05-11. It
prints its own log on the header UART as shipped (`console-boot*.log`), without `BOOT_UART=1`.

## The checks

| # | Did | Booted | `bl.partition` / `bl.tryboot` | Result |
|---|---|---|---|---|
| 1 | power on, then `systemctl reboot` | part 2, `current` | 2 / 0 | **pass**: GPT card, `autoboot.txt` `boot_partition`, WiFi from the card's own files, `ssh` 22 s after reboot |
| 2 | `spike-try 3` (`[tryboot] boot_partition=3`, reboot `"0 tryboot"`) | part 3, `b` | 3 / 1 | **pass**: the flag switches partition, and partition 3's own `[tryboot]` applies |
| 3 | `systemctl reboot` | part 2, `current` | 2 / 0 | **pass**: one-shot |
| 4 | `spike-try 2` | part 2, `new` | 2 / 1 | **pass**: the kernel-candidate path |
| 4b | `systemctl reboot` | part 2, `current` | 2 / 0 | **pass** |
| 5 | `spike-try --raw 3` (reboot `"3"`, no tryboot) | part 3, `a` | 3 / 0 | **pass**: a one-shot partition switch needs no flag and no write to `autoboot.txt` |
| 5b | `systemctl reboot` | part 2, `current` | 2 / 0 | **pass**: that is one-shot too |

Every reboot came back on ssh in 22-23 s. Idle, the minimal root uses 184 MB of vip's 965 MB and
476 MB of disk. No failed units. History as vip logged it: `spike-report.txt`.

## What it took (all now in the build)

1. **Interface names.** udev renamed `wlan0` → `wld0` and `eth0` → `end0`, so
   `wpa_supplicant@wlan0` waited for a device that never came. piv keeps `wlan0` without
   `net.ifnames=0`, through some part of its stock image not tracked down; a root built from
   packages doesn't. Fix: `net.ifnames=0` on every command line. Everything in `devices/` and rtpi's `device.env` says `wlan0`/`eth0`.
2. **The WiFi key's form.** piv's netplan keeps the key hashed, as 64 hex digits. wpa_supplicant
   takes that form only unquoted; quoted it is read as a passphrase, rejected as too long, and
   **the error message prints the key**. It reached the console log (scrubbed in place before
   commit) and the session transcript. Fix: write a 64-hex key unquoted. The real build takes
   the key from 1Password, which should hold the passphrase, but it handles both.
3. **The reboot argument.** `systemctl reboot "0 tryboot"` is refused ("Too many arguments");
   it's `systemctl reboot --reboot-argument="0 tryboot"`. `vip-boot` has to use that form.
4. **The clock.** Nothing set it (no RTC battery, no NTP client), so vip thought it was July.
   `systemd-timesyncd` is added.

1 and 3 were patched on the live card (`net.ifnames=0` in all four `cmdline.txt`, the new
`spike-try`), and 2 in its `wpa_supplicant-wlan0.conf`, before checks 1b-5. A fresh build has
all four.

## For the layout

Nothing in `docs/vip-image.md`'s card layout has to change. One addition is on offer: check 5
shows `reboot "<N>"` boots partition N once without touching `autoboot.txt` or the tryboot flag.
That's a simpler `vip-boot rescue` (nothing to write, so nothing to leave behind), and it keeps
the tryboot flag, and `autoboot.txt`'s `[tryboot]`, for kernel and argument candidates only.
