# Pedal Project

The pedal as a system. This repo owns the goal, the hardware design, the diagrams, the
decisions and the plan, plus the Core host's configuration as code (`devices/<host>/`), the
Pico firmware (`firmware/`), and the pedal service `pedald` beside `namchaind`
(`devices/common/rootfs/usr/local/lib/pedald/`, designed in `docs/pedal-service.md`). The engine (`namchain`), the rig designer (`ljoss`), the kernel (`rtpi`) and DSP research
(`NAMBench`) are separate repos; `docs/working-across-repos.md` says which repo owns
what, which machines exist, and the rules against drift.

This file is canonical for every agent. `CLAUDE.md` only imports it (and
`docs/hardware-handoff.md`); change this file, not that one.

**Core host** (the board that runs the DSP, "Core" in `about.md`):
- **`vip`** (Raspberry Pi 5, 1 GB, aarch64) **is the Core host** (from 2026-10-01). It's built
  from an image (`devices/vip/make-card`), has no compiler, and is where testing happens until
  it's a working pedal nobody should disrupt; then the test hardware is chosen again.
- **`piv`** (Raspberry Pi 500, aarch64) is the live bench device and build host. It isn't updated
  in step with vip meanwhile: it runs namchain `d4fb8e5`, deployed 2026-09-30, and
  `scripts/status --host piv` shows how far behind that and its `devices/` tree are. Its dev
  checkouts are under `~/code.local/pedal/`, as on the Mac.
- **`pro`** (HP ProDesk 600 G5 Mini, i5-9500T with 9 MiB L3, 16 GB, 2 TB NVMe, x86-64, Ubuntu
  Server 26.04) is the Core host candidate for the bigger case, picked for its larger L3 after a
  Pi 5 struggled with many parallel A2-Full instances; a Behringer UMC202HD (USB) is its audio
  interface. `ssh pro` works. Measured 2026-10-31: 9 Full models per core (14 with `-march=native`),
  but 13-21% slower per model with five cores busy, so the cache explanation is not confirmed.
  Since 2026-11-01 it runs **the Pi hosts' own tooling**: `devices/pro/{apply,check,backup}` are the
  same links into `devices/common/` and the host-side script is `pedal-device` (the separate
  `pro-device` is retired), with six cores split 0 housekeeping / 1-5 render / 5 active, 72 units
  masked, and Ubuntu's **signed** amd64 RT kernel booted through GRUB's one-shot by rtpi's
  `pro-boot`. `scripts/deploy-engine --host pro` builds on pro itself (it has a compiler).
  [docs/pro.md](docs/pro.md).

Full hardware context, schematic findings and reasoning: [docs/hardware-handoff.md](docs/hardware-handoff.md).

## How to start a session

- **On an empty machine, run `scripts/bootstrap`** ([README.md](README.md) has the one-line version).
  It needs only git and the network, and it makes the whole workspace. Nothing depends on what a
  machine already has checked out.
- **Open the workspace, not a repository inside it.** Everything the pedal is made of lives in
  `~/code.local/pedal/`: this repository as `pedal.project/` beside `namchain/`, `ljoss/`, `rtpi/`
  and `NAMBench/`. A session opened on that folder can read and write all of them with no extra
  permissions; one opened on a single repository cannot write its siblings. Open the container for
  cross-repo work, and one repository only when the change is confined to it. The directory is
  deliberately not a repository and must never become one — [docs/workspace.md](docs/workspace.md)
  is the design, and `scripts/workspace check` asserts it.
- **Sync this checkout first.** Pull it to `origin/main` before doing anything. Pushes
  happen only when the owner asks for one; work stays local until then.
- **Two agents on one repo** each get a git worktree, under
  `<workspace>/.worktrees/<name>/<repo>` — inside the sandbox, hidden from search, and outside
  every repository, so it needs no `.git/info/exclude` entry. There is one checkout of each
  repository on the Mac (the second one, `~/cursor-projects/pedal.project`, was retired on
  2026-10-06).
- **Read the plan's "Next session starts with"** (`plan.md`) — it names the exact next
  steps and what changed last.
- **Check the machines.** Run `scripts/status`: every repo on the Mac and piv, the workspace's
  layout and git guard, who holds the Core host's lock, what `namchaind` reports, and whether
  `devices/<host>/components.lock` and the deployed engine and `devices/` tree are current. Every
  script defaults to vip (`--host piv` for piv). Ask before touching either board's hardware or
  starting anything heavy on it (quiet and shared, rule 8).

## Commands

- `scripts/deploy-engine [--host vip] [--commit <rev>] [--no-tests]`: build a namchain
  commit and run its tests (for vip on the Mac, in the image build's container,
  `devices/common/image/build-namchain`; piv and pro build in a dedicated tree of their own), install
  into `/opt/namchain/<commit>/`, swap `current`, write the manifest, restart `namchaind`.
- `PUT http://<host>:47820/library/{models,irs}/<path>` with `If-None-Match: *`: put a model or an IR on
  the pedal, which never replaces a file; pedald is the only writer of them (docs/pedal-service.md, "Files").
- `devices/<host>/{apply,check,backup}` (symlinks into `devices/common/`): the Core
  host's configuration as code. Run `backup` before changing anything. `pedal-device apply <stage> --root
  <dir>` applies the same tree to a root that isn't running (vip's image build);
  `devices/vip/test-offline-apply` checks that in the build container.
- `devices/vip/eeprom-fetch` and, on the host, `sudo vip-eeprom status|verify|apply|clean`: the
  bootloader EEPROM, pinned by `eeprom.lock`. Never `-d` or `-f`: an EEPROM write is the one act with
  no card-level fallback (docs/vip-image.md, "The bootloader EEPROM").
- `devices/common/test-pedald [<test>…]`: the pedal service's tests, the diagnostics and bench-test
  tests, `scripts/tests`, and the bench test's page in Chromium (through uv and Playwright; run it
  under `scripts/sandbox-cache` from a session). They run on the Mac, not on the Core host (rule 8).
  The service is `devices/common/rootfs/usr/local/lib/pedald/`; `docs/pedal-service.md` is its
  design. `sudo systemctl start pedal-diag` samples the host, the codec and the link
  (docs/diagnostics.md, `scripts/diag`).
- `sudo systemctl start pedal-measure`: measures one cost row the device has no number for (P4),
  only while the pedal is healthy (`pedal-measure --dry-run` says which), and writes a fragment to
  `/var/lib/pedal/cost-fragments/`. Merging is by hand, with `devices/common/cost-merge`
  (docs/managing-processing-power-and-optimising-for-fast-switching.md).
- `devices/vip/make-card [--image-only] [--disk /dev/diskN] [--dev]` (links to
  `devices/common/make-card`): build vip's whole card in colima from the commits in
  `devices/vip/image.lock` (namchain built and tested there, both roots, the boot partitions),
  secrets from 1Password vault `fx`, then write a card. `--lock` pins the lock to HEADs; `--dev`
  builds the working trees and marks the image `-dirty`. `docs/vip-image.md` is the design.
  `--remote` writes no card: it puts the new pedal root on the running vip through its rescue
  root, tries it once, and makes it the default only once the engine stays up
  (`--remote --previous --image <build dir>` goes back to the root before).
- `scripts/status [--host vip] [--no-fetch]`: every repo on the Mac and piv, the Core
  host's lock, `namchaind`'s status, and whether `devices/<host>/components.lock`, the engine and
  `devices/` are current. Start every session with it.
- `scripts/fleet check [BUILD] [--core CORE]`, `status [--json] [--no-hosts]`, `serve [--port 8765]`:
  the fleet in `fleet/` (Cores, parts, builds, sets, proofs, docs/operations-plan.md). `check` validates
  the files and judges a combination by its parts, so `box --core pro` is refused with reasons. `status`
  reads every Core, CI and the lab, and changes nothing. `serve` is the private dashboard, on this machine
  only.
- `scripts/host-lock [--host vip] [--wait <s>] -- <command>`: run a command while
  holding the Core host's lock; `--who` says who holds it. Every soak, benchmark and
  deploy goes through it.
- `scripts/sandbox-cache [--status|--print|--refresh] [-- <command>]`: run a command with uv's and
  Playwright's caches cloned into `<workspace>/.cache/`, which a sandboxed session needs for the
  browser tests ([docs/workspace.md](docs/workspace.md), "Tool caches").
- `scripts/public-check [--all|--workspace|--range A..B] [--no-live]`: every repository here is public, so
  what a push adds must not name a LAN address, a global IPv6 address, a MAC address, a secret, or this
  household's own details (read live, stored nowhere, never printed). The pre-push hook and CI run it. A
  match stops the push: mask the value, or list the path in the repository's `.public-check-allow` with
  the reason. A name and an email address are fine (docs/operations-plan.md, Decision 3).
- `scripts/components-lock [--host vip] [--check]`: write `devices/<host>/components.lock`
  from what the host is running, or compare. Commit the file with the change.
- `firmware/build.sh`, `firmware/flash.sh`, `firmware/tools/{echo,protocol}-test.py`: build,
  flash and bench-test the Pico firmware (Pico 2 W; SDK 2.3.1 and Arm GNU Toolchain 15.3.rel1
  under `~/pico/`). `FW_ECHO=1` builds step 1's echo for the echo test.
- `scripts/pico-power-test [--host vip] [--leg read|reboot|shutdown]`: does the Pico keep its 5 V
  through a Core host reboot or shutdown (plan 3.6)? Reads the Pico's own uptime from its USB console
  before and after; `--leg shutdown` needs the host powered back on by hand.
- `scripts/codec-noise.py <capture.wav>`: the codec's noise floor from an `arecord` capture — DC
  offset, unweighted and A-weighted RMS in dBFS and µV, and the spectral lines that show a hum comb.
  `--selftest` checks the weighting against the standard's figures; the procedure it belongs to is
  [docs/codec-bringup-2c.md](docs/codec-bringup-2c.md).
- `scripts/codec-input-noise.py [--host vip] --state "…" [--arms engine,playback,alone]`: that
  measurement as one command, under the host's lock — it stops and restarts `namchaind` for the
  `arecord` arms, retries an arm that dies with `pcm_read: Input/output error`
  ([docs/audio-dma-irq.md](docs/audio-dma-irq.md)), and writes a page of graphs and numbers to
  `bench-results/<date>-codec-input-noise/`. `--rebuild DIR` re-analyses without the pedal;
  `scripts/noise-document.py` is the page builder alone. Procedure:
  [docs/codec-bringup-2c.md](docs/codec-bringup-2c.md); results so far:
  [bench-results/2026-10-13-input-hum-and-the-host-supply.md](bench-results/2026-10-13-input-hum-and-the-host-supply.md).
- `scripts/benchtest [--host vip] [--fake]`: the bench test. Under the host's lock it starts
  `pedal.benchtest` (on demand, never at boot; it stops itself after 5 idle minutes, or from Stop on
  the page), opens its page — the pedal's blocks with a pass/fail lamp each — and stays as its audio
  helper (sox and `scripts/codec-noise.py`). `--fake` runs it on the Mac with no pedal.
- Write evidence into a repo's `bench-results/`, never `/tmp`.

## Architecture

- **The pedal owns its state** (D17, [docs/pedal-owns-state.md](docs/pedal-owns-state.md)): `namchaind`
  and the pedal service between them own the running rig, the stored rigs and banks, the undo
  history, the model/IR files and the block catalogue. ljoss and rigpa are views: they send edits and
  commands and are told of every change with its cause ("Footswitch 2 → Clean").
- `namchaind` (from namchain) renders the rig and drives ALSA directly (`alsa_raw`).
  No JACK, PipeWire or LV2. It pushes every change to its subscribers (`engine.subscribe`).
- The **pedal service**, `pedald`, in this repo beside `namchaind` (D4), owns the library, banks,
  resume, autosave, undo, uploads, the catalogue's templates, the pedal's id and name, and the
  footswitch/MIDI mapping, and streams its events (`GET /events`). namchain stays a generic engine.
  [docs/pedal-service.md](docs/pedal-service.md).
- **ljoss** finds pedals over DNS-SD (`_pedal._tcp`) and talks to each directly over WiFi: edits go
  straight to `namchaind`, commands to `pedald`. It keeps no rigs of its own, and its Models & IRs
  library reaches a pedal through "Compare Files…". The Pico handles physical controls only and
  never carries rigs or models (D2).
- **rigpa** (its own repo, `../rigpa`) is the pedal's on-device UI on the Core host's
  screen, on core 0 (D14), wide (the 8.8″ bar) or compact (the box's 4.3″ panel): the same kind of
  view as ljoss, over TCP loopback.

## Constraints — ask before violating any of these

- The Core host is a **Raspberry Pi 5-class board, aarch64** (BCM2712, Cortex-A76).
  `vip` has **1 GB of RAM**: check memory for loaded models and the pedal service, not
  just CPU.
- The WM8960 codec is **I2S master**; the Core host is I2S slave. The codec board has
  its own 24 MHz oscillator and MCLK is not exposed.
- The Core host **owns the I2C bus** to the codec (0x1A). The Pico never writes codec
  registers.
- The Core host does **DSP and the screen only** (D14: rigpa, on housekeeping core 0,
  SCHED_OTHER, gated by a soak). The encoder and buttons, footswitches, MIDI, LEDs and GPIO
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
- **Work in the repo that owns the change.** Cross-repo sessions are opened on the workspace
  (`~/code.local/pedal/`), which is where the other repos are — [docs/workspace.md](docs/workspace.md).
  Cross-repo changes land in dependency order
  (engine before app, bridge before firmware), each commit green on its own.
- **Commit to `main`** (no pull requests for these repos); from this harness, pushes
  wait for the owner's say-so.
- **Nothing runs on the Core host from a state nobody recorded.** Deploys go through
  `scripts/deploy-engine`; every binary carries its commit; `devices/<host>/` owns all
  other state.
- **The Core host is quiet and shared.** No builds on it during a soak or while playing (vip
  never builds anything); only one measurement at a time; leave no processes behind.

## Where things are

- `plan.md` — the plan and its history; start at "Next session starts with".
- `../rigpa/` — the on-device UI (D14); its spec and plan are in its `docs/`.
- `workspace.repos`, `scripts/workspace`, `workspace-root/`, `tools/git-hooks/` — the workspace:
  what it holds, the files at its root, and the guard that stops a checkout being embedded in a
  repository. [docs/workspace.md](docs/workspace.md) is the design.
- `fleet/` — the fleet as data, with its schemas and the dashboard page; `scripts/fleet` reads it.
- `firmware/` — the Pico firmware; [docs/uart-protocol.md](docs/uart-protocol.md) is the
  Pico ↔ Core host contract.
- `docs/`: `workspace.md` (the workspace and its guard), `working-across-repos.md` (repos, machines, rules), `hardware-handoff.md`
  (schematic findings and reasoning), `codec-bringup-2a.md` (the 2a bench walkthrough), `codec-bringup-2c.md` (2c: the
  shunt swap and the supply and ground legs, with `scripts/codec-noise.py` reading its captures),
  `build-board1-breadboard.md` and `build-board1.md` (board 1 on the breadboard, then soldered),
  `build-footswitches.md` (the small case's three footswitches: the net, the lugs, and the cut-down
  control board, `footswitch-pico.svg`), `rig-switch-strategies.md`, `uart-protocol.md`, `pedal-service.md` (the service's design: what
  it owns, storage, uploads, the mapping, failure modes, what is left to implement — in order —
  and the thread accounting), `operations-plan.md` (agreed 2026-11-03: running the Cores as a fleet, rebuilding from nothing, the
  public dashboard), `pro.md` and `zap.md` (the other two Core hosts), `pairing.md` (BLE pairing, the pedal's own
  Wi-Fi network, and how ljoss joins it), `vip-image.md` (building vip's card,
  its rescue and pedal roots, boot fallback), `audio-dma-irq.md` (the audio DMA interrupt
  thread: what it is, its measured cost, why it outranks the render thread, and the one way it
  fails — the `pcm_read: Input/output error` that kills a capture, with its kernel log decoded
  and the fix `rtpi` may carry), `bom.md`,
  `modules.md` (a proposal, 2026-10-11: the circuits as pluggable boards, their cables and
  connectors, and the ground tree; its map, which checks the tree, is `diagrams/modules.html`),
  `balanced-outputs.md` (a proposal, 2026-10-14: XLR outputs and impedance-balanced TRS, phantom,
  mute, pad, ground lift, and where the case bonds), `pro.md` (the x86 Core host for the bigger
  case: why, what it is, what is not yet done).
- `stripboard/`, `breadboard/` — board layouts as data; each script checks its placement against
  the netlist (`stripboard/board1.py` holds board 1's) and draws it. `stripboard/module_boards.py`
  holds the module boards; `stripboard/stripmaster_export.py` writes the codec carrier, the input
  buffer, the output board and the footswitches' Pico board as `.stripmaster` documents beside
  their build sheets in `stripboard/module-boards/`, for `../stripmaster`, and reads each back
  through stripmaster's model to check every pin hole and net. The layout stays in
  `module_boards.py`: the documents are derived, so an edit made in stripmaster is carried back
  there, and opening one in stripmaster rewrites its saved view. Name documents on its command
  line to write only those, so one edited in stripmaster and not carried back is left alone.
- `schematic/` — the pedal's schematic sheets as KiCad files, each written from the wiring table in
  the script beside it (`schematic/case-wiring.py` holds the prototype case's: IN, OUT L and OUT R,
  the two output fixtures, the case's 4-way strip and the codec header as it is today). The script
  checks the wiring against KiCad's exported netlist; `schematic/renders/` holds the pictures.
- `devices/<host>/rootfs/` — the Core host's configuration as code.
- `enclosure/` — two Blender models and their renders: the **console model**, the pedal in its
  current case (the Hammond 1456RH3 and the 8.8″ bar screen; a design render, panel positions
  provisional), and the superseded 1590DD-size box (parts, layout, wiring). `enclosure/README.md`
  says which is which, what's approximate and how to rebuild each.
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
