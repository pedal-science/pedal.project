# Working across the repos

The pedal's software is spread over several repositories and three machines. This page says what
each one owns, how a change travels from an editor to the pedal, and the few rules that stop the
copies drifting apart. It was written on 2026-09-23 from a survey of every checkout. What that
survey found is recorded in `plan.md` under "Where things stand", because it describes a moment
rather than a rule.

---

## The pieces

| Repo (GitHub `rikkus/…`) | Checkout on the Mac | Owns |
|---|---|---|
| `pedal.project` | `~/code.local/pedal/pedal.project` | The pedal as a system: goal, hardware design, diagrams, decisions, plan. The Core host's appliance configuration (`devices/`), the Pico firmware (`firmware/`), and the pedal service (`pedald`, in `devices/common/rootfs/usr/local/lib/pedald/`) beside `namchaind` |
| `namchain` | `~/code.local/pedal/namchain` | The engine library, `namchaind`, `namchainctl`, the soak and bench tools, and **the control protocol** (protocol 2) |
| `ljoss` | `~/code.local/pedal/ljoss` | The rig designer (macOS/iOS), including flattening the rig tree into an engine graph |
| `rtpi` | `~/code.local/pedal/rtpi` | The Core host's kernel, the boot-slot safety net, RT tuning, and so any **device-tree** change such as the WM8960 sound card |
| `NAMBench` | `~/code.local/pedal/NAMBench` | NAM and IR kernel research. It reaches the pedal only through `namchain`, as a vendor patch or a port |
| `rigpa` | `~/code.local/pedal/rigpa` | The pedal's on-device UI (C++, Qt 6) on the Core host's screen (D14). A client of `namchain`'s protocol and of `pedald`'s library API, never their owner; reads the library read-only. Its deployment on the Core host is `devices/`'s, like the engine's |
| `OptimisationWorkOnNeuralAmpModelerCore` (fork) | `~/code.local/pedal/namchain/vendor/NeuralAmpModelerCore` | The planar NEON kernels (upstream PR #313). It is **vendored into `namchain` as a declared submodule** at `all-optimisations`, so there is one checkout of it, not two |
| `AudioDSPTools` (fork) | not checked out here | The partitioned-FFT IR branch, which `namchain` carries as a port — `nc.cab.ir` doesn't use AudioDSPTools. `rikkus/AudioDSPTools` no longer exists on GitHub; the only copy of `partitioned-ir` is `~/code.local/nam/AudioDSPTools-spread` |
| `midi-commander-custom` (fork) | `~/code.local/comidi/midi-commander-custom-rikkus` | The MIDI Commander's firmware and button configuration. Deliberately outside the workspace: it is a peripheral, and its two sibling clones in `comidi/` are other people's |

Those five rows above `AudioDSPTools` are the ones the workspace holds, plus this repository: the
six checkouts under `~/code.local/pedal/` are the accepted layout since 2026-10-06, declared in
`workspace.repos` and checked by `scripts/workspace`. [docs/workspace.md](workspace.md) says why
they are arranged that way and what the guard around them does. The NAM research checkouts stay
where they are, in `~/code.local/nam/`.

**Where a new thing goes.** If it only makes sense for this pedal, it lives in `pedal.project`. If
it stands on its own (an engine, an app, a kernel), it gets its own repo or goes in the one it
belongs to. So the Pico firmware and the process that talks to it live here: they share the
UART protocol and change together. A reverb goes in `namchain`, and a device-tree node goes in
`rtpi`.

## The machines

| Host | Role | Notes |
|---|---|---|
| **M2** (MacBook Air) | Where editing and agent sessions happen, and where every deploy is started. Xcode, macOS builds of the engine | Holds every repo, all six of them under `~/code.local/pedal/` |
| **vip** (Pi 5, 1 GB, aarch64) | **The Core host** (from 2026-10-01), and nothing else. Built from an image (`devices/vip/make-card`, `docs/vip-image.md`); where testing happens until it's a pedal nobody should disrupt | No compiler: everything arrives built (the engine in colima on the Mac, `scripts/deploy-engine`) |
| **piv** (Pi 500, aarch64) | The live bench device and the ARM build host: native aarch64, armv7 cross-compiler (GCC 15.2), `qemu-arm-static` for running armv7 tests | Allowed to be busy or down, so every build that runs on it also needs a fallback (colima on the Mac, which `rtpi` and vip's image already use). Its dev checkouts stay at `~/code.local/<repo>`: the workspace is the Mac's layout, and `scripts/workspace root --repo` falls back to that path, so the scripts work in both |

## The rules

1. **One home per fact.** Pedal-level material (hardware, diagrams, system decisions, the plan) lives
   here and nowhere else. Component repos *link* to it. A copy is a fork that nobody maintains.
2. **A contract lives with whoever implements it, and consumers link to it.** The engine protocol is
   `namchain`'s (`docs/daemon.md`, `docs/ui-integration-plan.md` §1), and `ljoss/docs/ENGINE.md`
   already follows this rule. The Pico ↔ Core host UART protocol lives here
   (`docs/uart-protocol.md`), beside both ends.
3. **Work in the repo that owns the change.** Cross-cutting sessions are opened on the workspace
   (`~/code.local/pedal/`), which holds every repo as a sibling (below). A session that is deep in
   one component is opened on that component's repository.
4. **Work lands on each repo's default branch**, committed and pushed, with no pull requests. That's
   how you work on your own repos; forks and other people's repos still go through PRs. An aspect
   you ask to keep separate gets its own branch, named the same in every repo it touches, and its
   work is committed and pushed there until it merges. A change that spans repos lands in
   dependency order (engine before app, bridge before Pico firmware), each commit green on its
   own. The plan names the commits that belong together, so "which ljoss goes with which namchain"
   is never a guess.
5. **Nothing runs on the Core host from a state nobody recorded.** Every deployed binary carries the
   commit it was built from, marked dirty if the tree was. A manifest on the host and a lock file
   here say what is running. (Your MIDI Commander firmware already stamps its builds this way, and
   NAMBench pins every variant it measures to a commit.)
6. **Build configurations are committed.** A number is only as good as the flags behind it: the one
   that is not in git is the one you cannot rebuild. NAMBench gets this right — its
   `-mfpu=neon-vfpv4` is committed and checked — and the pedal's boards are measured on builds whose
   flags are committed the same way. A number you cannot rebuild is a number you cannot defend.
7. **Device state is code.** Everything on the Core host above the kernel goes into idempotent
   scripts here under `devices/<host>/`, following `rtpi`'s layout: the `namchaind` unit, config and
   token, limits, the model/IR/rig library, ALSA mixer state, and the bridge's unit. Kernel and
   device tree stay in `rtpi`. Pull a backup before changing anything, as `rtpi` does.
8. **The Core host is quiet and shared.** Only one measurement runs at a time, enforced by a lock.
   Check the board is idle before starting, leave no processes behind, and write evidence into a
   repo's `bench-results/`, never `/tmp`. `namchain` learned the last two the hard way.

## How a change reaches the pedal

| Change | Loop |
|---|---|
| Engine (`namchain`) | Build and unit-test on the Mac → push → `scripts/deploy-engine` builds it in colima as vip's image does, runs the tests, installs into a versioned directory on vip, swaps a symlink, restarts the unit → check with `namchainctl` / `ljoss` → soak if it touches the render path. A new card or `make-card --remote` pins it in `devices/vip/image.lock` |
| App (`ljoss`) | Xcode on the Mac → **Connect to this computer** (Settings → Hardware runs `namchaind` here, capturing a live input device or a looped WAV) or against vip over WiFi → `Tools/check-device.sh` for the handshake and `audible_generation` |
| Kernel, device tree (`rtpi`) | On vip the pedal's kernel is rtpi's **rebuild** (`make vip-rt`), which is in no archive: it reaches the board as hash-pinned artefacts in the card image (`devices/vip/image.lock`, `docs/vip-kernel-image.md`) or into a running root (`make vip-install-rt`) → either way `vip-boot try-kernel` stages it in the spare slot and boots it once → `vip-boot-validate` promotes it or it rolls back (`bench-results/vip-card/fallbacks.md`); the card carries the stock kernel in slot b as the fallback. rtpi's boot files reach vip through its image (`make-card`, `--remote`) |
| DSP research (`NAMBench`) | Fork branch → upstream PR, plus either a patch or pin in `namchain/vendor` or a port into one of `namchain`'s own nodes → `namchain`'s golden, parity or tolerance tests prove the swap |
| Pico firmware (`firmware/`) | `firmware/build.sh` on the Mac (Pico SDK 2.3.1, Arm GNU 15.3.rel1) → `firmware/flash.sh` (picotool, or the UF2 volume) → the bench tests through the Debug Probe (`firmware/tools/`) → **and now the pedal service over the Core host's UART**: on vip the link is `ttyAMA0`, and `pedald` holds the session with it |

Rollback on the Core host is the previous symlink. For the kernel it is `rtpi`'s known-good slot.

## Setting up an agent session

- **Open the workspace for cross-repo work.** `~/code.local/pedal/` holds all six repositories as
  siblings, so a session opened on that folder can read and write every one of them with no extra
  permissions and nothing to configure — no `additionalDirectories`, no per-machine settings file.
  That is the whole point of the layout ([docs/workspace.md](workspace.md)); the
  `.claude/settings.local.json` block that used to list the other checkouts as extra directories
  was deleted with the move on 2026-10-06.
- **Open one repository only when the change is confined to it.** A session rooted at
  `~/code.local/pedal/namchain` can read its siblings but not write them: the session's cwd is the
  sandbox's writable root, and there is exactly one of those.
- **In each component repo:** an `AGENTS.md` (purpose, build and test commands, constraints) and a
  `CLAUDE.md` that is just `@AGENTS.md`. Cursor and the DeepSeek harness read the former, and
  Claude Code reads the latter. Each ends with one line pointing here for system context.
  `namchain`'s points into its `plan.md` at "How to resume" rather than the whole file.
  `pedal.project` is the same since 2026-09-29: its `AGENTS.md` is canonical and its `CLAUDE.md`
  imports it and `docs/hardware-handoff.md`. The 2026-09-27 split, with two briefs, drifted
  within a day. This is the rule for all of the owner's work, not just these repos.
- **There is one checkout of each repository on the Mac.** The second `pedal.project`
  (`~/cursor-projects/pedal.project`) was retired with the move on 2026-10-06; pull the workspace's
  checkouts to `origin/main` before starting, and push only when asked.
- **Two agents on one repo** each get a git worktree, under
  `~/code.local/pedal/.worktrees/<name>/<repo>` — inside the sandbox, hidden from search, and
  outside every repository, so neither sees or clobbers the other's uncommitted work and neither
  needs a `.git/info/exclude` entry.
- **Every session starts with `scripts/status`**, which reports each repo on each host (branch,
  HEAD, ahead/behind, dirty), the workspace's layout and git guard, who holds the Core host's lock,
  and what `namchaind` there reports.

## Tooling this needs (built in Phase 0 of the plan)

| Tool | Does |
|---|---|
| `scripts/status` | The table above, in one screen. Exists: repos on the Mac and piv, the workspace's layout and guard, the lock, `namchaind`'s status, and whether `devices/<host>/components.lock`, the engine and `devices/` are current |
| `scripts/workspace` | The repositories the workspace holds (`workspace.repos`), the files at its root, and the checks that keep both honest — added with the move on 2026-10-06 ([docs/workspace.md](workspace.md)) |
| `scripts/host-lock` | `flock` on the Core host, held from the Mac for as long as a command runs. Every soak, benchmark and deploy goes through it. Exists; `deploy-engine` and `devices/<host>/apply` take it themselves, and a nested call for the same host just runs its command |
| `scripts/deploy-engine` | Build a `namchain` commit, never from a dev checkout: for vip in colima on the Mac, exactly as its image builds it; for piv in a dedicated tree on piv. Run the tests, install into a versioned directory, write the manifest, restart |
| `devices/<host>/` | The appliance configuration and its idempotent apply/backup scripts |
| `devices/<host>/components.lock` | The component commits that make up what a Core host is running (board, kernel, namchain, the `devices/` tree), written by `scripts/components-lock` after every deploy and apply. Exists |
