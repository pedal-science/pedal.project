# Plan

**Written:** 2026-09-23. It replaces the bootstrap plan: read `about.md`, design a way of working
across the repos, ask questions, write this. The repo strategy that came out of it is
[docs/working-across-repos.md](docs/working-across-repos.md). The questions and your answers are
recorded under **Decisions**.

**First target:** play guitar through the Core host using the SSL 2+ that is already attached, with ljoss
editing the rig live over WiFi, and the pedal coming back with the same rig after a power cycle.

---

## The Core host moves to a Pi 5

**vip** (Raspberry Pi 5, 1 GB, aarch64, BCM2712, 4 × Cortex-A76) is the Core host since
2026-10-01. **piv** (Pi 500, same SoC) was the host before it and is now the live bench device and
build host. The two boards share an SoC, so performance measured on one carries to the other; what
does not carry over is memory: vip has 1 GB, and piv has more.

piv is a Raspberry Pi 500 (Cortex-A76, 4 cores, **aarch64**). Checked 2026-09-25:

- Ubuntu kernel `7.0.0-1017-raspi-realtime`, **PREEMPT_RT**.
- Cores **2–3 isolated** (`isolcpus=managed_irq,domain,2-3 nohz_full=2-3 rcu_nocbs=2-3`,
  `irqaffinity=0-1`).
- SSL 2+ attached 2026-09-26 as card id `II`, through a hub on the xHCI controller whose interrupt
  is `xhci-hcd:usb4`. Since 2026-09-28 it's direct on that controller's USB 3.0 port, on a new
  cable: the old cable corrupted packets (Phase 1 step 5, "Pops"). Root storage is on the other one (`usb2`). rtpi-audio-tune now finds the
  controller from the interface's USB id (rtpi `04b8a98`); before that fix it was pinning the
  disk's interrupt to core 2.

What this changes:

- **Build.** namchain builds and tests natively for aarch64 on piv, with the planar NEON kernels
  active, so the armv7 cross build and qemu step are off the critical path. `scripts/deploy-engine`
  builds native aarch64 for each host.
- **No builds on the host that plays audio.** Building on it disturbs it: no builds on vip or piv
  during a soak or while playing, and the Mac (colima) is the fallback builder.
- **Device configuration is vip's own** (`devices/vip/tune.conf`): one housekeeping core (0) carrying
  `pedald`, the control side, WiFi and the SD card; cores 1–3 rendering, with the render thread on
  core 3 and the audio interrupt delivered to core 1 — a render core, but never the active one
  (2026-10-09); the `performance` governor uncapped at the Pi 5's 2.4 GHz.
- **Performance numbers are vip's.** vip's cost table (`devices/vip/cost.json`, 14 rows, source and
  method in [bench-results/2026-10-08-cost-table-vip/README.md](bench-results/2026-10-08-cost-table-vip/README.md))
  is measured on vip:
  `NAM.WaveNet.full` 0.111 of one core at n = 9, `lite` 0.0333 at n = 30, `IR.8192` 0.0222 at
  n = 45. Where this plan still quotes a measurement from another board, it says so at the row.
- **Memory.** vip's 1 GB is a real constraint. `namchaind`'s resident size with a full rig loaded,
  and with models held ready for switching, is in Phase 1 step 7 below.
- **The hard constraints in `CLAUDE.md`** are written for a Pi 5 Core host. Phase 1 needs nothing Pi-specific, since it uses the SSL 2+
  over USB.
- **Phase 2 goes on a Pi.** The WM8960 goes on the 40-pin header, where Pi overlays apply. The Pi's
  stock `wm8960-soundcard` overlay assumes the Pi supplies clocks, so the pedal uses its own
  (`devices/common/rootfs/etc/pedal/codec/wm8960-codec-master.dts`) and keeps the codec as clock
  master with a 24 MHz MCLK. The bring-up is on vip, or on piv when vip is busy.
- **Phase 3.** The Pico's UART goes to the host's header UART on pins 8/10. The protocol doesn't
  change.

**Baseline boot assets:** Ubuntu's `raspi-realtime` kernel with rtpi's rebuild on top
(`docs/vip-kernel-image.md`). **Proposed 2026-09-29** in [docs/vip-image.md](docs/vip-image.md),
with how vip is built (one command on the Mac writes a blank card), its rescue and pedal roots, and
the fallbacks. It has six choices for you at the end.

## Where things stand

### Against the goal in `about.md`

| Goal | Today | Gap |
|---|---|---|
| Entirely digital effects | namchain renders NAM, cab IR, EQ (bands, tilt), cut filters, feedback delay, gain and lane mixing: 11 primitives and 7 macros. 27 of ljoss's 102 blocks map onto them | Nothing required for your own use (D7). The rest stay badged "unavailable" in ljoss |
| A rig document becomes a virtual rig | ljoss encodes rigs and drives `namchaind` over TCP (protocol 2, token), proven against a daemon on macOS and live against vip | Nothing: it runs on the Core host |
| External MIDI controller | The MIDI Commander (USB and DIN out, your own firmware fork, its own two expression inputs sending CC11/CC4) | All of it: the DIN input on the Pico, the UART link, and mapping MIDI onto rigs |
| Very low noise | Analogue design drafted in `docs/hardware-handoff.md`. Codec wired, measured and soaked on the bench ([docs/codec-bringup-2a.md](docs/codec-bringup-2a.md)) | Input R/C mapping not yet checked. Analogue parts not bought. No noise-measurement method yet |
| NAM models | One A2-Full (WaveNet) model costs **0.111 of one core** on vip, measured at 9 copies with p99 97.4% of the deadline (`devices/vip/cost.json`; source and method in [bench-results/2026-10-08-cost-table-vip/README.md](bench-results/2026-10-08-cost-table-vip/README.md)) | Models load when a rig compiles, not held ready for switching. Switching crossfades; warm start is namchain's M3 |
| IR | `nc.cab.ir` convolves the **whole** IR directly (`nam::Linear`, no length cap), and refuses any IR that isn't at 48 kHz because there is no resampler | Your library is mostly 500 ms files (about 24,000 taps), and two thirds of it is at 44.1 or 96 kHz. Measured on vip, an 8192-tap cab costs 0.0222 of a core and a 2048-tap one 0.010 (`devices/vip/cost.json`) — a fifth of a Full model, so direct convolution fits beside one. Resampling the library's other rates is namchain's |
| Immune to glitches | PREEMPT_RT with core 3 isolated, clean hour-long soaks, crossfaded edits, per-node guards | Not yet shown under WiFi and app traffic, on the codec, through boot (no bypass yet), or across power loss (SD card) |

### Repos, machines and documents (surveyed 2026-09-23)

- **namchain** on the Mac is at `origin/main` (`9e9d947`) plus uncommitted CoreAudio and loop
  backends: 12 modified files and 7 new ones, including a new, untracked block diagram. piv's
  checkout is 4 commits behind.
- **ljoss** is checked out as `~/code.local/nodey`. It has one unpushed commit and about 30 files
  of LocalEngine and model-library work in progress. piv's copy is stale at `7618314` (11 Sep).
- **The documents have drifted:**
  - There are two hardware handoffs. The copy in namchain, `docs/research/`, has your notes that
    the codec and the RP2350 board hadn't arrived; the one here has the later control-surface
    section.
  - There are three generations of the block diagram, and the newest is untracked in namchain. In
    both two-layer versions the AVDD arrow has no target.
  - `docs/handoff-from-claude.md` is newer than `CLAUDE.md`. `CLAUDE.md` describes the codec
    modifications as done.
  - The handoff's "JACK or PipeWire plus the NAM LV2 plugin" is out of date: `namchaind` drives
    ALSA itself.
- **Hardware:**
  - The WM8960 board is in hand and unchecked, so stock.
  - The RP2350-USB-A is due within a week. It has 15 GPIO, and the control surface as designed
    needs about 18.
  - There's no standard Pico 2 yet.
  - TRS jacks yes, other analogue parts no.

---

## Decisions

| # | Decision | Source | Consequence |
|---|---|---|---|
| D1 | First target: play through the Core host with the SSL 2+, with ljoss over WiFi | you | Phase 1 comes before the codec and the Pico |
| D2 | ljoss talks to `namchaind` on the Core host directly over WiFi. The Pico does physical controls only | you + recommendation | No app traffic over the UART. WiFi load gets soak-tested. Pico WiFi stays possible with a Pico 2 W (see Shopping), but it would never carry rigs or models |
| D3 | Rigs, models and IRs are stored on the pedal. It resumes the last rig, with its models, at power-up, and changes rigs with no app connected | you | A rig library on the device, a path for uploads, resume, and models held ready for fast switching |
| D4 | A **pedal service** beside `namchaind`, in this repo, owns the rig library, resume, uploads and the footswitch/MIDI mapping. namchain stays a generic engine | you | namchain's only new job is keeping models loaded and ready (plus any small hooks the service needs) |
| D5 | Mic input: leave room, build later | you | Reserve a panel position and the codec's right input (RINPUT1) |
| D6 | MIDI arrives as 5-pin DIN into the Pico, through an optocoupler | you | The MIDI Commander needs its own power (the DC7's USB-A). USB MIDI goes in the debt register |
| D7 | No new DSP is needed before the pedal is usable | you | Effects work is off the critical path |
| D8 | Bring the codec up stock, then modify it, measuring before and after | proposed | `CLAUDE.md`'s "differs from stock" becomes "planned modifications" |
| D9 | Work across repos as set out in `docs/working-across-repos.md` | proposed | Phase 0 |
| D10 | Every rig one interaction away is held ready: the current bank (the 4–8 rigs the footswitches step through) plus any rig MIDI can jump to. A switch takes **≤ 50 ms** from footswitch or MIDI to the new sound, crossfaded, with **no dropout and no click** | you, 2026-09-26 | 3.8 is required, not optional, and comes before 3.5. namchain's M3 (warm start) moves onto the critical path. Whole rigs are held ready: compiled plans, loaded models and prepared IRs. vip's 1 GB bounds the bank. *How* each rig is kept ready is a tier (`docs/rig-switch-strategies.md`), set by experiments E1 and E2. **Amended 2026-10-09 (you):** the ready set is the rigs the footswitches reach next, not everything MIDI could jump to — that set is unbounded, and a jump outside the neighbours is a catch-up (P8), which the 50 ms bar does not cover. Warming more of the bank is optimisation, after the pedal is gig-ready |
| D11 | The Core host runs the pedal's own Wi-Fi network; the Pico advertises over BLE and the phone joins with `NEHotspotConfigurationManager.joinAccessoryHotspot` | you, 2026-10-01 | Phase 5 ([docs/pairing.md](docs/pairing.md)). The pedal root retires its station config, the bench reaches the pedal over Ethernet, and neither `sftp` nor a typed address is needed for the app |
| D12 | The first pairing gets an out-of-band code on the pedal's screen, before the pedal releases its BLE bundle. v1 pairs without it | you, 2026-10-01 | 3.7's display carries a security job, not only a nice one; the code is the Mac's way in too, and the QR stays the fallback |
| D13 | The five repositories live in one workspace, `~/code.local/pedal/`, which is deliberately **not** a repository; a guard installed by path refuses an embedded checkout that nothing declares | you + recommendation, 2026-10-06 | [docs/workspace.md](docs/workspace.md). A session opened on the workspace writes in all five with no extra permissions; `scripts/workspace check` and `scripts/status` keep the layout, the declaration and the guard from rotting silently |
| D14 | The pedal gets a screen, an 8.8″ 1920×480 touch bar display (mini‑HDMI video, USB touch), in a larger enclosure (Hammond 1456RH3). Its UI is **rigpa** (C++, Qt 6), on the Core host's housekeeping core 0: a client of `namchaind` and of `pedald`'s library API that reads the library read‑only. The Pico keeps every physical control (D2 stands); the main rotary, apply and back join the footswitches on the UART. Supersedes "the Core host does DSP only" and 3.7's ST7789 | you, 2026-10-09 | `../rigpa/docs/spec.md` and `plan.md`. **Conditional:** a soak on vip with rigpa off, idle and animating must show 0 xruns, 0 overruns and the worst block under 90% (rigpa plan V2); if not, rigpa's rendering is cut back until it does. vip's kernel, boot config and image gain a display stack (rigpa plan V1) |

**On storage (D3).** The existing design already keeps models and IRs on the pedal, in
`namchaind`'s `models_root` and `irs_root` on the SD card. D3 and D4 bring in the four things it
deliberately left out:
- getting files there from the app
- a rig library on the device
- resuming at boot
- keeping models loaded in RAM, ready to switch.

---

## Phase 0 — Make the repos and machines agree

Small and first, because every later phase deploys from it.

1. **Correct `CLAUDE.md`.** Done 2026-09-25.
   - Take the title and the diagram notes from `docs/handoff-from-claude.md`, then remove that file.
   - Current phase → this plan's.
   - "Hardware that differs from stock" → "planned modifications (D8)".
   - Add D2 and D4 as architecture lines, and a pointer to the repo map.
2. **One hardware handoff.** Done 2026-09-25; namchain's copy is a pointer.
   - Merge your notes from `namchain/docs/research/namchain-hardware-handoff.md` into
     `docs/hardware-handoff.md`: arrival status, the note that a Pi 5-class board is the Core host,
     the schematic path, and your note about keeping the diagram's formatting.
   - Rewrite its software section: `namchaind` on `alsa_raw` instead of JACK/LV2, plus D2–D6.
   - In namchain, replace the research copy with a one-line pointer here.
3. **One diagram.** Done 2026-09-25: `docs/diagrams/nam-pedal-block-diagram.drawio`. The App
   arrows now go to the Engine (D2), which moved the 5 V supply row down 60 px to clear a path.
   - Move namchain's two-layer diagram and its untracked `-2` successor here, and retire this
     repo's single-layer one. The `-2` file is already here, unchanged
     (`docs/diagrams/nam-pedal-block-diagram-2.drawio`); it left namchain's working tree with step 4.
   - Attach the AVDD arrow to the codec.
   - Drop "App comms (WiFi)" from Control, replace JACK/LV2 with `namchaind`, and add the pedal
     service.
   - Keep the lower, USB-interface layout, labelled Phase 1.
   - Render it with the draw.io CLI to check it.
4. **Park the in-flight work.** Done 2026-09-24, at your call to keep it separate.
   - namchain's CoreAudio and loop backends are on the `local-engine` branch (`4cec06c`).
   - ljoss's LocalEngine and model-finder work is on its own `local-engine` branch (`f83ad56`).
   - Both branches are pushed, and both `main`s are clean.
   - ljoss's finished test commit (`6fc69b0`) is pushed to `main`.
   - piv's namchain and ljoss checkouts are fast-forwarded to `origin/main`.
   - Work on either aspect continues on `local-engine`, committed and pushed there.
5. **Rename `~/code.local/nodey` → `~/code.local/ljoss`.** Done 2026-09-25, with its Claude
   project history moved to match. namchain's comparison doc already uses
   that path, and it's the one piv uses. Xcode's DerivedData will rebuild.
6. **Commit the armv7-NEON build** in namchain. Done 2026-09-25 (namchain `907ef81`):
   `cmake/toolchains/armv7-neon-linux-gnueabihf.cmake`, a CI job that runs the tests and the
   planar parity gate under qemu-arm, and a configure summary that compiles `a2_planar.h`'s own
   gate. Verified on piv: 261/261 tests pass and the parity test runs.
   - A toolchain file or `CMakePresets.json` entry for NEON-guaranteed boards (`-mfpu=neon-vfpv4`),
     keeping the generic `vfpv3-d16` one for redistributable builds. NAMBench already does this
     with `NAMBENCH_ARM_FPU`.
   - Add it to CI as a build job.
   - Fix the configure summary. It prints "A2 planar NEON: OFF" on an armv7 NEON build while the
     planar kernels are running, because `NAMCHAIN_A2_PLANAR_ACTIVE` only matches
     aarch64/arm64/armv8.
7. **Agent setup.** Done 2026-09-25. Claude Code loads the other repos' `CLAUDE.md` only with
   `CLAUDE_CODE_ADDITIONAL_DIRECTORIES_CLAUDE_MD=1`, which the local settings set.
   - `.claude/settings.local.json` with the other checkouts as extra directories.
   - `AGENTS.md` plus a one-line `CLAUDE.md` in namchain, rtpi and ljoss.
   - Check whether Claude Code reads `CLAUDE.md` from extra directories.
8. **Scripts here:** `scripts/status`, `scripts/host-lock`, `scripts/deploy-engine` and
   `components.lock`, as specified in the repo doc. Done 2026-09-28. `scripts/deploy-engine`
   (native aarch64 for each host) and `scripts/sync-library` came
   first.
   - `scripts/host-lock` holds a `flock` on the host (`/run/lock/pedal-host.lock`) through an ssh
     session with a heartbeat, so a sleeping Mac or a dropped network lets go within 30 s. The lock
     file names the holder. `deploy-engine` and `apply` take it; `sync-library` deliberately doesn't,
     because step 8's soak runs it in the middle.
   - `components.lock` is written by `scripts/components-lock` from the host itself (the binary
     `namchaind` is actually running, and `/etc/pedal/applied`), with no timestamps, so it only
     changes when a component does.
   - `scripts/status` fetches and reports every checkout on the Mac and piv, then the Core host.
     First run: piv's dev checkouts are 1–11 commits behind (they aren't what runs; the build tree
     is), the engine is 3 commits behind namchain's `origin/main`, and `devices/piv` was last
     applied from a dirty tree (`c23c053-dirty`, committed as `56c7dae`).

**Done when:**
- `scripts/status` shows every repo clean, or deliberately on a named branch, on every host.
- `scripts/deploy-engine` rebuilds the NEON configuration from a commit.
- `CLAUDE.md`, the handoff and the diagram each exist once and agree.

## Phase 1 — Play through the Core host

On piv before vip arrived, then on vip (see [The Core host moves to a Pi 5](#the-core-host-moves-to-a-pi-5)). Step 1's recorded id is the SSL 2+'s on piv; step 2's measurements were piv's, and vip's
replaced them. The first target was reached on vip through the codec (below).

1. **Open devices by name** (namchain). `alsa_raw` resolves `hw:CARD=<id>` or `hw:<id>,<dev>`
   through `/proc/asound/<id>`, so a reboot can't point the engine at the wrong card. This is
   needed for the WM8960 too.
   Done 2026-09-25 (namchain `412e151`). The SSL 2+'s id is `II` (ALSA takes it from
   "SSL 2+ Mk II"), so the config names `hw:CARD=II,DEV=0`.
2. **Make an amp + cab rig fit** (namchain).
   Done 2026-09-25 (namchain `79939b4`). `nc.cab.ir` now uses `PartitionedConvolution` from your
   AudioDSPTools fork at `b505422`, with all three NAMBench optimisations. The core's `nam::Linear`
   it replaced was already a partitioned FFT, but without the spreading. It also resamples 44.1/96 kHz
   IRs and caps them at 8192 taps, as the plugin does, less the plugin's −18 dB.
   **Partly undone 2026-09-26** (namchain `04a1fc8`): you deprecated the AudioDSPTools fork, and it
   was gone from GitHub, so a clean clone couldn't build. `nc.cab.ir` is back on the core's
   `nam::Linear`; the resampling, the 8192-tap cap and the `.nam` path stay. On piv at q64,
   A2-Full + full cab went from p99 8.7% to 15.4%, with 0 overruns. At q32 it's 24% with 5
   overruns a minute, and a few ~1 ms blocks appear with either convolver, cause unknown
   (namchain `bench-results/piv-cab-ir.txt`). vip's cost table puts the same shape at 0.0222 of a
   core for an 8192-tap cab: see the debt register.
   **For step 8:** the rig has to be run the way the pedal runs it, with the host's own tuning in
   force — `devices/vip/tune.conf` owns the CPU split, the clock and the audio interrupt, and
   `pedal-tune check` prints the temperature and throttle state beside them.
   - Then port the partitioned FFT convolution from your AudioDSPTools `partitioned-ir` branch
     into `nc.cab.ir`: direct up to 512 taps and FFT above, as the branch's `Auto` does.
   - Test it against the direct path within a stated tolerance. The branch measured 136–138 dB
     below the signal, so bit-identity won't hold, but a tolerance test will.
   - Latency stays at zero, because the branch keeps a direct head.
   - Beside A2-Full, the FFT path's burstiness may matter: each partition's transform lands in one
     callback. Spreading that work across the quiet callbacks was a "not worth it yet" item in
     `NAMBench/IR-PATH.md`. On one shared core it may become worth it, and 1.8's soak decides.
3. **Deploy.** Done on piv 2026-09-26 (namchain `04a1fc8`, `devices/piv`). `scripts/deploy-engine`
   builds natively on piv in `~/pedal-build/namchain`, runs the tests, installs to
   `/opt/namchain/<commit>/` behind a `current` link, and generates the TCP token on the host
   (`/etc/namchain/token`, never in git). `namchaind` runs in `pedal-rt.slice`, render thread
   FIFO 80 on core 3, TCP on `0.0.0.0:47810`. The SSL 2+ has to be opened with all its channels
   (8 in, 6 out); asking for 1/2 leaves the engine "lost". Still to do: a fixed address or mDNS
   for ljoss (avahi is installed but inactive on piv).
   - `namchaind` and `namchainctl` go to the host through `scripts/deploy-engine`.
   - Install the systemd unit and config under `devices/<host>/`:
     - `alsa_raw` on the card by name, render thread pinned to core 3
     - `Slice=pedal-rt.slice` (the only slice allowed on core 3), `LimitRTPRIO=95`,
       `LimitMEMLOCK=infinity` (a service doesn't get `limits.d`)
     - start from the settings the soaks used (quantum, periods, output-queue cap)
     - TCP on the LAN with a token from a file.
   - Give the host a fixed address (a DHCP reservation) or use its mDNS name, because ljoss has no
     discovery.
4. **Library on the pedal.** Rsync the models and IRs your rigs use into the host's library folders,
   no conversion needed: `nc.cab.ir` resamples 44.1 and 96 kHz IRs itself (step 2).
   Done on piv 2026-09-26: `scripts/sync-library` mirrors `~/Documents/Audio/NAM` and `IRs` (53
   models, 1,538 IRs, 157 MB) into `/var/lib/pedal/library/{models,irs}` and asks the engine to
   rescan. That settles the open question of where data lives, for now: `/var/lib/pedal/library`.
5. **ljoss → the Core host.**
   - Point ljoss's Hardware settings at the host, and run `Tools/check-device.sh` against it.
   - Play an amp + cab + EQ + delay rig and edit it live.

   Done on piv 2026-09-28, through the SSL 2+ (`namchaind` moved back from the WM8960 for this,
   `e8d8413`: the codec has no buffer or output stage yet).
   - ljoss reaches piv as `piv.fritz.box` (the router's DNS follows DHCP; avahi isn't needed).
     The token is in ljoss's keychain entry, and in `~/.config/pedal/piv.token` for
     `check-device.sh`, which passed: authenticated, the rig audible after one poll, 0 xruns.
   - A rig of a NAM amp + cab capture (Ampeg VT-40, `gear_type: amp_cab`, so no IR), tone stack,
     EQ and delay, played from a guitar loop into SSL input 1 and edited live from ljoss: it
     sounds right, and 40-odd edits went through with 0 xruns.
   - The SSL's Monitor Mix must be fully on playback, or the dry input masks the rig.
   - Fixed on the way: ljoss re-rendered forever once connected, at 100% of a core, and cancelled
     every send (ljoss `b8cf180`).
   - For step 8, the rig needs an amp-only model plus a full-length cab IR, as specified.
   - **Pops, 2026-09-28: a bad USB cable.** Tiny pops through piv, none with the SSL on the Mac.
     namchain `980ef47` added `engine.record` (every capture and playback period to WAV) and the
     output queue's drops and insertions to `engine.status`. With an empty rig, out 1 equalled
     in 1 on every frame, but the SSL's loopback (capture in 3 = out 1 as received) matched out 1
     only at a delay that stepped, mostly by −6 frames, with no xrun anywhere.
     - It was the same with `aplay`/`arecord` and `namchaind` stopped, so not the engine. Slips:
       one per 72 s through the powered hub, one per 3 s direct, one per 1.4 s on the USB 2.0
       port. `lowlatency=0` made no difference, and period 128 only cut them by two thirds.
     - usbmon (`tcpdump -i usbmonN -s 0`) settled it. The kernel copied both directions exactly,
       but IN packets arrived empty with −71 (`EPROTO`, corrupted on the wire): each lost 6 frames
       of all 8 inputs, the guitar included, which namchaind then played. ALSA, namchaind and
       `dmesg` report none of it. Power was fine (5 A supply, not throttled, EXT5V 5.10 V).
     - A new cable, same port: 0 `EPROTO` and 0 slips in 180 s on the wire, and 0 in 790 s
       through `namchaind`. No pops heard. The −18 (`EXDEV`) packets are only the URBs cancelled
       at stream stop.
     - The check, for next time: `wire-test.sh` and `wire.py` in `scripts/usb-audio/`.
     - The SSL then went back to its first port (`xhci-hcd:usb4`, the controller without the
       root SSD) on the new cable: 0 slips and 0 `EPROTO` in 180 s on the wire.
6. **Resume at power-up (pedal service v0).**
   - A small process polls `engine.status`. When the generation changes, it saves `rig.get`'s
     document atomically into the rig library.
   - `namchaind` starts that document at boot. It already compiles and prewarms a startup rig
     before the clock starts.
   - Whether the service stays beside `namchaind` or later fronts it for the app is left to 3.2.
     Decided 2026-09-28: **beside**; the app keeps its direct connection
     ([docs/pedal-service.md](docs/pedal-service.md)).

   Done on piv 2026-09-26: `pedal-resume` (`devices/common`). It compares documents, not
   generations, because a knob change (`set`) leaves the generation where it was. It saves 2 s
   after the rig stops changing, so a knob drag is one write, to
   `/var/lib/pedal/library/rigs/last.json`, atomically, and keeps the previous one as
   `last.prev.json`. `namchaind` starts `last.json`, and an `ExecStartPre` seeds it from
   `/etc/pedal/default-rig.json` on first boot. Tested across a `namchaind` restart and a reboot
   of piv (2026-09-26): it came back on the saved rig (the −2 dB tone edit), running, 0 xruns,
   with every `devices/piv` check green and the audio interrupt pinned. Then a hardware reboot
   (power pulled): the same again, with `last.json` intact and valid, and the rig running 13.9 s
   after the kernel started. piv's root is a USB SATA SSD, not an SD card, so this says nothing
   yet about vip's storage; that stays Phase 4's.
   **2026-10-04: `pedal-resume` is retired.** `pedald` (3.2's v1) owns the same job — one writer of
   `last.json` — with the save rule R2 asked for widened: it watches `generation`, `params_applied`
   **and** the rig the engine reports, because a `rig.load` moves the rig's path and name and leaves
   both counters alone (measured). On vip it wrote `last.json` for the app's rig the same evening.
   First number for step 7: the rig was published and the render thread running **13.2 s** after
   the kernel started (userspace reached multi-user at 25 s; firmware and bootloader time before
   the kernel not counted).
7. **Measure what D3 needs:**
   - how long `rig.apply` takes on the Core host, from the command to hearing the new rig, with
     its NAM and IR: the **cold-switch baseline** that 3.8 has to beat to reach D10's 50 ms
   - power-on to sound (13–14 s from kernel start to a running rig on piv, 2026-09-26; firmware
     time and the first audible output still to add — method at the end of this step).
   - `namchaind`'s memory with one rig loaded, and per extra model held: what bounds the bank on
     vip's 1 GB.

   D10 already settles that 3.8 comes before footswitches. The boot number decides how urgent the
   bypass relay (3.6) is.

   Measured on piv 2026-09-26 (`tools/measure-switch.py`; namchain
   `bench-results/e1-warm-candidates-piv.txt`):
   - **Cold switch:** `rig.apply` to the new rig audible and the fade done, cycling four A2 + cab
     rigs: **25 ms** median (27 max) with the files in the page cache, **33 ms** median (35 max)
     read from disk, 0 xruns. Add ~5 ms of output path (the loopback, out 3 → in 1, measures 8.7 ms
     round trip): about 38–40 ms to the jack, already inside D10's 50 ms. **But** the new rig starts
     from NAM's silence-state prewarm, and E1 shows that is the wrong sound for the first 170–340 ms
     (up to +15 dBFS from what it should be). Fast, but not right: see E1.
   - **Memory:** `namchaind` with one rig: 21 MB resident. Each extra rig held: ~2 MB. vip's 1 GB
     is not a constraint on the bank.
   - **Power-on to sound:** 13.2–14.2 s from kernel start to a running rig (three boots, the last a
     power cycle). Power cut to rig running was 33.7 s, but that includes however long piv was
     unplugged: the bootloader leaves no timestamp to separate it, so firmware time is unmeasured.
     A Pi 5 is typically a few seconds before the kernel; call it **~20 s power-on to sound**. WiFi
     came up ~5 s after the rig did, so the app can't reach the pedal until well after it plays.
     20 s of silence at power-on makes the bypass relay (3.6) worth having.
   - Found on the way: `namchaind`'s control thread, which compiles rigs, ran SCHED_FIFO 80 with
     core 3 allowed, beside the render thread. The pedal's drop-in now keeps it on cores 0–1 at
     normal priority.

   **What is left, and how (2026-10-02).** Only the power-on number, and its two ends want
   different tools.
   - **Before the kernel — the firmware's and the bootloader's own time.** The Pi 5's bootloader
     already prints it: vip's EEPROM config has `BOOT_UART=1`, and on a Pi 5 that output goes to
     **UART10 on the dedicated debug connector** (the Raspberry Pi bootloader docs), which is
     also where vip's console is (`console=ttyAMA10,115200`). `/dev/ttyAMA10` is the only UART
     device vip exposes, so the console is not on the 40-pin header's UART that 3.4 wants for
     the link — 3.4 has to enable that UART, not move a console off it. One 3-pin JST-SH cable
     therefore carries the bootloader's first line and the kernel log.
     `tools/measure-boot.py` captures it from the Mac through the Debug Probe's UART bridge (the
     `/dev/cu.usbmodemNNN` that `firmware/tools/echo-test.py` already finds), or any 3.3 V
     USB-TTL; a passive capture needs only GND and the Pi's TXD, and nothing is written back to
     the getty on that port. The probe's SWD port is unaffected, but its UART bridge leaves the
     echo test's GP0/GP1 wiring while it watches the Pi.
   - **Power-on itself is the one thing the wire cannot show.** The first bootloader byte arrives
     a small, unstated time after power is applied. Quote that offset as the uncertainty,
     calibrate it once against the 5 V rail with a scope, or stamp t0 from a switched supply —
     but say which: a power-on number without its anchor is not a number.
   - **After the kernel, no probe is needed.** `dmesg` starts at `[    0.000000]`, and
     `journalctl -b -o short-monotonic -u namchaind` is kernel-relative.
   - **Measured 2026-10-02**, three boots (`bench-results/2026-10-02-boot-time-vip/`). First
     bootloader byte → kernel, the firmware's own counter for the same span, kernel → rig
     published, and the total:
     - **plug pull** (`power-on-reset 1`): 12.95 s, 12.82 s, 7.48 s → **20.43 s**
     - a second, incidental power-on: 12.96 s, 12.84 s, 7.52 s → 20.48 s
     - **power button**, PMIC standby (`power-on-reset 0`): 16.64 s, 16.51 s, 6.52 s → 23.16 s

     The two clocks (Mac and the firmware's own) agree to 0.12–0.13 s every time, which is what
     the wire costs, so that is this method's accuracy; the two power-on boots agree with each
     other to 10 ms at every stage. **The pedal's case is the plug pull: a rig is playing 20.4 s
     after the bootloader's first byte**, plus the PMIC and boot-ROM time before it, so the
     "~20 s power-on to sound" above holds and 3.6's relay keeps its justification. "Rig
     published" is still not "measured at the jack".
     - The button boot's extra 3.7 s is **one silent stall** between `Halt: power_off: 0` and
       `PCIEx1: PWR 0 DET_WAKE 0` inside the EEPROM bootloader (firmware clock 1.17 → 4.85 s);
       the plug pull runs the same lines with no stall, so it is the standby path, not the
       pedal's, and needs no explaining for 1.7.
     - Everything from the second bootloader stage on is identical across the three boots to
       within 0.03 s, including **4.66 s between `Boot mode: SD` and the SD card coming up** —
       a fixed wait, the largest in a boot, and Phase 4's target. The 52.8 MB initrd is 2.2 s
       more (rtpi's slimming work's) and the 14.7 MB kernel 0.6 s.
     - The kernel half is 7.5 s on a plug pull (namchaind started at 5.80 s, getty at 12.3 s of
       kernel time) against piv's 13.2–14.2 s above, so the pedal's own boot is no longer the
       slow half.
   - **The jack end, measured the same day** (`bench-results/2026-10-02-boot-time-vip/jack/`): a
     220 Hz tone into the pedal's input socket, out through the HPL fixture into the SSL's input
     1, recorded while the boot ran. **First bootloader byte → audible: 21–22 s** (12.95 s of
     firmware and bootloader, then 8.9 s of kernel and userspace), and the engine's own
     `published` line lands within a second of it — so "playing" and "audible" are the same moment
     at this resolution, and the analogue path adds nothing measurable. Power removed → audible
     was 31.5 s, 9.6 s of which was the owner's own time unplugged. Only the power-on instant
     itself is still unmeasured, on neither the wire nor the jack.
   - Two bench facts that came out of getting there, both now known: **vip's HPL only reaches
     2a's output fixture** (a lead straight onto the codec pin has no return path and reads as
     silence, which cost an afternoon), and **HPR is not wired at all** — the right half of the
     fixture is missing, which is Phase 2's board 1 work. Also worth recording: the guitar lead
     had come out of LIN1, and vip's input path had never carried a signal on this bench until
     that was found.
   - **"First audible output" is not on the wire either.** Capture the jack (`engine.record`, or
     the Mac's interface) on the same Mac clock as the serial reader, or report the engine's own
     readiness and say that is what it is. "Rig published" is not "sound".
   - **Monotonic timestamps only** (`-o short-monotonic`, `dmesg`): vip has no RTC battery, and
     its journal dates the first entries 2026-07-27 before the clock jumps.
   - The Pico's own boot is milliseconds and belongs to 3.1/3.4, on its USB console, not on this
     probe.
   - **Done, 2026-10-07: the EEPROM is recorded and diffed.** The pin and the board's state live in
     `devices/vip/rootfs/usr/local/lib/rpi-eeprom/eeprom.lock` (upstream commit, image and
     recovery by sha256, version, timestamp, the three keys), `check` diffs all of it (`vcgencmd`,
     or the nvmem device this note named, which reads the same thing without root — `rpi-eeprom`
     and `raspi-utils` arrived in `devices/vip/packages` on 2026-10-05), and `vip-eeprom` is the
     one way to change it. The board went from the factory `66f33f7e` (2026-05-11) to `1accd665`
     (2026-09-25) with the configuration carried across
     (bench-results/2026-10-07-eeprom-update.md; docs/vip-image.md, "The bootloader EEPROM"). What
     is still open is the *choice*, not the record: `NET_INSTALL_AT_POWER_ON=1` spends about a
     second at cold boot on keyboard and network-install probing (`NET_INSTALL_KEYBOARD_WAIT`
     defaults to 900 ms) which the pedal does not need, and turning it off is a configuration write
     (`rpi-eeprom-config --apply`), not an image update — and still an EEPROM write.
   - Take the host's lock for the reads around it, and **power-cycle** vip rather than `reboot`ing
     it: a cold boot is what this step asks for. The lock cannot span the power loss — it is an
     `flock` held by an ssh session on the host, so pulling the power drops it. Evidence:
     `bench-results/2026-10-02-boot-time-vip/`.

8. **Soak it the way it will be used.** An hour through `namchaind` with an A2-Full + full-length
   cab IR rig, holding the Core host's lock, with ljoss editing over WiFi and one library rsync in the
   middle.
   - Gate: 0 driver xruns, 0 deadline overruns and 0 guard trips, with the worst block inside
     namchain's ARMv7 bar of 90% of the deadline.
   - Separately: the same soak with only an rsync running, so WiFi's cost, if it has one, is
     isolated.
   - **First run, 2026-09-28 (namchain `abe1f34`, q64): FAIL, and not to spec.** 60 min, the
     SSL direct on its first port, looping guitar, ljoss editing, `sync-library` at 30 min. 0 driver
     xruns, 0 guard trips, 0 queue drops or insertions, 36–41 °C, never throttled. But 7 blocks
     past the deadline (worst 1.87 ms, 140%) and 18 past 90%, all in five 10 s windows at
     28–29 min with 3–7 transitions each; the other 64 windows with transitions had none.
     - Every ljoss edit arrived as a structural transition (182 transitions, 0 `params_applied`),
       each dual-rendering the rig for the fade. ljoss sent the whole document (`rig.apply`)
       250 ms after the last change. A proposed change is in [docs/rig-edits.md](docs/rig-edits.md).
       Its first step is in ljoss `462e678`: a knob the engine ramps is now streamed as
       `rig.patch` ramps.
     - The spec rig (GVT52 G5 as A2-Full, high shelf, ORNG 421v-CNT) ran only for the first
       2.6 min. This entry first said ~28 min, and was corrected the same day. Then ljoss connected
       and applied its own rigs for the rest of the hour: "New Rig 2" almost throughout, "Crunch
       Lead" at 13–14 min, and "New Rig 3" briefly at 2.6 and 27.4 min. `engine.status` names the
       rig but not its models, so only the load shows what each held:
       - p99 7–8% at first;
       - 16% by 13 min, like the spec rig;
       - 7–8% from 29 min to the end, on the VT-40 amp_cab rig with no IR that was left loaded.
     - **The overruns came from running two plans of a heavy rig at once.**
       - From 27.6 to 29.1 min, "New Rig 2" ran at p50 ~30% and p99 39–52% on its own, three to
         four times the spec rig's load. No fade stayed open.
       - A transition renders both plans for the 5 ms fade, and twice a p99 of ~50% is the
         deadline. The five windows with blocks past 90% held 22 transitions.
       - Twice the spec rig's p99 is ~32%. So this run shows nothing against the spec rig. It does
         show that at q64 a structural edit overruns on a rig above ~45% p99, whoever sends it.
         namchain has no admission control yet (its `docs/transitions.md`, "What is next").
     - The render thread took 705 minor page faults (0 major) over the hour. They aren't needed to
       explain the overruns. Their cause is still open: `mlockall(MCL_CURRENT)` doesn't cover a plan
       built later.
     - To re-run it to spec, the spec rig has to be the rig open in ljoss. ljoss applies its own
       document when it connects, which is what replaced the spec rig this time.
     - `sync-library`'s rsync ran, then its `namchainctl assets --refresh` failed with "the daemon
       closed the connection" (1,538 IRs; the reply is probably over the message cap), which
       stops the script before its summary.
       - `engine.schema` failed the same way, because it lists the IRs as options. Both failed only
         on the Unix socket, where a reply is one datagram, of at most about 208 KiB. Over TCP both
         fitted under the old 1 MiB limit: `engine.assets` at 1,016,823 bytes (97%), and
         `engine.schema` at 808,492. So ljoss, which uses TCP, could still connect. An earlier
         version of this note said it couldn't.
       - Fixed the same day. namchain `503aac9` gives replies a 16 MiB limit of their own, and
         ljoss `6ae4563` reads them. `sync-library` now refreshes over TCP to the host itself: exit
         0, then 52 models and 1,538 IRs.
     - Tools: `namchaind`'s new `engine.status` `render` object (every block against its deadline),
       and `scripts/soak/` (monitor, summary, events).
   - **Repeatable from 2026-09-29.** A soak no longer needs someone editing in ljoss.
     - namchain `b28e86b` records what a client sends (`namchain-session-record`, a proxy ljoss
       connects through) and replays it on the same timing (`namchain-session-replay`), as
       described in its `docs/sessions.md`.
     - `scripts/soak/soak-replay SESSION --duration 3600 --sync-library-at 1800` runs step 8: it
       loops the session from the Mac, over WiFi as ljoss would, while `soak-monitor.sh` samples
       the host, all under the host's lock. The evidence goes to `bench-results/`.
     - Soak 1's edits can't be replayed: its monitor saved `engine.status` every 10 s and nothing
       of what ljoss sent, and piv's journal (RAM only) went at the 2026-09-29 reboot.
     - The ljoss session of 22:17–22:37 that evening (`docs/rig-edits.md`) is rebuilt as
       `scripts/soak/sessions/2026-09-28-ljoss.session.jsonl`, by the script beside it:
       - It starts from the rigs ljoss saved and walks its watch log
         (`bench-results/2026-09-28-ljoss-edits-watch.log`) back from them.
       - The result is 5 rebuilds and 178 ramped knob patches over 20 minutes, the counts the
         watch saw.
       - It checks that each half ends on the rig ljoss saved.
       - Replayed against a local `namchaind`: all 178 patches were smooth, with no errors.
       - The script's docstring lists what is approximate.
     - Record the next real editing session through the proxy, and that becomes the reference.
     - **Run on piv 2026-09-30, 15:37–16:37: PASS.** namchain `d4fb8e5`, the SSL 2+ at q64.
       - The session went round 3 times: 18 rebuilds, 511 knob patches (all smooth), 30 mutes and
         7,190 status polls, from the Mac over WiFi. Nothing was refused and every request was answered.
       - `scripts/sync-library` ran at 30 min.
       - Driver xruns 0, deadline overruns 0, guard trips 0, blocks over 90% 0, device lost 0.
       - Load was p50 8%, p99 24% and p99.9 36%. The worst block was 85% (1,134 µs of 1,333 µs).
         No interval with a transition had a block over 90%.
       - Replies: `rig.patch` p99 20 ms, `rig.apply` max 51 ms. Temperature 35.6–40.6 °C, never
         throttled.
       - Evidence: `bench-results/2026-09-30-soak-replay-2026-09-28-ljoss-piv.*`.
   - Once 3.8 exists, the soak also switches rigs: a switch every few seconds through a bank, with
     the same gates plus D10's: each switch ≤ 50 ms and no click in the output (namchain's glitch
     detector on the captured output).

**Done when:**
- From power-on, the Core host plays the last rig (an A2-Full amp and a full-length cab IR) through the
  SSL 2+ with no app connected.
- ljoss on the Mac edits it live.
- An hour of playing and editing is clean.
- `components.lock` names what's running.

**First target reached** (declared by Rik, 2026-10-02), on vip with the WM8960 rather than the SSL 2+:
vip resumes its rig from power-on, ljoss edits it live (2e1a63a,
`check-streaming`), the hour's replay soak passes (974060c), and `devices/vip/components.lock`
names what runs. The two-amp Ambient Wash failing the gate alone is open, under "Next session
starts with".

## Phase 2 — The codec and the analogue stages

**2a. Stock bring-up.** The board is in hand, so this can overlap Phase 1. The bench walkthrough
for piv is [docs/codec-bringup-2a.md](docs/codec-bringup-2a.md). Found while writing it
(2026-09-27): piv's stock `wm8960-soundcard` overlay makes the Pi the clock master at 12.288 MHz,
so it needs its own overlay (`i2s_clk_consumer`, 24 MHz MCLK). The header's I2C is I2C1 on GPIO2/3,
and the Pi has one I2S frame clock, so DACLRC is wired, ADCLRC is left off, and the codec runs its
ADC from DACLRC (`wlf,shared-lrclk`, `wlf,gpio-cfg`).
1. **Inspect the board.**
   - ~~Jumper states: AVDD-ISO, SPKVDD.~~ Done 2026-09-26 from photos: stock (see the handoff).
     Confirm SPKVDD → VIN with a meter.
   - Map the input R/C table by continuity. The board has no reference designators, so the
     silkscreen can't confirm it. LINPUT1 first.
   - ~~Photos into `references/`.~~ Done: `references/wm8960-photos/`.
2. **Wire it stock.**
   - VIN from the host's 5 V, so the onboard LDO feeds AVDD with AVDD-ISO intact.
   - 3V3, I2C and I2S from the host's header, on short leads.
   - The header's I2C is I2C1 on GPIO2/3, and the Pi has one frame clock, so DACLRC is wired and
     ADCLRC is left off (the handoff's open item, answered in 2a).
3. **Device tree** (rtpi).
   - A WM8960 `simple-audio-card` on the Pi's I2S, from `i2s_clk_consumer` up:
     - codec at 0x1A, clock master (`bitclock-master` and `frame-master` on the codec)
     - a 24 MHz fixed clock as its MCLK, so the driver can set its PLL up for 48 kHz.
   - Built with rtpi's check on the built DTB, tried through the one-shot slot, then promoted.
4. **Mixer state as code** (`devices/common/rootfs/etc/pedal/codec/wm8960.mixer`): ALC off, 3D off,
   speaker amp off, OUT3 off, LINPUT1 → PGA near 0 dB → ADC, DAC → HP_L/HP_R.
5. **Measure with the SSL 2+ as the instrument:**
   - frequency response
   - noise floor, A-weighted, input shorted
   - THD at −1 dBFS
   - round-trip latency with `namchain-latency`.
6. **An hour-long soak on the codec**, with the same gates as Phase 1.

**2b. Review the design, then buy parts.**
1. **Review the analogue design** against the WM8960 datasheet before ordering:
   - ×10 guitar gain against the line input's full scale (about 1 Vrms at AVDD 3.3 V). Headroom
     for hot pickups is the question.
   - The 47 nF / 4.7 nF shunt, given the buffer's real output impedance.
   - The output level into an amp's input.
   - The LDO's noise.
   - How the star ground is laid out.
   - The reserved RINPUT1 (D5).

   **Early findings** (2026-09-24, from the WM8960, OPA1642 and OPA2197 datasheets). 2a's
   measurements confirm or overturn them.
   - **×10 is far too much gain.** It puts full scale at 0.14 V peak at the jack, while guitar
     peaks run from about 0.5 V to 2 V. Put full scale near the loudest expected peak instead:
     about ×1 for guitar (1.4 V peak), with a pad ahead of the buffer for Line. The codec's PGA
     can't add gain quietly either. The datasheet gives its equivalent input noise as 150 µV at
     +30 dB, against about 20 µV (A-weighted) through the 0 dB path.
   - **At these gains the codec sets the noise floor, not the op-amp.** Its ~20 µV is far above
     the OPA1642's ~0.7 µV, or even a TL072's ~2.5 µV, over 20 kHz. What the op-amp has to
     provide is headroom.
   - **Headroom depends on the bias point.** The OPA1642's input range stops 3.5 V below its
     supply, so at 9 V with the drafted 4.5 V bias, input peaks above +1 V distort. Biased at about
     2.75 V, it has roughly ±2.5 V. The OPA2197, which is rail-to-rail, gets about ±3 V at a 3 V
     bias before its input stage changes over, and it keeps working beyond that.
   - ~~**Keep the 47 nF shunts.**~~ Overturned by the review below: they distort. The board's own 100 Ω already isolates the op-amp from them, so the
     draft's extra 100 Ω isn't needed and the corner stays at 34 kHz. The 4.7 nF swap only
     mattered for an unbuffered, high-impedance source.
   - **The output level works.** HP_L and HP_R reach 1 Vrms at full scale. That's hot for an amp's
     input and right for a line input, and `namchaind`'s output gain sets it either way.
   - **AVDD draws about 5–8 mA** (the datasheet's playback figures), so a TO-92 78L33 is plenty.
     There's a simpler option for 2c too: feed the board's VIN from a 78L05 on the 9 V side. AVDD
     then comes off the host's supply with no cutting, and the board's own LDO becomes a second stage.
   **Review against 2a (2026-09-27).** Measured on piv; numbers in
   [docs/codec-bringup-2a.md](docs/codec-bringup-2a.md#results), datasheet v4.2.
   - **Full scale is 1.0 V rms, in and out, as the datasheet says.** The meter's 0.81 V (input) and
     0.45 V (output) were its 200 V range failing at low volts. Codec out → fixture → LIN1 loses
     only 0.4 dB, so the two full scales agree, and the input noise, −93.5 dBFS(A) shorted, matches
     the datasheet's 94 dB SNR. So ~21 µV A-weighted at the pin.
   - **×1 on Inst stands**: 1.4 V peak at the jack is full scale. **Headroom for hot pickups is a
     mixer setting, not a part**: the PGA goes below 0 dB (to −17.25 dB), so −3 dB gives 2 V peak
     and −6 dB 2.8 V peak, which is about where the OPA2197 runs out of swing below its 2.9 V bias.
     Each dB of it costs a dB of noise at the jack. Start at 0 dB and move it only if a guitar clips.
   - **The Line pad and the 2.9 V bias stand.** The pad is passive ahead of the follower, so the
     op-amp never sees more than 1.4 V peak.
   - **The 47 nF shunts distort. Overturned: replace them.** They're ceramic, and their value moves
     with voltage. Measured through LIN1 with a ~200 Ω source, THD rises 6 dB per octave: −78 dB at
     100 Hz, −65 dB at 1 kHz, −58 dB at 4 kHz, against the datasheet's −89. The worse the source
     impedance, the worse it gets (a 12 Ω source gave −72 dB at 1 kHz). Behind the buffer the board's
     own 100 Ω is still in series, so expect about −71 dB at 1 kHz. **Fix in 2c:** swap LIN1's
     shunt (top row, column 4) for a film capacitor. 47 nF PET keeps the 34 kHz corner; 4.7 nF
     would do too. Both are in the drawer. Measure before and after with the codec's own loop.
   - **Source impedance matters for response too**: SSL out 4 (~2 kΩ) put −3 dB at 1.5 kHz. The
     buffer's output is near 0 Ω, so the corner stays at 34 kHz (−0.3 dB at 20 kHz). No extra 100 Ω.
   - **Output level: 1.0 V rms at full scale, confirmed.** DAC THD −81 dB, flat within 0.1 dB.
     Right for a line input, hot for an amp's front end; `namchaind`'s output gain sets it.
     The output stage (10 µF bipolar, 100 Ω, 1 MΩ) stands; into 10 kΩ its corner is 1.6 Hz.
   - **The LDO's noise isn't the limit yet.** With the board's own LDO fed from piv's 5 V, input
     noise is at the datasheet figure. 2c's 78L05 trial is to beat the enclosure, not the bench.
   - **Grounding is the bigger risk.** Sharing ground with the SSL through piv put a 90 Hz comb at
     −86 dBFS, 7 dB over the codec's own floor. In the pedal: one star, one path from piv's ground
     to it (the header GND), and nothing else that joins the two supplies.
   - **RINPUT1 stays reserved** (D5). Its input resistance is 49 kΩ at 0 dB PGA, 3 kΩ at +30 dB, and
     the mixer keeps it unrouted.
   - Also measured: the converters' round trip is 55–57 samples (1.16 ms).
2. **Settle the values.** Done 2026-09-27: the provisional values in
   [docs/bom.md](docs/bom.md) stand unchanged (×1 Inst, 680 kΩ / 330 kΩ Line pad, 2.9 V bias,
   10 µF / 100 Ω / 1 MΩ out). Two additions: hot-pickup headroom through the PGA in the mixer
   file, and the film replacement for LIN1's 47 nF in 2c.
3. **Build the buffer and the output stage** on stripboard, powered from a Cioks outlet through the
   LDO. First on the breadboard ([docs/build-board1-breadboard.md](docs/build-board1-breadboard.md),
   `breadboard/board1.py`), then soldered on stripboard ([docs/build-board1.md](docs/build-board1.md),
   `stripboard/board1.py`); both placements are checked against the one netlist. Decided 2026-10-01:
   the breadboard proves the circuit, the stripboard is practice before the enclosure's tighter
   board A, and the noise is measured on the stripboard. Board 1 (about 127 × 36 mm) doesn't fit
   the enclosure; board A gets its own layout in Phase 4.
4. **Calibrate the input meters with a player in the path** — the step that makes ljoss's meters
   mean something, and the reason board 1 is not finished when it plays. A meter is only useful
   once its full scale is the jack's clip point rather than digital 0 dBFS: this input clips at
   **−11.25 dBFS** and the app draws 0 dBFS, so the bargraph promises about 11 dB of headroom that
   does not exist. Everything the campaign measured was the **codec's** scale, driven by the
   interface's line output (about 2 kΩ, +14.5 dBu at 0 dBFS) into a jack wired straight to LIN1.
   No guitar has ever been the source into this input, and board 1 changes the loading the source
   sees — which is a fact about the jack, and so about what the player's own signal is *at* the
   meter. Two runs, and the first one needs no board 1 at all.
   - **Now: a real guitar into a guitar buffer pedal into the input.** The stand-in the case
     measurements already name (2026-10-04). The buffer's job here is not to make the signal
     hotter: it is to hand the pedal what a pedalboard hands it, a low-impedance source, while
     the guitar is loaded by the buffer instead of by the codec. Record with the pedal's own
     `engine.record` as well as the SSL, and take the guitar pass as a **played take**, not
     `signals.py`'s DI file: the file proves the meter arithmetic, and a player is what the scale
     is for. If the buffer has a second output, put it into an SSL input so the take's own level
     is known independently of the pedal's reading. Update ljoss's calibration block
     (`input_clip_dbfs`, `input_full_scale_dbu`, the meter's floor and nominal) from what comes
     back. Expect the clip counter's pinned-frame counts to stay unhelpful until it counts the
     converter's own positive rail: read them as a pointer, not a measurement.
   - **Once board 1 is built: both switch positions.** The same **Inst** run through the 1 MΩ
     follower at unity, and the **Line** run with the SSL as the known line source, because the
     two cannot share a scale — full scale is about 3.06 V peak at the jack on Line against
     0.92 V peak on Inst, and a passive guitar through the Line pad is judged through 680 kΩ
     (the 470 Hz pole). Each position gets its own clip point and its own calibration block, so
     the app has to know which one the switch is in and pick the matching scale — a hardware
     switch the app cannot see is a meter that lies in one of its two positions. Measure the
     Line pad's ratio here rather than trusting 330k/(680k+330k), and settle the PGA question
     (bench entry, items 1–2) while the ladder is set up.
   - Order and cost: this is a `Tools/levels` campaign, so it goes under the host lock, after the
     codec's card is back — it is down at the time of writing, and no campaign can run until it
     answers. Both runs are written up as dated bench entries, and ljoss's two blocks land in
     dependency order after them.

**2c. Modify and compare.**
- Replace LIN1's 47 nF ceramic shunt with a film capacitor (2b finding), and measure THD against
  frequency before and after.
- First try the option that needs no cutting: VIN from a 78L05 on the 9 V side.
- If that isn't enough, cut AVDD-ISO and fit the external LDO, open SPKVDD and disconnect VIN.
- Measure against 2a, and keep what measurably helps.
- Procedure and the rows it produces: [docs/codec-bringup-2c.md](docs/codec-bringup-2c.md). One
  change per leg, captures read by `scripts/codec-noise.py`, and 2b's expectation that on the bench
  the supply legs change nothing.

**Done when:**
- Guitar → buffer → WM8960 → `namchaind` → output stage → amp works.
- The noise floor is recorded at each stage.
- An hour on the codec is clean.
- The input's clip point is known **at the jack, in both switch positions**, and ljoss's meters are
  scaled to it rather than to 0 dBFS (2b.4) — the player's meters are how the stage is judged, and
  they are wrong until that number exists.

## Phase 3 — The control surface and the pedal service

1. **Boards and tools.**
   - Pico 2 (see Shopping), and C/C++ with the official Pico SDK on the Mac.
     - It plays to your C++, and it has TinyUSB and PIO built in, so USB host is available later.
     - It debugs through the Debug Probe with the least friction.
     - MicroPython starts faster but is weak at USB host and timing. Rust (Embassy) is excellent
       but a second new thing at once.
   - Blink, then echo over UART through the Debug Probe.
   - Built 2026-09-28: `firmware/` holds the firmware (Pico 2 W, SDK 2.3.1, Arm GNU Toolchain
     15.3.rel1; `firmware/build.sh` and `firmware/flash.sh`), and `firmware/tools/echo-test.py`
     runs the round trip through the Debug Probe's UART bridge (probe RX ← GP0/pin 1,
     probe TX → GP1/pin 2, GND). Blink and the echo are flashed and running, and the round trip
     is confirmed on the bench, byte-for-byte (`bench-results/2026-09-28-pico-uart-echo.txt`).
2. **Design the pedal service** (`docs/pedal-service.md`):
   - what it's responsible for
   - beside `namchaind` or in front of it for the app
   - storage layout on the SD card
   - the upload API
   - the event vocabulary where footswitch and MIDI meet
   - security (the same token model)
   - failure modes: the service being down must never mean audio is down.
   - Designed 2026-09-28: [docs/pedal-service.md](docs/pedal-service.md), and reviewed by Claude
     the same day (R1–R15, at the end of the doc). **Beside** `namchaind`, as D4 has it — the
     app keeps protocol 2 directly, and the service is a second client, not a gateway. It owns
     the library on the pedal, the bank, resume (v0's behaviour, one writer), uploads (atomic,
     ids, a model's declared rate must be 48 kHz), the mapping tables and the Pico link; it asks
     namchain for the ready set and the switch once 3.8's calls exist. Two listeners on one
     token: the engine's 47810 and the service's HTTP 47820, reached by the service over TCP
     loopback because `engine.assets`/`engine.schema` replies outgrow a Unix datagram. The **MIDI
     channel is ignored** until a second controller wants the reserved `CFG`.
   - Staged to follow D10 (R1): v1 with 3.4 (the link and resume; switching on the bench only),
     v2 with 3.8 (the ready set, and switching for real), v3 when uploads get a step.
   - **Open, yours:** the relay rule (R4; proposed: bypass after 5 s without the link or 2 s
     without `audio_ready`), ljoss on connect (R6, `docs/rig-edits.md` C12), and who owns the
     switching budget, namchain or the service (R14).
3. **UART protocol**, the contract kept here.
   - Framed, checksummed and versioned.
   - Events: rig up/down/select, bank, CC value, bypass.
   - State back to the Pico: rig name, health, audio-ready.
   - Heartbeats both ways.
   - Draft 1 written 2026-09-28: [docs/uart-protocol.md](docs/uart-protocol.md). The frame
     (sync, type, length, CRC-16/CCITT-FALSE), the `HELLO`/`WELCOME` handshake and 1 s session
     timer, the event kinds that footswitch and MIDI share, `ACK`/retry with dedupe, `STATE`
     back, `PING`/`PONG`. It defers the relay-on-link-loss policy and the MIDI channel question
     to step 2's failure-mode work.
   - The firmware implements it (`firmware/src/protocol.c`) and the frame-level loopback passes
     on the bench, retransmit and link-down included (`firmware/tools/protocol-test.py`;
     `bench-results/2026-09-28-pico-protocol-loopback.txt`). The service end was a test script
     until step 2; **since 2026-10-04 it is `pedald`** (v1, draft 1 framing), and the two ends hold
     a live session on vip.
   - Draft 2, proposed in Claude's review of 2026-09-28 (U1–U8 in the doc): the CRC's text
     corrected, strings length-prefixed, one `EVENT` in flight with a queue behind it, dedupe
     per session, `engine_bypass` renamed `engine_muted`, and (U8) footswitches sending
     `cc` 80–82 so footswitch and MIDI messages are identical. The firmware's resync now does
     what the text says (compile-checked; `protocol-test.py` has a check for it, to run on the
     bench). **U8 is decided (2026-10-06): the footswitches send `cc` 80–82.** A press on the
     pedal and the same button on the MIDI Commander are then one message apart from `source`,
     and the map stays in the one place D4 puts it — the service's table — instead of a `CFG` map
     the Pico would have to keep in step. `source` is kept on every event, so a per-source map can
     come later with no wire change, and `pedald` needs no change for the decision at all
     (`mapping.py`'s `DEFAULT_CC` already maps 80 `rig_down`, 81 `rig_up`, 82 assignable). That
     was the last item of draft 2 that blocked 3.5; the firmware sends the `cc` when 3.5 builds
     the switches. **And draft 2 is written into both ends** (2026-10-06): `str8` strings, the
     `engine_muted` flag, `ERROR` on a version mismatch, `HELLO` answered every time (a Pico that
     reset says so with `HELLO`, and answering only the first left it hunting), and no `PING`,
     `STATE` or `ACK` answered without a session — so a pair that disagrees goes quiet on both
     sides instead of propping up half a link. The version is **2.0**: what a mismatch costs was
     read off both ends (the strings are wrong, nothing else is), and that is a failure worth
     refusing rather than diagnosing. Evidence: `firmware/src/protocol.c` + `protocol.h`,
     `pedald`'s `protocol.py`, the firmware builds clean, and `devices/common/test-pedald` is 194
     tests. **And it is on the pedal** (2026-10-06, later): the Pico was reflashed from the
     committed tree as `bb6dde1`, the loopback passed every check against it — `HELLO` carrying
     `firmware='bb6dde1'`, the `str8` `STATE`, and the refusal (`ERROR` code 1, "Pico speaks 2.0,
     service 1.0", no session, then back up) — and `devices/vip/apply` put the 2.0 `pedald` on vip
     in the same stop. The live pair now holds a 2.0 session, `scripts/diag --host vip` reports the
     link up with no bad frame, and `devices/vip/components.lock` moved to `bb6dde1`. The loopback
     ran **on vip** rather than through the Debug Probe: the probe's UART lead would not make
     contact at the Pico's pins, and the vip port is the production one anyway. Evidence, including
     the crossed-signal-pair diagnosis and the old service reading `fw '\x07bb6dde1'` in the second
     before the deploy — the mismatch's fingerprint, seen for real:
     [bench-results/2026-10-06-draft2-swap-bench.md](bench-results/2026-10-06-draft2-swap-bench.md).
     **3.3 is done.**
4. **The Core host side.**
   - A UART on the Pi's 40-pin header that carries nothing but the link: no kernel console, no
     getty, no SysRq. On piv, pins 8/10 are `ttyAMA0`, and its kernel console is there
     (`console=ttyAMA0,115200` in its command line, 2026-09-28 backup). Either move the console,
     or give the link another RP1 UART through a `config.txt` overlay (the Pi 5's `uart2-pi5` to
     `uart4-pi5`; check Ubuntu's image has them). `devices/<host>/` owns whichever it is.
   - **Done on vip 2026-10-04, and nothing had to move.** vip's console and getty are on
     `ttyAMA10` (the debug connector), so pins 8/10 are free: `ttyAMA0` carries the link, 115200,
     GP0 → pin 10 and GP1 → pin 8 with GND, with `uart0` muxed onto them. A by-hand session came
     up first (`bench-results/2026-10-04-rewire-faults-and-the-pico-console.md`), then `pedald`
     took the port and the two ends have held a session since
     (`bench-results/2026-10-04-the-pedal-plays-in-a-case.md`).
5. **Firmware v1.**
   - Three footswitches, with 100 nF at each switch, debounce and long-press.
   - DIN MIDI in: optocoupler, UART RX at 31 250 baud.
   - Status LEDs.
   - Everything else goes over the UART.
   - First, move the link's UART receive from the polled main loop to an interrupt filling a ring
     buffer. The RP2350's RX FIFO is 32 bytes (under 3 ms at 115200), so a display redraw or a
     burst of MIDI in the loop can overflow it.
6. **Bypass relay.** Choose a relay whose **de-energised** state is bypass.
   - Then no power, a crashed Pico and a booting Core host all fail to bypass.
   - The Pico energises it only once the service reports audio ready.
   - When it drops back to bypass after boot is `docs/pedal-service.md`'s relay rule, open (R4).
     The Pico and the Core host share the 5 V input, so the Pico stays powered through a Core
     host reboot or hang — **the test below holds for form 2 (2026-10-05)**, which is what the case
     will use; the proposal (bypass after 5 s without the link, or 2 s without
     `audio_ready`) is what keeps "a booting Core host" failing to bypass then too. Set its times on
     the bench, and check what a hung Core host puts out: silence, or a repeating buffer.
   - A long press gives a panic bypass.
   - **Does the Pico keep its power through a vip reboot? Test it before relying on it.** The
     Pico takes 5 V from vip (Phase 4's power), in one of two ways:
     1. A USB-A port to the Pico's micro-B. Simplest, and vip can reflash the Pico over it. But a
        Pi switches its USB-A power, and may cut it during a reboot or at shutdown.
     2. vip's header pin 2 through a 1N5817 into VSYS. The header's 5 V is more likely to stay
        live while the supply is on.
     **2026-10-04: form 1 is what the bench is wired as** — the Pico is powered from vip's USB-A,
     and its console rides the same cable.
     **Measured 2026-10-05: form 1 fails the reboot leg and form 2 holds both legs.** The Pico's own
     uptime counter (it prints
     `fw: up N s` on its USB console; the counter measures power, where `dmesg` cannot, because the
     host re-enumerates the device on every boot either way) went **48,930 s → 20 s** across a
     `sudo reboot` of vip on form 1, with a control showing the read itself does not reset it. On
     **form 2** — header pin 2 → 1N5817 → VSYS, USB cable left in for the console — it went
     **100 s → 135 s** across a reboot and **190 s → 295 s** across a shutdown: the Pico never reset.
     So form 2 is the arrangement, the diode is the right way round, "the Pico stays up" holds for
     the relay rule above, and the header's second 5 V consumer should take **pin 4**, leaving pin 2
     to the codec's VIN alone. Method and evidence: `scripts/pico-power-test`,
     [bench-results/2026-10-05-pico-power-test.md](bench-results/2026-10-05-pico-power-test.md).
     Power the Pico each way with its LED blinking, then `sudo reboot` vip, and separately shut
     it down. Watch whether the Pico restarts. Keep the first way that holds through both; if
     neither does, the Pico restarting with vip is still safe (the relay drops to bypass), but
     the relay rule above loses its "Pico stays up" case. Record the result here and in the BOM.
   - Check for a pop at **power-off**. The relay drops to bypass within a few ms, but the codec's
     output collapses at the same moment, and which wins decides whether it's audible. If it is: the
     Pico watches its supply and drops the relay a little before the codec loses power.
   - The output coupling cap must settle before the relay first engages. 10 µF into ~1 MΩ is
     τ ≈ 10 s, inside the boot; 100 µF (τ ≈ 100 s) would still be charging and pop.
7. **Display and encoder**, low priority per `about.md`. *Superseded by D14 (2026-10-09): the
   screen is the Core host's, shown by rigpa; only the encoder and buttons stay here, as rigpa's
   main rotary, apply and back (rigpa plan H1).* Check it has no onboard LDO before
   powering it (per `CLAUDE.md`). It picks up a job with Phase 5 (D12): the pairing out-of-band
   code, and on the same screen the QR that gets the Mac onto the pedal's network.
8. **Rigs ready for switching** (D10; namchain's M3). Required before 3.5: without it a footswitch
   press stalls on the SD card, JSON parsing and prewarm, and then clicks.
   - The **ready set**: the current bank (4–8 rigs) plus any rig MIDI can jump to. Each one held
     as a compiled plan with its models loaded and prewarmed and its IRs prepared. Changing bank
     refills the set in the background, off the render core.
   - A switch is a crossfade (namchain's equal-power fade) from the running plan to a ready one:
     **≤ 50 ms** from the event to the new sound, with nothing allocated, loaded or parsed on
     the render thread.
   - The pedal service owns the set (it knows the bank and the MIDI map); namchain provides
     "hold these ready" and "switch to this one" as protocol calls. That split goes in 3.2.
   - How each rig is kept ready is its **tier** (proposed 2026-09-26, detail and worked numbers in
     [docs/rig-switch-strategies.md](docs/rig-switch-strategies.md)):
     - **0, toggles in the live rig:** every instance runs, bypassed or not, so a toggle is only
       a crossfade. The rig's all-on budget is reserved anyway.
     - **1, one-press candidates** (footswitch neighbours, the assignable target): Full always
       warm, IRs kept as a record of their input. ~11 ms, exact.
     - **2, the rest of the bank and MIDI jumps:** a Lite copy always warm takes over at once;
       Full catches up in the background and takes over with a 5 ms crossfade.
     - **3, anything else** (ljoss): loaded in RAM; Lite catch-up at the switch, then Full as in
       tier 2.

     Anything not warm is caught up, never started from silence (E1). Requests don't queue: one
     switch is in flight, and a newer request replaces the pending one. The service drops
     candidates a tier when the budget is full, and refuses a rig that can't run all-on (M2).
   - E1 and E2, below, decide whether the tiers hold.

   **E1 — always-warm candidates: an experiment before deciding.** The question is whether every
   rig in the ready set can be kept *running* on the live input all the time, so a switch is only
   a crossfade between two models that are both already in the right state. That's the smallest
   switch time possible, with no catch-up step at all. It may turn out impractical; measure first.

   Arms, each on piv (then vip) with the same A2-Full + cab rigs:
   - **A. Cold** (today): `rig.apply` loads, parses and prewarms. The 1.7 baseline.
   - **B. Warm, silent state:** models loaded and prewarmed with NAM's own prewarm (it runs the
     net on zeros and caches that state, so re-prewarm is a memcpy), idle until needed. The switch
     crossfades from a model that has only heard silence.
   - **C. Warm, caught up** (namchain M3's design, its §7.4): as B, then just before the switch a
     warm worker off the render core replays the last ~132 ms of real input (A2's receptive
     field) into the candidate, so its state matches what's being played.
   - **D. Always warm:** every candidate in the ready set processes the live input continuously,
     output discarded, on core 2 (piv and vip isolate 2 and 3; 3 renders). Switching is a crossfade
     between two running models.

   Measure, per arm and for ready sets of 1, 2, 4 and 8 rigs:
   - switch latency, event to new sound, from the captured output
   - clicks: the glitch detector, plus a null against an always-on reference model (how far B's
     and C's state is from D's, over the first 132 ms after the switch)
   - **the render core's tail** with the other work running beside it: p99 and max on core 3,
     overruns. The risk in D is not core 2's own load (a Full model is ~0.11 of a core on vip at
     the fit point, so 8 fit in about 90%) but contention for the shared L3 cache and memory
     bandwidth, which isolation can't partition. namchain has measured that kind of interference
     on piv: with memory pressure on the housekeeping cores the render p99 went from 8% to 37%
     and the worst block from 23% to 52% (`bench-results/2026-10-02-multi-core-piv.md`,
     "Interference on the housekeeping cores").
   - core 2's load, memory (vip has 1 GB), temperature and throttling over an hour.

   Build it as a bench tool first, not an engine feature: `namchain-soak` rendering on core 3,
   with a second RT thread on core 2 running N candidate models on the same input. Decide from
   the results: D if the render tail and memory hold with a full bank, otherwise C, with B as the
   floor. D also depends on namchain rendering on two threads, which is its M4 (parallel
   rendering, off by default), so D's result is also the case for or against admitting M4.

   **E1 results, piv, 2026-09-26** (namchain `bench-results/e1-warm-candidates-piv.txt`, tool
   `tools/warm/namchain-warm-bench`). A rig is a library A2 model + an 8192-tap cab; q64.
   - **B (silent prewarm) is the wrong sound for 170–340 ms** after every switch (0/44 pass the
     glitch detector's convergence rule; no clicks, but up to +15 dBFS from the right output). The
     cold path A does the same today.
   - **C (catch-up)** with 170 ms of replay: 39/44 pass, −51 to −68 dBFS. With **340 ms** of replay:
     −114 dBFS, all pass; the replay costs **27 ms**, so ~38 ms to the jack. These models remember
     longer than their nominal receptive field.
   - **D (always warm)** is identical by construction, and costs the render core almost nothing:
     0 overruns in every run, p99 14.7% → 16.7% of the deadline with 5 candidates warm for 10
     minutes, 17.4% with 8. Core 2 is the limit: **5 candidates fit one core** with its p99 under a
     quantum (97%); 6–8 keep up on average but run a block or two late at the tail. ~2 MB each.
     Switch ~11 ms to the jack.
   - piv stayed at 36–41 °C, never throttled. vip is the same SoC; its cooling needs checking.

   **What E1 led to:** the tiers above. D becomes tier 1, for a few rigs only. C becomes the
   catch-up in tiers 2 and 3, with Lite first. B is never used. The cold path (`rig.apply` of a
   new document) should catch up as well, since today it has B's problem. D needs namchain to run
   candidates on a second thread (its M4), and E1 argues for admitting that.

   **E2 — before building the tiers** (2026-09-26; the reasoning is in
   `docs/rig-switch-strategies.md`). E1 measured one model plus an IR. The tiers rest on four
   things it didn't measure:
   1. **Lite against Full** for every library model: the null level between them, and whether a
      5 ms crossfade either way can be heard (listening plus the glitch detector). Lite and Full
      are separate submodels in each `SlimmableContainer`, so the handover is a small change of
      sound. If it can be heard, tier 2 becomes tier 1 or catch-up.
   2. **Catch-up for chains** of 1–4 models in series, against replay lengths of 85, 170, 340 and
      680 ms per model. Does depth d need d × 340 ms, which makes the work grow as d(d+1)/2? And is
      an error of −60 dB as good as −114 dB to the ear?
   3. **Warm density without IRs:** how many Full and how many Lite models keep up on one core,
      and on a housekeeping core under load (warm work only needs to keep up on average). Measure
      the render core's tail beside them. The estimate is ~10 Full or ~50 Lite per core.
   4. **IRs as input records:** fill a convolver from recorded input and check it matches one
      that ran all along.

   Extend `namchain-warm-bench` for these rather than build engine features. Then decide the
   tiers, and the limits the pedal service enforces.

   **E2 results, 2026-10-06** (namchain `083de32`, which is the bench with these four modes; the
   evidence files are `e2-lite-vs-full.txt`, `e2-chains-and-irs.txt` and `e2-warm-density-vip.txt`
   in its `bench-results/`, or read them with the whole reading in
   [bench-results/2026-10-06-e2-tiers.md](bench-results/2026-10-06-e2-tiers.md)). Input: a guitar DI
   recorded for this, [guitar-di.wav](guitar-di.wav), 48 kHz mono 24-bit, 56.66 s — its level was
   checked not to matter (trimming it 22.7 dB moved the relative null by 1.4 dB).
   1. **Lite against Full: the premise is false.** All 52 library models, both submodels, compared
      sample by sample: they are level-matched (median 0.09 dB) and time-aligned (lag 0, within a
      sample), and 9 to 40 dB apart (median 21.7 dB below the signal, worst the Ampeg SVT VR 8x10
      Beta52A+DI at 9.2). They are **two separately trained networks**, not one at two widths: the
      worst model shares 56 of the Lite's 1871 weights with its Full, the vendored `A2.nam` 4. Its
      "small change of sound" is wrong on every model in the library. **The crossfade does not
      click** — 102 of 104 model-directions were clean at all 11 switch points, and the two that
      were not are 20–40% over the second-difference bar in the DI's decaying tail — **but it
      thumped**: the fade was equal-power, which for correlated signals (Lite and Full are ρ 0.97 to
      1.00) adds `2ρg₁g₂` at the midpoint, measured at +2.6 to +3.0 dB on every one of the 104 rows
      and heard as a short thud. No glitch rule can see a level bump: it is continuous, is not a
      dropout, adds no out-of-band energy and converges. Compensating the weights for the
      correlation (`sqrt(1+2ρg₁g₂)`, ρ clamped to [0,1]) takes all 104 rows to 0.00 dB and clears
      the two findings as well — namchain `bench-results/e2-fade-thump.txt`. **The engine's fade is
      fixed the same way** (2026-10-07): `rt::Crossfade` measures ρ from the first block it is handed
      and normalises the weights as it reads them, measured through the class, through `nc.xfade` and
      through a plan-level transition at **+3.0 dB before and 0.00 after**. It also turned up a
      second defect — `prewarm` ran a silent block through `nc.xfade` despite its `skip_prewarm`, so
      every local transition was 3.7 ms of crossfade where 5 ms was asked for — and that is fixed
      too, with tests for both. So tier 2's
      "a Lite takes over at once" plays a different-sounding rig for the catch-up, and the branch
      above applies: it needs a listening test, and the files are made by
      [bench-results/2026-10-06-e2-listening](bench-results/2026-10-06-e2-listening/README.md).
   2. **Chains need 170 ms per model, not 340.** Four different models in series: 170 ms of replay
      per model is **bit-identical** to the chain that ran all along at depths 1–4; 85 ms is enough
      at depth 1–2 and fails at 3–4 (−50.1, −57.8 dBFS). The work is `d(d+1)/2` single-model
      replays, confirmed by the cost on vip: 9.8, 29.4, 58.8 and 98.2 ms at depths 1–4. E1's 340 ms
      is also explained — a series chain's memory is the **sum** of its stages' (6347 samples for
      the model + 8192 for the cab = 303 ms), and the bench's default replay was `max()` of the two.
   3. **8 Full or 30 Lite per core, not ~10 and ~50.** On vip, p99 of the warm thread under one
      quantum (E1's bar): 8 Full is 89.1%, 10 is 112.9%; 30 Lite is 97.4%, 40 is 141.2%. The cost of
      the *audio* is small — the render core's p99 goes 8.08% → 10.60% with 8 Full warm, no overruns
      — and a lower-priority spinner saturating the warm core changes nothing measurable (89.1 →
      94.3%), which is also the "under load" case. The estimates were optimistic because the same
      cache crowding the two-amp result found is here: the first Full costs 6.6% of a quantum and
      the eighth 11.1%.
   4. **An IR as a record works.** Reset the convolver at the switch and fill it from the last 8192
      samples of the model's output: **−138.5 dBFS** worst (float rounding in the partitioned FFT),
      for **1.26 ms** on vip. It only applies to rigs with a separate cab (35 of the 52 models carry
      their own), and it is an optimisation rather than a requirement.

   **What that leaves the decision:** tier 1 (Full warm, exact) at 8 models per warm core, tier 2
   (Lite warm) at 30, tier 3 unchanged with a Lite-first catch-up about a third of the Full cost.
   That supports what `docs/rig-switch-strategies.md` already sketches — tier 1 for the one-press
   candidates, tier 2 for the rest of an 8-rig bank — **if** the Lite standing in is acceptable.
   If it is not, the bank is tier 1 and 8 models per core is the ceiling. The one measurement left
   is the listening test in item 1.

**Done when:**
- With no app, the footswitches and the MIDI Commander step through rigs stored on the pedal.
- Changes are click-free, and each takes ≤ 50 ms (D10), through an hour's switching soak.
- The relay covers boot and failure.

## Phase 4 — Enclosure, power and hardening

**2026-10-04: the rear wall is being trialled in a plastic stand-in.** A temporary plastic box
carries IN, OUT L and OUT R in the Neutrik jacks in exactly the arrangement this phase plans for the
aluminium case, and vip's USB-C lead passes through a hole in that wall straight into the Pi's port
(the panel-mount extension is still to buy). It plays
([bench-results/2026-10-04-the-pedal-plays-in-a-case.md](bench-results/2026-10-04-the-pedal-plays-in-a-case.md)),
which is the first hardware check the enclosure model has had: `enclosure/README.md` used to say
none of its layout had been near hardware. The cut positions the plastic box ended up with are worth
recording before the aluminium one is drilled.

- **Panel:**
  - the display module's fixed screen/knob/button unit
  - three footswitches
  - IN, OUT L, OUT R
  - MIDI DIN, 9 V, 5 V
  - a reserved mic position (D5)
  - the expression jack only if the debt entry below says so.
- **Power** (decided 2026-10-01; parts in `docs/bom.md`):
  - **5 V:** the Raspberry Pi 45 W USB-C supply into a USB-C panel-mount extension on the rear
    panel, plugged into vip's own USB-C port. vip negotiates 5.1 V at 5 A and keeps its input
    protection. Rejected: a bare USB-C socket wired to vip's header pins. It can only get 3 A, and
    it bypasses vip's protection.
  - **The layout must make room for the plug.** In today's model, vip's USB-C port is about 2 mm
    from the front wall, and a right-angle plug needs about 8–10 mm. The likely fix: replace the
    Dupont leads on vip's header with a 40-way ribbon to board A. The ribbon is low enough for the
    header to sit under the display, so vip can move back 10–15 mm. Check the footswitch bodies
    and the ribbon's fold in the model.
  - **The Pico** takes its 5 V from vip, as 3.6's reboot test decides.
  - **9 V** isolated for the analogue side, and the star ground.
  - **Proposal (open, 2026-10-02): collapse to a single USB-C input.** The 5 V side is already a
    USB-C extension into vip's own port; the open question is only the analogue rail. Recommended
    route: a small **isolated DC-DC converter** (5 V → 9 V, ~1 W, galvanically isolated —
    RECOM/Traco/Murata class) fed from vip's 5 V header, then a common-mode filter and an LDO, then
    the existing 78L33 for AVDD. The converter's isolation keeps the analogue ground separate from
    vip's, meeting only at the star point, so the analogue supply still never carries vip's current;
    the LDO and choke make the rail quiet. This drops the 9 V barrel and its cut-out, removes the
    Cioks from the pedal's dependencies, and adds one converter module on the power stripboard. The
    buffer's 9 V is headroom, not a requirement — a 5 V buffer is possible but tightens the margin —
    so 9 V stays. It must be measured for hum/noise against the Cioks-fed LDO before it is decided.
    Rejected: two Li-ion cells (one powering the analogue side while the other charges, switched by
    a relay) — a cell is 2.5–4.2 V, so a boost converter beside the input stage is unavoidable, and
    the charge controllers reintroduce the switching noise the scheme exists to avoid. If it
    goes ahead, the converter is a switcher inside the box and needs the display's treatment:
    the choke and LDO handle the conducted noise (the part that reaches the audio), and
    distance/orientation — plus a steel screen only if it ends up near the 1 MΩ input — handle
    the radiated noise; the handoff records the split.
  - **Battery option (2026-10-02): a 9 V battery as an alternative to the 9 V barrel.** A
    **switched** 2.1 mm DC socket disconnects the battery when the barrel is plugged, so the barrel
    takes precedence and can never back-feed or charge the battery — which is what makes every
    chemistry safe, including a lithium primary. Battery + through a 1N5817 to the 9 V rail, battery
    − through the socket's switch to the star ground; the barrel keeps its own 1N5817. The enclosure
    must leave room for a PP3 (≈48.5 × 26.5 × 17.5 mm) and its snap, reachable for replacement. A
    680 kΩ + 330 kΩ divider (both in hand) from the 9 V rail to a Pico ADC gives a battery meter on
    the display and, over a new UART message, in the pedal service's API; it shows voltage plus a
    coarse threshold, not a percentage (the chemistries' discharge curves differ). Detail and the
    chemistry/safety notes: the handoff's Power section.
- **Mounting, and the case kept out of the ground scheme** (decided 2026-10-01):
  - A 3 mm FR4 plate, cut to the inside of the box, is screwed to the base plate. vip and both
    stripboards stand on **nylon** standoffs on the plate, held by nylon screws (countersunk from
    under the plate). vip's mounting holes are grounded, and the star tag sits under a board
    screw, so metal standoffs would join the grounds to the case and make a loop through it.
  - The electronics come away with the base plate when the box opens. Leave enough slack in every
    wire to the shell's connectors and controls to fold the base out beside the box.
  - **Open: should the case be grounded?** Measure hum with the case floating, and bonded to the
    star at that one point only, then keep the quieter.
  - The plate costs 3 mm of height and removes the metal path for heat into the base. The heat
    soak below covers that.
- **Survive pulled power.** A read-only root (overlayroot) plus a small data partition for rigs and
  models, written atomically. A pedal gets unplugged mid-write, and today one SD card holds
  everything.
- **Heat in the box.** An hour's soak inside the closed enclosure, recording temperatures. On a bare
  board it is a non-event: 1, 2 and 3 render cores peak at 40.8 °C, the same as a three-core
  `stress-ng` reference (`bench-results/2026-10-02-multi-core-piv.md`, "The thermal soak"), and the
  pedal's own hour through the codec ran at 53.8–58.2 °C, never throttled
  (`bench-results/2026-10-08-cost-table-vip/README.md`, T10). None of it has been measured inside an
  enclosure, which is what this is for.
- **Boot time**, if 1.7 shows the relay isn't enough on its own.

## Phase 5 — The pedal's own network: pairing and the app's way in

Designed 2026-10-01: [docs/pairing.md](docs/pairing.md). The pedal advertises itself over BLE; ljoss
pairs with it through the system's accessory sheet (AccessorySetupKit, iOS 18+), receives the pedal's
network and its `namchaind` token over a bonded BLE link, and joins the pedal's own Wi-Fi with
`NEHotspotConfigurationManager.joinAccessoryHotspot`. No house network, no typed address, no pasted
token, and the second visit asks nothing. It pays off the debt register's "the app needs the home
network", and it closes "no discovery: the host is typed in" with the same change.

It does not depend on 3.5–3.8: the Pico work is BLE, a gesture and (later) the display, none of it on
the audio path, and the Core host work is `devices/` and the service. It is aimed at vip, the Core
host since 2026-09-30, and it touches nothing on the render path.

**Decided 2026-10-01** (the doc has the detail): the Core host runs the access point and the Pico does
BLE; the first pairing's out-of-band code rides on 3.7's display, so 3.7 now carries a security job
as well. The rest of the design's decisions are proposals at the end of the doc. **Plan only for now:**
the stages below wait for your go-ahead.

Steps (each committed on its own, spikes first — the Apple half is the one part of this pedal that
cannot be tested from a shell, and the design turns on what the spikes find):

0. **Spikes, evidence in `bench-results/pairing/`.**
   - **The Core host as an access point.** `hostapd`, a static address and a DHCP server on `wlan0`,
     a Mac and a phone join, `namchaind` answers over it. Measure boot-to-AP-up, and an hour of
     playing while ljoss edits over it against plan 1.8's gates. It decides the channel, the address
     range and the AP's real cost.
   - **The Pico as an AccessorySetupKit-shaped peripheral.** Advertise the service UUID and name,
     bond (LE Secure Connections, Just Works), read a protected characteristic — from the Mac with a
     `bleak` script in `firmware/tools/`, as `ble_wifi_provisioner` does. The Bluetooth address must
     be the same across reboots, reflashes and a flash wipe, or it is set from the board's unique id.
   - **The Apple half, on a real phone.** The sheet shows the pedal's picture and name; the tap
     pairs; `joinAccessoryHotspot` joins the AP. Settles `ssidPrefix` against
     `finishAuthorization(settings.ssid)`, the `setupOptions`, `joinOnce`'s 15-second rule and the
     entitlement. **If the join cannot be made to work, the design changes here**, to the QR path.
   - **The bench loop.** The Mac on the pedal's AP runs `scripts/status` and `sync-library`, and an
     upload is timed.
1. **The pedal's network** (`devices/`, `pedald`): `pedal-ap` writes `hostapd.conf` from
   `/var/lib/pedal/state/net.json`, `wlan0` gets the address and the DHCP server, the name resolves
   over mDNS, the station path leaves the pedal root (the rescue root keeps it), and the image stops
   writing the house Wi-Fi secret into the pedal root. The Pico's record and the Core host's cache
   merge by generation, per `docs/uart-protocol.md` draft 3.
2. **The Pico's record and setup mode** (`firmware/`): the record (passphrase, SSID suffix,
   generation) and the bond store in flash, setup mode and its window, the protected characteristic
   and the bundle, the forget gesture, and `PROV`/`PAIR`.
3. **ljoss pairs** (ljoss): the plist keys and the capability, the ASK session, the picker image from
   `enclosure/renders/`, the bundle over CoreBluetooth, the join, the keychain record, the Hardware
   page's pedal section, and the re-join on returning to the foreground. The Mac keeps the manual
   path.
4. **Lifecycle** (with 3.7's display when it exists): remove and rotate on both sides, a second
   phone, the pedal's own forget gesture, and `backup` covering the cache. The out-of-band code is
   decided, so this is where 3.7 earns its place: the pedal shows a code and the app offers it back
   before the pedal releases the bundle, with the QR for the Mac and as the fallback.
5. **Soak it** as the doc stages it, with a rotation and a power cut in the middle.

**Done when:**
- A pedal and a phone that have never met pair with the system sheet and no typing.
- The pedal plays from power-on with no house network anywhere.
- ljoss edits it over the pedal's own network, and an hour of it is clean.

## Tracks off the critical path

- namchain M2: admission control. (M3, warm start, is on the critical path now: D10 and 3.8.)
- **Rig switch prediction** (2026-10-07). Which rigs are kept warm is chosen today from what the
  player can reach in one action: the footswitch neighbours, the current bank, anything MIDI can map
  to (D10; [docs/managing-processing-power-and-optimising-for-fast-switching.md](docs/managing-processing-power-and-optimising-for-fast-switching.md) D4). That is a *guess* about what
  comes next, and for a pointer it is barely a guess at all: ljoss puts several rigs on screen at
  once and a click or tap is exactly as likely as a footswitch press. Getting cleverer — what the
  list is showing, where the pointer or the eye is, what was played last, the set list — would let
  the warm set follow the player instead of guessing. **Explicitly after THE PEDAL is gig-ready, and
  not a dependency of it**: the `predict` node in
  [docs/diagrams/plan-dependency-graph.html](docs/diagrams/plan-dependency-graph.html), which the goal
  gate points to. It would change *which* rigs are warm, not how warmth works — the cost model, the
  packing and the catch-up path are the same either way.
- DSP when you want it: noise gate, tuner, reverb, compressor, modulation.
- ljoss on iOS: it compiles, but the touch path has never been run.

---

## Debt register

These are restrictions accepted now, with a sketch of how each gets paid off later. You asked for
exactly this: think about them now, fix them after the higher-priority work.

| Restriction | Why it's accepted now | How to pay it off later |
|---|---|---|
| MIDI is DIN only: USB-only controllers won't connect, and the MIDI Commander needs its own power | Simplest, isolated | USB host on the Pico through PIO-USB: two GPIO plus a USB-A socket, which is essentially what the RP2350-USB-A does. The event layer stays transport-agnostic, so this is a firmware change |
| The RP2350-USB-A has 15 GPIO, and the design needs about 18 (display 5–6, encoder and button 4, footswitches 3, UART 2, MIDI 1, relay 1, LEDs 1+, expression 1) | A Pico 2 has 26 | Pico 2 for the control surface, RP2350-USB-A for experiments. If pins run short: footswitches on a resistor ladder into one ADC, WS2812 LEDs on one pin, or an MCP23017 on the Pico's own I2C bus (never the Core host's) |
| The pedal plans its own expression jack, but the MIDI Commander already has two expression inputs | — | Decide whether the pedal needs its own. If not, drop the jack and its GPIO, since MIDI already carries expression |
| Only program and control changes get mapped at first | Enough to change rigs | A mapping table in the pedal service: PC → rig, CC → parameter (streamed only when `engine.schema` marks it rampable), bank select, notes |
| Mono engine: pan and stereo effects are refused. Two chains give dual mono | namchain decision: declare and refuse | namchain's stereo work, when a stereo effect is actually wanted. The outputs are already two channels |
| Two power inputs: 5 V USB-C for vip and a separate 9 V for the analogue side (Cioks), so the pedal depends on a multi-outlet PSU and has two panel cut-outs | Decided 2026-10-01 and measured on the bench; the single-cable route needs an isolated converter that must be measured before it is trusted | Collapse to one USB-C input: an isolated DC-DC (5 V → 9 V) + LDO off vip's 5 V header for the analogue rail. The two-battery alternative is rejected — see Phase 4 Power |
| The whole rig renders on one core (core 3), and A2-Full alone takes ~11% of it at the fit point | **Deliberate since 2026-10-07, not just where we are**: a rig is atomic and the other real-time cores exist to keep rigs warm, because switching latency is what the pedal is for. Spending a second core on one rig would cost the warmth that makes a switch instant (D1–D4, [docs/managing-processing-power-and-optimising-for-fast-switching.md](docs/managing-processing-power-and-optimising-for-fast-switching.md)) | A rig too big for one core is trimmed to Lite or refused — the cost model's job (D2, D3, D6). namchain's parallel rendering (M4) stays in the engine, off and unused by the policy; the heaviest rig measured is a single chain it could not help anyway |
| No resampler for models: a NAM model must already be at 48 kHz | IRs no longer need one: `nc.cab.ir` resamples 44.1 and 96 kHz (Phase 1.2) | Resample at load in namchain, or convert on upload in the pedal service. Until then its upload API refuses a model that declares another rate (`docs/pedal-service.md`) |
| One instrument input | D5 | A mic stage on RINPUT1, and a decision on phantom power (a DC-DC converter beside the ADC) |
| WM8960 claims the Pi's I2S | On a Pi 5 the firmware exposes no HDMI audio (`dtparam=audio` is ignored; `docs/vip-image.md`), so nothing else wants that bus | None needed. A second codec would mean TDM or USB |
| No way to upload from the app yet | D4 | The pedal service's upload API. ljoss gets a "send to pedal" action. Designed 2026-09-28: `docs/pedal-service.md`, its v3, which has no plan step yet. `sync-library` moves onto the API then: its `rsync --delete` would remove uploads |
| The app needs the home network | Phase 1 happens at home | The pedal as its own access point (Phase 5, [docs/pairing.md](docs/pairing.md)): the Core host runs it, the Pico does BLE, and ljoss joins with `NEHotspotConfigurationManager.joinAccessoryHotspot`. The Mac keeps the typed address and token |
| No discovery: the host is typed in | — | mDNS from the pedal service; and for ljoss the provisioning bundle hands it the address, the port and the token (Phase 5) |
| Plain-text token, no TLS | Trusted LAN | A tunnel, or TLS in the service, if it ever leaves the LAN |
| Everything lives on one SD card | — | Overlayroot plus a data partition (Phase 4) |
| An I2S fault can silence the pedal with no error. On piv (2026-09-27) BCLK was pulled and refitted while `namchaind` ran: it kept reporting `running`/`ok` with 0 xruns, but nothing came out, most likely a lost frame alignment that put the rig on the unconnected channel. Restarting `namchaind` fixed it | The build solders its connections; on the bench, restart `namchaind` after touching the header | A liveness check in namchain or the pedal service: flag an input that has been digitally silent (or DC, or stuck) for a few seconds while the device is running, and reopen the device. Possibly check that the codec's clock rate matches what the Pi receives. The Pico could show it and hold bypass |
| `nc.cab.ir` is back on the core's `nam::Linear` (2026-09-26): every partition multiply lands in one callback. On piv that's p99 15% for A2 + cab at q64; on vip an 8192-tap cab is 0.0222 of a core at its fit point, a fifth of a Full model (`devices/vip/cost.json`) | You deprecated the AudioDSPTools fork that spread the work | Spread the multiplies inside namchain, or upstream a partitioned convolver to the NAM core or sdatkinson/AudioDSPTools. Needed for q32, or if vip's soak shows the tail is too close at q64 |

## Open questions

These don't block Phase 0 or 1.

- **Pedal service:** beside `namchaind` (the app keeps its direct connection) or in front of it
  (one endpoint and one token for the app, one extra hop for knob streams)? Decided in 3.2:
  beside ([docs/pedal-service.md](docs/pedal-service.md)).
- **Where data lives on the Core host:** namchain's default is `/etc/namchain`, and the library
  landed at `/var/lib/pedal/library` (Phase 1.4). `/var/lib/...` is the more conventional place for
  user data; the final answer comes with the overlayroot design.
- **Rig designers for other platforms** (`about.md`): the engine protocol is where any second
  client would plug in, and `namchainctl` is its reference client. A browser UI served by the pedal
  service would reach every device with nothing to install. Worth weighing before a Qt designer.
  Not before the pedal plays.

## Shopping

Every part, with its CPC order code, price and purpose, is in [docs/bom.md](docs/bom.md).

- **Ordered from CPC (41 lines, £117.19 ex VAT). As of 2026-09-30 everything has arrived except the
  OPA2197:**
  - 2 × Pico 2 WH and the Debug Probe
  - two breadboards (one a spare) and header strips. You already have jumper leads, including the
    female-to-female ones for the WM8960 bring-up.
  - five Neutrik NMJ6HF-S switched TRS jacks: IN, OUT L, OUT R, expression, and a spare
  - the MIDI-in parts. The BOM gives the circuit and its values.
  - everything else that doesn't wait on a decision: the output stage (which 2a's measurements
    need too), power, the relay and its driver, footswitches, LEDs, sockets and stripboard
  - the op-amp: 2 × OPA2197 on SOIC-to-DIP adapters. **Not arrived:** back-ordered until 4 Oct,
    and CPC is sending it separately. The adapters and sockets are here, so everything around it
    can be built first.
  - the Inst/Line switch and the Line pad's resistors, at provisional values; screened cable and
    hook-up wire.
- **To buy** (decided 2026-10-01, Phase 4): the USB-C panel extension, the Pico's USB cable,
  the FR4 mounting plate and nylon standoffs. See the BOM.
- **Not designed yet:** the mic stage, cooling and the panel hardware.

## Next session starts with

**The core rules changed, P6 is on the pedal, and the hour is running** (2026-10-09). The owner
amended the rules: **all but one core renders**, the non-render core carries everything *except*
interrupts, the audio interrupt is **delivered to a render core**, and that core is **never the
active one**. vip's tree had drifted from that since 2026-09-29 (two housekeeping cores, 0–1, copied
from piv), which is what P7 had read D5 through. vip now isolates 1–3, keeps one housekeeping core
(0), sends every interrupt there, and has the audio IRQ delivered to core 1; `pedal-tune check`
asserts the four rules, and **`vip-boot set-args`** is new — it rewrites every slot's tuned command
line from `device.env` on a board that is already up (`--restore` puts the old line back), where this
used to need a whole staged kernel. Evidence:
[bench-results/2026-10-09-core-rules-vip](bench-results/2026-10-09-core-rules-vip/README.md) —
including T6's two arms, which came out identical (IRQ on core 1 or core 0: 16.8 ns against 17.0 ns
per wake, same render distribution, zero xruns either way), so the reversal rests on the rules and on
where the preemption lands, not on T6.

**P6 (namchain M3) is implemented, tested and live**: per-document render state, a warm document
rendering on an inactive core at priority 70, and a switch that hands it to the device thread
(`namchain/docs/warm-set.md` is the engine's design; the pedal sets `warm_cpus [1, 2]`). Eight live
switches on the pedal: `handover_blocks: 3` plus a 5 ms fade (~9 ms) each, **0 xruns, 0 blocks over
the deadline, 0 dropped warm blocks**, warm lag 0–1 block while sharing core 1 with the interrupt.
What the service half added (`24349e7`, verified live): `pedald` holds the rig the footswitches reach
next warm — `rig.warm` when the neighbour changes, `rig.switch` on every press, with a cold publish
as the fallback — so the engine is no longer waiting for a caller.

**What landed since, 2026-10-09 evening.** **T5 ran and found more than it was pointed at**: a warm
document costs the rig the player is hearing, and the cost table did not model it at all (a 0.735 rig
holds the deadline alone, misses it 61 times in two minutes with one neighbour and 3,543 times with
two). **D3 now charges the coexistence** — `coexistence.factors` in the device's own table, 1.25 for
one warm document and 1.4 for two, derived from the measured knees — with a **failsafe** behind it
(the engine cools the warm set when a window of the render load's histogram has any block over the
deadline or a hundredth past nine tenths of it, and refuses a new warm for ten seconds:
`warm_pressure`, `pressure_cools`). **T7's service half passed**: a new `POST /event` in pedald takes
the Pico's own vocabulary over HTTP, and eight presses through it were **8/8 handovers**, 0 xruns,
with the warm set sliding to the new neighbour. **T8's storm passed while paced** (60/60 at 2/s,
59/59 at ~3/s) and broke only under *bursts* of ten concurrent presses, during which the board
**rebooted** — cause unknown; the journal is persistent on vip now so the next one is diagnosable, and
the lead is the 5 V rail. The bench's switch arm was fixed (four harness bugs of its own) and its
cross-rig verdict closed as **UNPROVEN with the reasons measured**: on one rig against itself the
handover is an *exact* match (−1000 dBFS). **E2's listening verdict arrived** — the owner cannot hear
a Lite standing in for a Full — so **P8's design is settled** in the document (Lite first, Full behind
it, 170 ms per model replayed, compensated crossfade), D6's teeth are visibility rather than sound,
and the pedal decided **what it warms**: one rig, the one a press reaches, with the engine's charge
deciding whether it fits and `/status` reporting the decision (`warm_decision`).

**T9 ran through the pedal, and the replay behind the Lite never ran (2026-10-10).** The board is on
**`894b67c`** (deployed; 5/5 ctest and `unit` 372/372 in the board's own container build; the cost
table names it with the reason in `bar`, applied, `devices/vip/check` green). T9's numbers, three runs
an arm with the warm set verified empty at each press: **the Lite is audible 41 ms after the press**
(the one-step publish it replaces was 32 ms on this small rig) **and the Full 320 ms after it**, with
`lite.adopted` true, `cost.lite_first` set while the Lite stands in, `catch_up.full` reaching
`published` every time, and 0 xruns / 0 blocks over the deadline throughout. A press through pedald's
`POST /event` is **108–110 ms**, of which ~100 ms is the service's own HTTP round trip — and it is a
*handover* in a two-rig bank, because the service holds the neighbour warm, so the cold path a
footswitch takes is the one the engine arm measures. **The defect: in all three two-step runs
`catch_up.state` is `exact` with a 14,539-frame window and the catch-up runs for ~270 ms, then ends
`catch_up.replay: no_input` and `catch_up.blocks: 0`** — no input was ever replayed, so the Full is
crossfaded in cold. The engine's own tests reach `exact` on the test backend, so it is board-specific
and it is **the engine's to find**: the history ring on the render path is the suspect and its
counters are not in `engine.status`. The refusal path is confirmed on the pedal (a chain with a
slimmable model and the LSTM refuses with `unbounded`, `frames: 0`, `detail` naming `amp1`, and still
publishes the Full). Evidence: `bench-results/2026-10-10-t9-lite-first/`. The pedal was put back —
`last.json` playing, pedald and namchaind active, library holding only the two resume files. **Owed
next: the replay defect** (engine), then T9's physical press at the jack (3.8's), a heavier Full, and
the literal first-press-after-boot with a cold card.

**Found while measuring T11 (2026-10-10): the bank is empty, so nothing is warm and a press does
nothing.** The engine holds only the audible document, pedald's `warm_decision` says `idle` with
`wanted: null`, and `/status` shows `bank: {"banks": [[]], "size": 0, "current": null}` — while the
library holds the rigs and pedald has *costed* them (its verdicts name them). Banks are explicit and
there is no endpoint that sets one (`docs/pedal-service.md`: "banks and the map have no endpoint yet"),
so a pedal that has just been synced with a library warms nothing and its footswitches have nothing to
step to. That is why both T11 halves ran with cpu1 idle, and it is a blocker for 3.8 rather than a
measurement detail. The sensible default is the one to argue about first: **a service with a library
and no bank has one bank, and it is the library** (D10's "the rigs the footswitches reach next"), set
by the service when it finds no bank, with the app's own banks taking precedence once the API exists.

**State of T11's warm-document half (2026-10-10).** The hour itself is measured and passes (both
halves: no block over the deadline, 0 xruns, worst 90.5% and 85.3%, 80.4 °C, 2400 MHz, low-voltage
alarm 0 — T11's block in the document has it). What no run has had yet is a warm document rendering
(cpu1 0.7% throughout), and both causes are now fixed in the tree: the bank was empty (`mapping.py`
drops empty banks and falls back to the library — **applied to the board**), and the failsafe fired on
blocks *near* the deadline rather than over it, cooling the document every ten seconds (namchain
`ee4c53d` — **not yet deployed**). To finish T11: deploy `ee4c53d`, run
`scripts/measure-housekeeping --seconds 1800 --target 0.60 --extra renderer --skip-quiet`, and expect
cpu1 busy. Evidence: `bench-results/2026-10-11-t11-warm/`.

**P4's verification needs a model the table has no row for, and the library has none** (checked
2026-10-10: eight models from eight directories, each costed through a rig built from `last.json`, all
`unmeasured: none` and all at the same cost — the library is one family the table covers). So the
verification has to *bring* the gap, and the file to bring is already in the engine's own tree:
**`namchain/vendor/NeuralAmpModelerCore/example_models/lstm.nam`** — an LSTM, a family vip's table has
no row for (its two NAM rows are WaveNet full/lite). **Its trigger half is verified** (2026-10-10): copied in, built into a rig and
loaded, that LSTM made the engine report `cost_unknown` and pedald report
`needs_measuring: [{"row": "unknown.NAM", "count": 1, "reference": ".../t5-lstm.nam", ...}]` -- the row
a first-sight rig actually reports is `unknown.NAM`, which the measurer did not match until that
verification found it (fixed). **It is verified end to end** (2026-10-10, `bench-results/2026-10-10-p4-first-sight`): the LSTM in a
rig raised `cost_unknown` and `needs_measuring`, `pedal-measure` measured it on core 2 (finding and
hash-checking the DI first) and wrote the fragment, and the fragment names the row the engine could
not -- `NAM.LSTM.full`, 0.00885 of a core, 113 copies at the fit point. **P4 is done end to end** (2026-10-10): the fragment was
merged with `cost-merge` (vip's table now has 15 rows, `NAM.LSTM.full` at 0.00885 of a core), applied,
and `devices/vip/check` is green — a rig on that family is admitted at its true cost instead of D8's
`unknown`. Nothing is left of P4; then `pedal-measure`, merge the
fragment with `devices/common/cost-merge`, and confirm the row resolves with no xrun. (An LSTM is also
the case the *bench* has to refuse rather than approximate — `lookback` says `Unbounded` — so the
fragment it produces is one to read rather than wave through.)

**Owed, in the order to take them.** **T11, P4, P8's publish and piv's tool have all landed** (T11:
`bench-results/2026-10-11-t11-warm`; P4: `bench-results/2026-10-10-p4-first-sight`; P8's two-step
publish: namchain `7d9cbbd` + `1a07af0`; piv's tool: rtpi `a6d4d67`), so the list starts at what is
actually left.

(1) **P8's catch-up replay — done 2026-10-10** (namchain `810a1fd`, `ea453c0`, `74ebd08`,
`2830f5d`, `89193f5`; 367 cases and 271,552 assertions green, `ctest` 5/5): the Full's first blocks
are bit-identical to a Full that had been running, and 3,840 of 3,840 samples differ without it. D6's
visibility holds with it, because the compile now runs off the control thread. What follows is what
this item said while it was still open:
**an attempt at this was in flight, unattended, at the end of the session that wrote this line** — a
subagent was briefed with the previous delegation's findings and told to land the smallest testable
slice (the input-history buffer plus the replay, with the measurable claim) and commit early, so a
commit on `namchain`'s `main` may appear without a human in the loop. If one is there, read its message
before redoing the work; if there is not, nothing was lost and the paragraph below is the brief.
with the second publish inline on the control thread no client can observe the temporary Lite (the control
loop answers one request at a time, so `/status` always describes the end state), so "coming up to full"
needs the Full's compile off the control thread. The replay itself is the one piece of P8 deliberately not
written: catching the Full up needs
the *recent input*, and the engine's live input ring is a four-block dropping pool rather than the
~170 ms of history the design's numbers come from, so it needs a buffer on the warm path (the
`lookback` length per model is already the engine's, and `Unbounded` for a model whose memory cannot be
replayed exactly, which P8 must refuse to promise about rather than approximate). Then T9 through the
pedal: press-to-full-rig, with the Lite in the meantime and that state visible where D6 says.

(2) **piv's reboot** — the tool is built, tested (**33 cases green**, and the vip suite beside it 54 with
10 skipped for `dtc`) and **pushed** (`rtpi a6d4d67`; the subagent's own push died on the locked ssh
agent, so it went over https), and it is the *board* that has not moved. **Corrected below**: the two
commands this item used to give are not the route for this change — `piv-boot set-args` edits the
active line in place, with no candidate and no automatic fallback, and on piv it was reading the
wrong file as well, so it refused a write nobody was making (`rtpi a497598`, which fixed the
resolution and took the suite to 44). The route is the tryboot one-shot, spelled out under
"What `piv-boot` is not" below. On piv:

    sudo piv-boot status                       # card line, running line, proposal, diff
    sudo piv-boot set-args --yes --reboot      # write it and reboot, which is what applies it

then `rtpi-audio-tune check` and `devices/piv/check`, and `cat /proc/cmdline` should show
`isolcpus=...1-3`, `irqaffinity=0`, `skew_tick=1`. `--restore` puts the newest backup back, and a
write and its restore inside the same second used to collide on the backup name — the suite caught
that, which is why `--restore` no longer backs up over its own restore point. The owner's call on
timing, since it is a reboot.

**One gap the tool does not close by itself**: nothing installs `piv-boot` on piv. `vip-boot` arrives
at image build; piv has no such path yet, so the first real use needs the file copied to
`/usr/local/sbin/piv-boot` on the board (or a small deploy script, which does not exist). The
subagent's own pushes died on the locked ssh agent and its `origin/main` ref is stale as a result --
both commits are on the remote through https (`a6d4d67`, `26b80bb`), so "ahead 3" is the ref, not the
remote. `make test-tools` runs both suites: piv 33 tests, vip 54 with 10 skipped for `dtc`.

**What a piv copy could not inherit from `vip-boot`**, for whoever touches this next: vip's whole model
is two fixed slots with `profile.txt`/`tryboot.txt` rewritten in place at fixed length, an `os_prefix`,
and tryboot staging a candidate — and piv has none of it: one `cmdline.txt` on one partition, no slot,
no `os_prefix`, so no one-shot `try-args` to arm (which is exactly why the tryboot route could not carry
an arguments change on this card), and the line's length changes, so the write is temp-plus-fsync-plus-
rename rather than a fixed-length write in place.

(3) **3.8's acceptance** — a press end to end (footswitch → Pico → pedald → engine → sound), then 3.5.
Still the owner's: the power question behind T8's reboot (the journal is persistent now, so a
recurrence will say).

(1) **P8's implementation** — the two-step publish in namchain: publish the Lite (the `lite_first` trim
and its reporting in engine and service are in), compile the Full behind it, replay the `lookback`
length of recent input into it (the length and the input are already the engine's), then crossfade with
E2's compensated shape. The service already accepts a temporary Lite; T9 measures it.

(2) **piv** — its tree is on the rules (isolate 1-3, housekeeping 0, the USB audio interrupt on core 1)
but the board still boots the old command line (`cat /proc/cmdline` shows 2-3 and `irqaffinity=0-1`).
piv **has** the slot: `/boot/firmware/config.txt` carries `[all] os_prefix=current/` with
`[tryboot] os_prefix=new/`, and `new/` is absent only because nothing has been staged into it yet.
So the route for an arguments change is the designed one — the one-shot, which stages `new/` as
`current/` plus the tuned arguments, boots it once, and keeps `current/` bootable so a candidate
that does not come up falls back by itself:

    make piv-audio-boot-args          # flash-kernel, then --audio-tuning, then watch the reboot
    # or by hand, with a kernel release you name yourself:
    scripts/safety/arm-try-piv.sh --expect "$(ssh piv uname -r)" --audio-tuning --reboot

then `rtpi-audio-tune check` and `devices/piv/check` on the board. Its own session, and the owner's
call on timing, since it is a reboot.

**What `piv-boot` is not.** It read the wrong file until this fix — with `os_prefix=current/` the
firmware reads `/boot/firmware/current/cmdline.txt`, and the tool opened the one-option leftover at
the root of the boot partition — so its `set-args` is **not** the route to use for an untested
change: it edits the active line in place, with no candidate behind the change and no automatic
fallback (the tool now says so in its own output, and prints the path it resolved). It is worth
having for the case the tryboot route does not fit — a board that is already up and arguments
already known to boot — and `--restore` puts the newest backup back.

**What a piv copy could not inherit from `vip-boot`**, for whoever touches this next: vip's whole model
is two fixed slots with `profile.txt`/`tryboot.txt` rewritten in place at fixed length, an `os_prefix`,
and tryboot staging a candidate — and the arguments-changing part of it has no counterpart here:
`vip-boot try-args` rewrites both slots at once, while piv has one line in one tree, so the write is
temp-plus-fsync-plus-rename rather than a fixed-length write in place. The one thing piv does have
is the slot itself, which is what makes `arm-try-piv.sh --audio-tuning` the route — and it has been
exercised: rtpi's `devices/piv/last-known-state.txt` records a completed tryboot
(`this boot is a tryboot: 1`) with `current/` and `old/` both `good` and no `new/`, which is a
candidate that was staged, booted and promoted.

(3) **3.8's acceptance** — a press end to end (footswitch → Pico → pedald → engine → sound), then 3.5.
Two things are still the owner's: the power question behind T8's reboot (the journal is persistent now,
so a recurrence will say) and which piv route above to take.

Two faults were found by putting this on the board and are fixed: **`pedal-interface.json` was never
installed** (it lived outside the rootfs, which is the only thing that installs anything, so
`pedal-diag.service` had never started and every check that compares the board against the model had
silently done nothing), and `pedal-diag --json` could not parse its own gatherer's `COST` line. `tib`
is gone from all five repositories — device trees, tooling, kernel fragments, measurement data and
prose — rather than marked retired. `piv` is the one device behind these rules, and its tree is now
ahead of its boot (config on the rules, kernel args still the old ones) — the state (2) above.

**E2 is measured; the tiers wait on one listening test** (2026-10-06). All four of 3.8's open
questions are answered — Lite against Full over the whole library, catch-up for chains, warm
density on vip, and an IR kept as a record — and the reading is
[bench-results/2026-10-06-e2-tiers.md](bench-results/2026-10-06-e2-tiers.md), with the tables in
namchain's `bench-results/e2-*.txt`. The one thing left is a judgement no bench makes: **is a Lite
standing in for a Full audible?** That is what decides whether tier 2 survives as designed or the
bank has to be tier 1, and it is 40 MB of WAVs in `build/e2/audition/24bit/` made by
[bench-results/2026-10-06-e2-listening](bench-results/2026-10-06-e2-listening/README.md) — play
`-full`, then `-lite`, then `-handover`, for the six models listed there. Everything else it needs
is a decision, not a measurement: the tier table, and the limits the service enforces from it.

**The fade thumped, and that is a fix you have heard the reason for** (2026-10-06, later the same
day). The handover files the listening test uses had an equal-power fade, which is right for
uncorrelated signals and +3 dB at the midpoint for correlated ones — and Lite and Full are correlated
at 0.97–1.00, so every handover added 2.6–3.0 dB of low end for 5 ms. That was the thud. It is
measured, fixed in the bench (`--fade-shape compensated`, all 104 rows at 0.00 dB, zero findings) and
re-recorded: `build/e2/audition-fixed/24bit/` is the same six models to A/B against
`build/e2/audition/24bit/`. The engine's `rt::Crossfade` is the same law, so this is every `nc.xfade`
of a bypass flip and every whole-chain fade between two similar rigs — **it wants its own change,
with the transition tests**, and `namchain bench-results/e2-fade-thump.txt` is the measurement to
work from. What the glitch detector cannot see is the wider lesson: it has four rules for
discontinuities, dropouts, high frequencies and convergence, and none of them is a level check.

Two loose ends from the same session, neither blocking: the bench's per-candidate memory came out
larger for a Lite than a Full (fixed to fault the buffers in first, but worth a look at whether
`SetSlimmableSize` before a rig's `Reset` — which is what `nc.nam` does too — leaves the selected
submodel with the container's pre-`Reset` buffer sizing), and E1's default replay was `max()` of a
rig's two stages where a series chain's memory is the *sum*.

**3.3's last open item is decided, and it unblocks 3.5** (2026-10-06, U8). The footswitches send
`cc` 80–82 — what the MIDI Commander's own buttons send — so a press on the pedal and a press on
the Commander are the same message apart from `source`, and the trigger-to-action map stays in the
one place D4 gives it: `pedald`'s `mapping.py`, which already maps them (`DEFAULT_CC`: 80
`rig_down`, 81 `rig_up`, 82 the assignable one). **Nothing in the service changes.** `source` is
kept on every event, so a per-source map can come later without a wire change. **Draft 2 itself is
now in both ends** (version 2.0, same day): `str8` strings, `engine_muted`, `ERROR` on a version
mismatch, `HELLO` answered every time, and no `PING`/`STATE`/`ACK` answered without a session
([docs/uart-protocol.md](docs/uart-protocol.md) has the rules and why each one exists). **And it
is on the pedal** (later the same day): the Pico was flashed as `bb6dde1`, the loopback passed every
check against it — the refusal included — and `devices/vip/apply` put the 2.0 `pedald` on vip in the
same stop, so the live pair holds a 2.0 session and `devices/vip/components.lock` is at `bb6dde1`
([bench-results/2026-10-06-draft2-swap-bench.md](bench-results/2026-10-06-draft2-swap-bench.md),
which also records the crossed signal pair that cost an hour and how it was told apart from a dead
one). **3.3 is done**, and with it the last thing blocking 3.5.

**What is next, cheapest first, unchanged otherwise:** **3.5 Firmware v1** (the three
footswitches, DIN MIDI in, LEDs — the footswitches sending `cc` 80–82 per U8), then **3.8** (the
ready set and `rig.switch`, then `pedald` v2's bank and map), and alongside them **2b.3 board 1**,
which takes the analogue side off the bench fixtures. The Pico's reflash is no longer on the list.

**The five repositories are one workspace now** (2026-10-06). Everything the pedal is made of
lives in `~/code.local/pedal/`: `pedal.project/` beside `namchain/`, `ljoss/`, `rtpi/` and
`NAMBench/`. A session opened on that directory can read and write all five with no extra
permissions, because a session's cwd *is* the sandbox's writable root and there is exactly one of
it — which is why the per-machine `.claude/settings.local.json` that listed them as additional
directories is gone, and why the DeepSeek harness needs no per-write approval. The directory is
deliberately **not** a repository: a checkout inside one is recorded as a gitlink and clones as an
empty directory that says nothing about what is missing, and at the workspace root that mistake
would be available for all five at once. Design, and the alternatives with the measurements that
ruled them out: [docs/workspace.md](docs/workspace.md). Evidence, and what was established about
the harnesses before anything moved:
[bench-results/2026-10-06-workspace-move.md](bench-results/2026-10-06-workspace-move.md).

`workspace.repos` declares what the workspace holds; `scripts/workspace check` asserts it, and
`scripts/status` prints it at the start of every session rather than leaving it to be assumed.
`tools/git-hooks/` refuses a commit or a push that embeds a repository **nothing declares** —
"nothing declares" being the point, since namchain's vendored fork is a declared submodule and
still commits. It is installed by path through an `includeIf` block in `~/.gitconfig`, so every
clone and every worktree under the workspace gets it with no step of its own; its failure mode is
silent (git ignores an include target that is not there), which is what the check exists for.
`tools/tests/test-workspace-guards` proves both directions, and it was also proved once in the
live workspace (`bench-results/2026-10-06-workspace-move/guard-acceptance.txt`).

The move was a rename within one volume, with nothing copied: the before/after snapshots
(`bench-results/2026-10-06-workspace-move/{before,after}.txt`) differ only by this session's
commits, four worktrees removed and the root files added. Every branch survived, including the
local-only `x/*` and `local-engine` ones, and the vendored submodule is at the same commit.

Commits, **all local and unpushed, waiting for your say-so**: pedal.project `44f049b` (declaration,
guard, `scripts/workspace`, docs, path fixes), namchain `3933713`, ljoss `175f925` (its compiled
default `namchaind` path now resolves from its own file path, so a moved workspace needs no edit
there), rtpi `5940267`, NAMBench `dbe7e12` (the one family repo that had neither `AGENTS.md` nor
`CLAUDE.md`).

**One thing only the owner can confirm, and it is the point of the exercise:** open a session on
`~/code.local/pedal` and write a file in each of the five repositories. The guard, the layout, the
instruction files, the worktree rule and every script have been checked from here; a session rooted
*at the workspace* is the half that needs a session rooted there. Two housekeeping notes for the
same moment: the DSH workspace list still holds entries for the old paths, and Claude Code will
start a fresh per-project entry for the new one.
**The card carries both kernels, so vip is re-paveable without losing the pedal's kernel**
(2026-10-05). `make-card --remote` had refused a root swap: vip runs rtpi's rebuild
(`7.0.0-1017-raspi-realtime-numaemu1-trimmed`), the image built the stock kernel, and `--remote`
cannot move a FAT boot slot. Now `devices/vip/image.lock` pins the rebuild as **artefacts** from
rtpi's `build/vip/` (release, kind, rtpi commit, three sha256s), `make-card` verifies every hash
before the container starts, `build-image` installs it into the root with rtpi's own
`vip-install-kernel` and fills **slot b with the stock kernel** as the fallback, and `remote`'s
guard checks the booted slot's `vmlinuz` against the image instead of comparing release strings.
rtpi's half is `ad9fee1`; the design, what changed while doing it and the one open question
(automatic kernel rollback on repeated guard trips) are
[docs/vip-kernel-image.md](docs/vip-kernel-image.md). **Done on the board the same day**: the build
(`build/vip/20261005T202527Z`) went to vip with `--remote` and validated, and both kernels were then
seen to boot and promote — `try-kernel 7.0.0-1017-raspi-realtime` (validated, promoted slot b) and
back to the pedal kernel (slot a, active) — so vip now runs what a fresh card would: slot a the
rebuild, slot b the stock kernel, both good, `devices/vip/check` green. That card write is still
owed for one thing: rescue's `authorized_keys` came from an older card, so the Core key was
installed into the rescue root by hand (the record in `devices/vip/authorized_keys` is what the next
write will put there).

**Diagnostics landed** (2026-10-05, this session): `scripts/diag` /
`devices/common/rootfs/usr/local/sbin/pedal-diag` reads everything the host, the codec, the Pico
link and both local sockets will say about themselves, compares it with
`devices/common/rootfs/etc/pedal/pedal-interface.json` (the wiring tables as data) and prints what is wrong, the
evidence, the likely cause naming a physical thing, and the measurement that closes it. Modes: a
report, `--json`, `--watch` (continuous, ~1.5 ms CPU and ~2.8 kB a sample, its own cost printed),
`--deltas` (what changed over a long run), `--probe` (the invasive checks; refuses while the engine
plays) and `--selftest`. `pedal-diag.service` runs it on demand in the loose profile; `pedald`'s
`/status` gained the link's byte counters, drop count and last-rx age, which is what makes a rate
possible. Design and the I2C dead end: [docs/diagnostics.md](docs/diagnostics.md).

**Probes and the link are reported as connections** (later the same day): the report reads the
machine the operator is sitting at as well as the pedal host (`ioreg`'s USB tree on macOS, sysfs on
Linux), because a Debug Probe's USB is plugged into one of them and only its UART or SWD lead
reaches the pedal — the fact that had "no Debug Probe attached to this host" reading as a pedal
fault. It says `No debug probes connected via USB to any device`, or names the machine each probe is
on, with the port it brings up and who holds it; `--probe` reads that port for three seconds to say
what the probe is watching (the Pico's `a5 5a` frames, or a Linux console's text) and reports
silence as silence rather than inventing a target. The Core→Pico UART link is reported in the same
voice, and its two absent states are now told apart: the kernel has no `ttyAMA0` at all (RP1's
UART0 disabled; `pedal-uart.service` owns the overlay, named from `pico_link.enabled_by`) versus the
kernel has it and `/dev` has no node for it, which is udev's business and not the device tree's.
Tests: `devices/common/tests/test_diag.py`, 11 more of them.

**The codec's registers still cannot be read, and now the tool says so out loud** (2026-10-06):
`i2c-tools` is on vip, so `--probe` asks the chip itself (`i2cget -f -y 1 0x1a <reg> w`) and
reports either the chip's own words beside the driver's cache (`codec.cache_differs` is a write
that never landed) or the controller's abort reason from `dmesg` (`codec.read_failed`, which is
what happens today: every read aborts with lost arbitration and SDA stuck at low while writes are
clean). The SDA hold time is ruled out (300/1000/3000 ns, honoured and ineffective), and the two
measurements that would separate the controller from the codec are a second I2C device with a
known ID register, or a scope on SDA/SCL during one read. rtpi now carries the other half:
`devices/vip/dt/rp1-i2c1-recovery.dts`, which arms the driver's GPIO bus recovery. Full evidence:
[bench-results/2026-10-06-codec-i2c-reads-and-the-sda-hold-time.md](bench-results/2026-10-06-codec-i2c-reads-and-the-sda-hold-time.md).

**The recovery overlay is in the boot partitions now** (2026-10-06, later): `vip-boot init-*`
compiles every `rtpi/devices/vip/dt/*.dts` into each boot tree's `overlays/` — both slots of the
pedal partition and rescue's — and enables each with a `dtoverlay=` line, so a card written from
the image carries it and a `.dts` that will not compile stops the build. `dtc` was added to the
build container for that. vip's own card was updated by hand (its config.txt predates the
mechanism, and does not even carry the `dtoverlay=uart0` line vip-boot has written since
2026-10-05), so after the next reboot a wedged bus is freed by the driver instead of by a reboot.
What that reboot has to show is `running with GPIO recovery mode! scl,sda` in `dmesg`; the arming
was already seen once at runtime. Commands and the revert:
[bench-results/2026-10-06-boot-overlay-installed.md](bench-results/2026-10-06-boot-overlay-installed.md).

**A known-register I2C device exists to settle controller-versus-codec** (2026-10-06): the spare
Pico 2 W now runs a bench firmware, `firmware/bench/i2c-slave/` — a slave at `0x2a` whose registers
are an identity word, its complement, a live seconds counter and a scratch register, so a read path
that returns stale or half-read bytes fails it. Wire four leads to the header (GP4->pin 3, GP5->pin
5, GND->pin 6, VSYS->pin 2) and `i2cget -f -y 1 0x2a 0x00 w` either answers `0xdead` — the
controller reads, and the codec's read is the fault — or aborts the way the codec's reads do, which
puts the controller's read path at fault. The procedure and the outcome table are in its README.
The measurement waits for the Core host's lock: a levels campaign held it all session.

**And it answered the question** (2026-10-06, later): on one bus in one run the controller read the
bench slave at `0x2a` perfectly — identity word, its complement, a moving counter — while every read
of the codec at `0x1a` failed with `lost arbitration` and `SDA stuck at low`, and a scan shows the
codec answering its own address. So the controller's read path is fine and **the codec's read is the
fault**: its protocol, its board or the part. Reaching a bus that could answer took four faults, all
found by evidence: no link from the breadboard to header pins 3 and 5; the lead from pin 5 not
conducting (proven by driving vip's pins low and reading the slave's own line-level report); the
Pico's pads cleared by swapping the leads, where the fault followed the wire; and the instrument's
own register addressing, which treated a register number as a byte offset. What remains open is
*why* the codec cannot be read, which needs a scope on SDA/SCL during one read or a second controller
known to read the same part. Evidence:
[bench-results/2026-10-06-i2c-read-fault/](bench-results/2026-10-06-i2c-read-fault/).

**The pedal is back** and its reads still fail the same way. After the reboot the codec's driver
probe had failed (no card, mute pedal); with the bus wired again the probe was retried in place —
`echo 1-001a > /sys/bus/i2c/drivers/wm8960/bind`, then `systemctl start pedal-codec` — the card came
back and the pedal reports 10 ok, 1 info. Its writes never stopped working, which is why the probe
succeeds. `pedal-uart.service` still fails at boot on a `dtoverlay` race (see below) although the
link is up.

**A boot-time race between the two overlay services, and the lock that ends it** (2026-10-06):
`pedal-uart.service` failed at boot with `* Failed to create '/tmp/.dtoverlays' - 17`. `dtoverlay` is
not reentrant: it keeps its stack of applied overlays in that one directory and refuses to start when
it is already there, and `pedal-uart` and `pedal-codec` both call it with nothing ordering them.
Nothing was lost this boot — the firmware honoured `enable_uart=1` by itself, so the link came up
anyway — but the same race can hit the codec's overlay, which is not harmless. Fixed with
`dtoverlay-locked`: both callers go through a helper that takes a `flock` on
`/run/lock/pedal-dtoverlay.lock` and then `exec`s dtoverlay, so the lock is held for exactly as long
as the load takes and the kernel releases it. Ordering the units would have fixed that pair, coupled
two unrelated peripherals, and left a third caller free to reintroduce the race; the lock is on the
resource they share. `devices/common/tests/test_overlays.py` (4 tests, and run on vip where `flock`
exists) holds both halves: that nothing in the image's rootfs invokes dtoverlay directly, and that
the helper really waits. Putting it on the card needs `devices/common/apply`, which refuses while the
engine is running, so it applies at the next convenient stop.

**The flaky httpd test, and the real race underneath it** (2026-10-06):
`test_httpd.HttpdTest.test_stop_is_safe_twice_and_leaves_no_thread_running` failed about one run in
seven, and the leftover thread's own stack said why: a `pedald-http-conn` handler sitting in
`recv()`. `stop()` shut each live connection down and then *closed* it, and closing a socket another
thread is inside `recv()` on does not wake that thread — it can leave it waiting on a descriptor that
has been closed, and possibly reused, underneath it, until its 30 s read timeout. `_shutdown` now
only shuts down, which is the documented way to wake a blocked reader, and the handler closes its own
connection in its `finally`, so the peer still sees EOF and the descriptor is freed a moment later;
`stop()`'s docstring now says what it owns — ending connections, not freeing them. The test's 5 s
wait, which had been covering the bug, is 1 s of grace for a thread's own exit, and a new test
(`test_stop_shuts_the_peer_down_and_stops_answering`) holds the client-visible half: EOF on a live
connection, nothing answering on the port afterwards. Five runs of the full suite (187 tests) and 400
rounds of the stop path in a loop: clean.

**And the audio-level half landed in namchain** the same day (namchain `a69d315`): `engine.levels`
is a read-only method returning the device's input and output levels per channel, each chain's, and
every plan node's labelled with its `element` and `role` — which is what "every macro in the running
rig" means, since namchain lowers a macro into primitives that keep the client's `element`. The
probes are relaxed atomics written once per period in the loop `outputs_finite` already walks, read
and reset so a poller's windows are disjoint and its numbers add up. The same commit publishes the
PCM `format` and gives ALSA a real `backend_diagnostics`, splitting the one `xruns` number into
`capture_overruns` and `playback_underruns` — the split the 2026-09-2x soak needed and could not
have. `pedal-diag` reads it already and stops saying "levels unavailable". **Remaining: the meters
in ljoss** (a 20 Hz `engine.levels` poll and the views), which is the next piece.

**The meters in ljoss were already there, and the measurement half is done** (2026-10-06). The note
above was stale: ljoss has the 20 Hz poll (`Ljoss/Engine/EngineLevels.swift`), the shared decay and
the bars (`Ljoss/Views/LevelMeters.swift`), and a campaign of its own measuring what the numbers mean
at the jack (ljoss `60e70d8`, `Tools/levels/`). What this session added is the other side of the
question — what measuring *costs* — and the switch to stop paying it:

- **namchain `f00714d`**: `--levels` / `--no-levels` (config key `"levels"`), which turns the feature
  off **at the source**. `CompileOptions::levels: false` leaves a plan's probe vector empty, so
  `measure_node` sees a null probe and the render path does no per-sample level work at all. With it
  off, `engine.levels` is refused (`levels_disabled`), `engine.status` omits the levels object, and
  `features` omits `"levels"` — three absences, so a client degrades to having no meters rather than
  polling a method that cannot answer. Decided once, at construction and at each plan's compile,
  because a local transition compiles a plan on the render path.
- **Measured on vip**, and written up with its method, its stability check and its caveats:
  [bench-results/2026-10-06-levels-switch.md](bench-results/2026-10-06-levels-switch.md). The short
  version: measuring a 34-node rig costs **2.2% of one core with the switch off and 4.5% with it on**,
  the per-sample cost being ~0.7–1.5 ms/s of a core per measured node; a client polling
  `engine.levels` costs **~0.06 ms a poll on a 2-node rig and ~0.13 ms on a 34-node rig**, linear in
  the rate, and so small beside the per-sample cost that the reply's size is most of it. The heaviest
  condition in the campaign — a 34-node rig with a client polling at 20 Hz — still cost only 4.8% of
  one core. This is an upper bound rather than a real rig's number: a rig with an A2 model in it
  would show a smaller *share*, because an inference swamps a probe.

**What the meters still lack is their scale, and a guitar has never been the source that set it.**
The campaign's numbers are the codec's, measured through the interface's line output, and a meter
drawn to 0 dBFS on this input claims about 11 dB of headroom the jack does not have. The fix is a
calibration, not a display tweak: **2b.4** runs the campaign again with a real guitar into a guitar
buffer pedal in front of the input — possible today, and it is the stand-in the case measurements
already name
([2026-10-04-case-first-sound-end-to-end.md](bench-results/2026-10-04-case-first-sound-end-to-end.md)),
and then again for the Inst and Line positions once board 1 exists, because the two positions
cannot share a scale. That item is the dependency: until it has run, the bars are accurate and
meaningless.

**The conversion never touches the audio core, and two finer switches turn the sampling down**
(2026-10-06, namchain `5eff47e`). The worry was that the control thread's dB conversion — square
root, logarithms, JSON — might be sharing the render core and eating the headroom the audio work
needs. It is not:

- The control thread carries `CPUAffinity=0-1` from the device's own drop-in and runs `SCHED_OTHER`;
  the render thread pins **itself** to core 3 at `SCHED_FIFO 80`, because `sched_setaffinity(0, …)` is
  per-thread and its only call site is `promote_render_thread`. Shown live on vip, not just read:
  `ps -L` puts the two threads on cores 1 and 3.
- What does cost the render thread anything is the per-sample probe write and the cache-line traffic
  with its reader on core 1. That, not the maths, is the price of a meter — which is what the new
  switches reduce.

Two switches, both **off by default**, both experiment-grade:
`--levels-first-frame` folds one frame per period instead of every frame (the render path's level
work falls 64×, and a meter starts missing transients — it says so, reporting `frames: 1` per
period); `--levels-rate-hz N` drains the probes at most N times a second and answers a read in
between from the held reply (a saving for the control thread, not for render headroom). Measured at
1 Hz client polling on the 34-node rig: **2.26% off, 5.12% default, 4.52% with the rate limit, 2.87%
with the sparse fold, 2.30% with both** — so both together bring a 34-node rig's meters to about
0.06 pp of one core, and the two are very nearly additive because they act on different resources.
The report, with charts and the measured caveats:
[bench-results/2026-10-06-levels-switch.md](bench-results/2026-10-06-levels-switch.md). It ran under
the host lock while the I2C bench firmware was being written in this repo, and the half-window
stability re-runs reproduced to 0.02 pp.

**Publishing a probe once a period recovers 55% of the cost of having meters, and measures every
sample** (2026-10-06, namchain `dd8d480`). The per-sample fold was writing the probe's `std::atomic`
fields, which share cache lines with each other, and the control thread reads them — so the render
thread was losing those lines on every sample. The cost was coherency, not arithmetic, which is why
`--levels-first-frame` could buy 2.25 pp by not looking at 63 samples in 64.

`--levels-publish-period` gets the same saving without looking away: the render thread folds into
`level::Window`, plain memory no other thread has touched, and adds the window to the probe's atomics
once a period — the shape `account_render_time` has always used. The meter reads the same thing
because a publish *adds* (raise the peak, `fetch_add` the rest) rather than setting: add and max
against the zeroed reset a reader performs are order-independent, so no sample is lost or counted
twice. A reader can now see a window up to one period old — 1.33 ms at q=64.

Measured at 1 Hz on the 34-node rig, 90 s windows, both controls taken on the day: **2.22% off,
5.40% measuring, 3.66% publishing per period** (+1.43 pp), and **3.06%** with the rate limit stacked
(+0.83 pp) — 55% and 74% of the cost recovered. Stability at 60 s reproduced to 0.18 pp on the
largest figure.

**Both are now the defaults** (namchain `663d0c9`, same day, on the owner's call): publishing once per
period, and an **8 Hz** drain rate — half what ljoss's 20 Hz meter can show, so five reads in six are
answered from the held window and a level is at most 125 ms old. `devices/vip/rootfs/etc/namchain/
namchaind.json` names both explicitly, so the appliance does not depend on remembering what a binary's
defaults are, and vip is applied and running them. **Measured as it ships, against the running
service, polled at ljoss's real 20 Hz: 3.31% of one core, against ~5.6% for the per-sample path** —
about 2.3 pp, with every sample still measured (227 real measurements out of 1,801 reads, none empty).
Both keep an off-switch: `--no-levels-publish-period` and `--no-levels-rate-hz`. The sparse fold
stayed off, because it compromises what a meter reads and this gets a comparable saving without that.

One instrument lesson worth keeping: CPU is counted in 10 ms ticks, so a measurement window resolves
`10 ms ÷ window` of a core. At the 30 s a five-minute sweep allows, the rate limit's 0.60 pp is under
half a tick — a number, not a measurement. Spend the budget on window length before condition count.

**3.6's power question is answered: the header feed holds, the USB-A port does not — and the codec is
down** (2026-10-05). The instrument is the pedal's own: the Pico prints `fw: up N s` on its USB
console every 5 s, and `N` counts from the Pico's own reset, so it measures **power** where `dmesg`
cannot (the host re-enumerates the device on every boot either way) and where a `HELLO` cannot (the
Pico re-sends `HELLO` after a 1 s link timeout, restart or not). Read twice, 20 s apart, as a control
first — the read itself does not reset it (48,850 → 48,880 s, and again 48,890 → 48,920 s).

- **Form 1, vip's USB-A → micro-B: out.** Across a `sudo reboot`: **48,930 s → 20 s**. vip's kernel
  came up 10:10:17 UTC and the Pico re-enumerated as `2e8a:0009` at 10:10:20. The engine came back
  `running`/`ok`, resumed ljoss's "New Rig", worst block 18.9%, and the reboot's only cost was
  **2 xruns**, the stream stopping and starting.
- **Form 2, header pin 2 → 1N5817 → VSYS: in.** With the USB cable left in for the console (the
  reboot cuts the USB-A rail either way, so a survivor is surviving on the header): **reboot 100 s →
  135 s** across a 26 s outage, **shutdown 190 s → 295 s** across a 95 s outage. Both legs held, so
  the feed works and the diode is the right way round — a reversed 1N5817 would have left the Pico on
  USB alone and it would have restarted exactly as form 1 did. `pedald` did log a `HELLO` after the
  shutdown leg, from a Pico that demonstrably never reset: that is the caveat above, measured.

So **the relay rule (R4) keeps its "the Pico stays up" case** — it can hold bypass on link loss
through a Core host reboot or a shutdown, rather than relying on having restarted into a safe state —
and the USB cable stays only as the console and the flashing path. The header now has **two 5 V
consumers**: the codec board's VIN is on pin 2 (`docs/codec-bringup-2a.md` stage 4), so the Pico's
feed belongs on **pin 4**, with pin 2 left to the codec alone — pins 1 (3.3 V), 2 (5 V), 3 (SDA) and
5 (SCL) are neighbours.

**Open, and the reason the pedal is not playing: the codec stopped answering.** `pedal-codec` fails
with `card wm8960 did not appear`, `/proc/asound/cards` is empty and the engine is `lost`/`error`.
It is **not** the 2026-10-04 fault: the reset write to `0x1a` returns **`-121` (`EREMOTEIO`, a NACK)
rather than `-110` (`ETIMEDOUT`, the controller's timeout)**, so the Pi drives the bus and is told
"nobody here" — the board is not answering, not holding a line. The engine was `running`/`ok` at
10:12, before the Pico's feed was added, and the card has not appeared since the power cycle that
followed it; the board's supplies and its I²C are four adjacent header pins (1, 2, 3, 5) and its VIN
shares pin 2 with the new lead. Check those leads and the board's seating in its socket strips first
(the I²C interface is in the DBVDD domain, fed from **3V3 on pin 1**, so a displaced pin 1 alone
gives this symptom). Full record and the verbatim log:
[bench-results/2026-10-05-pico-power-test.md](bench-results/2026-10-05-pico-power-test.md).

Instrument: `scripts/pico-power-test` (`--leg read|reboot|shutdown`). Two things it cost, both
recorded: vip's journal is **volatile** (`/run/log/journal`, tmpfs), so a previous boot's shutdown
sequence is not recoverable; and the console must be opened with `stty raw -echo` before it is read,
or the host echoes what it receives back down the port and the firmware's bench stand-in answers its
own output in a loop.

**The pedal plays, assembled, in a case — with the Pico on the link** (2026-10-04). Not a part on the
bench any more: the owner played the assembled pedal this evening. A **temporary plastic box** stands
in for the aluminium case, and its rear wall carries **IN, OUT L and OUT R** in the Neutrik jacks, in
the arrangement the aluminium case will use; vip's own **USB-C** supply lead comes through a hole in
that wall straight into the Pi's USB-C port (no panel-mount extension yet); the **Pico** is powered
from one of vip's **USB-A** ports into its micro-B, with its UART on the header (`ttyAMA0`, GP0 → pin
10, GP1 → pin 8, GND). The owner's report: the codec and `namchaind` "work perfectly", ljoss sends
rigs, it "sounds great", rigs can be edited and switched "with no glitches, no delays", and the
latency "feels like zero". Evidence, and the list of what it does *not* show:
[bench-results/2026-10-04-the-pedal-plays-in-a-case.md](bench-results/2026-10-04-the-pedal-plays-in-a-case.md).
Read from vip while that rig was loaded: `namchaind` `running`, `ok`, `hw:CARD=wm8960,DEV=0`, 48000 Hz
/ q64, **0 xruns**, 0 guard trips, `issues: []`, worst block **20.3%** of the 1333 µs deadline (0 over
90%), ljoss's "New Rig" applied over TCP, 52 models and 1,538 IRs in the library, model budget 300,808
of 458,752 bytes. `pedald` **v1 is deployed and running** (the service's own evidence is
[bench-results/2026-10-04-pedald-on-vip.md](bench-results/2026-10-04-pedald-on-vip.md)):
`pedald 0.1 up: link /dev/ttyAMA0, http on 0.0.0.0:47820`, `Pico says hello: fw '0.1', protocol
1.0`, and its save rule wrote `/var/lib/pedal/library/rigs/last.json` for that rig.

**Three things this makes true.** Phase **3.4** is in service, not on the bench: `ttyAMA0` carries
the link and the other end is `pedald`, not a test script — the Core-side UART needed no console
moving on vip (the console and getty are on `ttyAMA10`). Phase **3.2**'s **v1 has landed**
(783a8de, dcaf0e2): the service is up, the `HELLO`/`WELCOME` session comes up against a live Pico,
and `pedal-resume` is retired into it — one writer of `last.json`. And Phase **3.6**'s Pico power
question now has its first wiring on the bench, which is the one that needs a reboot to answer.

**And three it does not.** **Switching is still the app's path, not the pedal's:** no footswitches,
no MIDI in, no relay, so the Pico's only job today is the link and its console, and every switch the
owner made went ljoss → `namchaind` on the **cold** path — 25–35 ms, inside D10's 50 ms, but with
E1's **170–340 ms** of wrong-sounding state at the front of it. "No glitches" and "no latency" are
the owner's ear, not the glitch detector and not a timing at the jack; D10's gate is a switching soak
and it belongs to 3.8. **The Pico's firmware is `fw '0.1'`**, which no checkout's `git describe`
produces — reflash from a known commit before trusting anything firmware-side. And **the case is not
the aluminium one**: nothing is panel-mounted, the display, footswitches, MIDI and the toggle are
absent, and the analogue side still runs without board 1 (no input buffer, no output stage of its
own), which is why [2026-10-04-case-first-sound-end-to-end.md](bench-results/2026-10-04-case-first-sound-end-to-end.md)'s
fixtures are still in the path.

**The next four things, cheapest first:** (1) **3.6's Pico power test** — the Pico is wired for it
right now, and ten minutes decides whether the USB-A route survives a vip reboot and shutdown, which
the relay rule needs; (2) **reflash the Pico from a known commit**; (3) **3.8** — namchain's ready set
and `rig.switch`, then `pedald` v2's bank and map — which D10 puts before the footswitches, because
without it a press stalls on the SD card and the first 170–340 ms is E1's wrong sound; (4) alongside
those, **2b's board 1** (Phase 2b.3), which is what takes the analogue side off the bench fixtures.
The UART contract's **U8** decision (footswitches sending `cc` 80–82, so footswitch and MIDI
messages are identical) is needed before 3.5 and is the owner's to make.

**Three disturbed leads, and the Pico's USB console driver** (2026-10-04). After the rewire,
`namchaind` was `running` but `lost` with no sound card at all (`pedal-codec` failed with
"card wm8960 did not appear"): the codec's I²C bus was dead — every address on `i2c-1`, and the
driver's own reset write to `0x1a`, ran to the controller's 1 s timeout, which is a held line
and not an absent chip. Reseated, the card came back; the next failure was `capture timed out
after 1000 ms (last state 3, ring 0 frames)` — PCM `RUNNING`, no frames — because **BCLK was
out of the header**: with no bit clock the RP1's I²S RX makes no DMA requests, so no period
ever completes. Once the clock was back the capture was **exact zeros**, and that third lead —
**ADAT (ADCDAT)** in the wrong socket on the codec board — is diagnosed, fixed and measured in
[bench-results/2026-10-04-case-no-audio-diagnosis.md](bench-results/2026-10-04-case-no-audio-diagnosis.md),
which also settles the output side (the rig leaves on channel 0 = HPL, so the interface's cable
belongs in OUT L until a chain's `output_channel` is bound). A timeout and zeros are not the
same fault: no clock versus no data. All three fixed at the bench. After: card 0 `wm8960`,
engine `running/ok`, `issues: []`, blocks 750/s at q64, 2 xruns in total and none recent, render
worst 3.4% of the 1333 µs period, 0 over deadline. Evidence:
[bench-results/2026-10-04-rewire-faults-and-the-pico-console.md](bench-results/2026-10-04-rewire-faults-and-the-pico-console.md).

**vip's trimmed kernel keeps `cdc_acm` now** (2026-10-04, rtpi `e873c9c`). The Pico 2 W on
vip's USB (`2e8a:0009`, serial `5988E9A10C2344D7`) presented its CDC-ACM pair with **no driver
bound** and no `/dev/ttyACM0`: the `localmodconfig` trim had `CONFIG_USB_ACM` unset, and while
the module is missing nothing can bind the Pico, so it can never appear in `/proc/modules` — a
self-fulfilling absence, the shape `vip-keep.fragment` already describes for `inet_diag`.
`config/vip-keep.fragment` keeps it as its fifth deliberate exception, the kernel was rebuilt
(106 modules; all 71 the board loads present), installed and tried: slot a promoted, both slots
good, nothing armed, guard 0. `/dev/ttyACM0` now appears (`cdc_acm 3-2:1.0: ttyACM0: USB ACM
device`) and the codec and engine came through the reboot unchanged. The release string is
unchanged, so `devices/vip/components.lock` still matches the host. The rebuild also drops
`crypto/af_alg`, `crypto/algif_hash`, `crypto/sm4` and `crypto/sm4_generic` — fetch-day keeps in
the 109-module build that nothing loads now; add them to the keep fragment if that matters. The
USB CDC is the firmware's console, not the link — and the link is now on vip too: the Pico's UART
was moved from the Debug Probe to the header (GP0 → pin 10, GP1 → pin 8, GND), `ttyAMA0` carries
its 1 Hz HELLO, and a hand-driven WELCOME/STATE/PING session came up (session up, 15 frames,
0 bad, `link down` a second after the frames stopped). The first placement was dead both ways and
a re-seat fixed it; `ttyAMA0` was already free of console and getty (the console is on `ttyAMA10`),
so step 4 has nothing to move. What the link still waits for is the pedal service (Phase 3.2).
Note the firmware reports fw "0.1", which no current checkout's `git describe` produces — reflash
from a known commit before trusting firmware-side numbers.

**The prototype case has a schematic** (2026-10-03). The IN jack and both output jacks in the
plastic box are a KiCad sheet now, [schematic/prototype-case.kicad_sch](schematic/prototype-case.kicad_sch),
written from the wiring table in [schematic/case-wiring.py](schematic/case-wiring.py). It holds the
two output channels as the same circuit (10 µF with its + towards the codec, 100 Ω, 1 MΩ bleed), the
input's screened cable (core → LIN1; braid bonded to the sleeve at the jack end only, cut flush at
the other end), the case's 4-way strip (pin 1 OUT L tip, pin 2 OUT R tip, 3 and 4 reserved for the
INST/LINE switch and the DC socket), and J4 as the codec header stands today — the sheet's notes say
what replaces it once board 1 exists (the core to board 1's IN pad, the strip pins to OUT-L and
OUT-R with the bypass relay in those runs). Two checks pass: `kicad-cli sch erc` reports **0
violations**, and `case-wiring.py --check` compares KiCad's netlist against the intended nets — all
eight match, and the eight spare pins are confirmed unconnected. Renders in `schematic/renders/`.
The hand-drawn `docs/prototype-case-wiring.svg` and its PNG are deleted.

**vip's kernel has NUMA emulation on** (2026-10-03). The one config line Ubuntu ships off,
`CONFIG_NUMA_EMU=y` (beside `CONFIG_NUMA=y` and `CONFIG_NUMA_MEMBLKS=y`), is now on: vip runs
`7.0.0-1017-raspi-realtime-numaemu1`, the pedal's stock kernel rebuilt from the exact Ubuntu
source tag with nothing else changed, tried through vip-boot's slot machinery (slot b promoted,
slot a keeps the stock kernel) and recorded in `devices/vip/components.lock`. rtpi owns the
whole loop now: `make vip-rt` (build; `config/vip-numa-emu.fragment`, rtpi `b1736c4`),
`make vip-install-rt`, `make vip-try`. Full record:
[bench-results/vip-card/vip-numa-emu.md](bench-results/vip-card/vip-numa-emu.md).

Emulation activates only with `numa=fake=N` on the command line, which the bootloader's own
default cmdline supplies (`numa=fake=4`; the stock kernel logs "Malformed early option 'numa'"
and boots on). The module trim is live too: **vip's default kernel is now
`7.0.0-1017-raspi-realtime-numaemu1-trimmed`** (109 modules instead of 6,646, rtpi `c5e4a2b`),
slot b; the stock kernel is the fallback in slot a; the full `-numaemu1` build stays installed
on the root but holds no slot. Full record:
[bench-results/vip-card/vip-numa-emu.md](bench-results/vip-card/vip-numa-emu.md). The only
follow-up still open: folding the rebuilt kernel into the image build if emulation proves worth
keeping. Nothing is pushed (rtpi `c5e4a2b`, `955c2b9`, `b1736c4` and this entry are local).

**The app can be its own device** (2026-10-02). ljoss has **Connect to this computer**: it runs
`namchaind` as a child of the app, captures from a CoreAudio **input device** (or loops a WAV) and
plays through an **output device**, both chosen by UID in Settings → Hardware. While it is on, the
host/port/token fields and both Connect buttons are disabled — and they show the *stored* device, not
the loopback session, so nothing can write `127.0.0.1` and a local token over the board's
configuration — and at launch the daemon is started **instead of** connecting to a device. That last
part is the point of the change: the mode used to try the remembered device first, fail, start the
daemon and leave the session behind the failure it had just shown.

It needed the engine first, and the engine needed two things nobody had noticed because everything
used the default device:

- **`--device <UID>` had never resolved a UID.** `kAudioHardwarePropertyTranslateUIDToDevice` refuses
  every size this code can offer it on macOS 27 (`kAudioHardwareBadPropertySizeError`), including the
  size of `AudioValueTranslation` itself, and the one refusal test passes a deliberately bogus UID —
  which fails the same way a working call refuses a bad string. UIDs are matched by enumeration now,
  which is what live input cannot do without (there is no default *input* to fall back on).
- **The parked backend played the last period N times** when a callback carried more than one: one
  shared scratch vector, popped once per period and read for every period. This machine's probe sees
  512 frames and the stream's IOProc is handed 1024, so every other half-buffer was a repeat. An
  underrun also wrote nothing, leaving the previous callback's audio in the device buffer.

Landing on `main`, in dependency order: namchain `8535d2f` (the affinity calls are Linux's, so main
did not build on a Mac at all), `8f90644` (the parked CoreAudio + loop backends, rebased),
`2620aa2` (the multi-period, underrun, message and reported-bound defects above), `7f1eedc`
(`--input-device`, and a **private aggregate device** when the input and output differ — two devices
have two clocks and the engine has no resampler, so the HAL follows the output and resamples the
input); ljoss `0c077b3` (the mode, the pickers, the disabled device fields, the launch order, the
microphone entitlement) and `0564aa5` (the recording below, and what it does not cover). Both local
`local-engine` branches now point at their `main`. That was `git branch -f`, not a literal rebase, and
deliberately: main already carries the parked work in rewritten form, so replaying the parked commit
could only have resolved every hunk in main's favour and ended at the same commit with a duplicate of
the finished work beside it. The parked commits stay at `origin/local-engine` and in the reflog.

Verified on the Mac (SSL 2+ Mk II, 8 in / 6 out): app → `namchaind --backend coreaudio
--input-device <SSL> --capture-channels 2 …` as its child, `engine.status` health ok with the
measured 512-frame period, 2 in / 6 out, **0 xruns**, `live_input: 1`, and the daemon publishing the
app's rig (generation 1); quitting the app stopped the child. The WAV-loop form ran the same way
(`live_input: 0`, `loop_wraps: 4`), and the aggregate path by hand (SSL in, built-in speakers out:
`aggregate_device: 1`, 0 xruns, no aggregate left behind). **The capture is signal, not the silence a
refused microphone would give**: three seconds recorded from the built-in mic through the daemon is
143,872 samples, peak 0.10, RMS 0.015, none of them zero (playback correctly all zeros with no
document loaded). **Reusing a token works**: with a daemon already listening on the app's port with
the stored token, the app started no second daemon, the rig still reached the engine, and quitting the
app left that daemon running. ljoss's `./Tests/run-model-tests.sh` passes (328 assertions) and the
app builds clean. On Linux in colima, namchain main builds and **4 of 5** ctest groups pass;
`ctl_cli` fails only because `chmod` on a Unix socket over colima's virtiofs mount returns `EINVAL`
(proved with a three-line probe), not because of anything here.

**Latency: real-time scheduling and the device's own buffer** (2026-10-02). The mode played
correctly and arrived late — about 36 ms — and the budget was measurable rather than mysterious. On
this Mac the SSL 2+ Mk II reports a 512-frame IO buffer (10.67 ms at 48 kHz), 74+74 frames of input
safety and latency (3.1 ms) and 14+14 output (0.6 ms); the engine waited about a period on the capture
side and primed the output ring with **two periods** of cushion, which is where the rest went. So the
period is the thing to shrink, and two engine changes make a small one safe and selectable:

- **macOS gets real-time scheduling, and it is verified rather than assumed.** `src/rt/scheduling.cpp`'s
  non-Linux half was a stub that said so, so the render thread ran as ordinary work. It turns out
  `pthread_setschedparam(SCHED_FIFO)` *does* work for an unprivileged macOS process — the Linux route
  needs root, this one does not — and `pthread_getschedparam` reads it back, so the report is a reading
  (`SCHED_FIFO priority 60`, `rt_policy 4`). On top of it the thread takes a
  `THREAD_TIME_CONSTRAINT_POLICY` window sized to the audio period: the configured ceiling at start-up,
  then the device's measured period as soon as `open_device` knows it. Three macOS 27 behaviours were
  measured, not assumed: a further `pthread_setschedparam` answers `EINVAL` once a window is in force,
  so the call is skipped when the thread already holds what was asked for (the daemon re-applies on
  every device open — and a window in force means the *priority* can no longer be changed at all, which
  is now a test); the mach timebase conversion is the opposite of the way it reads
  (`ticks = ns * denom / numer`, or the `uint32_t` overflows and the kernel answers
  `KERN_INVALID_ARGUMENT`); and macOS accepts the window then reports it back as the default, so the
  report says "accepted, and these are the numbers asked for" instead of claiming to have read it. A
  daemon asked for nothing still reports priority 0, not Darwin's 31.
- **`--device-buffer-frames N`** (config key `device_buffer_frames`) asks the device for an IO buffer
  of N frames, applied after the stream device is chosen and *before* the period is probed — the probe
  measures what the callback is handed, which is what this changes. The request is checked against the
  device's own range and **read back** into `backend_diagnostics.device_buffer_frames`, so a device
  that clamps to 512 is not described as running at 32, and the value the device had is **put back in
  `stop()`**, because leaving somebody's interface at 32 frames is not this tool's decision. A crash in
  between leaves it set; that is the price of writing a device property at all.

ljoss `d9ad735` sends `--device-buffer-frames 32` (0.67 ms) and `--rt-priority 60` in place of
`--rt-priority 0`, offers 0/32/64/128/256/512 in a **Device buffer** picker with the frame count and
its milliseconds, and explains in the footer which number is a request and which is a ceiling — the
Audio row shows the period the device actually gave. The two new keys are missing from every settings
file an earlier build wrote, and the synthesised `Codable` decoder throws on that, which the store's
`try?` would have turned into the *default* settings: the mode off and the user's interface forgotten
on the first launch after the update. Decoding is lenient now, with a test that loads a file from
before the keys existed.

Verified on the Mac: `--device-buffer-frames 128` on the built-in speakers opened at
`period_size 128`, `realtime: true`, `rt_policy 4`, **0 xruns**, and the buffer was back at 512 after
the daemon stopped; the log showed both promotions (a 21,333 µs window from the 1024-frame ceiling,
then 2,667 µs from the measured 128). At **32 frames with a model loaded** the stream held for 14 s at
`period_size 32`, **0 xruns**, `render_degraded: false`, and the speakers' buffer went back to 512.
namchain's ctest is 5/5 (318 cases, including a hardware-free macOS case for the policy, the window
and the `EINVAL` skip) and ljoss's tests pass. Expected monitoring latency at 32 frames: about
0.67 ms of capture, 1.33 ms of output cushion and the interface's own 3.7 ms — roughly **6 ms**,
against 36 ms before. The SSL itself was not asked to open at 32 by hand (ljoss's own child was
already live on it), so what is verified for *that* interface is its reported range (15..4096, which
contains 32) and the mechanism on two other devices; the Audio row is the place the result shows up.

**Open:** nothing is pushed (both repos are committed on `main`, local only); vip still runs the
engine from 2026-10-01 (`2e1a63a`) and these commits have not been deployed, which is where the
pedal's own next step would start; the microphone prompt itself was never seen on this machine (the
grant was already in place), so the refused-microphone path — silence, by design — is untested by
hand; and the recording above is of a daemon started from a shell, not of the app's own child (the
daemon's `record_dir` default is a Linux path the app does not override), so for the app the evidence
is the device opening and the stream running, plus the entitlement it carries.

**Multi-core rendering, done and reported** (2026-10-02). namchain's M4 is built: `render_threads`
shares a document's chains over a block-synchronous pool, one core by default and **bit-identical**
to it, with the per-core model budget to match — namchain `69b5b54`, `6ca4324`, `cf7aa84`, developed
and tested on **piv** against the `all-optimisations` NAM core
(`rikkus/OptimisationWorkOnNeuralAmpModelerCore`, `f5c48d1`). It works where there are chains to share:
two A2-Full chains go from p99 15% to 8%, and under memory pressure the two-core render holds the
deadline where the one-core render misses it four times a minute. **It does not help the pedal's
heaviest rig, and that is the finding that matters:** the Ambient Wash's two amps are *in series on
one chain*, so there is nothing to overlap, and the rig is comfortable on one core anyway (p99 ~14%).
The failure that motivated the work was measured on a busy vip and is **withdrawn**; the figure is
corrected in `namchain/docs/daemon.md`. Plan and findings: [docs/multi-core.md](docs/multi-core.md);
measurements, method and advice:
[bench-results/2026-10-02-multi-core-piv.md](bench-results/2026-10-02-multi-core-piv.md).**

**vip** (arrived): `docs/vip-image.md` step 1 is done, the spike card proved the boot layout on
vip unchanged (`bench-results/vip-spike/results.md`). Step 2 is done too: rtpi's `vip-boot`,
tested off the board and on vip (`bench-results/vip-spike/vip-boot.md`). Step 3 is done:
`devices/vip/`, with `namchaind` on the WM8960, which is wired to vip and comes up as clock master
(`bench-results/vip-spike/codec.md`). Steps 4 and 5 are done: `devices/vip/make-card` builds the card from `devices/vip/image.lock`
(bit-identically), and vip boots from a blank card onto WiFi, playing, `check` green
(`bench-results/vip-card/results.md`). Steps 6 to 8 are done, so `docs/vip-image.md` is finished: every fallback rehearsed on vip
(`bench-results/vip-card/fallbacks.md`), `devices/vip/make-card --remote` reimages vip from the Mac
through rescue (`bench-results/vip-card/remote.md`), and **vip is the Core host**: every script
defaults to it, `components.lock` is per host (`devices/<host>/components.lock`), and
`scripts/deploy-engine` builds the engine for vip on the Mac. vip runs image 20260930T220004Z
(pedal 438a71f, rtpi bae26dc) with namchain 2e1a63a deployed by `deploy-engine` (meta and bypass as a ramp, 2026-10-01). namchain f422dd0
plays a missing model or IR as a bypass, and ljoss 5da4ea6 marks the block.

**Rig edits** (`docs/rig-edits.md`, 2026-10-01): steps 1 and 2 are built, and `meta`. namchain
`2b5584e` keeps a client's `meta` on the document, chains and nodes; `2e1a63a` ramps a bypass
instead of rebuilding (feature `bypass_ramp`); ljoss `d57933d` needs no patch op for it. 2e1a63a
is deployed to vip, and ljoss's `Tools/check-streaming.sh` passes against it: a 201-step drag of
three knobs as 580 ramps, a bypass with no rebuild
(`bench-results/2026-10-01-check-streaming-vip-2e1a63a.txt`). Open: the two-amp
Ambient Wash fails the gate on vip by itself at q64 (vip soak item 3, "Measured steady").

**Testing happens on vip for now** (decided 2026-09-30), until it's a working pedal that shouldn't
be disrupted; then the test hardware gets chosen again. **That moment has arrived (2026-10-04):**
vip is the assembled pedal the owner plays, wired into the case, with the Pico on its USB-A and the
link running — so the next thing that needs a test host (2b's breadboard, a soak, a kernel try) either
waits for a window the owner grants or goes on other hardware, and the choice of that hardware is
open again. piv isn't updated meanwhile, except that it
runs namchain d4fb8e5 since the 2026-09-30 step 8 soak (Rik asked for it); and `devices/piv/check` reports `pedal-codec` and `pedal-device` as differing
(they moved to `devices/common` and changed). The piv phases below wait on that choice.

Phase 1 on piv, on the SSL 2+. Steps 3–6 are done. Step 7 is measured on vip (its own note in
Phase 1) and at the jack, leaving only the power-on instant: the pedal is audible 21–22 s after
the bootloader's first byte on a plug pull, and the engine's `published` agrees within a second.
1. ~~The step 8 soak at q64~~: done 2026-09-30 with `scripts/soak/soak-replay` and the rebuilt
   ljoss session, PASS (step 8 in Phase 1 has the numbers).
2. ~~Then the same soak with only the rsync, to isolate WiFi's cost~~: done 2026-09-30, 18:50–19:50,
   `scripts/soak/soak-replay --idle --sync-library-at 1800`: no edits, one `sync-library` at 30 min
   over home WiFi (the library was already in sync, so mostly rsync comparing file lists). PASS.
   | piv, Crunch Lead, q64, d4fb8e5 | load p50 / p99 / p99.9 | worst block | blocks ≥ 30% |
   |---|---|---|---|
   | idle, no edits or sync (16:52, `soak-idle-piv`) | 6% / 16% / 20% | 36% | 37 |
   | sync only (`soak-sync-only-piv`) | 6% / 17% / 20% | 34% | 8 |
   | ljoss session replayed, plus sync (`soak-replay-…`) | 8% / 24% / 36% | 85% | ~13,000 |
   All three: 0 xruns, overruns, guard trips. The sync costs nothing measurable; the tail is the edits'
   (rebuilds and ramps), not WiFi's.
3. **The same three soaks on vip, with the WM8960** (2026-10-01; namchain d4fb8e5, q64, vip's image
   with the tuning as built: cores 2-3 isolated, the codec's DMA interrupt on core 2, 2.4 GHz —
   that pin is core 0 since P7; `docs/audio-dma-irq.md`, "Which core it lands on (P7)").
   `soak-monitor.sh` reads the thermal zone and the core clocks there (vip has no `vcgencmd`).
   | vip, Crunch Lead, q64, d4fb8e5 | load p50 / p99 / p99.9 | worst block | blocks ≥ 30% | gate |
   |---|---|---|---|---|
   | idle, no edits or sync (`soak-idle-vip`) | 6% / 12% / 20% | 38% | 20 | PASS |
   | sync only (`soak-sync-only-vip`) | 6% / 13% / 21% | 39% | 67 | PASS |
   | ljoss session replayed, plus sync (`soak-replay-2026-09-28-ljoss-vip`) | 8% / 23% / 36% | **94%** | 9,981 | **FAIL** |
   All three: 0 xruns, 0 overruns, 0 guard trips, no queue drops; 48-53 °C and every core at
   2.4 GHz throughout, so vip doesn't throttle at its clock cap with no heatsink. The replay fails
   on **two blocks past 90% (92% and 94%)**, both beside rig rebuilds 17 and 27 s into the second of
   the session's three loops; the same rebuilds in the other two loops stayed under. So the same
   load as piv's (p99 23% against 24%), and the same cause as soak 1's overruns: a structural edit
   renders both plans for the fade, and at q64 a rebuild of these rigs lands near the line and
   occasionally just over it (piv's worst was 85%). Not WiFi, not the sync, not the codec.
   - Two runs didn't count: the first replay was cut 22 min in when the Mac's VPN connected with
     local network sharing blocked, and the first sync-only hour lost its sync when the 1Password
     SSH agent locked (it stands as the idle row).
   - What to do about the rebuild peak: of admission control, q128, or ljoss sending fewer rebuilds,
     you chose the last (2026-10-01). The two blocks were an amp added and an amp removed, and every
     knob was already a ramp, so ljoss has nothing left it could send differently. The saving has
     to come from namchain doing less per structural edit: it recreates every node of the chain
     and runs both whole plans for the fade. `docs/rig-edits.md`, "Claude's replies, 2026-10-01",
     proposes carrying unchanged nodes across, so that only the changed block fades. It also
     answers C4 (bypass as a ramp), the tree-to-graph question and unknown keys. **Decided
     2026-10-01:** build it; the conversion stays in ljoss (a); unknown keys go in a `meta` object
     (not built yet).
   - **Built and rerun, PASS** (2026-10-01, 20:33–21:34 UTC, namchain 974060c, `deploy-engine`; the
     same session, sync at 30 min; `soak-replay-2026-09-28-ljoss-vip-local`):
     | vip, Crunch Lead, q64, 974060c | load p50 / p99 / p99.9 | worst block | blocks ≥ 30% | gate |
     |---|---|---|---|---|
     | ljoss session replayed, plus sync | 8% / 20% / 34% | 84% | 6,869 | PASS |
     18 structural edits: 12 local (each faded 1 or 2 inputs, kept 10–18 nodes), 6 crossfades (the
     rig switches, which change the input or output node). `local_base_mismatches` 0; 0 xruns,
     overruns, guard trips, queue drops; 48–52 °C, 2.4 GHz throughout. Highest block in each
     10 s monitor interval holding the second amp's add / remove, per loop: 70/84%, 71/70%, 77/67%
     (soak 1: 92% and 94%). Ambient Wash's own intervals with no edit reach 40–67%; rig switches
     21–48%. The 84% interval holds the two-amp rig playing as well as the removal, which creates
     nothing, so it is likely the two-amp rig's own peak. Offline numbers are in namchain's
     `docs/transitions.md`, "Measured offline".
   - **Measured steady** (2026-10-01, 10 min each, no edits, namchain 974060c;
     `scripts/soak/sessions/ambient-wash-{one,two}-amp-steady.session.jsonl`,
     `steady-ambient-wash-{one,two}-amp-vip`):
     | vip, Ambient Wash steady, q64 | load p50 / p99 / p99.9 | worst block | peak per 10 s interval | gate |
     |---|---|---|---|---|
     | one amp | 8% / 22% / 36% | 60% | 34–60%, median 48% | PASS |
     | two amps | 15% / 46% / 67% | **98.9%** | 63–98%, median 79% | **FAIL** |
     Both: 0 xruns, overruns, guard trips, queue drops; 49–53 °C, 2.4 GHz. So step 1 is done: the
     second amp's add and remove (70–84%) sit at or below the two-amp rig's own load. But **the
     two-amp rig fails the gate by itself**: 7 blocks over 90% in 10 minutes, 6 of them nowhere
     near an edit, and 27 of 63 intervals peak at 80% or more. The replay soaks passed only because
     they play it for a few seconds per loop. It is the heaviest rig in the session (two A2 amps,
     the feedback delay, reverb); at q64 on vip it has no headroom. Not decided: q128 for such
     rigs, admission control refusing them (step 3 in `docs/rig-edits.md`), or finding where its
     peaks come from first (its median block is 15%, about 200 µs, and its worst 1.3 ms: the
     trouble is the tail, not the mean).
   - **Where the peaks come from** (2026-10-02, offline on vip's core 2, namchain 2e1a63a;
     `bench-results/2026-10-02-two-amp-tail-vip/results.md`): **memory**. Each amp is A2-Full
     (8 channels, 23 layers, about 450 KB of ring buffers), and two of them don't fit in a core's
     512 KB L2. So each block reads from the L3 and DRAM the other cores share, and the tail is
     whatever else on vip touches memory. A `dd` on core 0 doubles the rig's median. Each amp
     alone has p99 about 20%, both together 53%; flat out (no wait between blocks) the rig's p99
     is 26%, paced 59–76%. Not the cab IR (cut to 2048 taps: no change) and not the block size
     (q128: median unchanged, worst block still 92%). Two A2-Lites peak at 55%; Full + Lite at
     98% on core 2, which runs harsher than the live engine's core 3, so that needs a live soak.
     Not decided: the choice now is between a cost rule that refuses (or downgrades to Lite) a
     second A2-Full on one chain (admission control, rig-edits step 3, with E2's Lite tier), and
     engine work to shrink A2-Full's working set. q128 is ruled out as the fix.
