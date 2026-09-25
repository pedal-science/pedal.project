# Pedal Project

A guitar pedal running Neural Amp Modeler (NAM) kernels on `tib`, an ASUS Tinker
Board (RK3288). DSP performance is solved: A2-Full runs at ~53% of one core with the
NEON build, on a PREEMPT_RT kernel that has been soak-tested for dropouts.

Current phase and everything after it: [plan.md](plan.md). First target is playing
through `tib` with the SSL 2+, with ljoss editing the rig over WiFi.

Full hardware context, schematic findings and reasoning:
@docs/hardware-handoff.md

Which repo owns what, the machines, and the rules against drift:
[docs/working-across-repos.md](docs/working-across-repos.md).

## Architecture

- `namchaind` (from namchain) renders the rig and drives ALSA directly (`alsa_raw`).
  No JACK, PipeWire or LV2.
- ljoss talks to `namchaind` on `tib` directly over WiFi. The Pico handles physical
  controls only and never carries rigs or models (D2).
- A **pedal service** in this repo, beside `namchaind`, owns the rig library, resume
  at power-up, uploads, and the footswitch/MIDI mapping. namchain stays a generic
  engine (D4).

## Hard constraints — ask before violating any of these

- `tib` is **not a Raspberry Pi**. No `config.txt`, no Pi overlays, no HAT conventions.
- `tib` is **armhf** (32-bit ARMv7, Cortex-A17). Do not assume aarch64.
- The WM8960 codec is **I2S master**; `tib` is I2S slave. The codec board has its own
  24 MHz oscillator and MCLK is not exposed.
- `tib` **owns the I2C bus** to the codec (0x1A). The Pico never writes codec registers.
- `tib` does **DSP only**. Display, encoder, footswitches, MIDI, LEDs and GPIO belong
  to the Pico, which talks to `tib` over UART.
- Footswitch and MIDI events produce **identical** UART messages.
- Codec ALC and 3D enhancement stay **off**.

## Planned codec modifications (D8)

The SparkFun WM8960 board is in hand and **stock**. It is brought up stock first,
then modified and measured before and after (plan Phase 2c). Candidates: AVDD-ISO
cut with an external LDO, SPKVDD open, VIN disconnected — or, first, VIN fed from a
78L05 on the 9 V side, which needs no cutting.

## Check before first power-up

- Display module (ST7789 + EC11): confirm there is no onboard LDO, then run it at
  **3.3 V**. Its switch pull-ups go to VCC and RP2350 GPIO is not 5 V tolerant.

## Diagrams

`docs/diagrams/` — draw.io, two layers: blocks and connections. The small squares
on the connection layer are routing junctions, **not components**. When reasoning
about the diagram, check that edges still have `source`/`target` set and that no
junction joins two distinct nets, but treat the connections as being to the blocks
under the small squares on the blocks layer, not to the squares themselves. It's
drawn this way to attach connections at arbitrary positions on blocks and keep them
horizontal or vertical. If there's a better way to do that, discuss.

Don't break the formatting. If the diagram is confusing, render it to an image
with the draw.io CLI and read that, or ask.

## Commands

<!-- Added in Phase 0 step 8: scripts/status, scripts/tib-lock, scripts/deploy-engine. -->
