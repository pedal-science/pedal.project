# vip: the card image

**Status:** plan, 2026-09-29. vip (Raspberry Pi 5, 1 GB) has arrived. This covers how vip is made
from nothing: one command on the Mac builds everything and writes a blank SD card, and the card
boots vip straight onto the network. It also covers how vip keeps itself reachable when a
kernel, a command line or its own root filesystem is broken. Your decisions of 2026-09-29 are
recorded at the end. **All eight steps are done** (2026-09-29 to 10-01): the spike card proved the layout
on vip, and rtpi's `vip-boot` ran every path on it (`bench-results/vip-spike/`). Step 2 changed
the slots, below: two fixed slots `a/` and `b/` and a pointer file, where this plan had
`current/`, `new/` and `old/`.

It settles the open question in `plan.md` ("which repo owns vip's kernel and boot
configuration") as proposed below, under [Who owns what](#who-owns-what).

## The goal

```
devices/vip/make-card            # on the Mac, with a blank card in the reader
```

Then put the card in vip, power it on, and `ssh vip` works about a minute later. `devices/vip/check`
is green, `namchaind` is running the default rig, and `scripts/status --host vip` shows the
commits it was built from. Run it again with the same pinned inputs and you get the same system.

No step happens by hand on vip, and none happens on piv. vip has no compiler
(`working-across-repos.md`), so everything arrives built.

## What exists already, and what carries over

| From | What | Use on vip |
|---|---|---|
| rtpi, piv | A/B kernel slots in one boot partition (`current/`, `new/`, `old/`), chosen by the Pi firmware's one-shot `tryboot` flag and `os_prefix`. Both rehearsals passed on hardware | The same slot layout for vip's kernel. The mechanism, not Ubuntu's `piboot-try` script (see below) |
| rtpi, piv | `piboot-validate`: sshd listening, a *physical* interface with an address, the expected kernel, PREEMPT_RT. The dracut lockout arguments. The watchdog at 14 s, in the initramfs too | All of it, for candidates |
| rtpi, piv | `AUDIO_TUNING_ARGS` (isolcpus, nohz_full, rcu_nocbs on 2-3, irqaffinity 0-1, skew_tick) staged as a candidate command line, so a bad set of arguments rolls back like a bad kernel | The "tuned" profile below |
| rtpi, piv | Ubuntu's `linux-raspi-realtime` 7.0.0-1017 is already well configured for RT, and a custom build buys little (rtpi README, "Is a custom kernel worth building for piv?") | vip's first kernel. rtpi's `piv-ubuntu-rt`/`piv-vendor-rt` builds stay available for when a patch is needed |
| rtpi | Fail *safe*: a failed clear, a hang or a power cut returns to the known-good | Every mechanism below keeps that property |
| pedal.project | `devices/common` + `devices/piv`: the `namchaind` drop-in, `pedal-tune`, `pedal-resume`, `pedal-wifi`, the cpuset slices, masked units, limits, sysctl, the codec overlay and mixer | Baked into the image, then `devices/vip/apply` works on the live board exactly as it does on piv |
| namchain | `docs/distro-slimming.md`: the tail on piv is memory traffic on the housekeeping cores, not CPU time. A machine that runs nothing else is the predictability win | A minimal root built from packages, not a stripped desktop image. piv had 2,587 packages; vip has 1 GB |
| pedal.project | `scripts/deploy-engine`, `sync-library`, `host-lock`, `components-lock`, `status` | Each gets `--host vip`. deploy-engine gains a "built on the Mac" path, since vip can't build |

What doesn't carry over: `piboot-try` and flash-kernel. They were built for a machine that
upgrades itself with apt, and their traps are in rtpi's README (the `rm -rf old new`, the silent
no-op on an unknown flavour, unattended-upgrades restaging behind your back). vip is an appliance
built from an image: kernels arrive through the image or a deliberate install, so a small script
of our own that does the same firmware-level thing is simpler and has fewer traps.

## Two roots: rescue and pedal, not untuned and tuned

You asked whether to have two root filesystems, one to diagnose and recover from and one with the
hardcore configuration. The answer proposed here is two roots, split by *purpose*, with tuning as
a per-boot profile of the pedal root.

- **The pedal root** is the only system that plays. It boots in one of two profiles:
  - **tuned** (the default): `AUDIO_TUNING_ARGS` on the command line, `pedal-tune`, the cpuset
    slices and the pinned audio interrupt, and `namchaind` running.
  - **loose**: the same root and kernel, with no isolation arguments, and
    `systemd.unit=pedal-maint.target`, so the engine and the tuning don't start. For profiling
    with all four cores, bisecting a tuning problem, or doing heavy work on the box.

  A profile is a kernel command line plus a systemd target, so it can be chosen for one boot
  (and falls back by itself) or made the default. The configuration you're diagnosing stays the
  configuration that failed, minus one switch.
- **The rescue root** is small, separate and rarely changed. It exists to be reachable when the
  pedal root isn't. It has a different kernel package (Ubuntu's plain `linux-raspi`, not the RT
  one), its root is mounted read-only, and it holds no pedal configuration. It has networking
  (WiFi and Ethernet), sshd, mDNS, an HDMI console, and the tools to repair the pedal root:
  fsck, mount and edit it, change the boot selection, or restore the pedal root from the image
  kept on the card ("factory reset over ssh").

Why not tuned and untuned roots: two copies of one system drift, you'd have to keep both current,
and neither protects you from the case that actually costs a trip to the card reader, which is a
pedal root that no longer boots to the network. A rescue root that shares nothing with the pedal
root except the card covers that, and it only changes when you choose to change it.

Both roots use the same hostname, the same SSH host keys and the same `authorized_keys`, so
`ssh vip` works whichever is running. The prompt and `/etc/motd` say which one you're in, and
`vip-boot status` prints the boot state.

## The card

GPT, so partitions carry labels and there's no four-primary limit. The Pi 5 bootloader reads
`autoboot.txt` from the first FAT partition and boots whichever partition it names.

| # | Label | Type | Size | Holds |
|---|---|---|---|---|
| 1 | `bootsel` | FAT32 | 64 MB | `autoboot.txt` only, plus the boot counter and the last fallback reason. Both roots can write it |
| 2 | `pedal-boot` | FAT32 | 512 MB | The pedal's `config.txt`, `profile.txt` and `tryboot.txt`, and kernel slots `a/` and `b/`, each with its kernel, initramfs, DTBs, overlays, `cmdline-tuned.txt` and `cmdline-loose.txt` |
| 3 | `rescue-boot` | FAT32 | 256 MB | The rescue kernel, initramfs, DTBs and `config.txt` |
| 4 | `rescue` | ext4 | 1.5 GB | The rescue root. Mounted read-only, `/var` and `/tmp` on tmpfs |
| 5 | `pedal` | ext4 | 3 GB | The pedal root |
| 6 | `pedal-data` | ext4 | rest | `/var/lib/pedal` (the library, rigs, `last.json`), soak evidence, and `images/`: the pedal root's image that rescue can restore from |

The image is about 6 GB and fits the 8 GB card; the data partition grows to fill the card on first
boot (`systemd-repart`). The library is 15 MB today, so size isn't a constraint either way.
**Decided:** vip runs from the 32 GB card, for headroom and wear levelling. The 8 GB card can be
made by the same command as a spare. The data partition is there from day one
because it's the one thing that's hard to add later. Phase 4's read-only pedal root and a second
pedal root for A/B updates can come later: they need `pedal-data` to exist, and nothing else.

## How it boots, and how it falls back

The firmware's `tryboot` flag is one-shot: `reboot '0 tryboot'` sets it, and the firmware clears
it *before* loading anything. So anything chosen with it lasts one boot, and a hang, a watchdog
reset or a power cut returns to the default. With `tryboot_a_b=1`, the flag selects a
partition in `autoboot.txt`, and `[tryboot]` sections in that partition's `config.txt` also apply.
That's what piv uses today, one level down.

One tool, `vip-boot` (rtpi, `devices/vip/usr/local/sbin/vip-boot`), is the only thing that writes
the boot selection. The pedal's `config.txt` is written once and never again; it includes two
small files that `vip-boot` rewrites:

```
[all]       include profile.txt     os_prefix=a/ and cmdline=cmdline-tuned.txt: the default
[tryboot]   include tryboot.txt     what the next one-shot changes, e.g. os_prefix=b/
```

Kernels live in two fixed slots, `a/` and `b/`. `profile.txt` names the active one; the other
holds the previous kernel, or a candidate while one is tried. **A card is written with both slots
filled** (2026-10-05): slot `a/` holds the pedal's kernel — rtpi's rebuild, installed from
hash-pinned artefacts because it is in no archive — and slot `b/` the stock Ubuntu RT kernel that
`devices/vip/packages` installs, both marked good. So the spare slot is not
empty on a fresh card: `vip-boot try-kernel <the other release>` is a validated way back from a
kernel that will not come up, without a card reader. [vip-kernel-image.md](vip-kernel-image.md) is
the design, the artefacts and the reasons. Promoting a candidate is one
rewrite of `profile.txt`, not a rename of directories, so at no moment does the card lack a
kernel to boot. Every file `vip-boot` changes on FAT (`autoboot.txt`, `profile.txt`,
`tryboot.txt`, the counter) is rewritten in place at the same length, inside one sector, so a
power cut mid-write leaves the old sector or the new one. Tested on vip with the spike
(`include` under `[tryboot]` applies; a later `os_prefix` wins).

| You want | Command | What boots | Afterwards |
|---|---|---|---|
| Normal | power on | the active slot, default profile (tuned) | — |
| Try a kernel | `vip-boot try-kernel <rel>` | the spare slot once | validate passes → it becomes the active slot, and the other keeps the previous kernel. Anything else → the active slot again, and the candidate is marked bad |
| Try new boot arguments | `vip-boot try-args '<args>'` | the spare slot with the same kernel and the new tuned arguments | the same as a kernel |
| One loose boot | `vip-boot loose` | the active slot, loose profile | next boot is tuned |
| Loose until told otherwise | `vip-boot default loose` | loose every boot | `vip-boot default tuned` |
| Rescue once | `vip-boot rescue` (`reboot "3"`: no flag, nothing written) | rescue-boot | next boot is the pedal |
| Stay in rescue | `vip-boot rescue --stay` (or from rescue: `vip-boot stay`) | rescue every boot | `vip-boot default pedal` from rescue |

### Falling back without being asked

A candidate that fails falls back on its own, as on piv. The harder case is the **default**
pedal root breaking, for example an apply that breaks the network, a bad fstab entry or a wedged
unit. For that:

- The pedal's initramfs increments a boot counter on `bootsel` on every boot.
- `pedal-guard` clears it once the boot has reached `multi-user.target` with `namchaind` running.
- If the initramfs finds the counter at 3 (three boots in a row that never got that far, whether
  they hung into the watchdog, dropped to an emergency shell (it reboots) or reset), it writes
  the reason to `bootsel`, arms `rescue` and reboots. Rescue sees the reason, makes itself sticky
  and says so in its motd and in `vip-boot status`.

**The network is deliberately not part of the pedal's health.** At a gig there's no home WiFi,
and a pedal that reboots into rescue mid-set because it can't see a router is worse than one
you can't ssh into. So a missing network sends a *candidate* back (it's one-shot anyway, and
validate is what protects remote access while you're developing), but never the default. A
default pedal that plays with no network is healthy.

### What this still doesn't cover

- A default kernel that hangs before its initramfs runs. The counter never moves, so it resets
  into the same thing. Only a power cycle or a smart plug fixes that, as on piv. It's also
  unlikely, since a kernel only becomes the default after passing validation.
- A corrupt `bootsel` partition, a corrupt EEPROM or a dead card. The spare card is the floor.
- Firmware files at the root of a boot partition, which the slots don't cover (as on piv).

### The bootloader EEPROM

Everything above is card-level; the EEPROM is the one piece of vip they cannot reach, and it holds
the bootloader that reads `autoboot.txt`, `tryboot_a_b` and the slots. It is recorded rather than
left to apt, and it is never changed as a side effect (the package's `rpi-eeprom-update.service`,
which would apply a pending update at every boot, is masked in `devices/vip/rootfs/etc/pedal/`).

- **The image is pinned, not package-managed.** Ubuntu's `rpi-eeprom` (28.14, from the snapshot)
  ships images *older* than this board's factory EEPROM — 2025-12-08 in `default` and 2026-02-23 in
  `latest`, against the board's 2026-05-11 — so the packaged tool reports "up to date" and can
  never see a newer release. `devices/vip/rootfs/usr/local/lib/rpi-eeprom/eeprom.lock` pins one
  upstream commit, `pieeprom-2026-09-25.bin` and `recovery.bin` by sha256, and the version and
  config the board is expected to carry; `devices/vip/eeprom-fetch` fetches it there and verifies
  both ends. The image files are not in git, for the same reason the pedal kernel's artefacts are
  not ([vip-kernel-image.md](vip-kernel-image.md)).
- **One tool on the board, `vip-eeprom`** (`/usr/local/sbin/vip-eeprom`): `status`, `verify`,
  `apply`, `clean`. It points the packaged `rpi-eeprom-update` at the pinned tree with
  `FIRMWARE_ROOT`, mounts the pedal boot partition before writing (fstab has it `noauto`; unmounted,
  `-a` writes `recovery.bin` and `pieeprom.upd` into the empty directory on the root filesystem, says
  "updates pending", and the firmware never sees them), and refuses the two flags that would lose
  information: `-d` (which discards the EEPROM's configuration for the image's own) and `-f` (which
  skips the version check).
- **`devices/vip/check` diffs three things**: the version and timestamp the bootloader reports, the
  three config keys, and the pinned tree's bytes. It compares against `eeprom.lock`'s state block,
  which carries the board's own history: it left the factory on `66f33f7e` (2026-05-11) — upstream
  keeps that image as `firmware-2712/old/default/pieeprom-2026-05-11.bin` — and went to `1accd665`
  (2026-09-25) on 2026-10-07, the configuration carried across unchanged
  ([2026-10-07-eeprom-update.md](../bench-results/2026-10-07-eeprom-update.md)). The `tryboot`
  one-shot was re-verified under the new firmware the same day, since `autoboot.txt`,
  `tryboot_a_b`, `os_prefix` and `include` are all firmware behaviour and were last proven on the
  factory image.
- **An EEPROM write is the one act with no card-level fallback.** The firmware this board came with
  has no A/B EEPROM (upstream added it on 2026-05-13; the 2026-09-25 image has it), so a power cut
  during the write needs a PC: Raspberry Pi Imager's `Misc utility images → Bootloader → SD Card
  Boot` card, or `rpiboot` over USB-C. `apply` only *stages*: the next boot's ROM runs
  `recovery.bin` from the boot partition, writes the EEPROM and resets, so Linux never runs that
  boot and `bootsel`, the slot markers and the guard counter are untouched. `clean` afterwards
  removes what the flash leaves behind (`recovery.000`, `pieeprom.upd`, `pieeprom.sig`), which
  nothing else would: the service that does it on Raspberry Pi OS is the masked one.
- **The config is upstream's stock default, not bespoke**: `BOOT_UART=1` (the bootloader's own log
  on the header UART the Pico's link shares, [2026-10-05-header-uart-disabled.md](../bench-results/2026-10-05-header-uart-disabled.md)),
  `BOOT_ORDER=0xf461` (the SD card first) and `NET_INSTALL_AT_POWER_ON=1`, which spends about a
  second of cold boot in keyboard and network-install probing the pedal does not need. Changing
  that last one is `rpi-eeprom-config --apply` — a configuration write, a different act from an
  image update, and still an EEPROM write.

**Console.** Unlike the Pi 500, the Pi 5 has a 3-pin UART debug header. The Debug Probe plugs
straight into it, the kernel console goes there (`ttyAMA10`), and `BOOT_UART=1` in the EEPROM
adds the bootloader's own output. That gives a remote read of a failed boot and, for Phase 1
step 7, the firmware time that piv couldn't measure. It also frees pins 8/10 (`ttyAMA0`) for the
Pico link, which is Phase 3 step 4's open question. **Decided:** the probe stays on the Pico for
now. The image sets the console up on the header anyway, so moving the probe over is a plug-in
job if vip ever needs it. Until then a boot that fails before the network needs HDMI and a
keyboard.

**Wired Ethernet.** There's none near vip today, so WiFi is the way in, and both roots depend on
it. Both also bring up `eth0` with DHCP when a cable is present: moving vip onto a cable is the
rescue path if its WiFi configuration is ever what broke.

## The build

Everything runs in colima on the Mac. The M2 is arm64, so the container runs aarch64 Ubuntu
natively, with no qemu and no emulation. Nothing needs loop devices or a `--privileged` container;
the one privilege is `CAP_SYS_ADMIN`, for mmdebstrap to mount `/proc` in the root it builds
(the spike, `devices/vip/spike/build`, does exactly this):

- **Roots:** `mmdebstrap --variant=minbase` from `snapshot.ubuntu.com` at a pinned timestamp, so
  the same inputs give the same packages. Ubuntu 26.04 `resolute` (decided), with
  `resolute-updates` for the 7.0.0-1017 kernels. `SOURCE_DATE_EPOCH` is set from the pinned
  snapshot.
- **Customisation** happens in the root after mmdebstrap (`devices/common/image/build-image`):
  user `rik`, the hostname, fstab by label, the network, mDNS (`vip.local`), the watchdog
  drop-ins, the SSH host key and the secrets. Then, for the pedal root:
  - `pedal-device apply --root` installs `devices/common` + `devices/vip`, enables units and
    masks units without starting anything. So the image is exactly "fresh + apply", and apply
    stays the one source for the configuration.
  - `namchaind` goes into `/opt/namchain/<commit>/` with its manifest, as deploy-engine does.
  - The pedal root's own image, compressed, goes into `pedal-data/images/` for rescue to restore
    from.
- **namchain** is built in the same container from its pinned commit, with the same flags
  deploy-engine uses on piv (`-march=armv8-a -mtune=cortex-a76`, Release). Its tests run there,
  on the same resolute userland vip runs. This is the "built on the Mac" path deploy-engine needs
  anyway, so it's shared.
- **Filesystems and the card image** are assembled as files: `mkfs.ext4 -d` fills each ext4
  partition from a directory (owners and file capabilities kept), `mtools` fills the FAT ones,
  and `sfdisk` writes the GPT into the image file.
- **Inputs are pinned, not taken from whatever is checked out.** pedal.project, rtpi and namchain
  are exported with `git archive` at the commits in `devices/vip/image.lock`, so a dirty working
  tree can't leak into an image. `--dev` allows dirty trees for iterating, and marks the image
  `-dirty`, as rule 5 asks.
- **Output:** `build/vip/<stamp>/vip.img` (gitignored), and `devices/vip/images/<stamp>.manifest`
  (committed): every input commit, the snapshot, the package list with versions, and the image's
  hash. `components.lock` is written from vip after first boot, as for piv.

**Secrets never enter git, and live in 1Password.** `make-card` reads them with `op read` at
build time and writes them straight into the roots as the files the services already expect,
mode 600, root-owned: the WiFi connection in both roots, and `/etc/namchain/token` in the pedal
root. They never pass through a file on the Mac.

**Where (settled 2026-09-29):** the 1Password vault **`fx`**, read by the service account `fx`.
Its token is in the Mac's login keychain, item label `fx` (service
`1password-fx-vault-service-account`); `make-card` passes it to `op` as
`OP_SERVICE_ACCOUNT_TOKEN`, in memory, so the build needs neither the desktop app nor a sign-in.
The account sees only `fx`. The items:

| 1Password item in `fx` | Fields | Goes to |
|---|---|---|
| `wifi` (Wireless Router) | `network name`, `wireless network password` (the passphrase) | the WiFi connection in both roots |
| `namchaind` (Password): **piv's** token, copied 2026-09-29, so ljoss connects to vip unchanged | `password` (64 characters) | `/etc/namchain/token` |
| vip's SSH host keys, generated once by the first run and stored back (not there yet) | | `/etc/ssh/ssh_host_*` in both roots |

Keeping the host keys means a reflashed vip is the same machine to `ssh`, with no `known_hosts`
warning. `authorized_keys` comes from `devices/vip/authorized_keys` and is installed verbatim in
both roots: who may log in is a recorded input, not whatever an SSH agent happens to hold. A host
without that file falls back to `ssh-add -L` with a warning. Its one key is the Core hosts' key,
`~/.ssh/core_ed25519` on the Mac, named to `vip` and `piv` by `~/.ssh/config` (`IdentitiesOnly`
and `IdentityAgent none`, so no agent and no prompt); it is deliberately not the key for anything
else. `devices/vip/check` compares the file with the host's. The build stops early if the token
can't read `fx`, before any time is spent.

Reusing piv's token needs one step in 4: copy it from piv into 1Password, piped straight from
`ssh piv sudo cat /etc/namchain/token` into `op`, never shown. It also changes a rule:
`namchaind`'s drop-in and deploy-engine say the token is made on the host and never leaves it.
From now on it's made once, kept in 1Password, and installed by the image. deploy-engine still
makes one if a host has none.

### Writing the card

The guards `devices/common/write-card` owns:

- List external physical disks, and refuse an internal disk and anything that isn't removable.
- Show the name and size, and ask you to type `vip` before writing.
- `diskutil unmountDisk`, then `sudo dd` to `/dev/rdiskN` (the raw node is several times faster),
  with progress.
- Read the written length back and compare its hash, then eject.

`--image-only` stops before the card; `--disk /dev/diskN` skips the prompt for which disk (not the
confirmation).

### Pi 5 settings in the image

- `config.txt` for pedal-boot: `arm_64bit`, the watchdog on (the Pi 5 firmware ignores `dtparam=audio`; no HDMI audio
  card), no `vc4-kms-v3d` (display off on the pedal, following distro-slimming's point about the
  GPU's memory traffic), the kernel console on `ttyAMA10`. The WM8960 overlay stays
  loaded at runtime by `pedal-codec`, as on piv.
- rescue-boot keeps the KMS driver, so the HDMI console works with a keyboard.
- `cfg80211.ieee80211_regdom=GB`, the dracut arguments (`rd.shell=0 rd.emergency=reboot
  rd.retry=60 rd.timeout=90`) and `panic=10` on every command line.
- No apt timers, no snapd, no cloud-init, no unattended upgrades: they're not installed, rather
  than masked. `masked-units` for vip gets shorter as a result.
- The EEPROM isn't on the card. `vip-eeprom` is the one way to change it, and `devices/vip/check`
  diffs its version and configuration against `devices/vip/`'s pin — see "The bootloader EEPROM"
  above for the pin, the procedure and what a failed write costs.

## Who owns what

Following "one home per fact" and "work in the repo that owns the change":

| Repo | Owns |
|---|---|
| **rtpi** | The boot-selection mechanism: `vip-boot`, the validate hook, `pedal-guard`'s counter logic in the initramfs, the watchdog and dracut drop-ins, and vip's `device.env` (board facts, `AUDIO_TUNING_ARGS`). Any custom kernel. The rehearsals |
| **pedal.project** | `devices/vip/` (the pedal root's configuration, as for piv), the image build and `make-card` (the appliance), `image.lock` and the manifests, and `--host vip` in `scripts/` |
| **namchain** | The engine, built in the container at a pinned commit. Nothing new in the repo beyond making sure its build works there |

`make-card` lives in `devices/common/` and `devices/vip/make-card` is a link to it, like
`apply`, `check` and `backup`, so a Pi 500 could be rebuilt the same way later. The Pi 5
differences go in `devices/vip/image.env`.

## Steps

Each is committed on its own. rtpi lands before pedal.project where they meet.

1. **A spike card, to prove the boot mechanics on vip** (a throwaway card, stock kernel, no
   pedal). Three FAT partitions and one root, then check by hand:
   - vip's EEPROM boots a GPT card and honours `autoboot.txt` with `tryboot_a_b=1` and
     `boot_partition`.
   - `[tryboot]` in the selected partition's `config.txt` still applies with a partition switch.
   - The spike boots onto WiFi from a connection file written at build time.

   Done when all three are seen and the EEPROM version is recorded. If one fails, the layout
   changes here, before anything is built on it.

   **Done, 2026-09-29.** All three seen, and a fourth: `reboot "<N>"` boots partition N once
   with no flag and no write, which suits `vip-boot rescue`. EEPROM 2026-05-11. What the image
   needed: `net.ifnames=0` (else `wlan0` is `wld0`), a 64-hex WiFi key written unquoted,
   `systemd-timesyncd`, and `systemctl reboot --reboot-argument=…` in `vip-boot`.
2. **rtpi:** `devices/vip/device.env`, and `vip-boot` with its validate hook, the counter and
   the fallback, written for an image-built host. Unit-test the state logic off the board.

   **Done, 2026-09-29.** `tests/vip-boot` (30 tests), and every path run on vip with the spike
   (`bench-results/vip-spike/vip-boot.md`), which found four bugs the tests couldn't: the
   initramfs counter ran before the card's partitions appeared, validation queued two minutes
   behind `network-online.target`, tools missing from the initramfs, and a loose boot with no
   `pedal-maint.target` would strand vip. For step 3: `pedal-maint.target`, and
   `RequiredForOnline=no` on `eth0`. For step 4: `ca-certificates` in both roots, and room for
   dracut on the pedal root.
3. **pedal.project:** `devices/vip/` from `devices/piv/`, not copied blind (no docker or libvirt
   notes, the Pi 5's interrupt layout, 1 GB), and `pedal-device apply --offline` for the image.

   **Done, 2026-09-29.** `devices/vip/`: `namchaind` on the WM8960 (2 in, 2 out; the codec is
   wired to vip, `bench-results/vip-spike/codec.md`), `pedal-tune` pinning the codec's interrupt
   (`dw_axi_dmac_platform`, the RP1's DMA) to core 2 itself, a short mask list, networkd and
   wpa_supplicant with `eth0` not required for online, keys-only sshd, `pedal-maint.target`, and
   `devices/vip/packages`, the pedal root's package list for step 4. The codec files moved to
   `devices/common` (both Pi hosts). `pedal-device apply --root <dir>` applies offline, with the
   root's own systemctl; `devices/vip/test-offline-apply` builds a root from the package list and
   checks the result. The step's plan said `--offline`; it's `--root`, since it needs the root.

   **Changed, P7.** That pin is now core 0, a housekeeping core: the interrupt runs SCHED_FIFO 85,
   above the render thread's 80, so it must not land on an isolated core. Core 2 was the standing
   design when this step was written, not a measurement; see `docs/audio-dma-irq.md`, "Which core
   it lands on (P7)", and D5 of
   `docs/managing-processing-power-and-optimising-for-fast-switching.md`.
4. **The build:** the container, both roots, namchain, the image, the manifest. Done when
   `make-card --image-only` produces an image from pinned inputs, and a second run with the same
   pins produces the same package list and file tree.

   **Done, 2026-09-30.** `devices/vip/make-card` (`devices/common/make-card`, container side
   `devices/common/image/build-image`), pinned by `devices/vip/image.lock`: snapshot
   20260929T000000Z, rtpi 217ca9b, namchain 503aac9 (what piv runs; its HEAD isn't pushed).
   Two runs from the lock (`devices/vip/images/20260929T232637Z.manifest` and `…233219Z`) gave
   the same packages (174 pedal, 159 rescue), the same file trees, and a **bit-identical image**
   (sha256 `9719226b…`): fixed filesystem and partition UUIDs, `SOURCE_DATE_EPOCH` on every file,
   dracut `--reproducible`. About six minutes a run; 5.8 GB, 1.5 GB of it data. namchain's five
   test suites pass in the container. What it does beyond the plan above, or differently:
   - One SSH host key, ed25519, made by the first run as a 1Password SSH Key item
     (`fx/vip-ssh-host`) and read with `?ssh-format=openssh`; `HostKey` names it, `sshd-keygen`
     is masked and `ssh.socket` disabled (sshd runs as `ssh.service`, which validate follows).
   - mDNS by resolved on both roots, so `ssh vip.local` works without the router's DNS.
   - The roots are GPT type root-arm64 and pedal-data generic Linux, so `systemd-repart`
     (`/etc/repart.d/50-pedal-data.conf`) matches pedal-data alone and grows it on first boot;
     fstab's `x-systemd.growfs` grows the filesystem.
   - Rescue: read-only root with tmpfs on `/tmp`, `/var/tmp`, `/var/log`, `/var/lib/systemd` and
     `/var/lib/sudo`, a volatile journal, root autologin on HDMI and the UART header (no
     passwords exist; whoever holds the board holds the card), and a prompt that says rescue.
   - The golden-reference test's own build runs `make -j` unbounded and ran colima's 6 GB out of
     memory; the build makes it first at `-j2`.
   - **Debt:** `pedal-device`'s manifest (`/var/lib/pedal/manifest`) lives on pedal-data with the
     library, so restoring the pedal root from its image keeps the old manifest. Step 7 should
     move it into the root (`/var/lib/pedal-device`), or rewrite it on restore.
5. **The card:** done when a blank card goes into vip, vip powers on, and without any other step
   `ssh vip` works, `devices/vip/check` is green, `namchaind` is running the default rig, and
   `components.lock` matches the manifest.

   **Done, 2026-09-30**, on the third card (`bench-results/vip-card/results.md`). The first hung at
   `systemd-firstboot` (machine-id `uninitialized`); the second needed the library the card
   doesn't carry, so namchain now plays a block whose model or IR is missing as a bypass and
   ljoss marks it (f422dd0, 5da4ea6). A fresh card boots playing the default rig's blocks as
   bypasses, and `sync-library --host vip` brings the rig in without a restart. `pedal-tune
   check` learned that the RP1's interrupt chip reports no effective affinity. Left for step 8:
   `components.lock` holds one host, piv, and `devices/vip/apply` overwrites it.
6. **Rehearse every fallback on vip**, as rtpi did on piv, and record the results in
   `bench-results/`:
   - a kernel candidate that passes, and one that can't find its root;
   - a bad boot argument through `try-args`;
   - `loose` once, and as the default;
   - `rescue` once and `--stay`, and back;
   - a pedal root broken on purpose (a unit that hangs the boot, then a broken fstab): it reaches
     rescue by itself after three boots, and `vip-reimage pedal` from rescue puts it back;
   - no network at all: the pedal plays and stays in the pedal root;
   - power pulled during boot, and during a rig save.

   **Done, 2026-09-30** (`bench-results/vip-card/fallbacks.md`), everything passing in the end.
   Found and fixed on the way: the loose profile locked everyone out (`pedal-maint.target` lacked
   `systemd-user-sessions`); `vip-boot status` crashed on rescue's read-only root; OpenSSH 10
   penalised the Mac for waiting on a boot (local networks are now exempt); and a pedal root that
   hung or dropped to emergency mode would never have rebooted, so the counter never moved. Now
   emergency and rescue mode reboot, and **`vip-boot deadline`** reboots a pedal boot that hasn't
   cleared the counter in five minutes (never one that reached the engine). A hanging root reached
   rescue by itself in 16.5 min, a broken fstab in 6.5; `vip-reimage pedal` (rtpi) restored it from
   pedal-data in about 10. Rig saves and the boot counter survived power pulls.
7. **Reimage from the Mac, without touching the card:** `make-card --remote` streams a new
   pedal root to vip while it's in rescue, then boots it as a candidate. After this, reproducing
   vip is one command even when it's sealed in the enclosure.

   **Done, 2026-09-30** (`bench-results/vip-card/remote.md`). `make-card --remote` takes vip to
   rescue (rescue the default), sends the image into pedal-data (checked, the old one kept as
   previous), writes it over the pedal root, boots it once, and makes it the default only once the
   engine stays up and `vip-boot-validate` passes: 16 minutes with the build. A broken root is
   refused and falls back to rescue; `--remote --previous --image <dir>` put the good one back in 5.
   That test found `pedal-guard` counting a restarting namchaind as up; now the engine must stay
   up in one run for 10 s. Not covered: a kernel change (refused: `vip-boot try-kernel`'s job), and
   the rescue root and boot partitions, which only a card write changes.
8. **The move:** `--host vip` in `status`, `host-lock`, `deploy-engine`, `sync-library` and
   `components-lock`; `AGENTS.md`, `working-across-repos.md` and `plan.md` say vip is the Core
   host and piv goes back to being the build host; the SSL 2+ moves to vip.

   **Done, 2026-10-01.** Every script defaults to vip (`--host piv` for piv). `components.lock`
   is per host, `devices/<host>/components.lock`, so applying to one host doesn't rewrite
   another's. `scripts/deploy-engine --host vip` builds namchain on the Mac in the image's
   container (`devices/common/image/build-namchain`, shared with the image build, whose binaries
   came out byte-identical after the change) and installs it; its first run found a test that
   can't make a Unix socket in a directory shared from the Mac, so it builds inside the container.
   `AGENTS.md`, `working-across-repos.md` and `hardware-handoff.md` say vip is the Core host;
   testing happens on it for now, and piv isn't updated (`plan.md`). The SSL 2+ stays with piv:
   vip plays through the WM8960.

Later, not now: the read-only pedal root and a second pedal root for A/B updates (Phase 4),
using `pedal-data` and the same `vip-boot` candidate path.

## Decided, 2026-09-29

| # | Question | Decision |
|---|---|---|
| 1 | The base | **Ubuntu 26.04 `resolute`**, minimal, with `linux-raspi-realtime`: the kernel every piv number was measured on. Raspberry Pi OS Lite would have meant an rtpi-built kernel from the start |
| 2 | Secrets | **1Password**, read with `op` at build time and written into the roots as runtime files. vip **reuses piv's `namchaind` token** |
| 3 | Cards | **32 GB** in vip. The 8 GB can be the spare |
| 4 | The Debug Probe | **Stays on the Pico** for now. The console is set up on vip's header, so moving it is easy |
| 5 | Ethernet | **None near vip.** WiFi is the way in; moving vip onto a cable is the rescue path |

Still open: whether the plan's next item, the Phase 1 step 8 soak, runs on piv as planned or
waits for vip.
