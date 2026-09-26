# Pedal Project — hardware handoff

Context brief for picking up the pedal build. Everything here was established
by reading the SparkFun schematic directly or decided deliberately; where
something is unverified it says so.

---

## Current status

- NAM **A2-full** kernel runs at **~53% of one core** on `tib`, with the armv7 NEON
  build and the planar-kernel vendor patch.
- PREEMPT_RT kernel built, running, and stress-tested — no dropouts or glitches
  on a quiet machine.
- Performance risk is therefore **closed**. Remaining work is physical build and
  bring-up, not DSP optimisation.
- In hand: `tib`, the WM8960 board (stock, inspected 2026-09-26), the display module.
  Due: RP2350-USB-A. In the basket: 2 × Pico 2 WH and a Debug Probe. See
  [bom.md](bom.md) and `plan.md`.

## Hardware

| Part | Notes |
|---|---|
| `tib` | ASUS Tinker Board, RK3288 Cortex-A17, **armhf / 32-bit** (no aarch64). Out of production; a similarly powerful Pi-class board would stand in, as namchain already builds and tests for aarch64 on a Pi 500 |
| Codec | SparkFun WM8960 Audio Codec Breakout, schematic v1.0 (Eagle 9.4.2, Jan 2023). Retired product — consider a spare. |
| Control MCU | Raspberry Pi Pico 2 (ordering). An RP2350-USB-A is due, but its 15 GPIO are short of the ~18 needed, so it's for experiments |
| Display | 2.4" ST7789 320×240 SPI module with EC11 encoder + tactile button, board V1.2 (in hand) |
| Front end | Hi-Z buffer, to be built |
| Power | Cioks DC7: 7 isolated outlets at 6 W each (660 mA @ 9 V); USB-A 1 A (Cioks' site may say 5 W) on v1, USB-C 15 W on v2; AUX 24 V @ 2 A |

**Topology: mono in, stereo out.** NAM input is mono; the chain may split into two
channels running different kernels, and those are sometimes kept as stereo rather
than recombined.

---

## Established from the SparkFun schematic

These were read off the drawing, not assumed.

### Clocking

- **Y1 is a 24 MHz oscillator**, VCC *and* EN both hard-tied to 3.3 V, so it runs
  permanently. Output goes through R10 (10 Ω) into MCLK, pin 11.
- **MCLK is not brought out to the header.** It cannot be supplied externally.
- Consequence: the codec's converters are clocked from this local oscillator.
  If `tib` were I2S master, its LRCLK and the codec's sample rate would come from
  independent references and drift. **The codec must be I2S master.**

### Inputs

Signal path from the header pad inward:

```
pad → 100 Ω series → [47 nF to GND] → 1 µF series → codec pin
```

- Coupling caps are **already fitted** (1 µF). Do not add more.
- The 47 nF shunt sits on the *source* side of the coupling cap, so the filter
  corner is `1 / (2π (Z_source + 100) × 47 nF)`:

| Source impedance | −3 dB |
|---|---|
| ~0 Ω | 34 kHz |
| 100 Ω | 17 kHz |
| 470 Ω | 5.9 kHz |
| 1 kΩ | 3.1 kHz |

- Component mapping (**unverified — the board has no reference designators on its
  silkscreen, so check by continuity from the pad before desoldering**). The parts sit
  above the codec as three rows of six: caps, resistors (dark bodies), caps:

| Input | Series R | Shunt C | Coupling C |
|---|---|---|---|
| LINPUT1 | R4 | C22 | C19 |
| LINPUT2 | R6 | C21 | C20 |
| LINPUT3 | R1 | C27 | C23 |
| RINPUT1 | R7 | C28 | C24 |
| RINPUT2 | R8 | C29 | C25 |
| RINPUT3 | R9 | C30 | C26 |

- If the buffer's output impedance pushes the corner too low, swap the relevant
  47 nF for **4.7 nF** (≈31 kHz with a 1 kΩ source). Don't remove them entirely.

### Outputs

- HP_L (pin 31), HP_R (pin 29) and OUT3 (pin 30) go **straight to the header with
  no coupling capacitors**. This is the capless configuration: OUT3 is a driven
  pseudo-ground, not ground.
- Tying an output sleeve to system ground without a series capacitor **shorts the
  OUT3 buffer**.
- There are no true line outputs on this chip. Speaker outputs (SPEAKER_LP/LN/RP/RN
  via 220 Ω ferrites L1–L4 and 1 nF C15–C18) are class-D and unused.

### Power

- `3.3V` header pin feeds **DCVDD, DBVDD and Y1**. The oscillator's jitter therefore
  tracks whatever supplies this rail.
- `VIN` (3.7–5.5 V) → C1/C31 → **U3, XC6222B331MR-G** (3.3 V, 700 mA out, **6 V max in**)
  → AVDD via the **AVDD-ISO** jumper. R18 is a 100 k pull-up on U3's EN, and EN is
  broken out on J4 pin 3.
- **SPKVDD jumper** selects 3.3 V or VIN; leaving both open means the class-D amp is
  unpowered and SPKVDD can be supplied at the header.

### As received (inspected 2026-09-26, photos in `references/wm8960-photos/`)

- **AVDD-ISO bridged**: onboard LDO feeds AVDD.
- **SPKVDD bridged to VIN**, 3V3 side open (from the photo; confirm with a meter). With VIN
  powered, the class-D amp is live, so the mixer state must keep it disabled.
- Two jumpers not in the schematic notes above, both bridged: **I2C** (enables the onboard
  2.2 kΩ pull-ups; check against any on `tib`'s header bus) and **LED** (PWR LED on 3V3, the
  rail that also feeds Y1; a candidate to cut under D8).
- A **Qwiic** connector carries I2C and 3V3. Leave it unused: `tib` is the only I2C master.
- Y1 marked 24.000 MHz. No headers fitted.

### Other

- I2C address **0x1A**, with 2.2 kΩ pull-ups already on the board.
- All six digital lines have **10 Ω series damping** (R10–R17).
- VMID (27) and MICBIAS (1) each have 4.7 µF to ground.
- **J4**: BCLK, DACLRC, DACDAT, ADCLRC, ADCDAT, SCL, SDA, 3.3V, SPKVDD, VIN, EN, GND
- **J5**: RINPUT3/2/1, LINPUT1/2/3, MICBIAS, HP_L, OUT3, HP_R, AVDD, SPK_LP/LN/RP/RN, GND

---

## Design decisions

### Clocking and buses

- **Codec is I2S master; `tib` is I2S slave.** Non-negotiable, see above.
- **`tib` owns the I2C bus.** The ASoC driver caches WM8960 register state. The Pico
  must never write codec registers — it talks to `tib` over UART and `tib` applies
  changes through ALSA mixer controls.

### Jumpers (planned, D8)

The target state after stock bring-up and measurement. The board is stock today.

- **AVDD-ISO: cut.** AVDD fed externally from a dedicated LDO.
- **SPKVDD: both open.** Class-D amplifier unpowered — it's a switching noise source
  next to the ADC inputs and serves no purpose here.
- **VIN: unconnected.** With AVDD-ISO cut and SPKVDD open it feeds nothing.

### Input stage

> **Superseded in part** (2026-09-24, datasheet review in `plan.md` Phase 2b): ×10
> is far too much gain, the OPA2197 replaces the OPA1642 (CPC doesn't sell it), the
> bias moves to ~2.9 V, and the extra 100 Ω and the 4.7 nF swap aren't needed. The
> provisional values are in [bom.md](bom.md). The reasoning below still holds for the
> single 1 MΩ jack and the Inst/Line gain switch.

One jack, **permanently 1 MΩ**. A pedal output is low-impedance and is perfectly
happy driving 1 MΩ, so impedance never needs switching — only level does.

- The front-panel switch is a **gain** switch, labelled **Inst / Line**, not a
  "Hi-Z" switch. Putting a mechanical contact at the highest-impedance node would
  invite hum and contact noise.
- OPA1642 (JFET input), 9 V single supply, 4.5 V bias from a 1 M/1 M divider
  decoupled with 10 µF, 1 M input resistor to that bias.
- Non-inverting: ×10 for guitar, ×1 for pedal output. This lands both sources in
  roughly the same window so the codec PGA sits near 0 dB rather than supplying
  26 dB of gain and its own noise.
- ~100 Ω series on the way out for stability into the board's 47 nF.

### Output stage

Each of HP_L and HP_R: **10 µF series + 100 Ω + 1 MΩ bleed to ground** → TS jack.
OUT3 unused and **disabled in the register configuration** — don't leave the driver
enabled as a return path with nothing connected.

### Power

Two inputs, deliberately:

- **5 V / 3 A** for `tib` — own USB-C brick, or the DC7 v2's USB-C. The v1's USB-A
  at 1 A is insufficient.
- **9 V centre-negative** from one isolated Cioks outlet → the buffer directly, and
  → a low-noise LDO → 3.3 V → AVDD.

The point is that the analogue supply never carries `tib`'s current. Hum comes from
current in shared ground paths; this arrangement means the two meet only at the
**star ground point**, where PSU 0 V, codec GND, buffer GND and jack sleeves are
joined at one place.

A single-cable alternative exists — 24 V AUX at 2 A into an onboard buck for 5 V
plus a linear regulator for 9 V — but it puts a 48 W-capable switcher inside the
enclosure and gives up the isolation. Rejected for the first build.

### Control surface (all on the Pico — `tib` never sees any of it)

**Display module** — 2.4" ST7789, 320×240, 4-wire SPI, board V1.2, with an EC11
encoder and a separate tactile button on the same PCB. (There is no joystick: the
two switches are the encoder's integrated push and one tactile.)

- 12-pin header, pin 1 = square pad:
  `GND · VCC · SCL · SDA · RES · DC · CS · BLK · A · B · PUSH · K0`
- **Run at 3.3 V.** Silkscreen says "3.3V/5V", but the encoder and button pull-ups
  (10 K, R4–R7) are referenced to VCC with no level shifting. At 5 V, A/B/PUSH/K0
  would idle at 5 V into RP2350 GPIO, which is not 5 V tolerant.
- **Unverified:** whether the board carries an LDO (AMS1117-style SOT-23 near VCC).
  If it does, it will drop out at 3.3 V and the plan must change to 5 V plus level
  protection on the four switch lines. Check before first power-up.
- Encoder and both switches are hardware-debounced on the board (10 K pull-up,
  100 Ω series, 100 nF). EC11 is 20 pulses / 20 detents: **decode one full
  quadrature cycle per count, 20 per revolution** — counting every edge gives 80
  and feels 4× too fast. Poll at ~1 kHz with a state machine; no extra software
  debounce. The RC gives ~1 ms rise.
- Backlight: `BLK` drives an SS8050 via 1 K, with a 10 K pull-up to VCC on the base
  — **on by default, off when BLK is pulled low**. Either leave it fixed on or PWM
  it well above audio (≥100 kHz). PWM at a few hundred Hz switches tens of mA at
  audio frequency beside the input stage.
- Noise: this is the loudest digital source in the enclosure. Short ribbon, routed
  away from the input jack and buffer, powered and grounded on the digital side
  only. Stop redrawing when nothing has changed — a static screen is quiet.
- Encoder and button positions are fixed relative to the screen, so the panel
  cutout must take all three as one unit. If a different knob position is wanted,
  that means a bare ST7789 module plus a separate EC11 instead.

**Footswitches** — three onboard, plus DIN MIDI in.

- **SPST momentary soft-touch**, not latching 3PDT. There is no true bypass to
  switch, the Pico owns state, and latching switches drift out of agreement with
  actual state after a preset recall or MIDI change. Momentary also allows
  long-press gestures.
- One GPIO each, internal pull-up, switch to ground. **100 nF across each switch at
  the switch**, plus a 10–20 ms firmware debounce window — footswitches bounce far
  worse than panel buttons.
- Suggested assignment: preset down, preset up, one assignable.
- **Long-press on one switch = panic hard-bypass**, driving the same relay the Pico
  holds during boot. Works without the screen.

**MIDI** — DIN-5 in with an optocoupler (6N138 or H11L1). Chosen over USB host
because it's what floor controllers output, needs no USB host stack, and the
optocoupler keeps the controller's ground out of the pedal's ground scheme.
USB host on the RP2350 is possible later if wanted.

**Expression** — TRS jack into a Pico ADC input. Cheap to fit now, miserable to
retrofit into a drilled enclosure.

**One internal message format.** Footswitch presses and incoming MIDI must converge
in the Pico into the same UART messages to `tib`. A preset change is a preset change
regardless of source; `tib`'s side is written once, and MIDI support is then a
firmware-only change.

---

## Software

The order and the done-when checks are in `plan.md`. What matters for the hardware:

- **Audio host is `namchaind`** (namchain), driving ALSA directly through its
  `alsa_raw` backend. It opens devices by name, so the SSL 2+ now and the WM8960
  later are chosen by card id, not number. No JACK, PipeWire or LV2, and PiPedal-style
  stacks assume a Raspberry Pi anyway.
- **ljoss** edits rigs on `namchaind` directly over WiFi (D2). The Pico never carries
  app traffic.
- **A pedal service** beside `namchaind` (this repo) owns the rig library on the SD
  card, resume at power-up, uploads, and mapping footswitch/MIDI events onto rigs
  (D3, D4).
- **MIDI is DIN in on the Pico** (D6). USB MIDI is a later firmware change.
- **Mic input**: panel position and RINPUT1 reserved, circuit later (D5).

Hardware-side work outstanding:

1. **Device tree** (in `rtpi`). A `simple-audio-card` node: WM8960 at 0x1A, with
   `bitclock-master` and `frame-master` on the codec DAI, and a 24 MHz fixed clock as
   MCLK so the driver can set its PLL for 48 kHz. `tib` has **one** I2S controller,
   held today by the HDMI card (`rockchip,tinker-codec`); the WM8960 card replaces
   it. There is no ready-made overlay — the Pi's `wm8960-soundcard` does not apply.
2. **Verify the I2S wiring** on this Tinker Board revision: which I2C bus the header
   carries, and whether the RK3288 side provides separate TX and RX frame clocks (the
   board breaks out ADCLRC and DACLRC separately, and the WM8960 can alternatively
   slave the ADC to DACLRC).
3. **ALSA mixer state as code** (`devices/tib/`). ALC **off** — it pumps audibly on
   guitar dynamics. 3D enhancement off. Speaker amp and OUT3 off. Simplest possible
   analogue routing. PGA near 0 dB, boost mixer at 0 dB (the boost stages are noisier
   than the PGA).
4. **Header UART** for the Pico link: UART1 on pins 8/10 (the console is ttyS2 on
   32/33).
5. **Pico firmware.** Three footswitches with long-press, DIN MIDI input, status LEDs,
   bypass relay; display and encoder later. Footswitch and MIDI events produce
   identical UART messages.
6. **Boot-time bypass.** ~30 s of boot before audio passes. A relay whose
   **de-energised** state is bypass, energised by the Pico only once `tib` reports
   audio ready. This is the difference between a gig-usable pedal and a desk toy.

---

## Open questions

- **Pico ↔ `tib` link**: UART chosen to avoid a USB gadget stack and an enumeration
  dependency at boot. Revisit if the Pico should also present as a USB MIDI device
  to a host computer.
- **Codec 3V3 source**: currently `tib`'s header. A second LDO off the 9 V would take
  the whole codec board — including the 24 MHz oscillator — off `tib`'s rails.
  Defensible addition; left out of the first pass.
- **Pico power**: shown from `tib`, which means the control surface is dead during
  boot. Its own 5 V would let it show a boot progress screen on the display and
  hold the bypass relay — now more attractive since the display is in hand.
- **Display module regulator** — see Control surface; blocks first power-up.
- **Enclosure, panel layout, bypass relay circuit** — not yet designed. Panel must
  accommodate the display module's fixed screen/knob/button geometry, three
  footswitches, IN, OUT L, OUT R, expression TRS, MIDI DIN, 9 V barrel, 5 V input.

---

## What not to assume

- This is **not** a Raspberry Pi. Pi-specific overlays, `config.txt` entries and
  HAT conventions do not apply.
- This is **not** aarch64. Anything assuming 64-bit ARM needs checking.
- Don't assume the codec board's modification state. It is stock today; D8 brings
  it up stock and modifies it afterwards, measuring each step. Inspect the jumpers
  before relying on either.

---

## References

- Block diagram: `docs/diagrams/` (draw.io source, two-layer: blocks and connections,
  with non-component junction squares on the connection layer). Keep its formatting;
  if it's confusing, render it and read the image, or ask.
- SparkFun WM8960 Audio Codec Breakout schematic v1.0:
  `references/Stereo_Audio_Codec_Breakout_WM8960_v10_Schematic.pdf`
- Display module schematic: `references/screen-board-schematic-*.png`
