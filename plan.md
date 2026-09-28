# Plan

**Written:** 2026-09-23. It replaces the bootstrap plan: read `about.md`, design a way of working
across the repos, ask questions, write this. The repo strategy that came out of it is
[docs/working-across-repos.md](docs/working-across-repos.md). The questions and your answers are
recorded under **Decisions**.

**First target:** play guitar through `tib` using the SSL 2+ that is already attached, with ljoss
editing the rig live over WiFi, and the pedal coming back with the same rig after a power cycle.

> **2026-09-26: `tib` is retired.** It stopped working on 2026-09-25. The Core host is now a
> Raspberry Pi 5: **piv** (Pi 500) stands in for the next few days, then **vip** (a Pi 5 with
> 1 GB, on order) becomes the target. Read "`tib`" in the phases below as "the Core host". What
> changes is under [The Core host moves to a Pi 5](#the-core-host-moves-to-a-pi-5).

---

## The Core host moves to a Pi 5

**vip** (Raspberry Pi 5, 1 GB, aarch64) is the Core target once it arrives. Until then, **piv**
stands in. The Pi 500 has the same SoC (BCM2712, 4 × Cortex-A76), so piv's performance numbers
should carry over to vip. What won't carry over is memory: vip has 1 GB, and piv has more.


piv is a Raspberry Pi 500 (Cortex-A76, 4 cores, **aarch64**). Checked 2026-09-25:

- Ubuntu kernel `7.0.0-1017-raspi-realtime`, **PREEMPT_RT**.
- Cores **2–3 isolated** (`isolcpus=managed_irq,domain,2-3 nohz_full=2-3 rcu_nocbs=2-3`,
  `irqaffinity=0-1`). `tib` isolated only core 3.
- SSL 2+ attached 2026-09-26 as card id `II`, through a hub on the xHCI controller whose interrupt
  is `xhci-hcd:usb4`. Since 2026-09-28 it's direct, on a new cable, in the USB 2.0 port
  (`xhci-hcd:usb2`, with the SSD): the old cable corrupted packets (Phase 1 step 5, "Pops"). Root storage is on the other one (`usb2`). rtpi-audio-tune now finds the
  controller from the interface's USB id (rtpi `04b8a98`); before that fix it was pinning the
  disk's interrupt to core 2.

What this changes:

- **Build.** namchain builds and tests natively for aarch64 on piv already, and the planar NEON
  kernels are active there, so the armv7 cross build and qemu step leave the critical path.
  `scripts/deploy-engine` gets an aarch64-native target. The armv7-NEON path is no longer
  needed now that `tib` is retired.
- **piv is no longer "allowed to be busy or down"** (`docs/working-across-repos.md`). Building on
  the host that plays audio disturbs it: no builds on piv during a soak or while playing, and the
  Mac (colima) is the fallback builder.
- **Device configuration.** `devices/tib/` was written for `tib` (core 3, the RK3288 clock cap,
  its interrupt layout). piv gets its own `devices/piv/`: render thread on core 3, core 2 free for
  the audio interrupt or a second chain, its own thermal and clock policy. Take `tib`'s last
  backup as the reference; don't copy it blind.
- **Performance numbers.** Every `tib` figure (A2-Full ~53–58%, cab p99 9–10%, A2 + cab p99 70%)
  is from a Cortex-A17. The A76 is much faster per clock, so re-measure A2-Full and A2 + cab on
  piv before relying on anything. The "A2-Full alone overran" question for step 8 was about
  `tib` and is dropped.
- **Memory.** vip's 1 GB is new as a constraint. Measure `namchaind`'s resident size with a full
  rig loaded, and with models held ready for switching, while still on piv.
- **The hard constraints in `CLAUDE.md`** have been rewritten for a Pi 5 Core host. Phase 1 needs nothing Pi-specific, since it uses the SSL 2+
  over USB.
- **Phase 2 goes on a Pi.** The WM8960 goes on the 40-pin header, where Pi overlays apply.
  rtpi's RK3288 device tree plan is dropped. The Pi's stock `wm8960-soundcard` overlay assumes
  the Pi supplies clocks, so check it (or write a small overlay) to keep the codec as clock
  master with a 24 MHz MCLK. Do the bring-up on vip, or on piv if vip is late.
- **Phase 3.** The Pico's UART goes to piv's header UART instead of `tib`'s UART1 on pins 8/10.
  The protocol doesn't change.
- **Device configuration moves on again when vip arrives:** `devices/vip/`, with piv's as the
  starting point. piv then goes back to being the build host.
- **Debt, for the next few days only.** While piv is the Core host, it isn't a build host that's
  "allowed to be busy". This ends when vip arrives.

**Open:** which repo owns vip's kernel and boot configuration. piv runs Ubuntu's
`raspi-realtime` kernel, not rtpi's. `tib`'s last config backup stays in `devices/tib/backups/`.

## Where things stand

### Against the goal in `about.md`

| Goal | Today | Gap |
|---|---|---|
| Entirely digital effects | namchain renders NAM, cab IR, EQ (bands, tilt), cut filters, feedback delay, gain and lane mixing: 11 primitives and 7 macros. 27 of ljoss's 102 blocks map onto them | Nothing required for your own use (D7). The rest stay badged "unavailable" in ljoss |
| A rig document becomes a virtual rig | ljoss encodes rigs and drives `namchaind` over TCP (protocol 2, token), proven against a daemon on macOS | Never run on `tib`. `namchaind` isn't installed there |
| External MIDI controller | The MIDI Commander (USB and DIN out, your own firmware fork, its own two expression inputs sending CC11/CC4) | All of it: the DIN input on the Pico, the UART link, and mapping MIDI onto rigs |
| Very low noise | Analogue design drafted in `docs/hardware-handoff.md`. `tib` currently uses the SSL 2+ | WM8960 in hand, inspected from photos (stock); input R/C mapping not yet checked. Analogue parts not bought. No noise-measurement method yet |
| NAM models | One A2-Full on `tib` at q64: p99 ≈ 58.5% of the deadline, 0 xruns over an hour (`namchain/bench-results/tib-summary.txt`) | The NEON build behind that number isn't committed. Models load when a rig compiles, not held ready for switching. Switching crossfades; warm start is namchain's M3 |
| IR | `nc.cab.ir` convolves the **whole** IR directly (`nam::Linear`, no length cap), and refuses any IR that isn't at 48 kHz because there is no resampler | **This blocks an amp + cab rig on `tib`.** Your library is mostly 500 ms files (about 24,000 taps), and two thirds of it is at 44.1 or 96 kHz. NAMBench measured direct convolution at 8,192 taps costing 42% of a `tib` core; your partitioned-FFT branch costs 5.3% on average, with a p99 of 21.7%. Beside A2-Full's ~58%, direct doesn't fit one core. namchain's own IR cost on `tib` is unmeasured |
| Immune to glitches | PREEMPT_RT with core 3 isolated, clean hour-long soaks, crossfaded edits, per-node guards | Not yet shown under WiFi and app traffic, on the codec, through boot (no bypass yet), or across power loss (SD card) |

### Repos, machines and documents (surveyed 2026-09-23)

- **namchain** on the Mac is at `origin/main` (`9e9d947`) plus uncommitted CoreAudio and loop
  backends: 12 modified files and 7 new ones, including a new, untracked block diagram. piv's
  checkout is 4 commits behind.
- **ljoss** is checked out as `~/code.local/nodey`. It has one unpushed commit and about 30 files
  of LocalEngine and model-library work in progress. piv's copy is stale at `7618314` (11 Sep).
- **tib** runs kernel `7.2.6-tib1` PREEMPT_RT with core 3 isolated, the SSL 2+ attached, on WiFi
  only. Its namchain binaries are from 16 Sep, before TCP, schema, assets and macros existed. There
  is no `namchaind` and no compiler.
- **tib's audio device moves**: the SSL 2+ has been card 2 and card 1 on different boots, and
  `alsa_raw` only accepts card *numbers*.
- **tib has one I2S controller, and HDMI audio holds it**: a `simple-audio-card` named
  `rockchip,tinker-codec`. The WM8960 card has to take it over.
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
| D1 | First target: play through `tib` with the SSL 2+, with ljoss over WiFi | you | Phase 1 comes before the codec and the Pico |
| D2 | ljoss talks to `namchaind` on `tib` directly over WiFi. The Pico does physical controls only | you + recommendation | No app traffic over the UART. WiFi load gets soak-tested. Pico WiFi stays possible with a Pico 2 W (see Shopping), but it would never carry rigs or models |
| D3 | Rigs, models and IRs are stored on the pedal. It resumes the last rig, with its models, at power-up, and changes rigs with no app connected | you | A rig library on the device, a path for uploads, resume, and models held ready for fast switching |
| D4 | A **pedal service** beside `namchaind`, in this repo, owns the rig library, resume, uploads and the footswitch/MIDI mapping. namchain stays a generic engine | you | namchain's only new job is keeping models loaded and ready (plus any small hooks the service needs) |
| D5 | Mic input: leave room, build later | you | Reserve a panel position and the codec's right input (RINPUT1) |
| D6 | MIDI arrives as 5-pin DIN into the Pico, through an optocoupler | you | The MIDI Commander needs its own power (the DC7's USB-A). USB MIDI goes in the debt register |
| D7 | No new DSP is needed before the pedal is usable | you | Effects work is off the critical path |
| D8 | Bring the codec up stock, then modify it, measuring before and after | proposed | `CLAUDE.md`'s "differs from stock" becomes "planned modifications" |
| D9 | Work across repos as set out in `docs/working-across-repos.md` | proposed | Phase 0 |
| D10 | Every rig one interaction away is held ready: the current bank (the 4–8 rigs the footswitches step through) plus any rig MIDI can jump to. A switch takes **≤ 50 ms** from footswitch or MIDI to the new sound, crossfaded, with **no dropout and no click** | you, 2026-09-26 | 3.8 is required, not optional, and comes before 3.5. namchain's M3 (warm start) moves onto the critical path. Whole rigs are held ready: compiled plans, loaded models and prepared IRs. vip's 1 GB bounds the bank. *How* each rig is kept ready is a tier (`docs/rig-switch-strategies.md`), set by experiments E1 and E2 |

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
     `docs/hardware-handoff.md`: arrival status, the note that a Pi could stand in for `tib`, the
     schematic path, and your note about keeping the diagram's formatting.
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
   gate. Verified on piv: 261/261 tests pass and the parity test runs. The committed armv7 build (`-mfpu=vfpv3-d16`)
   can't run A2-Full in real time on `tib` at all: 133% of a core, against 52% with NEON
   (`bench-results/tib-summary.txt` §1–2).
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
   (piv only, native aarch64; tib's cross build went with tib) and `scripts/sync-library` came
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

## Phase 1 — Play through tib

On piv until vip arrives (see [The Core host moves to a Pi 5](#the-core-host-moves-to-a-pi-5)). Steps 1 and 2 were done on `tib`; step 2's
numbers need re-measuring on piv.

1. **Open devices by name** (namchain). `alsa_raw` resolves `hw:CARD=<id>` or `hw:<id>,<dev>`
   through `/proc/asound/<id>`, so a reboot can't point the engine at the wrong card. This is
   needed for the WM8960 too.
   Done 2026-09-25 (namchain `412e151`). On `tib` the SSL 2+'s id is `II` (ALSA takes it from
   "SSL 2+ Mk II"), so the config names `hw:CARD=II,DEV=0`.
2. **Make an amp + cab rig fit on `tib`** (namchain).
   Done 2026-09-25 (namchain `79939b4`). `nc.cab.ir` now uses `PartitionedConvolution` from your
   AudioDSPTools fork at `b505422`, with all three NAMBench optimisations. The core's `nam::Linear`
   it replaced was already a partitioned FFT, but without the spreading. On `tib` at 1.416 GHz, a
   full-length cab alone is p99 9–10% of a 64-frame deadline (it was 111%), and A2-Full plus the cab
   is p99 70% (was 168%). It also resamples 44.1/96 kHz IRs and caps them at 8192 taps, as the
   plugin does, less the plugin's −18 dB. Numbers: namchain `bench-results/tib-cab-ir.txt`.
   **Partly undone 2026-09-26** (namchain `04a1fc8`): you deprecated the AudioDSPTools fork, and it
   was gone from GitHub, so a clean clone couldn't build. `nc.cab.ir` is back on the core's
   `nam::Linear`; the resampling, the 8192-tap cap and the `.nam` path stay. On piv at q64,
   A2-Full + full cab went from p99 8.7% to 15.4%, with 0 overruns. At q32 it's 24% with 5
   overruns a minute, and a few ~1 ms blocks appear with either convolver, cause unknown
   (namchain `bench-results/piv-cab-ir.txt`). On `tib` this brings back the 62%-at-8192-taps
   problem: see the debt register.
   **For step 8:** A2-Full *alone* overran 7–9 blocks in 30 s today, where the same load ran a
   clean hour on 16 Sep. `tib` is noisier than it was; find out why before the soak.
   Checked 2026-09-25: the kernel's isolation of core 3 is intact, and the journal shows nothing
   else running during those runs. But they ran back to back for ~9 minutes with no cool-down and
   no temperature recorded, the userspace confinement from namchain's host-slim had decayed, and
   the clock cap was set by hand for each run. `devices/tib/` now owns all of that (it replaces
   host-slim, caps the clock at boot, confines services and logins to cores 0–2, and moves the
   audio interrupt to core 2 at priority 85). Before step 8, rerun A2-Full alone from cool, with
   `sudo pedal-rt`, and record temperature and throttle state (`pedal-tune check` prints both).
   - First, measure `nc.cab.ir` on `tib` at your library's real lengths.
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
   - `namchaind` and `namchainctl` go to `tib` through `scripts/deploy-engine`.
   - Install the systemd unit and config under `devices/tib/`:
     - `alsa_raw` on the SSL 2+ by name, render thread pinned to core 3
     - `Slice=pedal-rt.slice` (the only slice allowed on core 3), `LimitRTPRIO=95`,
       `LimitMEMLOCK=infinity` (a service doesn't get `limits.d`)
     - start from the settings `tib`'s soaks used (quantum, periods, output-queue cap)
     - TCP on the LAN with a token from a file.
   - Give `tib` a fixed address (a DHCP reservation) or use its mDNS name, because ljoss has no
     discovery.
4. **Library on the pedal.** Rsync the models and IRs your rigs use into `tib`'s library folders,
   no conversion needed: `nc.cab.ir` resamples 44.1 and 96 kHz IRs itself (step 2).
   Done on piv 2026-09-26: `scripts/sync-library` mirrors `~/Documents/Audio/NAM` and `IRs` (53
   models, 1,538 IRs, 157 MB) into `/var/lib/pedal/library/{models,irs}` and asks the engine to
   rescan. That settles the open question of where data lives, for now: `/var/lib/pedal/library`.
5. **ljoss → tib.**
   - Point ljoss's Hardware settings at `tib`, and run `Tools/check-device.sh` against it.
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
     - The check, for next time: `wire-test.sh` and `wire.py` in `scripts/usb-audio/`. The SSL is
       now on piv's USB 2.0 port, which shares its xHCI controller with the root SSD (both
       interrupts are on core 2 at FIFO 85).
6. **Resume at power-up (pedal service v0).**
   - A small process polls `engine.status`. When the generation changes, it saves `rig.get`'s
     document atomically into the rig library.
   - `namchaind` starts that document at boot. It already compiles and prewarms a startup rig
     before the clock starts.
   - Whether the service stays beside `namchaind` or later fronts it for the app is left to 3.2.

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
   First number for step 7: the rig was published and the render thread running **13.2 s** after
   the kernel started (userspace reached multi-user at 25 s; firmware and bootloader time before
   the kernel not counted).
7. **Measure what D3 needs:**
   - how long `rig.apply` takes on the Core host, from the command to hearing the new rig, with
     its NAM and IR: the **cold-switch baseline** that 3.8 has to beat to reach D10's 50 ms
   - power-on to sound (13–14 s from kernel start to a running rig on piv, 2026-09-26; firmware
     time and the first audible output still to add).
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
8. **Soak it the way it will be used.** An hour through `namchaind` with an A2-Full + full-length
   cab IR rig, holding the Core host's lock, with ljoss editing over WiFi and one library rsync in the
   middle.
   - Gate: 0 driver xruns, 0 deadline overruns and 0 guard trips, with the worst block inside
     namchain's ARMv7 bar of 90% of the deadline.
   - Separately: the same soak with only an rsync running, so WiFi's cost, if it has one, is
     isolated.
   - Once 3.8 exists, the soak also switches rigs: a switch every few seconds through a bank, with
     the same gates plus D10's: each switch ≤ 50 ms and no click in the output (namchain's glitch
     detector on the captured output).

**Done when:**
- From power-on, `tib` plays the last rig (an A2-Full amp and a full-length cab IR) through the
  SSL 2+ with no app connected.
- ljoss on the Mac edits it live.
- An hour of playing and editing is clean.
- `components.lock` names what's running.

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
   - VIN from `tib`'s 5 V, so the onboard LDO feeds AVDD with AVDD-ISO intact.
   - 3V3, I2C and I2S from `tib`'s header, on short leads.
   - Settle which I2C bus is on the header, and whether it has separate RX/TX frame clocks (the
     handoff's open item).
3. **Device tree** (rtpi).
   - A WM8960 `simple-audio-card` on `tib`'s one I2S controller, replacing the HDMI card:
     - codec at 0x1A, clock master (`bitclock-master` and `frame-master` on the codec)
     - a 24 MHz fixed clock as its MCLK, so the driver can set its PLL up for 48 kHz.
   - Built with rtpi's check on the built DTB, tried through the one-shot slot, then promoted.
4. **Mixer state as code** (`devices/tib/`): ALC off, 3D off, speaker amp off, OUT3 off,
   LINPUT1 → PGA near 0 dB → ADC, DAC → HP_L/HP_R.
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
     then comes off `tib`'s supply with no cutting, and the board's own LDO becomes a second stage.
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
   LDO.

**2c. Modify and compare.**
- Replace LIN1's 47 nF ceramic shunt with a film capacitor (2b finding), and measure THD against
  frequency before and after.
- First try the option that needs no cutting: VIN from a 78L05 on the 9 V side.
- If that isn't enough, cut AVDD-ISO and fit the external LDO, open SPKVDD and disconnect VIN.
- Measure against 2a, and keep what measurably helps.

**Done when:**
- Guitar → buffer → WM8960 → `namchaind` → output stage → amp works.
- The noise floor is recorded at each stage.
- An hour on the codec is clean.

## Phase 3 — The control surface and the pedal service

1. **Boards and tools.**
   - Pico 2 (see Shopping), and C/C++ with the official Pico SDK on the Mac.
     - It plays to your C++, and it has TinyUSB and PIO built in, so USB host is available later.
     - It debugs through the Debug Probe with the least friction.
     - MicroPython starts faster but is weak at USB host and timing. Rust (Embassy) is excellent
       but a second new thing at once.
   - Blink, then echo over UART through the Debug Probe.
2. **Design the pedal service** (`docs/pedal-service.md`):
   - what it's responsible for
   - beside `namchaind` or in front of it for the app
   - storage layout on the SD card
   - the upload API
   - the event vocabulary where footswitch and MIDI meet
   - security (the same token model)
   - failure modes: the service being down must never mean audio is down.
3. **UART protocol**, the contract kept here.
   - Framed, checksummed and versioned.
   - Events: rig up/down/select, bank, CC value, bypass.
   - State back to the Pico: rig name, health, audio-ready.
   - Heartbeats both ways.
4. **The tib side.**
   - Enable a header UART in rtpi's device tree. The console is ttyS2 on pins 32/33; UART1 on
     pins 8/10 is the obvious one to use.
   - The pedal service reads it.
5. **Firmware v1.**
   - Three footswitches, with 100 nF at each switch, debounce and long-press.
   - DIN MIDI in: optocoupler, UART RX at 31 250 baud.
   - Status LEDs.
   - Everything else goes over the UART.
6. **Bypass relay.** Choose a relay whose **de-energised** state is bypass.
   - Then no power, a crashed Pico and a booting `tib` all fail to bypass.
   - The Pico energises it only once the service reports audio ready.
   - A long press gives a panic bypass.
   - Check for a pop at **power-off**. The relay drops to bypass within a few ms, but the codec's
     output collapses at the same moment, and which wins decides whether it's audible. If it is: the
     Pico watches its supply and drops the relay a little before the codec loses power.
   - The output coupling cap must settle before the relay first engages. 10 µF into ~1 MΩ is
     τ ≈ 10 s, inside the boot; 100 µF (τ ≈ 100 s) would still be charging and pop.
7. **Display and encoder**, low priority per `about.md`. Check it has no onboard LDO before
   powering it (per `CLAUDE.md`).
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
     overruns. The risk in D is not core 2's own load (A2-Full is ~7% of a core on piv, so 8 fit
     in about 60%) but contention for the shared L3 cache and memory bandwidth, which isolation
     can't partition. namchain has measured that kind of interference raising the render p99
     before (`bench-results/tib-nohzfull-summary.txt` §2).
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

**Done when:**
- With no app, the footswitches and the MIDI Commander step through rigs stored on the pedal.
- Changes are click-free, and each takes ≤ 50 ms (D10), through an hour's switching soak.
- The relay covers boot and failure.

## Phase 4 — Enclosure, power and hardening

- **Panel:**
  - the display module's fixed screen/knob/button unit
  - three footswitches
  - IN, OUT L, OUT R
  - MIDI DIN, 9 V, 5 V
  - a reserved mic position (D5)
  - the expression jack only if the debt entry below says so.
- **Power:** 5 V / 3 A for `tib`, 9 V isolated for the analogue side, the star ground.
- **Survive pulled power.** A read-only root (overlayroot) plus a small data partition for rigs and
  models, written atomically. A pedal gets unplugged mid-write, and today one SD card holds
  everything.
- **Heat in the box.** An hour's soak inside the closed enclosure, recording temperatures.
  Uncapped, `tib` hit its 90 °C trip. Capped at 1416 MHz it held 72–76 °C, but it has never been
  measured inside an enclosure.
- **Boot time**, if 1.7 shows the relay isn't enough on its own.

## Tracks off the critical path

- namchain M2: admission control. (M3, warm start, is on the critical path now: D10 and 3.8.)
- DSP when you want it: noise gate, tuner, reverb, compressor, modulation.
- ljoss on iOS: it compiles, but the touch path has never been run.

---

## Debt register

These are restrictions accepted now, with a sketch of how each gets paid off later. You asked for
exactly this: think about them now, fix them after the higher-priority work.

| Restriction | Why it's accepted now | How to pay it off later |
|---|---|---|
| MIDI is DIN only: USB-only controllers won't connect, and the MIDI Commander needs its own power | Simplest, isolated | USB host on the Pico through PIO-USB: two GPIO plus a USB-A socket, which is essentially what the RP2350-USB-A does. The event layer stays transport-agnostic, so this is a firmware change |
| The RP2350-USB-A has 15 GPIO, and the design needs about 18 (display 5–6, encoder and button 4, footswitches 3, UART 2, MIDI 1, relay 1, LEDs 1+, expression 1) | A Pico 2 has 26 | Pico 2 for the control surface, RP2350-USB-A for experiments. If pins run short: footswitches on a resistor ladder into one ADC, WS2812 LEDs on one pin, or an MCP23017 on the Pico's own I2C bus (never `tib`'s) |
| The pedal plans its own expression jack, but the MIDI Commander already has two expression inputs | — | Decide whether the pedal needs its own. If not, drop the jack and its GPIO, since MIDI already carries expression |
| Only program and control changes get mapped at first | Enough to change rigs | A mapping table in the pedal service: PC → rig, CC → parameter (streamed only when `engine.schema` marks it rampable), bank select, notes |
| Mono engine: pan and stereo effects are refused. Two chains give dual mono | namchain decision: declare and refuse | namchain's stereo work, when a stereo effect is actually wanted. The outputs are already two channels |
| The whole rig renders on one core (core 3), and A2-Full alone takes ~58% of it | namchain renders single-threaded. Parallel rendering is its M4, off by default | Two chains on two isolated cores: isolate core 2 too, and admit namchain's parallel mode only once it passes soak and glitch tests. A2-Lite, or slimmed models, where a rig is too big |
| No resampler: models and IRs must already be at 48 kHz | Phase 1 converts IRs on the way to the device | Convert on upload in the pedal service, or resample at load in namchain (the NAM plugin resamples IRs at load) |
| One instrument input | D5 | A mic stage on RINPUT1, and a decision on phantom power (a DC-DC converter beside the ADC) |
| WM8960 replaces HDMI audio on the one I2S controller | Nothing uses HDMI audio | None needed. A second codec would mean TDM or USB |
| No way to upload from the app yet | D4 | The pedal service's upload API. ljoss gets a "send to pedal" action |
| The app needs the home network | Phase 1 happens at home | The pedal as its own access point (check whether `tib`'s WiFi chip can run AP mode), or a phone hotspot |
| No discovery: the host is typed in | — | mDNS from the pedal service |
| Plain-text token, no TLS | Trusted LAN | A tunnel, or TLS in the service, if it ever leaves the LAN |
| `tib` is out of production | `about.md`: reuse what you have | namchain already builds and tests for aarch64, so a Pi 4/5-class board is the replacement path. A Pi Zero 2 W hasn't been measured, and A2-Full already uses about 58% of a Cortex-A17 core, which is faster per clock than the Zero's in-order A53 |
| Everything lives on one SD card | — | Overlayroot plus a data partition (Phase 4) |
| An I2S fault can silence the pedal with no error. On piv (2026-09-27) BCLK was pulled and refitted while `namchaind` ran: it kept reporting `running`/`ok` with 0 xruns, but nothing came out, most likely a lost frame alignment that put the rig on the unconnected channel. Restarting `namchaind` fixed it | The build solders its connections; on the bench, restart `namchaind` after touching the header | A liveness check in namchain or the pedal service: flag an input that has been digitally silent (or DC, or stuck) for a few seconds while the device is running, and reopen the device. Possibly check that the codec's clock rate matches what the Pi receives. The Pico could show it and hold bypass |
| `nc.cab.ir` is back on the core's `nam::Linear` (2026-09-26): every partition multiply lands in one callback. On piv that's p99 15% for A2 + cab at q64; on `tib` it was 62% for the cab alone at 8192 taps | You deprecated the AudioDSPTools fork that spread the work | Spread the multiplies inside namchain, or upstream a partitioned convolver to the NAM core or sdatkinson/AudioDSPTools. Needed for q32, or if vip's soak shows the tail is too close at q64 |

## Open questions

These don't block Phase 0 or 1.

- **Pedal service:** beside `namchaind` (the app keeps its direct connection) or in front of it
  (one endpoint and one token for the app, one extra hop for knob streams)? Decided in 3.2.
- **Where data lives on `tib`:** namchain's default is `/etc/namchain`. `/var/lib/...` is more
  conventional for user data. Decided with the overlayroot design.
- **Rig designers for other platforms** (`about.md`): the engine protocol is where any second
  client would plug in, and `namchainctl` is its reference client. A browser UI served by the pedal
  service would reach every device with nothing to install. Worth weighing before a Qt designer.
  Not before the pedal plays.

## Shopping

Every part, with its CPC order code, price and purpose, is in [docs/bom.md](docs/bom.md).

- **In the CPC basket, not yet ordered (2026-09-24, 41 lines, £117.19 ex VAT):**
  - 2 × Pico 2 WH and the Debug Probe
  - two breadboards (one a spare) and header strips. You already have jumper leads, including the
    female-to-female ones for the WM8960 bring-up.
  - five Neutrik NMJ6HF-S switched TRS jacks: IN, OUT L, OUT R, expression, and a spare
  - the MIDI-in parts. The BOM gives the circuit and its values.
  - everything else that doesn't wait on a decision: the output stage (which 2a's measurements
    need too), power, the relay and its driver, footswitches, LEDs, sockets and stripboard
  - the op-amp: 2 × OPA2197 on SOIC-to-DIP adapters. It's on back order until 4 Oct, so CPC may
    send it separately.
  - the Inst/Line switch and the Line pad's resistors, at provisional values; screened cable and
    hook-up wire.
- **Not designed yet:** the 5 V input, the mic stage, cooling and the enclosure hardware.

## Next session starts with

Phase 1 on piv, on the SSL 2+. Steps 3–6 are done, and 7 except firmware boot time.
1. The step 8 soak at q64: an amp-only A2-Full plus a full-length IR, ljoss editing over WiFi,
   one `scripts/sync-library` in the middle, under `scripts/host-lock`.
2. Then the same soak with only the rsync, to isolate WiFi's cost.
