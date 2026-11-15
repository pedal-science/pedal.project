# vip boot: measured 2026-11-15, and why <5 s from power-on is not achievable

**Question:** can `vip` go from power-on to rigpa running and displayed in under 5 seconds? If not,
what do the measurements say is in the way?

**Answer: no, not on this hardware and this software stack.** The measured cold-boot path is
**≈21.9 s from power-on to rigpa's first frame** (and Play is ≈0.5 s later). The firmware/EEPROM
stage alone is **≈8.7 s before the kernel starts**, and the kernel + initramfs are **≈5.5 s**
before userspace even begins. Even if the firmware were free, the current kernel, initramfs,
systemd path and Qt startup take **≈13.2 s** to the first frame. A 5 s target would require
replacing several layers, not tuning them.

This report was written from a **reboot** capture with the Debug Probe, not a cold power-on. The
first bootloader line is the anchor; power-on is before it by the boot ROM time, which is not on
the wire. The numbers below therefore **understate** power-on→kernel, never overstate it.

## The measured boot, 2026-11-15 (one boot, official Pi PSU)

| Stage | Measured | Evidence |
|---|---:|---|
| bootloader first line (`BOOTSYS release`) at firmware time | 1.18 s | serial |
| `BOOTSYS` → `Loading 'b/initrd.img'` | **3.97 s** | serial |
| initrd read (21,495,759 bytes) | 1.35 s | serial |
| vmlinuz read (14,069,804 bytes) | 0.61 s | serial |
| `Starting OS` at firmware time | 8.62 s | serial |
| kernel `[0.000000]` at firmware time | **≈8.75 s** | serial |
| kernel → userspace (`systemd-analyze`) | 2.435 s | systemd-analyze |
| initrd userspace (`systemd-analyze`) | 3.112 s | systemd-analyze |
| userspace → `rigpa.service` active | 5.876 s | unit stamps |
| `rigpa` start → first frame (`startup: first frame`) | 1.766 s | journal |
| **kernel start → rigpa first frame** | **13.189 s** | sum |
| **power-on → rigpa first frame** | **≈21.9 s** | 8.75 + 13.189 |
| rigpa first frame → ready/Play | 0.501 s | journal |

`systemd-analyze` reports 2.435 s kernel + 3.112 s initrd + 17.266 s userspace = 22.815 s to
`multi-user.target`, but the **screen** is up much earlier than multi-user: rigpa is active at
11.423 s after kernel start and paints at 13.189 s. The 17 s userspace tail is `pedal-tune`
(12.152 s) and `pedal-guard` (11.782 s), which gate `multi-user.target` but not the UI.

The first frame, from the journal:

```
startup: scene built at 1610 ms
startup: first frame at 1766 ms
startup: engine at 1779 ms
startup: document at 1908 ms
startup: ready at 2267 ms
startup: dismissed at 2268 ms (ready)
```

## Where the time goes

### 1. Before Linux: ≈8.7 s, and ≈4 s of it is card/bootloader setup

The bootloader's own clock:

```
1.18 s  BOOTSYS release 1accd665 2026/09/25
5.15 s  Loading 'b/initrd.img'
6.50 s  Read b/initrd.img 21,495,759 bytes
6.74 s  Loading 'b/vmlinuz'
7.35 s  Read b/vmlinuz 14,069,804 bytes
8.62 s  Starting OS
```

The read rates are **≈16 MB/s for the initrd and ≈23 MB/s for the kernel**; the files are read in
≈2 s together. The raw card itself reads at **≈90 MB/s** for a 64 MiB direct read, so the
firmware's read mode — not the card's bandwidth — is limiting the firmware stage. The larger item is the **≈4 s from `BOOTSYS` to the first initrd read**, which is
bootloader/card initialisation, not bandwidth. A faster card can only attack that 4 s; the reads
are already a small part of the 8.7 s.

The EEPROM is configured `BOOT_ORDER=0xf461`, `NET_INSTALL_AT_POWER_ON=1`, `BOOT_UART=1`
(bootloader `2026/09/25`). Those settings are plausible seconds to reclaim (SD-only boot order,
network-install off, retry count), but they were **not changed in this measurement**; changing the
EEPROM needs physical access to recover a mistake.

### 2. Kernel + initramfs: 2.435 + 3.112 = 5.547 s

That is already over 5 s before the first userspace process. The initramfs is 21 MB and includes
the pedal's guard, storage drivers, Plymouth and theme (Plymouth is masked at runtime, but still
in the image). Removing the initramfs entirely means building the storage (SDHCI/ext4) and panel
(DRM/DSI) drivers into the kernel; that could save roughly **2–3 s**, but the kernel would be
larger and the root still needs mounting.

### 3. Userspace to rigpa: 5.876 s, with a 2.9 s floor and a 2.1 s codec

`systemd-analyze critical-chain rigpa.service`:

```
rigpa.service +363ms
└─pedald.service @5.491s
  └─namchaind.service @5.069s +388ms
    └─pedal-codec.service @2.919s +2.144s
      └─basic.target @2.898s
        └─sockets.target @2.898s
          └─... proc-sys-fs-binfmt_misc.mount @2.824s
```

- `basic.target` is at **2.898 s** into userspace.
- `pedal-codec` adds **2.144 s** before `namchaind`; this is the audio-codec bring-up and was on
  rigpa's path only because rigpa was ordered after the engine. The ordering was changed on
  2026-11-15: see [early rigpa](../2026-11-15-boot-early-rigpa/README.md), which paints 1.9 s
  earlier.
- `namchaind` +388 ms and `pedald` +363 ms.
- Qt/QML then takes **1.766 s** to the first frame.

The `multi-user` tail (`pedal-tune`, `pedal-guard`) is **not** in this chain: it makes the boot
take 22.8 s to *complete*, but the screen is not waiting for it.

## What each target would require

| If the target is… | Current | Best plausible with tuning | Verdict |
|---|---:|---:|---|
| power-on → rigpa first frame | ≈21.9 s | ≈10–14 s (faster boot medium, no initramfs, earlier rigpa, trimmed kernel) | **<5 s not achievable** |
| kernel start → rigpa first frame | 13.189 s | ≈8–10 s | **<5 s not achievable** |
| userspace start → rigpa first frame | 7.642 s | ≈4–5 s (start rigpa before the engine, trim basic.target) | **<5 s marginal at best, and engine/audio would still be later** |
| kernel + initramfs alone | 5.547 s | ≈3 s (no initramfs) | already over 5 s today |

**The decisive bound:** the kernel + initramfs are 5.547 s and the firmware is ≈8.7 s. Even with a
free bootloader and an instant userspace, the current kernel/initramfs path cannot meet 5 s; even
with a free firmware, the current kernel + initramfs + userspace + Qt path cannot meet 5 s. This is
not a matter of one slow service.

## Is the SD card necessarily too slow?

No, not for the *reads* measured here: 21.5 MB initrd in 1.35 s and 14.1 MB kernel in 0.61 s.
The card is not the 5 s blocker; the ≈4 s of bootloader/card **setup** before the first initrd
read is worth attacking, and a faster card or NVMe boot may reduce it. But even deleting that 4 s
leaves ≈18 s. Boot medium alone cannot reach 5 s.

## Potential ways to speed the actual boot (with expected size)

1. **Bootloader/EEPROM** — SD-only `BOOT_ORDER`, `NET_INSTALL_AT_POWER_ON=0`, one retry,
   `BOOT_DELAY=0`; measure. Expected **−1 to −3 s**; needs physical recovery access.
2. **Faster boot medium / NVMe** — remove card init and improve reads. Expected **−2 to −4 s**
   in the firmware stage; still nowhere near 5 s.
3. **Remove the initramfs** — build SDHCI/ext4 and the DSI/KMS stack into the kernel, boot the
   root directly. Expected **−2 to −3 s**; needs a kernel rebuild and a careful boot trial.
4. **Start rigpa before the engine** — this was measured and kept on 2026-11-15: drop
   `After=namchaind/pedald` for the UI, start at `basic.target`, let `Startup` show the
   disconnected/starting state, and let engine readiness arrive later. Measured **−1.9 s to first
   frame** ([early rigpa](../2026-11-15-boot-early-rigpa/README.md)); Play data/audio still arrive
   about half a second after the first frame.
5. **Trim `basic.target` / `pedal-codec`** — the 2.9 s base and the 2.1 s codec are the userspace
   floor; a codec path that does not block `namchaind`/rigpa could save a second or two.
6. **Kernel config** — remove unused drivers/features and shrink the kernel; expected **−0.5 to
   −1 s**, high effort, risk to audio/USB/Wi-Fi.
7. **Keep the pedal powered/suspended** — wake-on-footswitch or wake-on-USB gives a perceived
   instant start without a cold boot; not a cold-boot answer and needs power/audio design.
8. **A second always-on MCU/display controller** — draw the splash/UI immediately while Linux
   boots; this is a hardware change, and the only route to “something on screen at power-on” that
   does not depend on Linux's 8.7 s firmware + 5.5 s kernel/initrd.

The realistic cold-boot outcome after all software work is **≈10–14 s to rigpa**, not 5 s.
If the product requirement is truly 5 s, it has to be met by keeping the host alive/suspended or
by a separate display controller, not by boot-time tuning.

## Reproduce

```sh
# serial capture (Debug Probe on the 3-pin UART header)
tools/measure-boot.py --seconds 90 --out /tmp/vip-boot
# then reboot; the first BOOTSYS line and the kernel [0.000000] line are the anchors
ssh vip 'systemd-analyze; systemd-analyze blame; systemd-analyze critical-chain rigpa.service'
ssh vip 'journalctl -b -u rigpa -o cat | grep startup:'
```

Evidence in this directory:

- [serial-boot.log](serial-boot.log) — the captured boot, from the first `BOOTSYS` line.
- [dmesg.txt](dmesg.txt) — the same boot's kernel log.

Caveats: one boot, one card (SK32G, date 04/2026), official Pi PSU, bootloader 2026/09/25. The
capture is a reboot, so power-on-to-first-byte is not included and the real cold-boot number is
slightly larger. `systemd-analyze`'s “kernel”/“initrd”/“userspace” are from the kernel's clock;
the firmware times are from the bootloader's own UART log.

## Ideas from the fast-boot references (added 2026-11-15)

From [instant-pi](https://github.com/AndreVallestero/instant-pi) and Qt's
[fast-booting part 3](https://www.qt.io/blog/2016/05/25/fast-booting-qt-devices-part-3-optimizing-system-image):

- **The closed RPi bootloader is the floor.** instant-pi measures a "CD bootloader overhead" of
  ~4.1 s; on this Pi 5 the bootloader still takes ~8.2 s to `Starting OS` after the network-install
  check is removed. No userspace work can go below that.
- **Build a tiny OS image** (Buildroot/musl/BusyBox, F2FS, LZ4/LZO kernel, stripped rootfs and
  modules, no initramfs): instant-pi reaches 4.7 s on an old Pi 0W including the bootloader. This
  is a replacement for Ubuntu/systemd, not a tuning step; it is the only credible path toward
  single-digit cold boot on this class of hardware.
- **Static Qt / optimized Qt** (Qt blog: strip rootfs 500→24 MB, kernel 5.5→1.6 MB, static Qt,
  disable console, faster SD/eMMC, compression): it takes a Qt device from 22.8 s to 1.56 s, but
  with U-Boot/SPL and full image control. Our Qt binary and QML start is ~1.8 s, a small part of
  the current ~17.4 s.
- **EEPROM tags** measured on 2026-11-15: keeping the original `BOOT_ORDER=0xf461` while setting
  `NET_INSTALL_AT_POWER_ON=0`/`NET_INSTALL_ENABLED=0` removes a **4.8 s** cold network-install
  wait and is kept; `BOOT_UART=0` and `USB_MSD_DISCOVER_TIMEOUT` remain untried.
- **Disable the serial console entirely** (`console=tty1` only): measured ≈0.5 s; the verbose
  logging was the big item (≈1.9 s) and is already off.
