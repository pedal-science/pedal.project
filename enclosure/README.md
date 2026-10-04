# Enclosure model

A Blender model of the pedal built into a 1590DD-size box (188 x 119 x 37.5 mm), shown twice on
a wooden floor:
closed, and with the top face taken off so the insides show. The parts that mount on the top
face (footswitches, display module, knob, LEDs, toggle) stay where they mount in both.

Open `pedal.blend` in Blender 5.2 or later. It isn't in git (at 56 MB, every version would stay
in the history): download it from the
[`enclosure-1590dd` release](https://github.com/rikkus/pedal.project/releases/tag/enclosure-1590dd),
or make it with `src/build --no-render`. It's self-contained, with textures packed.

## Playing with the layout in 2D

`layout.kicad_pcb` is the whole inside of the box seen from above, 1:1 in millimetres, as
footprints you can drag around. It is a **layout sandbox**, not a schematic and not something to
fabricate: no nets, no tracks. Open it in KiCad's PCB editor — that is all this file is for, so
moving parts, measuring gaps and checking what fits against the 188 x 119 mm outline needs no
other setup.

The drawing is the enclosure's outside 188 x 119 mm with the boards, the Pi and the panel parts
inside it, so a position's distance from the **top** of the drawing is its distance from the
**rear** wall. The one thing it cannot carry is height: the rear-wall parts (OUT L/R, EXP, IN,
MIDI, USB-C and 9 V) are all at z 16 in a row along the rear edge, and the display board hangs
above board A. Anything about what fits *over* something else still needs the model.

What is in it, all placed from `src/layout.py`, so it agrees with the model:

- Both stripboards with their real holes, cut centres and the standoffs that fix them.
- The Pi (`PI5`), the SparkFun codec on board A's socket strips (`CODEC`), the SOIC adapter
  (`SOIC_ADAPTER`) and the display module (`DISPLAY`), each named **on the drawing** as well as
  in the parts panel. The names are the modules' own reference fields, so they travel with the
  part when you drag it: the Pi's outline is the rectangle labelled `PI5`, the left stripboard
  is `BOARD_B` and the right is `BOARD_A`.
- The top face: three footswitches, four LEDs, the Inst/Line toggle, the display window and the
  stripe, on `Dwgs.User`.
- `WINDOW` and `STRIPE` mark features of the top face; the four circles in the corners are the
  lid-screw bosses.

`docs/diagrams/layout-overview.svg` and its `.png` twin are the same drawing exported at 1:1
for viewing without KiCad, made by `src/export-overview`.

`make_layout.py` writes the `.kicad_pcb`, and **will not overwrite it once KiCad has saved it**
unless run with `--force`: edit the `.kicad_pcb` freely. To push a layout you like back into the
model, move the positions into `src/layout.py`, which is what the Blender build and the GLB
exports read. The `.kicad_pro` is committed too, so it opens as a project; `.kicad_prl` is
per-user and ignored.

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
- **Not yet updated for the 2026-10-01 decisions** (`plan.md` Phase 4): the 5 V comes in through a
  USB-C panel extension into the Pi's own USB-C port, not to the header, and the Pi and boards
  stand on nylon standoffs on a 3 mm FR4 plate, not brass ones on the base plate.

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

None of this had been near hardware when it was drawn. **Since 2026-10-04, one part of it has:** a
temporary plastic box stands in for the case, and its rear wall carries IN, OUT L and OUT R in the
Neutrik jacks in the arrangement modelled here, with the USB-C supply lead through a hole to the
Pi's own port. It plays
([bench-results/2026-10-04-the-pedal-plays-in-a-case.md](../bench-results/2026-10-04-the-pedal-plays-in-a-case.md)).
Everything else — the footswitches, the display, the clock, and the board positions inside — is
still unchecked, and the cut positions the plastic box ended up with are worth recording before the
aluminium case is drilled. `src/layout.py` has the positions; the parts'
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
| `src/make_layout.py` | `layout.kicad_pcb`, the editable 2D layout (runs in KiCad's Python; `--force` to overwrite a saved one) |
| `src/export-overview` | `docs/diagrams/layout-overview.svg` and `.png`, the drawing at 1:1 for viewing |
| `src/make_screen.py` | The display's image |
| `src/build_scene.py` | Builds `pedal.blend`: `bl_pedal.py` (assembly, wiring), `bl_enclosure.py`, `bl_parts.py`, `bl_wires.py`, `bl_scene.py` (floor, lamps, cameras), `bl_util.py` |
| `src/build_board1.py` | Builds `stripboard/board1.blend` and its renders: board 1 alone, from `stripboard/board1.py` (`make_parts.py board1` first) |
| `src/render.py` | Renders cameras: `blender -b pedal.blend -P src/render.py -- [--samples N] [--scale %] [CAM_...]` |
| `src/preview_part.py`, `src/debug_view.py` | Dev views of one part or one pedal under plain light |
