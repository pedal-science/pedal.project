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
| `pedal.project` | `~/code.local/pedal.project` | The pedal as a system: goal, hardware design, diagrams, decisions, plan. Later: `tib`'s appliance configuration, the Pico firmware, and the `tib`-side control bridge |
| `namchain` | `~/code.local/namchain` | The engine library, `namchaind`, `namchainctl`, the soak and bench tools, and **the control protocol** (protocol 2) |
| `ljoss` | `~/code.local/ljoss` | The rig designer (macOS/iOS), including flattening the rig tree into an engine graph |
| `rtpi` | `~/code.local/rtpi` | `tib`'s kernel, the boot-slot safety net, RT tuning, and so any **device-tree** change such as the WM8960 sound card |
| `NAMBench` | `~/code.local/NAMBench` | NAM and IR kernel research. It reaches the pedal only through `namchain`, as a vendor patch or a port |
| `OptimisationWorkOnNeuralAmpModelerCore`, `AudioDSPTools` (forks) | not checked out here | The planar NEON kernels (upstream PR #313, which `namchain` carries as a vendor patch) and the partitioned-FFT IR branch. `namchain`'s `nc.cab.ir` doesn't use AudioDSPTools, so that branch reaches the pedal as a port |
| `midi-commander-custom` (fork) | `~/code.local/comidi/midi-commander-custom-rikkus` | The MIDI Commander's firmware and button configuration |

**Where a new thing goes.** If it only makes sense for this pedal, it lives in `pedal.project`. If
it stands on its own (an engine, an app, a kernel), it gets its own repo or goes in the one it
belongs to. So the Pico firmware and the `tib` process that talks to it live here: they share the
UART protocol and change together. A reverb goes in `namchain`, and a device-tree node goes in
`rtpi`.

## The machines

| Host | Role | Notes |
|---|---|---|
| **M2** (MacBook Air) | Where editing and agent sessions happen, and where every deploy is started. Xcode, macOS builds of the engine | Holds every repo |
| **piv** (Pi 500, aarch64) | **Core host stand-in until vip arrives.** Otherwise the ARM build host: native aarch64, armv7 cross-compiler (GCC 15.2), `qemu-arm-static` for running armv7 tests | Allowed to be busy or down, so every build that runs on it also needs a fallback (colima on the Mac, which `rtpi` already uses) |
| **vip** (Pi 5, 1 GB, aarch64) | The Core target from its arrival (ordered 2026-09-26), and nothing else | Same rules `tib` had: no compiler, everything arrives built |
| ~~**tib**~~ (Tinker Board S, armv7) | **Retired 2026-09-26** (stopped working 2026-09-25). "`tib`" in the rules below now means the Core host | History only: `devices/tib/` and its backups |

## The rules

1. **One home per fact.** Pedal-level material (hardware, diagrams, system decisions, the plan) lives
   here and nowhere else. Component repos *link* to it. A copy is a fork that nobody maintains.
2. **A contract lives with whoever implements it, and consumers link to it.** The engine protocol is
   `namchain`'s (`docs/daemon.md`, `docs/ui-integration-plan.md` §1), and `ljoss/docs/ENGINE.md`
   already follows this rule. The Pico ↔ `tib` UART protocol will live here, beside both ends.
3. **Work in the repo that owns the change.** Cross-cutting sessions start here, with the other
   repos added as extra directories (below). A session that is deep in one component starts in that
   component's repo.
4. **Work lands on each repo's default branch**, committed and pushed, with no pull requests. That's
   how you work on your own repos; forks and other people's repos still go through PRs. An aspect
   you ask to keep separate gets its own branch, named the same in every repo it touches, and its
   work is committed and pushed there until it merges. A change that spans repos lands in
   dependency order (engine before app, `tib` bridge before Pico firmware), each commit green on its
   own. The plan names the commits that belong together, so "which ljoss goes with which namchain"
   is never a guess.
5. **Nothing runs on tib from a state nobody recorded.** Every deployed binary carries the commit it
   was built from, marked dirty if the tree was. A manifest on `tib` and a lock file here say what
   is running. (Your MIDI Commander firmware already stamps its builds this way, and NAMBench pins
   every variant it measures to a commit.)
6. **Build configurations are committed.** Every `tib` number for `namchain` came from an armv7
   **NEON** build that exists only as a `CMAKE_CXX_FLAGS` override cached on piv. The committed
   toolchain file builds the `vfpv3-d16` variant, which can't run A2-Full in real time on `tib`
   (133% of a core, against 52%). NAMBench gets this right: its `-mfpu=neon-vfpv4` is committed
   and checked. A number you cannot rebuild is a number you cannot defend.
7. **Device state is code.** Everything on `tib` above the kernel goes into idempotent scripts here
   under `devices/tib/`, following `rtpi`'s layout: the `namchaind` unit, config and token, limits,
   the model/IR/rig library, ALSA mixer state, and the bridge's unit. Kernel and device tree stay
   in `rtpi`. Pull a backup before changing anything, as `rtpi` does.
8. **tib is quiet and shared.** Only one measurement runs at a time, enforced by a lock. Check the
   board is idle before starting, leave no processes behind, and write evidence into a repo's
   `bench-results/`, never `/tmp`. `namchain` learned the last two the hard way.

## How a change reaches the pedal

| Change | Loop |
|---|---|
| Engine (`namchain`) | Build and unit-test on the Mac → push a branch → piv builds armv7-NEON and runs the tests under qemu → deploy to `tib` into a versioned directory, swap a symlink, restart the unit → check with `namchainctl` / `ljoss` → soak if it touches the render path |
| App (`ljoss`) | Xcode on the Mac → run against a local `namchaind` (CoreAudio backend) or against `tib` over WiFi → `Tools/check-device.sh` for the handshake and `audible_generation` |
| Kernel, device tree (`rtpi`) | Build in colima on the Mac → stage as the candidate slot → one-shot try-boot on `tib` → promote with `tib-freeze-good` |
| DSP research (`NAMBench`) | Fork branch → upstream PR, plus either a patch or pin in `namchain/vendor` or a port into one of `namchain`'s own nodes → `namchain`'s golden, parity or tolerance tests prove the swap |
| Pico firmware (planned) | Build on the Mac with the Pico SDK → flash (UF2 or a debug probe) → test against the `tib` bridge over the UART |

Rollback on `tib` is the previous symlink. For the kernel it is `rtpi`'s known-good slot.

## Setting up an agent session

- **Here, for cross-repo work:** `.claude/settings.local.json` (per machine, gitignored) lists the
  other checkouts as extra directories, and sets the variable that makes Claude Code load their
  `CLAUDE.md` files too. Without it, extra directories are readable but their instructions are not
  loaded:

  ```json
  { "env": { "CLAUDE_CODE_ADDITIONAL_DIRECTORIES_CLAUDE_MD": "1" },
    "permissions": { "additionalDirectories": [
      "/Users/rik/code.local/namchain", "/Users/rik/code.local/ljoss",
      "/Users/rik/code.local/rtpi", "/Users/rik/code.local/NAMBench" ] } }
  ```

- **In each component repo:** an `AGENTS.md` (purpose, build and test commands, constraints) and a
  `CLAUDE.md` that is just `@AGENTS.md`. Cursor and the DeepSeek harness read the former, and
  Claude Code reads the latter. Each ends with one line pointing here for system context.
  `namchain`'s points into its `plan.md` at "How to resume" rather than the whole file.
  `pedal.project` itself has both too (2026-09-27): its `CLAUDE.md` stays the canonical brief,
  and its `AGENTS.md` carries the session start, commands, constraints and working rules for
  Cursor/DeepSeek agents.
- **`pedal.project` has two checkouts on the Mac.** The one these docs name,
  `~/code.local/pedal.project` (Claude Code's), and a second for Cursor/DeepSeek sessions (e.g.
  `~/cursor-projects/pedal.project`). Pull the session's checkout to `origin/main` before
  starting, push only when asked, and check the other checkout's uncommitted work before touching
  the same files.
- **Two agents on one repo** each get a git worktree, so neither sees or clobbers the other's
  uncommitted work.
- **Every session starts with `scripts/status`**, which reports each repo on each host (branch,
  HEAD, ahead/behind, dirty), who holds the Core host's lock, and what `namchaind` there reports.

## Tooling this needs (built in Phase 0 of the plan)

| Tool | Does |
|---|---|
| `scripts/status` | The table above, in one screen. Exists: repos on the Mac and piv, the lock, `namchaind`'s status, and whether `components.lock`, the engine and `devices/` are current |
| `scripts/host-lock` | `flock` on the Core host, held from the Mac for as long as a command runs. Every soak, benchmark and deploy goes through it. Exists; `deploy-engine` and `devices/<host>/apply` take it themselves, and a nested call for the same host just runs its command |
| `scripts/deploy-engine` | Build a `namchain` commit in a *dedicated* build directory on the Core host, never the dev checkout. Run the tests, install into a versioned directory, write the manifest, restart. Exists, piv only; the armv7-NEON cross build for `tib` went with `tib` |
| `devices/tib/` | The appliance configuration and its idempotent apply/backup scripts |
| `components.lock` | The component commits that make up what the Core host is running (board, kernel, namchain, the `devices/` tree), written by `scripts/components-lock` after every deploy and apply. Exists |
