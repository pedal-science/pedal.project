# vip: the card image

**Status:** plan, 2026-09-29. vip (Raspberry Pi 5, 1 GB) has arrived. This covers how vip is made
from nothing: one command on the Mac builds everything and writes a blank SD card, and the card
boots vip straight onto the network. It also covers how vip keeps itself reachable when a
kernel, a command line or its own root filesystem is broken. The choices marked **yours** are
listed at the end. Nothing is built yet.

It settles the open question in `plan.md` ("which repo owns vip's kernel and boot
configuration") as proposed below, under [Who owns what](#who-owns-what).

## The goal

```
devices/vip/make-card            # on the Mac, with a blank card in the reader
```

Then put the card in vip, power it on, and `ssh vip` works about a minute later. `devices/vip/check`
is green, `namchaind` is running the default rig, and `scripts/status --host vip` shows the
commits it was built from. Run it again with the same pinned inputs and you get the same system.

No step happens by hand on vip, and none happens on piv. vip has no compiler (as `tib` had none,
`working-across-repos.md`), so everything arrives built.

## What exists already, and what carries over

| From | What | Use on vip |
|---|---|---|
| rtpi, piv | A/B kernel slots in one boot partition (`current/`, `new/`, `old/`), chosen by the Pi firmware's one-shot `tryboot` flag and `os_prefix`. Both rehearsals passed on hardware | The same slot layout for vip's kernel. The mechanism, not Ubuntu's `piboot-try` script (see below) |
| rtpi, piv | `piboot-validate`: sshd listening, a *physical* interface with an address, the expected kernel, PREEMPT_RT. The dracut lockout arguments. The watchdog at 14 s, in the initramfs too | All of it, for candidates |
| rtpi, piv | `AUDIO_TUNING_ARGS` (isolcpus, nohz_full, rcu_nocbs on 2-3, irqaffinity 0-1, skew_tick) staged as a candidate command line, so a bad set of arguments rolls back like a bad kernel | The "tuned" profile below |
| rtpi, piv | Ubuntu's `linux-raspi-realtime` 7.0.0-1017 is already well configured for RT, and a custom build buys little (rtpi README, "Is a custom kernel worth building for piv?") | vip's first kernel. rtpi's `piv-ubuntu-rt`/`piv-vendor-rt` builds stay available for when a patch is needed |
| rtpi, tib | The lesson from tib's one-shot: fail *safe*. A failed clear, a hang or a power cut returns to the known-good | Every mechanism below keeps that property |
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
| 2 | `pedal-boot` | FAT32 | 512 MB | The pedal's `config.txt`, and kernel slots `current/`, `new/`, `old/`, each with its kernel, initramfs, DTBs, overlays and `cmdline.txt` |
| 3 | `rescue-boot` | FAT32 | 256 MB | The rescue kernel, initramfs, DTBs and `config.txt` |
| 4 | `rescue` | ext4 | 1.5 GB | The rescue root. Mounted read-only, `/var` and `/tmp` on tmpfs |
| 5 | `pedal` | ext4 | 3 GB | The pedal root |
| 6 | `pedal-data` | ext4 | rest | `/var/lib/pedal` (the library, rigs, `last.json`), soak evidence, and `images/`: the pedal root's image that rescue can restore from |

The image is about 6 GB and fits the 8 GB card; the data partition grows to fill the card on first
boot (`systemd-repart`). The library is 15 MB today, so size isn't a constraint either way.
**Proposed:** vip runs from the 32 GB card, for headroom and wear levelling, and the 8 GB card is
made by the same command as the spare (**yours**). The data partition is there from day one
because it's the one thing that's hard to add later. Phase 4's read-only pedal root and a second
pedal root for A/B updates can come later: they need `pedal-data` to exist, and nothing else.

## How it boots, and how it falls back

The firmware's `tryboot` flag is one-shot: `reboot '0 tryboot'` sets it, and the firmware clears
it *before* loading anything. So anything chosen with it lasts one boot, and a hang, a watchdog
reset or a power cut returns to the default. With `tryboot_a_b=1`, the flag selects a
partition in `autoboot.txt`, and `[tryboot]` sections in that partition's `config.txt` also apply.
That's what piv uses today, one level down.

One tool, `vip-boot`, is the only thing that writes `autoboot.txt` and the `[tryboot]` sections.
It arms a one-shot by writing the `[tryboot]` blocks for what you asked for, then reboots with the
flag. The `[all]` default changes only on promotion or when you ask for a new default.

| You want | Command | What boots | Afterwards |
|---|---|---|---|
| Normal | power on | pedal-boot `current/`, tuned | — |
| Try a kernel | `vip-boot try-kernel <rel>` | pedal-boot `new/` once | validate passes → promote `new/` → `current/` → `old/`. Anything else → `current/` again, and `new/` is marked bad |
| Try new boot arguments | `vip-boot try-args '<args>'` | `new/` with the same kernel and the new command line | the same as a kernel |
| One loose boot | `vip-boot loose` | `current/`, loose profile | next boot is tuned |
| Loose until told otherwise | `vip-boot default loose` | loose every boot | `vip-boot default tuned` |
| Rescue once | `vip-boot rescue` | rescue-boot | next boot is the pedal |
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

**Console.** Unlike the Pi 500, the Pi 5 has a 3-pin UART debug header. The Debug Probe plugs
straight into it, the kernel console goes there (`ttyAMA10`), and `BOOT_UART=1` in the EEPROM
adds the bootloader's own output. That gives a remote read of a failed boot and, for Phase 1
step 7, the firmware time that piv couldn't measure. It also frees pins 8/10 (`ttyAMA0`) for the
Pico link, which is Phase 3 step 4's open question. The basket has one Debug Probe, and the
Pico bench uses it too, so a second probe or an FTDI cable may be worth adding (**yours**).

## The build

Everything runs in colima on the Mac. The M2 is arm64, so the container runs aarch64 Ubuntu
natively, with no qemu and no emulation. Nothing needs loop devices or a privileged container:

- **Roots:** `mmdebstrap --variant=minbase` from `snapshot.ubuntu.com` at a pinned timestamp, so
  the same inputs give the same packages. Ubuntu 26.04 `resolute` (**yours**; see the end), with
  `resolute-updates` for the 7.0.0-1017 kernels. `SOURCE_DATE_EPOCH` is set from the pinned
  snapshot.
- **Customisation** happens in mmdebstrap hooks: user `rik`, the hostname, fstab by label, the
  network, the watchdog drop-ins, the dracut safety arguments, the SSH host keys and the secrets.
  Then, for the pedal root:
  - `pedal-device apply --offline` installs `devices/common` + `devices/vip`, enables units and
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

**Secrets never enter git.** The WiFi PSK, the `namchaind` token and the SSH host keys live in
`~/.config/pedal/vip/` (mode 600). The first run asks for what's missing and generates the host
keys once. Keeping the host keys means a reflashed vip is the same machine to `ssh`, with no
`known_hosts` warning. `authorized_keys` comes from the 1Password agent (`ssh-add -L`). Where the
PSK and token come from is **yours**: see the end.

### Writing the card

The same guards as rtpi's `restore-sd-on-mac.sh`:

- List external physical disks, and refuse an internal disk and anything that isn't removable.
- Show the name and size, and ask you to type `vip` before writing.
- `diskutil unmountDisk`, then `sudo dd` to `/dev/rdiskN` (the raw node is several times faster),
  with progress.
- Read the written length back and compare its hash, then eject.

`--image-only` stops before the card; `--disk /dev/diskN` skips the prompt for which disk (not the
confirmation).

### Pi 5 settings in the image

- `config.txt` for pedal-boot: `arm_64bit`, the watchdog on, `dtparam=audio=off` (no HDMI audio
  card), no `vc4-kms-v3d` (display off on the pedal, following distro-slimming's point about the
  GPU's memory traffic), a small CMA, the kernel console on `ttyAMA10`. The WM8960 overlay stays
  loaded at runtime by `pedal-codec`, as on piv.
- rescue-boot keeps the KMS driver, so the HDMI console works with a keyboard.
- `cfg80211.ieee80211_regdom=GB`, the dracut arguments (`rd.shell=0 rd.emergency=reboot
  rd.retry=60 rd.timeout=90`) and `panic=10` on every command line.
- No apt timers, no snapd, no cloud-init, no unattended upgrades: they're not installed, rather
  than masked. `masked-units` for vip gets shorter as a result.
- The EEPROM isn't on the card. `devices/vip/check` reports its version and config, and a
  one-off `vip-eeprom` sets `BOOT_UART=1` and the boot order with `rpi-eeprom-config`, recorded
  in `devices/vip/`.

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
   - The debug UART on the Debug Probe shows the bootloader and the kernel.

   Done when all three are seen and the EEPROM version is recorded. If one fails, the layout
   changes here, before anything is built on it.
2. **rtpi:** `devices/vip/device.env`, and `vip-boot` with its validate hook, the counter and
   the fallback, written for an image-built host. Unit-test the state logic off the board.
3. **pedal.project:** `devices/vip/` from `devices/piv/`, not copied blind (no docker or libvirt
   notes, the Pi 5's interrupt layout, 1 GB), and `pedal-device apply --offline` for the image.
4. **The build:** the container, both roots, namchain, the image, the manifest. Done when
   `make-card --image-only` produces an image from pinned inputs, and a second run with the same
   pins produces the same package list and file tree.
5. **The card:** done when a blank card goes into vip, vip powers on, and without any other step
   `ssh vip` works, `devices/vip/check` is green, `namchaind` is running the default rig, and
   `components.lock` matches the manifest.
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
7. **Reimage from the Mac, without touching the card:** `make-card --remote` streams a new
   pedal root to vip while it's in rescue, then boots it as a candidate. After this, reproducing
   vip is one command even when it's sealed in the enclosure.
8. **The move:** `--host vip` in `status`, `host-lock`, `deploy-engine`, `sync-library` and
   `components-lock`; `AGENTS.md`, `working-across-repos.md` and `plan.md` say vip is the Core
   host and piv goes back to being the build host; the SSL 2+ moves to vip.

Later, not now: the read-only pedal root and a second pedal root for A/B updates (Phase 4),
using `pedal-data` and the same `vip-boot` candidate path.

## Yours to decide

1. **The base.** Proposed: **Ubuntu 26.04 `resolute`**, minimal, with `linux-raspi-realtime`.
   It's the kernel every piv number was measured on, and it's already PREEMPT_RT. The
   alternative is Raspberry Pi OS Lite (trixie): a smaller, better-supported Pi userland, but its
   kernel isn't RT, so vip would start on an rtpi-built kernel (`piv-vendor-rt`) and piv's
   measurements wouldn't carry over directly.
2. **Secrets.** Where the WiFi PSK and the `namchaind` token come from: a file in
   `~/.config/pedal/vip/` that the first run asks for (proposed), or 1Password through `op`. And
   whether vip reuses piv's token, so ljoss connects unchanged, or gets its own.
3. **Cards.** 32 GB in vip, and the 8 GB made as the spare (proposed)?
4. **The Debug Probe.** Permanently on vip's UART header, with a second probe or an FTDI cable
   for the Pico bench?
5. **Ethernet.** Is there a cable near vip? Both roots bring up `eth0` if there is, and it's a
   second way in while WiFi is being worked on.
6. **The plan's next item** is the step 8 soak on piv. Run it on piv as planned, or wait and run
   it on vip once step 5 is done, since vip is the machine that matters?
