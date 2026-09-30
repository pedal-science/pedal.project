# Enclosure model

A Blender model of the pedal built into a 1590DD-size box (188 x 119 x 37.5 mm), shown twice on
a wooden floor:
closed, and with the top face taken off so the insides show. The parts that mount on the top
face (footswitches, display module, knob, LEDs, toggle) stay where they mount in both.

Open `pedal.blend` in Blender 5.2 or later. It isn't in git (at 56 MB, every version would stay
in the history): download it from the
[`enclosure-1590dd` release](https://github.com/rikkus/pedal.project/releases/tag/enclosure-1590dd),
or make it with `src/build --no-render`. It's self-contained, with textures packed.

## Renders

`renders/`, 1920 x 1080, Cycles. They show the earlier 1590XX layout until they are rendered
again from the current `pedal.blend`:

| File | Shows |
|---|---|
| `1_hero.png` | Both pedals from the front-left, lamps behind |
| `2_overhead.png` | Top down, closed beside open: the layout |
| `3_inside.png` | Into the open pedal: Pi 5, display, wiring |
| `4_face.png` | The closed pedal's face: stripe, screen, knob, toggle |
| `5_rear.png` | The rear: every connector |
| `6_wide.png` | The set: the floor lamps around the pedals |
| `7_boards.png` | The codec board and the Pi |

## What's in it

- **Enclosure.** 188 x 119 x 37.5 mm, drafted walls, a 3 mm fillet into the top face, lid-screw
  bosses in the corners, and a lipped base plate on four rubber feet. Black textured powder
  coat, with an orange band (y 53 to 106 mm) across the top and down both sides. Bare metal
  inside. Tayda's 33 mm-high 1590DD was tried first; see below for why it wasn't enough.
- **Top face.** The display window (black bezel, acrylic behind it), the EC11 knob and push
  button, Inst/Line toggle, four LEDs in panel clips, and three footswitches **69 mm** apart.
- **Rear.** Everything: OUT L and OUT R at the left, 5 V (USB-C), MIDI and 9 V in the middle,
  EXP and IN at the right (left and right as the player sees them).
- **Inside.** The Pi 5 on 3 mm standoffs at the front middle, under the middle footswitch. Either
  side of it, on 3 mm standoffs: board B at the left (the Pico 2 WH in socket strips, MIDI in,
  the bypass relay and its driver) and board A at the right (buffer on a SOIC adapter, bias,
  power, output stage, the SparkFun WM8960 in socket strips).
- **Wiring.** Dupont leads on the Pi's header for I2S, I2C, UART and 5 V; USB-C 5 V into the
  header; a split rainbow ribbon from the display, arched over the Pico, to board B; footswitch
  and LED wires in a tied loom just behind the footswitches, with 100 nF across each footswitch;
  expression and MIDI along the rear behind the boards; twisted pairs for the outputs; screened
  cable from the input jack; and the sleeves, 9 V return and board ground meeting at a star point
  on board A's front corner.

Positions for all of it live in `src/layout.py`.

## Where the parts come from

The parts are close, not exact.

- **Raspberry Pi 5.** Raspberry Pi's official STEP (MIT licence), converted to GLB through
  KiCad.
- **Pico 2 WH.** KiCad's Pico WH model, which has the same outline.
- **Boards.** Both stripboards, the SparkFun codec board, the display board and the SOIC
  adapter are built as KiCad boards from KiCad's library footprints and 3D models
  (`src/make_parts.py`). The stripboards have real holes and copper strips, and the script
  refuses overlapping parts.
- **Everything else.** The footswitches (MC7105-style), Neutrik NMJ6-style jacks, DIN, DC
  socket, USB-C socket, toggle, EC11 and knob, LEDs, TFT panel and fixings are modelled in
  Blender (`src/bl_parts.py`).
- **Stand-in.** The TQ2-5V relay is a stretched DIP-10 body.
- **Screen.** The image is rendered by `src/make_screen.py`.
- **Floor.** Poly Haven's "Wood Floor" texture (CC0).

## What the model says about the layout

None of this has been checked against hardware. `src/layout.py` has the positions; the parts'
meshes don't intersect except where they should touch (checked in Blender).

- **The height is the constraint.** At 33 mm (Tayda's 1590DD) the Dupont housings on the Pi's
  header reached the display board and the MIDI socket had nowhere to go, and the other gaps were
  0.5 to 2.5 mm. At 37.5 mm it all fits with room for wiring, but there's still no room for a Pi
  cooler under the middle footswitch: a low heatsink is the most that could go there.
- **The Pi sits under the middle footswitch.** Its USB and Ethernet stack has to sit between the
  middle and right footswitches, and the switch's tags sit over the bare middle of the board,
  clear of the tall parts along the HDMI edge.
- **Board B's standoffs have to move one hole in** (column 1, not 0), and board A's to column
  16: at the board edge they would land on the lid's lip.
- **The LEDs' legs are trimmed short**, so the Pico can sit under the left LED.
- **The rear connectors sit at z 16 mm**, so the DIN socket clears the display board above it.

## Rebuilding

```bash
src/build
```

This downloads the Pi 5 STEP and the floor texture, builds the boards in KiCad, renders the
screen image, builds `pedal.blend` and renders all seven cameras (about half an hour on an M2).
`src/build --no-render` stops after the `.blend`. It needs Blender 5.2 on `PATH` and KiCad 10 in
`/Applications`.

| Script | Does |
|---|---|
| `src/layout.py` | Every position and dimension, shared by the rest |
| `src/fetch-assets` | The two downloads, into `assets/` (gitignored) |
| `src/make_parts.py` | KiCad boards to GLB (runs in KiCad's Python) |
| `src/make_screen.py` | The display's image |
| `src/build_scene.py` | Builds `pedal.blend`: `bl_pedal.py` (assembly, wiring), `bl_enclosure.py`, `bl_parts.py`, `bl_wires.py`, `bl_scene.py` (floor, lamps, cameras), `bl_util.py` |
| `src/build_board1.py` | Builds `stripboard/board1.blend` and its renders: board 1 alone, from `stripboard/board1.py` (`make_parts.py board1` first) |
| `src/render.py` | Renders cameras: `blender -b pedal.blend -P src/render.py -- [--samples N] [--scale %] [CAM_...]` |
| `src/preview_part.py`, `src/debug_view.py` | Dev views of one part or one pedal under plain light |
