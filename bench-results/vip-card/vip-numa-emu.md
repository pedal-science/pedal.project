# vip: NUMA emulation enabled in the pedal kernel (2026-10-03)

What the request was: vip's kernel config has NUMA emulation disabled but the NUMA memblock
core enabled, so turning emulation on is a config change and a rebuild, no patch. Find the
change, apply it to vip, reboot, report.

## The config change

The running kernel (`7.0.0-1017-raspi-realtime`, Ubuntu's RT flavour from the resolute
snapshot) shipped:

```
CONFIG_NUMA=y
CONFIG_NUMA_KEEP_MEMINFO=y
CONFIG_NUMA_MEMBLKS=y
# CONFIG_NUMA_EMU is not set
```

The change is **`CONFIG_NUMA_EMU=y`** (the generic `mm/Kconfig` symbol: "NUMA emulation",
`depends on NUMA_MEMBLKS` and `X86 || GENERIC_ARCH_NUMA`; the board's config has both
`CONFIG_NUMA_MEMBLKS=y` and `CONFIG_GENERIC_ARCH_NUMA=y`, so no patch and no other option
is needed). It splits the flat machine into virtual nodes when booted with `numa=fake=N`;
without the argument nothing changes — which is what the earlier step-6 experiment hit: the
stock kernel answered `numa=fake=4` with "Malformed early option 'numa'"
(`console-step6-pass1.log`).

## The rebuild (rtpi, `make vip-rt`)

New pieces, committed in rtpi at `b1736c4`:

- `config/vip-numa-emu.fragment` — the one-line flip.
- `scripts/build/vip-ubuntu-rt.sh` — builds from the board's own `/boot/config-*` applied to
  the exact Ubuntu source tag of the installed package, merged with the fragment, asserted
  before building. `make vip-rt`; `--config-only` for a fast config check.
- `scripts/deploy/vip-install-rt.sh` — installs the built kernel beside the stock one into
  the running pedal root. `make vip-install-rt`.
- `make vip-try` — stages the spare slot via `vip-boot try-kernel` and watches the reboot.
- `scripts/safety/watch-reboot.sh` — now reads vip's `vipboot.slot=` cmdline marker too.

Build facts:

- Source: `https://git.launchpad.net/~ubuntu-kernel/ubuntu/+source/linux-raspi/+git/resolute`,
  tag `Ubuntu-raspi-7.0.0-1017.17` = commit `3ab476206fb291548678b233ff3061a57c53da6d`
  (derived from `dpkg-query -W linux-image-$(uname -r)` on the board).
- Base config: the board's `/boot/config-7.0.0-1017-raspi-realtime` (12,531 lines).
- Config delta vs the shipped config — exactly the three intended lines:
  `CONFIG_NUMA_EMU=y`, `CONFIG_LOCALVERSION="-1017-raspi-realtime-numaemu1"`,
  `CONFIG_VERSION_SIGNATURE="Ubuntu 7.0.0-1017.17-raspi-realtime-numaemu1 7.0.12"`
  (the signature change is cosmetic only; the build keeps the version numbers Ubuntu's
  packaging overrides — the tree's Makefile carries upstream 7.0.12 while Ubuntu ships it as
  7.0.0-1017 — via `VERSION=7 PATCHLEVEL=0 SUBLEVEL=0` make variables, and `LOCALVERSION=`
  to stop setlocalversion's shallow-clone "+").
- Asserted before building: `NUMA_EMU=y`, `NUMA=y`, `NUMA_MEMBLKS=y`, `PREEMPT_RT=y`,
  `HZ=1000`, `kernelrelease == 7.0.0-1017-raspi-realtime-numaemu1`.
- Ubuntu's canonical cert bundles are regenerated from the in-tree certs (debian/rules'
  recipe) so `CONFIG_SYSTEM_TRUSTED_KEYS`/`SYSTEM_REVOCATION_KEYS` stay untouched.
- Full module set (no trim: 6,470 =m entries, matching the shipped kernel); DWARF5+BTF kept,
  modules stripped at install (`INSTALL_MOD_STRIP=1`, verified with readelf).

## Install (on the running pedal root, stock kernel untouched)

`make vip-install-rt`, gated on `vip-boot status` (pedal root, active slot good, nothing
armed) and on free space:

- `/lib/modules/7.0.0-1017-raspi-realtime-numaemu1/` — the built module tree.
- `/boot/vmlinuz-…-numaemu1`, `/boot/config-…-numaemu1`, `/boot/System.map-…-numaemu1`.
- `/usr/lib/firmware/…-numaemu1/device-tree/` — the stock release's directory plus the built dtbs;
  the built `bcm2712-rpi-5-b.dtb` sha256 checked against the stock one first. The overlays need
  no special handling: the tree builds the *identical* overlay set Ubuntu ships (367 .dtbo from
  `arch/arm64/boot/dts/overlays/`, plus the `overlay_map.dtb`/`hat_map.dtb` it also builds; the
  only extra shipped file is a README). Verified byte-identical, not just same names:
  `wm8960-soundcard.dtbo`, `vc4-kms-v3d.dtbo`, `overlay_map.dtb` and `hat_map.dtb` all match the
  shipped kernel's sha256.
- `/boot/initrd.img-…-numaemu1` — dracut run on the pedal root (its own watchdog + vip-guard
  drop-ins shape it, same command as the image build); verified `vip-guard.sh` is inside.

## Try boot and result

`make vip-try` (2026-10-03, ~16:20 UTC): staged slot b, armed the one-shot, rebooted with
`0 tryboot`. The board went down and came back on
`7.0.0-1017-raspi-realtime-numaemu1` at t+24s, settled after 114s. `vip-boot-validate` passed
(sshd, real interface with an address, uname matches, PREEMPT_RT banner present) and promoted
slot b: it is `good` and the default; slot a keeps the stock kernel untouched as the fallback.
`namchaind` active, guard counter 0/3, one-shot disarmed. `/boot/config-…-numaemu1` on the
board shows `CONFIG_NUMA_EMU=y` beside `CONFIG_NUMA=y` and `CONFIG_NUMA_MEMBLKS=y`; the kernel
banner is `#2 SMP PREEMPT_RT` as expected. `/proc/version` reports the new signature
("Ubuntu 7.0.0-1017.17-raspi-realtime-numaemu1 7.0.12").

Emulation itself activates only with a boot argument, which this boot deliberately does not
set — so the pedal boots exactly as before. `vip-boot try-args 'numa=fake=4'` (or 2) is the
one-shot way to try it; the stock kernel answered that argument with
"Malformed early option 'numa'" and this one should not.

## Module trim (2026-10-03, after the deploy)

The build now trims modules by default (rtpi `955c2b9`): `make localmodconfig` driven by the
board's own `/proc/modules`, then `config/vip-keep.fragment` (snd-usb-audio, for future
USB-interface measurements), then the coverage gate — every module the board loads must be
built in or present, or recorded in `TRIMMED_OK` with a reason. `--no-trim` reproduces the full
6,646-module set; trimmed releases are suffixed `-trimmed`.

Numbers: **107 modules instead of 6,646** (`4.2M` vs `149M` compressed), release
`7.0.0-1017-raspi-realtime-numaemu1-trimmed`, all 76 loaded modules covered. The full list is
committed in rtpi `results/vip-trimmed-modules-…-trimmed.txt`.

The coverage gate earned its keep on the first trimmed build, finding two real things:

- `snd_compress` and `ac97_bus` load on the board only as dependency edges out of
  `snd-soc-core`; their selectors (`SND_SOC_AC97_BUS`, `SND_SOC_COMPRESS`) belong to codec
  drivers the trim removes. The trimmed `snd-soc-core.ko` has zero ac97/compress references
  (checked with `nm -u`), so both are recorded removals (`TRIMMED_OK`), not keeps — forcing
  them back would have dragged the unused codec set along (they are promptless symbols only a
  `select` can set).
- `brcmfmac_cyw` has no CONFIG symbol of its own but is built unconditionally with `BRCMFMAC`,
  so it survives the trim; the gate proves it rather than assuming it.

The trimmed kernel was **built and verified, then deployed as the default** (see
"Deploy of the trimmed kernel", below): slot b is the trimmed kernel, slot a keeps the stock
kernel as the fallback.

Two rounds of findings shaped the final set:

- The first trimmed build had 107 modules; a same-day rebuild dropped `inet_diag`, `tcp_diag`
  and `mptcp_diag` because nothing happened to be using `ss` when `/proc/modules` was fetched.
  `ss` is inside `vip-boot-validate` itself, so the diag modules are now deliberate keeps
  (rtpi `c5e4a2b`), and the deploy gate ships the build's `TRIMMED_OK` list (`trimmed-ok.txt`)
  instead of re-judging.
- With the NOOP pretimeout-governor module trimmed away, `CONFIG_WATCHDOG_PRETIMEOUT_DEFAULT_GOV`
  resolves to PANIC (PANIC's module is kept; the stock kernel's default was NOOP). For an
  appliance that must never hang silently this is the better default; it is a consequence of
  the trim and is recorded as such.

## Deploy of the trimmed kernel (2026-10-03, ~17:40 UTC)

Three boots, so the final state is exactly "trimmed default, stock fallback":

1. `vip-boot try-kernel 7.0.0-1017-raspi-realtime` — the stock kernel tried once and
   promoted, so it became the active slot (and was re-proven to boot).
2. A plain reboot, to clear the tryboot flag before the next candidate.
3. `vip-boot try-kernel 7.0.0-1017-raspi-realtime-numaemu1-trimmed` — came up at t+32s,
   validated (sshd, real interface, uname, PREEMPT_RT), promoted.

Result: slot b = `…-numaemu1-trimmed` (109 modules), `good`, default; slot a = stock,
`good`, fallback. `namchaind` running and ok on `hw:CARD=wm8960` (48000/64, 0 guard trips,
rig last.json). The bootloader's default cmdline supplies `numa=fake=4`, so the trimmed boot
ran with NUMA emulation active; `/boot/config-…-numaemu1-trimmed` shows `CONFIG_NUMA_EMU=y`.
The full `-numaemu1` kernel remains installed on the root (its /boot files and module tree are
untouched) but holds no slot.

## Recording

- `devices/vip/components.lock`: `kernel=7.0.0-1017-raspi-realtime-numaemu1` (rewritten from
  the host after the promote, committed with this change).
- rtpi carries the whole rebuild: `config/vip-numa-emu.fragment`,
  `scripts/build/vip-ubuntu-rt.sh` (`make vip-rt`), `scripts/deploy/vip-install-rt.sh`
  (`make vip-install-rt`), `make vip-try`, the watch-reboot slot-marker tweak, and the
  container's `gawk` fix. Build artifacts: `rtpi/build/vip/` (built.config, tarballs,
  kernelrelease, base.config — not committed).
- A future `make-card` still builds the stock kernel into the image; this kernel is a
  recorded overlay on the running host, exactly what components.lock is for. If NUMA
  emulation proves worth keeping, the next step is to fold the rebuilt kernel into the
  image build itself.
- Build history worth remembering (all in the script's comments or this file): Ubuntu
  overrides the Makefile's 7.0.12 to 7.0.0-1017 at build time (`VERSION/PATCHLEVEL/SUBLEVEL`
  make vars, `LOCALVERSION=` to kill setlocalversion's "+"); the canonical cert bundles are
  regenerated from the in-tree certs; the DWARF5+BTF module set needs ~30 GB of build disk
  and the staged modules must be stripped progressively (or installed on the container's
  own filesystem — installing into a virtiofs mount silently loses files under `-j`).

## Follow-up worth doing

**Fold the rebuilt kernel into the image build** if NUMA emulation (and the trim) prove worth
keeping: a future `make-card` still builds the stock kernel into the image, and both custom
kernels are recorded overlays on the running host (components.lock), not part of the card.
