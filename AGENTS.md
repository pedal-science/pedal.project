# Pedal Project

The pedal as a system. This repo owns the goal, the hardware design, the diagrams, the
decisions and the plan, plus the Core host's configuration as code (`devices/<host>/`) and
the Pico firmware (`firmware/`). The pedal service beside `namchaind` will live here too
(`docs/pedal-service.md`). The engine (`namchain`), the rig designer (`ljoss`), the kernel (`rtpi`) and DSP research
(`NAMBench`) are separate repos; `docs/working-across-repos.md` says which repo owns
what, which machines exist, and the rules against drift.

This file is canonical for every agent. `CLAUDE.md` only imports it (and
`docs/hardware-handoff.md`); change this file, not that one.

**Core host** (the board that runs the DSP, "Core" in `about.md`):
- **`tib`** (ASUS Tinker Board, RK3288, armhf) is **retired** as of 2026-09-26. It stopped
  working on 2026-09-25. Its numbers, `devices/tib/` and its backups stay as history.
- **`piv`** (Raspberry Pi 500, aarch64) stands in until `vip` arrives.
- **`vip`** (Raspberry Pi 5, 1 GB, aarch64) is on order and becomes the Core target when
  it arrives.

Older docs and plan phases say "`tib`"; read that as "the Core host". Full hardware context,
schematic findings and reasoning: [docs/hardware-handoff.md](docs/hardware-handoff.md).

## How to start a session

- **Sync this checkout first.** Pull it to `origin/main` before doing anything. Pushes
  happen only when the owner asks for one; work stays local until then.
- **There are two checkouts on the Mac.** The docs name `~/code.local/pedal.project`
  (Claude Code's); Cursor/DeepSeek sessions run from `~/cursor-projects/pedal.project`. Before
  touching a file, check the other checkout's uncommitted work so you don't clobber it.
  Two agents on one repo each get a git worktree.
- **Read the plan's "Next session starts with"** (`plan.md`) — it names the exact next
  steps and what changed last.
- **Check the machines.** Run `scripts/status`: every repo on the Mac and piv, who holds
  the Core host's lock, what `namchaind` reports, and whether `components.lock` and the
  deployed engine and `devices/` tree are current. piv is the Core host stand-in: ask
  before touching its hardware or starting anything heavy on it (it is quiet and
  shared, rule 8).

## Commands

- `scripts/deploy-engine [--host piv] [--commit <rev>] [--no-tests]`: build a namchain
  commit in a dedicated tree on the Core host (never the dev checkout), run the tests,
  install into `/opt/namchain/<commit>/`, swap `current`, write the manifest, restart
  `namchaind`. piv only for now.
- `scripts/sync-library [--host piv] [--dry-run]`: mirror `~/Documents/Audio/NAM` and
  `IRs` into `/var/lib/pedal/library/{models,irs}` on the Core host, and ask
  `namchaind` to rescan. Rigs on the host are never touched.
- `devices/<host>/{apply,check,backup}` (symlinks into `devices/common/`): the Core
  host's configuration as code. Run `backup` before changing anything.
- `scripts/status [--host piv] [--no-fetch]`: every repo on the Mac and piv, the Core
  host's lock, `namchaind`'s status, and whether `components.lock`, the engine and
  `devices/` are current. Start every session with it.
- `scripts/host-lock [--host piv] [--wait <s>] -- <command>`: run a command while
  holding the Core host's lock; `--who` says who holds it. Every soak, benchmark and
  deploy goes through it.
- `scripts/components-lock [--host piv] [--check]`: write `components.lock` from what
  the host is running, or compare. Commit the file with the change.
- `firmware/build.sh`, `firmware/flash.sh`, `firmware/tools/{echo,protocol}-test.py`: build,
  flash and bench-test the Pico firmware (Pico 2 W; SDK 2.3.1 and Arm GNU Toolchain 15.3.rel1
  under `~/pico/`). `FW_ECHO=1` builds step 1's echo for the echo test.
- Write evidence into a repo's `bench-results/`, never `/tmp`.

## Architecture

- `namchaind` (from namchain) renders the rig and drives ALSA directly (`alsa_raw`).
  No JACK, PipeWire or LV2.
- ljoss talks to `namchaind` on the Core host directly over WiFi. The Pico handles physical
  controls only and never carries rigs or models (D2).
- A **pedal service** in this repo, beside `namchaind`, owns the rig library, resume
  at power-up, uploads, and the footswitch/MIDI mapping. namchain stays a generic
  engine (D4). Designed 2026-09-28, with review points open:
  [docs/pedal-service.md](docs/pedal-service.md).

## Constraints — ask before violating any of these

- The Core host is a **Raspberry Pi 5-class board, aarch64** (BCM2712, Cortex-A76).
  `vip` has **1 GB of RAM**: check memory for loaded models and the pedal service, not
  just CPU.
- The WM8960 codec is **I2S master**; the Core host is I2S slave. The codec board has
  its own 24 MHz oscillator and MCLK is not exposed.
- The Core host **owns the I2C bus** to the codec (0x1A). The Pico never writes codec
  registers.
- The Core host does **DSP only**. Display, encoder, footswitches, MIDI, LEDs and GPIO
  belong to the Pico, which talks to the Core host over UART.
- Footswitch and MIDI events produce **identical** UART messages.
- Codec ALC and 3D enhancement stay **off**.
- `namchaind` drives ALSA directly (`alsa_raw`). No JACK, PipeWire or LV2.

**Planned codec modifications (D8).** The SparkFun WM8960 board is in hand and **stock**. It
is brought up stock first, then modified and measured before and after (plan Phase 2c).
Candidates: AVDD-ISO cut with an external LDO, SPKVDD open, VIN disconnected — or, first,
VIN fed from a 78L05 on the 9 V side, which needs no cutting.

**Check before first power-up:** the display module (ST7789 + EC11) has no onboard LDO, then
run it at **3.3 V**. Its switch pull-ups go to VCC and RP2350 GPIO is not 5 V tolerant.

## Working rules (`docs/working-across-repos.md`)

- **One home per fact.** Pedal-level material lives here and nowhere else; component
  repos link to it. A contract lives with whoever implements it.
- **Work in the repo that owns the change.** Cross-repo sessions start here, with the
  other repos added as extra directories. Cross-repo changes land in dependency order
  (engine before app, bridge before firmware), each commit green on its own.
- **Commit to `main`** (no pull requests for these repos); from this harness, pushes
  wait for the owner's say-so.
- **Nothing runs on the Core host from a state nobody recorded.** Deploys go through
  `scripts/deploy-engine`; every binary carries its commit; `devices/<host>/` owns all
  other state.
- **The Core host is quiet and shared.** No builds on piv during a soak or while
  playing; only one measurement at a time; leave no processes behind.

## Where things are

- `plan.md` — the plan and its history; start at "Next session starts with".
- `firmware/` — the Pico firmware; [docs/uart-protocol.md](docs/uart-protocol.md) is the
  Pico ↔ Core host contract.
- `docs/`: `working-across-repos.md` (repos, machines, rules), `hardware-handoff.md`
  (schematic findings and reasoning), `codec-bringup-2a.md` (the 2a bench walkthrough),
  `build-board1.md` (the board 1 bench walkthrough), `rig-switch-strategies.md`, `uart-protocol.md`, `pedal-service.md` (the service's design: what
  it owns, storage, uploads, the mapping, failure modes), `vip-image.md` (building vip's card,
  its rescue and pedal roots, boot fallback), `bom.md`.
- `stripboard/` — stripboard layouts as data; each script checks its layout against the netlist
  and draws it.
- `devices/<host>/rootfs/` — the Core host's configuration as code.
- `enclosure/` — a Blender model of the pedal in a 1590DD-size box (parts, layout, wiring) and its
  renders; `enclosure/README.md` says what's approximate and how to rebuild it.
- `docs/diagrams/` — draw.io, two layers: blocks and connections. The small squares on the
  connection layer are routing junctions, **not components**. When reasoning about the
  diagram, check that edges still have `source`/`target` set and that no junction joins two
  distinct nets, but treat the connections as being to the blocks under the small squares on
  the blocks layer, not to the squares themselves. It's drawn this way to attach connections
  at arbitrary positions on blocks and keep them horizontal or vertical; if there's a better
  way, discuss. Don't break the formatting. If it's confusing, render it to an image with the
  draw.io CLI and read that, or ask.

## Current state

`plan.md`'s "Next session starts with" is the one record of where things are. It isn't
repeated here, so it can't go stale here.

System context: this is the repo the component repos' `AGENTS.md` files point back to.
For the pedal as a whole, start here and with `docs/working-across-repos.md`.
