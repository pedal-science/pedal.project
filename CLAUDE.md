# namchain

A guitar pedal running Neural Amp Modeler (NAM) kernels on `tib`, an ASUS Tinker
Board (RK3288). DSP performance is solved — A2-full runs at ~53% of one core with a
local patch, on a PREEMPT_RT kernel that has been stress-tested for dropouts.
Current phase: physical build, codec bring-up, and the Pico 2 control surface.

Full hardware context, schematic findings and reasoning:
@docs/hardware-handoff.md

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

## Hardware that differs from stock

- SparkFun WM8960 breakout: AVDD-ISO **cut**, SPKVDD jumper **open**, VIN
  **unconnected**. Input 47 nF shunt caps may have been swapped for 4.7 nF.

## Check before first power-up

- Display module (ST7789 + EC11): confirm there is no onboard LDO, then run it at
  **3.3 V**. Its switch pull-ups go to VCC and RP2350 GPIO is not 5 V tolerant.

## Diagrams

`docs/diagrams/` — draw.io, two layers: blocks, and connections. The small squares on
the connection layer are routing junctions, **not components**. When reasoning about
the diagram, check that edges still have `source`/`target` set and that no junction
joins two distinct nets.

## Commands

<!-- Add build, flash, deploy and test commands for tib and the Pico here. -->
