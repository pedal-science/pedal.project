# Enclosure model

A Blender model of the pedal built into a Hammond 1590XX, shown twice on a wooden floor:
closed, and with the top face taken off so the insides show. The parts that mount on the top
face (footswitches, display module, knob, LEDs, toggle) stay where they mount in both.

Open `pedal.blend` in Blender 5.2 or later. It's self-contained, with textures packed, and
`src/build` makes it again from scratch.

## Renders

`renders/`, 1920 x 1080, Cycles:

| File | Shows |
|---|---|
| `1_hero.png` | Both pedals from the front-left, lamps behind |
| `2_overhead.png` | Top down, closed beside open: the layout |
| `3_inside.png` | Into the open pedal: Pi 5, display, wiring |
| `4_face.png` | The closed pedal's face: stripe, screen, knob, toggle |
| `5_rear.png` | The rear: MIDI, 9 V and 5 V in, jacks on the sides |
| `6_wide.png` | The set: the floor lamps around the pedals |
| `7_boards.png` | Behind the display: the codec and the Pico |

## What's in it

- **Enclosure.** Hammond's 1590XX drawing: 145.2 x 121.2 x 39.3 mm, drafted walls, a 3 mm
  fillet into the top face, lid-screw bosses in the corners, and a lipped base plate on four
  rubber feet. Black textured powder coat, with an orange band (y 53 to 107 mm) across the top
  and down both sides. Bare metal inside.
- **Top face.** The display window (black bezel, acrylic behind it), the EC11 knob and push
  button, Inst/Line toggle, four LEDs in panel clips, and three footswitches **52 mm** apart.
  70 mm doesn't fit: the outer switches would sit in the side walls.
- **Walls.** OUT L and OUT R on the left, IN and EXP on the right, MIDI, 9 V and 5 V (USB-C)
  on the rear.
- **Inside.** The Pi 5 on 3 mm standoffs under the footswitches. Behind it, under the
  display, two stripboards on 5 mm standoffs: board A (buffer on a SOIC adapter, bias, power,
  output stage, the SparkFun WM8960 in socket strips) and board B (the Pico 2 WH in socket
  strips, MIDI in, the bypass relay and its driver).
- **Wiring.** Dupont leads on the Pi's header for I2S, I2C, UART and 5 V; USB-C 5 V into the
  header; a split rainbow ribbon from the display to board B; footswitch, LED and expression
  wires in a tied loom along the front of the boards, with 100 nF across each footswitch; twisted
  pairs for the outputs and MIDI; screened cable from the input jack; and the sleeves, 9 V return
  and board ground meeting at a star point on board A's corner.

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

None of this has been checked against hardware.

- **The Pi 5 fits under the footswitches.** The switch tags end about 5 mm above its tallest
  parts there. Its USB and Ethernet stack has to be at the right-hand end to clear the right
  footswitch.
- **The EC11 sets the display's height.** The encoder's 6.5 mm body puts the display board
  6.6 mm under the panel, so the glass sits about 3 mm below the window.
- **The rear connectors have to sit high to clear the boards.** DIN is at z 25.5 mm, USB-C at
  29.5 mm and DC at 25 mm. The DC socket also had to move right of centre (x 76 mm) to clear the
  Pico and the display board.
- **Seen from above, the display module hides most of both stripboards.**

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
| `src/render.py` | Renders cameras: `blender -b pedal.blend -P src/render.py -- [--samples N] [--scale %] [CAM_...]` |
| `src/preview_part.py`, `src/debug_view.py` | Dev views of one part or one pedal under plain light |
