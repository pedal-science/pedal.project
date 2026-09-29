# vip: the step 1 spike card

Step 1 of [docs/vip-image.md](../../../docs/vip-image.md): a throwaway card that proves the boot
mechanics on vip before anything is built on them. Stock kernel (`7.0.0-1017-raspi`), no pedal,
hostname `vip-spike` so it never collides with the real `vip` in `known_hosts`.

```
devices/vip/spike/build                                   # ~2 min in colima → build/vip-spike/spike.img
devices/common/write-card --image build/vip-spike/spike.img --confirm vip-spike
```

## The card

| # | GPT name | FAT label | Holds |
|---|---|---|---|
| 1 | `bootsel` | `BOOTSEL` | `autoboot.txt`: `tryboot_a_b=1`, `boot_partition=2`, `[tryboot] boot_partition=3` |
| 2 | `pedal-boot` | `PEDAL-BOOT` | `config.txt` with `os_prefix=current/`, `[tryboot] os_prefix=new/`; slots `current/`, `new/` |
| 3 | `rescue-boot` | `RESCUE-BOOT` | the same with slots `a/`, `[tryboot]` → `b/` |
| 4 | `spike-root` | ext4 `spike-root` | resolute minbase, networkd + wpa_supplicant, sshd, watchdog at 14 s |

Every slot's `cmdline.txt` ends `spike.part=<N> spike.slot=<slot>`. `spike-report` prints those
beside the bootloader's own account (`/proc/device-tree/chosen/bootloader/{partition,tryboot}`)
and logs one line per boot to `/var/log/spike-boots.log`. `spike-try <N>` points `autoboot.txt`'s
`[tryboot]` at partition N and reboots with `"0 tryboot"`; `spike-try --raw '<arg>'` reboots with
any parameter.

## Checks

| # | Do | Expect | Proves |
|---|---|---|---|
| 1 | power on | `ssh vip-spike` works; `spike.part=2 spike.slot=current` | GPT card, `autoboot.txt` `boot_partition`, WiFi from a build-time file |
| 2 | `sudo spike-try 3` | `part=3 slot=b`, `bl.tryboot=1` | the flag switches partition, **and** partition 3's `[tryboot]` applies |
| 3 | `sudo reboot` | `part=2 slot=current` | the one-shot is one-shot |
| 4 | `sudo spike-try 2` | `part=2 slot=new` | a same-partition tryboot uses that partition's `[tryboot]` (the kernel-candidate path) |
| 5 | `sudo spike-try --raw 3` | `part=3 slot=a` | a one-shot partition switch without the tryboot flag (a possible `vip-boot rescue`) |
| 6 | `spike-report` | the EEPROM version and date | recorded in the results |

Results go in `bench-results/vip-spike/`.
