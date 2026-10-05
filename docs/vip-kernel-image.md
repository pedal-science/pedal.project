# vip's card: the pedal kernel, and the stock fallback beside it

**Status: implemented, 2026-10-05.** rtpi `ad9fee1` is the kernel half (`device.env`,
`vip-boot init-pedal-boot --fallback-release`, `vip-install-kernel`, the build/install scripts);
the commit beside this file is the pedal.project half. What differs from the plan is under
"What changed in the doing" at the end.

`devices/vip/make-card --remote --image build/vip/20261005T193736Z-dirty` refused, correctly:

```
[x] vip runs 7.0.0-1017-raspi-realtime-numaemu1-trimmed and the image 7.0.0-1017-raspi-realtime:
    a kernel change goes through vip-boot try-kernel, not a new root (yet)
```

`--remote` writes the pedal *root* and nothing else: the FAT pedal-boot partition, and so the
kernel and initrd the firmware loads, is untouched. A new root carrying only the stock kernel's
modules, booted by a slot holding the rebuilt kernel, comes up without `brcmfmac` and without the
codec's modules — no WiFi, nothing to ssh to. The guard is the difference between a refusal and a
card-reader trip.

The deeper fact is that vip's kernel stopped being the card's kernel on 2026-10-03/04. rtpi built
Ubuntu's `linux-raspi` RT kernel again with `CONFIG_NUMA_EMU=y` (rtpi `b1736c4`), trimmed it to the
modules the board actually loads (`955c2b9`, plus `c5e4a2b` and `e873c9c`), installed it into the
*running* root with `scripts/deploy/vip-install-rt.sh`, and promoted it with `vip-boot try-kernel`.
Both slots now hold `7.0.0-1017-raspi-realtime-numaemu1-trimmed`; `dpkg` still knows only the stock
package; the card still builds the stock kernel. Two kernel stories, and the board is on rtpi's.

## The goal

1. A card that boots the kernel the pedal is meant to run — rtpi's rebuild — built from rtpi's
   artefacts rather than from an apt package.
2. **Slot b holds the stock RT kernel, `good`**, so the A/B property rtpi's installer protects
   survives a reflash: a pedal kernel that will not come up has a validated fallback to hand.
3. The pedal root carries **both** releases' modules, `/boot` files and initrds, so either slot
   boots against it — the same arrangement rtpi's installer already leaves on a running root.
4. A kernel rebuild is a deliberate, recorded act: the artefacts are pinned by hash, and the card
   records which rtpi commit and which bytes went in.
5. `--remote` still refuses what it cannot move, and says which release and slot it objected to.

## What exists today

**vip-boot's slots** (rtpi `devices/vip/usr/local/sbin/vip-boot`):

- `SLOTS="a b"`, two self-contained directories in the pedal-boot partition: `vmlinuz`,
  `initrd.img`, the `bcm2712*.dtb`, `overlays/`, `kernel.release`, `tuned.args`,
  `cmdline-{tuned,loose}.txt`, `state` (`empty|staging|trying|good|bad`). `profile.txt` names the
  active slot and the default profile; `tryboot.txt` arms one one-shot (`os_prefix=<slot>/`).
- `init-pedal-boot` fills **only the first slot** and marks it `good`; the other is created
  `empty`. So a card has one kernel and no fallback slot — the gap this plan closes.
- `vip-boot-validate <release>` is handed **the slot's own release** (`cmd_validate` reads it from
  `kernel.release`), so two different releases in the two slots are already supported by
  construction. Nothing in the A/B machinery assumes they match.
- `try-kernel <release>` fills the **spare** slot from the running root's `/boot/vmlinuz-<release>`
  and `/usr/lib/firmware/<release>/device-tree`, then boots it once; validation promotes it, and
  the slot it displaced becomes the previous kernel. That is the whole rollback mechanism, and it
  works for either release because the root carries both.

**rtpi's build** (`scripts/build/vip-ubuntu-rt.sh`, `make vip-rt`) leaves in `build/vip/`:

| File | What it is |
|---|---|
| `kernelrelease` | the release string, e.g. `7.0.0-1017-raspi-realtime-numaemu1-trimmed` |
| `boot-<rel>.tar.gz` | `boot/{vmlinuz,config-<rel>,System.map-<rel>}` + `dtb/bcm2712*.dtb` |
| `modules-<rel>.tar.gz` | `lib/modules/<rel>`, stripped, `INSTALL_MOD_STRIP=1` |
| `build-kind` | `full` or `trimmed` |
| `trimmed-ok.txt` | the modules the trim deliberately drops (`ac97_bus snd_compress`) |
| `proc-modules` | the board's loaded modules at build time — the coverage gate's input |
| `bcm2712-rpi-5-b.dtb.sha256` | the built dtb's hash, checked against the stock one |
| `base.config`, `built.config` | the stock config and the result, for the config delta |

**rtpi's install** (`scripts/deploy/vip-install-rt.sh`, `make vip-install-rt`, then `make vip-try`)
does, on the running pedal root: gates on `vip-boot status` (pedal root, nothing armed, active slot
good, ≥600 MB free), extracts the modules at `/`, runs the module-coverage gate, installs
`/boot/vmlinuz-<rel>` + config + System.map, copies the **stock** release's
`/usr/lib/firmware/<stock>/device-tree` to the new release's directory and overwrites
`broadcom/*.dtb` with the built ones, runs `dracut --kver <rel>` with exactly build-image's flags
and asserts `vip-guard.sh` is in the initrd.

**The image build** (`devices/common/image/build-image`) installs the stock kernel from
`devices/vip/packages`, installs rtpi's userland (`vip-boot`, the validate hook, the guard
drop-ins, `device.env`) into the root, runs `dracut` for the one release, fills slot a with it, and
records one `pedal-kernel` line in the manifest.

## The design

**One name each.** `device.env` keeps `PEDAL_KERNEL` and gains `FALLBACK_KERNEL`:

| Name | Release | Comes from | Lives in |
|---|---|---|---|
| `PEDAL_KERNEL` | `7.0.0-1017-raspi-realtime-numaemu1-trimmed` | rtpi's artefacts | slot a, the root's `/lib/modules`, `/boot`, the manifest |
| `FALLBACK_KERNEL` | `7.0.0-1017-raspi-realtime` | `devices/vip/packages` (apt, pinned snapshot) | slot b, the root's `/lib/modules`, `/boot` |
| `RESCUE_KERNEL` | `7.0.0-1017-raspi` | rescue packages | the rescue root and its boot partition — unchanged |

Nothing on the board reads `PEDAL_KERNEL` today (checked: only rtpi's build and deploy scripts and
build-image do), so this rename costs no runtime behaviour.

**The card.** Slot a = `PEDAL_KERNEL`, good and active. Slot b = `FALLBACK_KERNEL`, good and idle.
`profile.txt` names a. The root carries both trees, so `vip-boot try-kernel <either>` works, and a
promotion moves the *other* kernel into the spare — the same swap rtpi's installer relies on today.

**The pedal kernel is an artefact, not a package.** Why not the obvious alternatives:

- Not apt: the release exists in no archive; rtpi's install script says so in its header ("not
  dpkg: vip is built from an image and its kernel never comes from apt").
- Not a `.deb` in git: 15 MB + 4.4 MB of binaries per build, and rtpi's rule is that a kernel is
  rebuilt, not committed.
- Not rebuilt inside the image build: the trimmed build's inputs are the **board's** `/proc/modules`
  and the **board's** running config, so it is not hermetic from the repo by construction — and it
  costs a full kernel build inside a container that is already 15 minutes. See open question 3.

So the artefacts are an **input pinned by hash**, the way the snapshot date and the three commits
already are.

**The procedure lives once.** The board-side half of `vip-install-rt.sh` becomes
`devices/vip/usr/local/sbin/vip-install-kernel` (rtpi), taking `--artefacts DIR` and `--root DIR`.
rtpi's installer calls it with `--root /`; build-image calls it inside the chroot. One copy of the
module-coverage gate, the dtb check, the dracut invocation and the `vip-guard.sh` assertion, which
is the part most likely to drift if written twice.

## Changes

### rtpi first (pedal.project's build reads rtpi's `device.env` at the pinned commit)

1. **`devices/vip/device.env`** — `PEDAL_KERNEL=7.0.0-1017-raspi-realtime-numaemu1-trimmed`, new
   `FALLBACK_KERNEL=7.0.0-1017-raspi-realtime`, with the comment that the pedal kernel arrives as
   artefacts through the card image and the fallback is what `packages` installs.
2. **`devices/vip/usr/local/sbin/vip-boot`** — `init-pedal-boot` gains `--fallback-release <rel>`
   (optional; without it, today's behaviour). Sketch:

   ```python
   def cmd_init_pedal_boot(env, args):
       ...
       first, *others = env["SLOTS"].split()
       write_new(os.path.join(d, "profile.txt"), profile_text(first, "tuned"))
       write_new(os.path.join(d, "tryboot.txt"), tryboot_text(None))
       board = Board(env); board.pedal_boot = d
       for s in [first] + others:
           os.makedirs(board.slot_dir(s), exist_ok=True)
           write_new(os.path.join(board.slot_dir(s), "state"), state_text("empty"))
       fill_slot(board, first, args.release, env["AUDIO_TUNING_ARGS"], kernel_root=args.kernel_root)
       board.set_state(first, "good")
       if args.fallback_release:                       # the known-good slot, ready to be tried
           fill_slot(board, others[0], args.fallback_release, env["AUDIO_TUNING_ARGS"],
                     kernel_root=args.kernel_root)
           board.set_state(others[0], "good")
   ```

   `fill_slot` already dies if the release's `vmlinuz`, `initrd.img`, device trees or overlays are
   missing, which is the check that the root really carries what slot b needs. Usage text updated.
3. **`devices/vip/usr/local/sbin/vip-install-kernel`** (new) — the procedure, moved out of the
   heredoc in `vip-install-rt.sh`: `--artefacts DIR --root DIR [--no-dracut]`, the module-coverage
   gate (full: exactly the fallback's modules; trimmed: everything in `proc-modules` present or
   builtin, minus `trimmed-ok.txt`), `/boot` install, device trees from `FALLBACK_KERNEL`'s
   directory with the built `broadcom` dtbs on top, `dracut` in the root with build-image's flags,
   the `vip-guard.sh` assertion. It needs the artefact directory to contain
   `{boot,modules}-<rel>.tar.gz`, `kernelrelease`, `build-kind`, `trimmed-ok.txt`, `proc-modules`,
   `bcm2712-rpi-5-b.dtb.sha256`.
4. **`scripts/deploy/vip-install-rt.sh`** — keep the `vip-boot status` gates and the scp, then run
   the new script with `--root /`; `STOCK="$PEDAL_KERNEL"` becomes `STOCK="$FALLBACK_KERNEL"`
   throughout (it means "the other kernel", which is the fallback now).
5. **`scripts/build/vip-ubuntu-rt.sh`** — the base and the gates become explicit about the fallback:
   the config comes from `/boot/config-$FALLBACK_KERNEL` and the package version from
   `linux-image-$FALLBACK_KERNEL` (the stock kernel stays installed in the root forever, which is
   what makes the rebuild reproducible from a known baseline regardless of what is running); the
   "refusing to build against a surprise kernel" gate accepts `FALLBACK_KERNEL`, `PEDAL_KERNEL`, or
   a suffixed rebuild of either; a build that reproduces `PEDAL_KERNEL` is what the image pins, and
   a build with a new suffix (`--localversion -numaemu2-trimmed`) is a candidate that goes through
   `try-kernel` first. New: write `built-from` (rtpi commit, `-dirty` if the tree was dirty) and
   `sha256sums` of the three artefacts into `build/vip/`, so the image can record them and
   "every binary carries its commit" holds for the kernel too.
6. **`tests/vip-boot`** — `init-pedal-boot` with and without `--fallback-release` (both slots good,
   profile a, the fallback's `kernel.release`/`tuned.args`/`cmdline-*.txt` written); a fallback
   release that is not installed dies at build time; validation of a slot whose release differs
   from the other slot's.
7. **`README.md`** — a "vip — the pedal kernel" section: `make vip-rt` → `make vip-install-rt` →
   `make vip-try`, how the fallback slot is used, and that the card image ships both.

### pedal.project (after rtpi's commit; `image.lock`'s rtpi pin moves to it)

8. **`devices/vip/packages`** — the `linux-image`/`linux-modules` lines keep their place, with the
   comment changed: this is the **fallback** kernel, installed by apt, the one slot b boots. The
   pedal kernel is not here (it arrives as artefacts).
9. **`devices/vip/image.lock`** — new lines, hand-changed like the snapshot:

   ```
   kernel=7.0.0-1017-raspi-realtime-numaemu1-trimmed
   kernel-kind=trimmed
   kernel-rtpi=<rtpi commit the artefacts were built from>
   kernel-boot-sha256=<sha256 of boot-<rel>.tar.gz>
   kernel-modules-sha256=<sha256 of modules-<rel>.tar.gz>
   kernel-dtb-sha256=<sha256 of bcm2712-rpi-5-b.dtb.sha256's first field>
   ```

   `--lock` rewrites the three repo commits and leaves these alone, as it does `snapshot=`.
10. **`devices/common/make-card`** — read the kernel lines from the lock (also under `--dev`, since
    an artefact is not a tree), take the files from `$RTPI_REPO/build/vip/`, verify every hash and
    that `kernelrelease` matches `kernel=`, copy the seven files into `$IN/kernel/`, and append
    `kernel=`, `kernel-kind=`, `kernel-rtpi=` and the hashes to `$IN/inputs`. Missing or mismatched
    artefacts **die** with the offending hash and the suggestion (`make vip-rt` in rtpi). A host
    with no kernel lines in the lock builds stock-only as today, with a warning naming the
    consequence (no fallback slot, rtpi's kernel not on the card).
11. **`devices/common/image/build-image`** — after `common "$PEDAL" pedal` and before the initramfs
    step: copy `/in/kernel` into the root's `/tmp/kernel`, run
    `inroot "$PEDAL" /usr/local/sbin/vip-install-kernel --artefacts /tmp/kernel` (which the previous
    step must have installed into the root — add it to the list of rtpi files copied in `common()`),
    delete `/tmp/kernel`, then `initramfs` for **both** releases, then
    `init-pedal-boot --release "$PEDAL_KERNEL" --fallback-release "$FALLBACK_KERNEL"`, then the
    `vip-guard.sh` check for **both** initrds. The manifest gains `kernel=<PEDAL_KERNEL>`,
    `kernel-kind`, `kernel-rtpi`, the three hashes, and `kernel-fallback=<FALLBACK_KERNEL>`; the
    single `pedal-kernel` line becomes those. `/etc/pedal-image` gains `fallback-kernel=` and
    `kernel-rtpi=`.
12. **`devices/common/image/remote`** — the guard stops comparing one string and starts asking the
    two questions `--remote` can actually answer:

    - the running release must be one the image carries (`kernel` or `kernel-fallback`), else die
      as today, naming both;
    - the **booted slot's** `vmlinuz` must be the bytes the image has for that release. Mount the
      pedal-boot partition (`sudo mount /boot/firmware`; fstab has it `noauto`, and vip-boot mounts
      it on demand), `sha256sum` `$(vip-boot status | awk '$3=="*"')/vmlinuz`, and compare against
      the image's recorded hash. The initrd is deliberately *not* compared: the image build's dracut
      runs in the container, so its initrd can never be byte-identical to the board's, and the
      kernel bytes are the invariant that matters — same kernel means the same build and so the
      same modules, which is what keeps the slot's own initrd valid under the new root. A mismatch
      is the one case the release name cannot catch: same release, different build. The message
      says to write a card or use `vip-boot try-kernel <release>`.

    The manifest carries the two releases, the artefact hashes, the rtpi commit, and one
    `*-kernel-vmlinuz` hash per release (build-image hashes `/boot/vmlinuz-<rel>` after the kernel
    is installed) — that last pair is what the guard above compares.
13. **`devices/vip/check`** — after the existing checks: both releases' module trees exist,
    `vip-boot status` reports slot a = `PEDAL_KERNEL` and slot b = `FALLBACK_KERNEL`, both `good`,
    and the running release is `PEDAL_KERNEL` unless a candidate is armed.
14. **docs** — this file's status; `docs/vip-image.md` (the card's boot partitions and the build
    step, which currently says one kernel); `docs/working-across-repos.md`'s who-owns-what row
    (rtpi owns the kernel and the install procedure, pedal.project's image consumes the artefacts);
    `plan.md`'s "Next session starts with".

## Anti-drift checks

| Fact that must agree | Checked by | On failure |
|---|---|---|
| `FALLBACK_KERNEL`'s package is in `devices/vip/packages` | build-image, before the roots | die: the fallback slot would have no kernel |
| `PEDAL_KERNEL` in device.env = `kernel=` in image.lock | make-card | die, naming both |
| artefact hashes = the lock's | make-card | die, printing both hashes |
| `kernelrelease` in the artefacts = `kernel=` | make-card | die |
| artefacts' `built-from` vs image.lock's rtpi commit | make-card | warn, record both (open question 2) |
| the root carries what slot b needs | `fill_slot`'s existing existence checks, at build time | die during the image build |
| the root carries what a slot boots, after a root swap | `remote`'s slot-hash guard | refuse the swap |
| the board's slots are the two releases | `devices/vip/check` | FAIL line |

## Sizes (measured on vip, 2026-10-05)

| | stock (`raspi-realtime`) | pedal (`...-numaemu1-trimmed`) |
|---|---|---|
| `/lib/modules/<rel>` | 155 MB | 16 MB |
| `/boot/vmlinuz-<rel>` | 15 MB | 14 MB |
| `/boot/initrd.img-<rel>` | 51 MB | 19 MB |
| `/usr/lib/firmware/<rel>/device-tree` | 3.2 MB | 6.3 MB |
| a filled slot (`du -sh /boot/firmware/a`) | — | **35 MB measured** |

The pedal-boot partition is `/dev/mmcblk0p2`, 511 MB, and holds **71 MB** today with two custom
slots (441 MB free) — so the pedal slot plus a stock one is a little over 100 MB of a 512 MB
`PEDAL_BOOT_MB`, and no partition change is needed. The pedal root grows by the pedal kernel's
~55 MB against 757 MB free (the build's own `used * 1.2 + 64 ≤ PEDAL_ROOT_MB` guard has room). Both
figures were read off vip on 2026-10-05. A fresh root also drops two accidents the running one
carries and this plan does not: `/lib/modules/lib` (561 MB, a mis-extracted copy) and the superseded
full `...-numaemu1` tree (561 MB).

## How it gets onto the board

- **A written card** is the whole arrangement in one go: slot a pedal, slot b stock, both good.
- **Without reflashing** (a running root that already has the pedal kernel — vip, today): once the
  image carries the release, `make-card --remote --image <dir>` passes its guard and swaps the root
  under the existing slot a. To get slot b populated as well, without a card write, use the
  supported path twice: `vip-boot try-kernel 7.0.0-1017-raspi-realtime` (validated; stock becomes
  active, the pedal kernel moves to the spare), then `vip-boot try-kernel
  7.0.0-1017-raspi-realtime-numaemu1-trimmed` (validated; the pedal kernel is active again with the
  stock kernel idle in slot b). Two one-shot cycles, each with a real validation, so a kernel that
  does not come up leaves the other one active. Do it when nothing is playing.

## Verification

1. rtpi: `tests/vip-boot` green; the two-release init rehearsed on a scratch root; the install
   script run twice (idempotent) and against a deliberately broken artefact set (each gate bites).
2. pedal.project: two `--image-only` builds from the same pins produce identical
   `tree-pedal`/`tree-pedal-boot`/`tree-rescue*` hashes and identical manifests — the artefacts are
   inputs, so this must still hold, and it is the check that nothing time-dependent crept into the
   new step.
3. The board: `vip-boot status` shows slot a pedal / slot b stock, both `good`; `uname -r` is the
   pedal release on a normal boot and the stock one after `try-kernel <stock>`; `namchaind` comes up
   on both; `devices/vip/check` green.

## Not in this plan

- **Automatic** kernel rollback (guard trips → try the other slot). This plan makes the fallback
  *present and validated*, not automatic — matching what rtpi's installer provides today. See open
  question 1.
- Building the kernel inside the image build; the full (untrimmed) `numaemu1` build; the rescue
  root; NAMBench numbers from either kernel.

## What changed in the doing

- **The guard compares `vmlinuz`, not the initrd** (item 12 above, corrected in place). The image
  build's dracut runs in the container, so its initrd can never be byte-identical to one the board
  built; requiring both would have refused every root swap. The kernel bytes are the invariant:
  same kernel ⇒ same build ⇒ same modules, which is what keeps the slot's own initrd valid.
- **`kernel-rtpi` for the first pinned artefacts is reconstructed.** They were built on 2026-10-04
  21:32, before rtpi had a `built-from` stamp (`ad9fee1` added it). The lock says so in a comment;
  `make-card` warns if the artefacts' own stamp disagrees, and new builds carry the real one.
- **`--no-trim` over a truncated name is refused.** The old suffix rule was relative to whatever
  kernel happened to be running, which made the "rebuild what is pinned" case an accident. The
  suffix now defaults to `PEDAL_KERNEL`'s own, and a full build over a `-trimmed` name is an error
  instead of silently overwriting a release that is already in a slot.
- **`vip-install-kernel` reads the artefacts directory only.** The image build mounts it read-only,
  so every scratch file (the coverage gate's lists) goes to a temporary directory; on a running
  root it also warns when `/proc/modules` has grown past the list the trim was built from.
- **`devices/vip/check` reads the host's own `device.env`** for the two releases and checks the
  slots against it, rather than comparing the host with the repo's rtpi checkout — that comparison
  is `scripts/status`'s job.

## Open questions for you

1. **Automatic kernel rollback?** Today a pedal kernel that hangs costs `GUARD_LIMIT` boots and then
   *rescue* becomes the default — the counter is about the root reaching `pedal-guard`, and a bad
   kernel trips it exactly like a bad root. With a good slot b on the card, the guard could instead
   try the other slot once (arm `os_prefix=<spare>/`, boot it, validate, and only then fall to
   rescue). That is a behaviour change in rtpi's failure model with its own tests. **Still open**,
   and this work is what makes it possible.
2. **Kernel vs rtpi commit** — settled as: warn and record both. `make-card` warns, the manifest
   and `/etc/pedal-image` record `kernel-rtpi`, and the lock's comment says when it was
   reconstructed.
3. **Share or duplicate the install procedure** — settled as: share.
   `devices/vip/usr/local/sbin/vip-install-kernel` is the one copy, run by rtpi's deploy on a
   running root and by build-image in its chroot.
4. **Names** — settled as `FALLBACK_KERNEL` / `--fallback-release`: the releases are both stock
   Ubuntu builds, and what distinguishes the second one is its job.
5. **Should `--remote` ever move a slot?** — settled as: no. It compares the booted slot's kernel
   with the image's and refuses; a kernel change is a card write or a `try-kernel` on the board.
