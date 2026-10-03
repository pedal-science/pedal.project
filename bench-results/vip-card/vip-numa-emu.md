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

**Module trim for vip kernel builds.** vip loads 74 modules; the config builds 6,470, and the
module set is where the build's hour goes. tib-rt.sh already has the mechanism: pull
`/proc/modules` off the board, `make localmodconfig`, a keep-list fragment for hardware not
attached on build day (wifi first), and an assertion that every loaded module is built-in or
present. A vip version is the same three pieces (a `--trim` flag in vip-ubuntu-rt.sh, a
`config/vip-keep.fragment`, the coverage check), tried with its own try-kernel boot. Left
undone deliberately: this build had to differ from the shipped kernel by one line, and a trim
is a second variable worth its own test.
