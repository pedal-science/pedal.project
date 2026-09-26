# Pedal Project

A guitar pedal running Neural Amp Modeler (NAM) kernels on a Raspberry Pi 5.

**Core host** (the board that runs the DSP, "Core" in `about.md`):
- **`tib`** (ASUS Tinker Board, RK3288, armhf) is **retired** as of 2026-09-26. It stopped
  working on 2026-09-25. Its numbers, `devices/tib/` and its backups stay as history.
- **`piv`** (Raspberry Pi 500, aarch64) stands in until `vip` arrives.
- **`vip`** (Raspberry Pi 5, 1 GB, aarch64) is on order and becomes the Core target when
  it arrives.

Older docs and plan phases say "`tib`"; read that as "the Core host".

Current phase and everything after it: [plan.md](plan.md). First target is playing
through the Core host with the SSL 2+, with ljoss editing the rig over WiFi.

Full hardware context, schematic findings and reasoning:
@docs/hardware-handoff.md

Which repo owns what, the machines, and the rules against drift:
[docs/working-across-repos.md](docs/working-across-repos.md).

## Architecture

- `namchaind` (from namchain) renders the rig and drives ALSA directly (`alsa_raw`).
  No JACK, PipeWire or LV2.
- ljoss talks to `namchaind` on the Core host directly over WiFi. The Pico handles physical
  controls only and never carries rigs or models (D2).
- A **pedal service** in this repo, beside `namchaind`, owns the rig library, resume
  at power-up, uploads, and the footswitch/MIDI mapping. namchain stays a generic
  engine (D4).

## Hard constraints — ask before violating any of these

- The Core host is a **Raspberry Pi 5-class board, aarch64** (BCM2712, Cortex-A76).
  Pi overlays and `config.txt` apply. The old "not a Pi" and "armhf" rules were about
  `tib` and no longer hold.
- `vip` has **1 GB of RAM**. Check memory for loaded models and the pedal service, not
  just CPU.
- The WM8960 codec is **I2S master**; the Core host is I2S slave. The codec board has its
  own 24 MHz oscillator and MCLK is not exposed.
- The Core host **owns the I2C bus** to the codec (0x1A). The Pico never writes codec
  registers.
- The Core host does **DSP only**. Display, encoder, footswitches, MIDI, LEDs and GPIO
  belong to the Pico, which talks to the Core host over UART.
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
