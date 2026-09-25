# Plan

**Written:** 2026-09-23. It replaces the bootstrap plan: read `about.md`, design a way of working
across the repos, ask questions, write this. The repo strategy that came out of it is
[docs/working-across-repos.md](docs/working-across-repos.md). The questions and your answers are
recorded under **Decisions**.

**First target:** play guitar through `tib` using the SSL 2+ that is already attached, with ljoss
editing the rig live over WiFi, and the pedal coming back with the same rig after a power cycle.

---

## Where things stand

### Against the goal in `about.md`

| Goal | Today | Gap |
|---|---|---|
| Entirely digital effects | namchain renders NAM, cab IR, EQ (bands, tilt), cut filters, feedback delay, gain and lane mixing: 11 primitives and 7 macros. 27 of ljoss's 102 blocks map onto them | Nothing required for your own use (D7). The rest stay badged "unavailable" in ljoss |
| A rig document becomes a virtual rig | ljoss encodes rigs and drives `namchaind` over TCP (protocol 2, token), proven against a daemon on macOS | Never run on `tib`. `namchaind` isn't installed there |
| External MIDI controller | The MIDI Commander (USB and DIN out, your own firmware fork, its own two expression inputs sending CC11/CC4) | All of it: the DIN input on the Pico, the UART link, and mapping MIDI onto rigs |
| Very low noise | Analogue design drafted in `docs/hardware-handoff.md`. `tib` currently uses the SSL 2+ | WM8960 in hand but not yet inspected. Analogue parts not bought. No noise-measurement method yet |
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
8. **Scripts here:** `scripts/status`, `scripts/tib-lock`, `scripts/deploy-engine` and
   `components.lock`, as specified in the repo doc.

**Done when:**
- `scripts/status` shows every repo clean, or deliberately on a named branch, on every host.
- `scripts/deploy-engine` rebuilds the NEON configuration from a commit.
- `CLAUDE.md`, the handoff and the diagram each exist once and agree.

## Phase 1 — Play through tib

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
   **For step 8:** A2-Full *alone* overran 7–9 blocks in 30 s today, where the same load ran a
   clean hour on 16 Sep. `tib` is noisier than it was; find out why before the soak.
   - First, measure `nc.cab.ir` on `tib` at your library's real lengths.
   - Then port the partitioned FFT convolution from your AudioDSPTools `partitioned-ir` branch
     into `nc.cab.ir`: direct up to 512 taps and FFT above, as the branch's `Auto` does.
   - Test it against the direct path within a stated tolerance. The branch measured 136–138 dB
     below the signal, so bit-identity won't hold, but a tolerance test will.
   - Latency stays at zero, because the branch keeps a direct head.
   - Beside A2-Full, the FFT path's burstiness may matter: each partition's transform lands in one
     callback. Spreading that work across the quiet callbacks was a "not worth it yet" item in
     `NAMBench/IR-PATH.md`. On one shared core it may become worth it, and 1.8's soak decides.
3. **Deploy.**
   - `namchaind` and `namchainctl` go to `tib` through `scripts/deploy-engine`.
   - Install the systemd unit and config under `devices/tib/`:
     - `alsa_raw` on the SSL 2+ by name, render thread pinned to core 3
     - start from the settings `tib`'s soaks used (quantum, periods, output-queue cap)
     - TCP on the LAN with a token from a file.
   - Give `tib` a fixed address (a DHCP reservation) or use its mDNS name, because ljoss has no
     discovery.
4. **Library on the pedal.** Rsync the models and IRs your rigs use into `tib`'s library folders,
   no conversion needed: `nc.cab.ir` resamples 44.1 and 96 kHz IRs itself (step 2).
5. **ljoss → tib.**
   - Point ljoss's Hardware settings at `tib`, and run `Tools/check-device.sh` against it.
   - Play an amp + cab + EQ + delay rig and edit it live.
6. **Resume at power-up (pedal service v0).**
   - A small process polls `engine.status`. When the generation changes, it saves `rig.get`'s
     document atomically into the rig library.
   - `namchaind` starts that document at boot. It already compiles and prewarms a startup rig
     before the clock starts.
   - Whether the service stays beside `namchaind` or later fronts it for the app is left to 3.2.
7. **Measure what D3 needs:**
   - how long `rig.apply` takes on `tib`, from the command to hearing the new rig, with its NAM
     and IR
   - power-on to sound.

   These two numbers decide whether keeping models loaded (3.8) has to come before footswitches,
   and whether the bypass relay (3.6) is urgent.
8. **Soak it the way it will be used.** An hour through `namchaind` with an A2-Full + full-length
   cab IR rig, holding the `tib` lock, with ljoss editing over WiFi and one library rsync in the
   middle.
   - Gate: 0 driver xruns, 0 deadline overruns and 0 guard trips, with the worst block inside
     namchain's ARMv7 bar of 90% of the deadline.
   - Separately: the same soak with only an rsync running, so WiFi's cost, if it has one, is
     isolated.

**Done when:**
- From power-on, `tib` plays the last rig (an A2-Full amp and a full-length cab IR) through the
  SSL 2+ with no app connected.
- ljoss on the Mac edits it live.
- An hour of playing and editing is clean.
- `components.lock` names what's running.

## Phase 2 — The codec and the analogue stages

**2a. Stock bring-up.** The board is in hand, so this can overlap Phase 1.
1. **Inspect the board.**
   - Jumper states: AVDD-ISO, SPKVDD.
   - Check the input R/C mapping table in the handoff against the silkscreen.
   - Photos into `references/`.
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
   - **Keep the 47 nF shunts.** The board's own 100 Ω already isolates the op-amp from them, so the
     draft's extra 100 Ω isn't needed and the corner stays at 34 kHz. The 4.7 nF swap only
     mattered for an unbuffered, high-impedance source.
   - **The output level works.** HP_L and HP_R reach 1 Vrms at full scale. That's hot for an amp's
     input and right for a line input, and `namchaind`'s output gain sets it either way.
   - **AVDD draws about 5–8 mA** (the datasheet's playback figures), so a TO-92 78L33 is plenty.
     There's a simpler option for 2c too: feed the board's VIN from a 78L05 on the 9 V side. AVDD
     then comes off `tib`'s supply with no cutting, and the board's own LDO becomes a second stage.
2. **Settle the values.** The parts are already in the basket, including the OPA2197 (CPC doesn't
   sell the OPA1642). [docs/bom.md](docs/bom.md) describes a provisional input stage built on these
   findings: ×1 on Inst, a 680 kΩ / 330 kΩ pad on Line, and a 2.9 V bias. If 2a's measurements move
   any of that, only resistor values change.
3. **Build the buffer and the output stage** on stripboard, powered from a Cioks outlet through the
   LDO.

**2c. Modify and compare.**
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
7. **Display and encoder**, low priority per `about.md`. Check it has no onboard LDO before
   powering it (per `CLAUDE.md`).
8. **Models ready for switching** (a slice of namchain's M3): hold the current bank's models
   loaded so a rig change touches neither the SD card nor JSON parsing. It is prioritised by 1.7's
   numbers.

**Done when:**
- With no app, the footswitches and the MIDI Commander step through rigs stored on the pedal.
- Changes are click-free.
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

- namchain M2/M3: warm-start model switching, admission control.
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

Phase 1 step 3: deploy `namchaind` to `tib`. Steps 1 and 2 are done.
