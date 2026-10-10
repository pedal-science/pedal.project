# The analogue boards' netlist, and the noise rules

Written 2026-10-10. This is the record of where the analogue circuit's connections live, how
they are checked, and which noise rules the layout is built to — and, for each rule, whether
it rests on a measurement or on reasoning. Board 1 is built and measured
([build-board1.md](build-board1.md)); board A is the same circuit for the enclosure
([plan.md](../plan.md) Phase 4).

## One netlist, checked

`stripboard/nets.py` holds the analogue circuit as a netlist: parts, and for every net the
component pins on it. It knows nothing about holes, so a layout can be redone without it,
and a net that is right in one layout cannot be wrong in another. Three things check against
it:

| What | How |
|---|---|
| the netlist itself | `python3 stripboard/nets.py` — every pin of every part is on exactly one net, and no two nets share a pin |
| board 1 | `python3 stripboard/board1.py` |
| board A | `python3 stripboard/board_a.py` |

`stripboard/stripboard.py` is the checker and the drawing they share. It enforces five rules,
and prints the size it found:

1. **the netlist** — every lead is on the net the netlist puts that pin on, and every pin of
   a part the board carries is on the board. A board says which parts are its own
   (`carries=`), because the circuit is split over more than one board;
2. **no two nets joined** — union-find over the copper: the strips, broken at the cuts, plus
   the links. This is the rule that catches the classic stripboard mistake, a part lying
   across two strips, which is silent until something hums;
3. **nothing on a cut hole** — a lead may sit on a cut hole *only* if it can still reach its
   net through the hole beside it (a pin whose strip is cut is wired to nothing otherwise);
4. **no lead under another part's body**, and nothing soldered where a wire only passes over;
5. **the fit rule** — every hole the board uses is inside its outline, and the outline is
   printed in millimetres and holes.

`stripboard/board1.py` reports:

    ok: 19 parts, 11 links, 22 cuts, 11 wires; 50x14 holes = 124.46 x 33.02 mm; drawings written

### What the extraction found: board 1's two pad values

Board 1's own data had **R5 = 680k and R6 = 330k**. Its topology is right — the switch taps
either side of R5, the buffer is a follower, the divider runs from the jack's coupling
capacitor to the bias — but that pair of values gives the Inst position about **0.81** and
Line about **0.33**, against the BOM's ×1 for Inst and −9.7 dB (0.33) for Line. Swapped
(R5 = 330k, R6 = 680k) the pad is −9.7 dB, which is what `docs/bom.md` and the 2b review say
it should be, and the jack still sees 1.01 MΩ either way. The netlist carries the swapped
values; **board 1 as built needs its two resistors exchanged** if the Line pad is to be the
−9.7 dB it was designed for. Nothing else about board 1 changed except where three pads sit,
because a cut strip cannot carry the switch's common to `U1.3`.

## The noise rules, and what each one rests on

The measured context is 2a's: the codec's ADC with its input shorted reads **−93.5 dBFS(A),
about 21 µV A-weighted** at 1.0 V rms full scale, unweighted −90.6 dBFS (about 30 µV), with
**no hum**; with the interface connected it reads −77 dBFS and shows a **90 Hz comb from the
SSL/host ground loop**, 7 dB above the codec's own floor. 2b's reading of that is that the
**ground path, not the supply**, is what limits this build — the codec's own LDO fed from the
host's 5 V already reaches the datasheet figure, so 2c's 78L05 leg is expected to change
nothing.

**Measured.** The 90 Hz comb is a measurement: a second ground path between the pedal and the
interface raises the floor by 7 dB. So is the codec's floor itself, and so is the 47 nF
ceramic shunt's distortion (loop THD −78 dB at 100 Hz to −58 dB at 4 kHz, rising 6 dB/octave).

**Reasoned.** Everything below that follows *from* those two measurements rather than being
one itself. Each is labelled.

| Rule | Why | Measured or reasoned |
|---|---|---|
| **One ground reference.** Every board's return goes to the star tag on its own wire; nothing is daisy-chained. | The 90 Hz comb is what a second ground path costs, measured. A star is the way to have exactly one. | **Measured** (the comb), reasoned (that this layout achieves it) |
| **The input reference is not shared with the relay/MIDI returns.** The control board's ground is its own wire to the star tag; the high-impedance input sits at the opposite corner of board A from the codec's digital row. | The relay coil's current and the MIDI optocoupler's edges are the switching currents in the box. `docs/build-board1.md` already keeps them off the analogue ground. | **Reasoned** |
| **The power board carries the supply currents.** D1, the bulk capacitance, R1/C2 and the 78L33 sit together, away from board A, so the 100 Hz charging current in C1/C2 does not flow in the copper the input reference sits on. | Ground currents in shared copper are what the comb shows; the same argument applies inside the pedal. | **Reasoned** — and 2b explicitly expects the supply leg to change nothing on the bench |
| **Decoupling at the op-amp pin, with its return next to it.** C3's ground lead lands on the same strip as U1.4, so the supply loop is the capacitor and the pin. | Standard practice; the loop area argument is the same one the comb supports. | **Reasoned** |
| **Signal and its return kept together.** The input comes in on screened cable with the screen bonded at the jack only; the outputs and the supply run as pairs; the input's return reaches the star by the shortest route the wiring allows. | The comb is a loop; loop area is what a loop picks up. 2a's lead practice (twist the ground lead with BCLK) is the same rule applied to the codec's digital side. | **Reasoned**, from a measured mechanism |
| **The high-impedance input stays away from the switching and the digital side.** The 1 MΩ node — the jack, C5, R5's top lead, the switch and U1.3 — is at the rear-right of board A, beside the jack; the codec's digital row (BCLK, the frame clock, SDA/SCL, 3V3) is at column 1, at the far end. The switch wires are the shortest the panel allows. | A 1 MΩ node is an antenna; 2a's bench already showed a 90 Hz comb arriving through a ground loop rather than through the air, so the emphasis is on keeping the *return* short and separate, not on shielding the node. | **Reasoned** |
| **Film, not ceramic, in the signal path.** C5 (input coupling) is 100 nF PET; LIN1's own 47 nF should become film in 2c. | The 2a loop measurement puts numbers on the ceramic's distortion. | **Measured** (2a's THD against frequency) |
| **The codec's analogue supply comes from the 9 V side.** AVDD from the 78L33 through the AVDD-ISO cut, VIN disconnected, SPKVDD open — 2c's leg 2, and only if leg 1 (VIN from a 78L05, no cutting) shows something. | 2c's whole design: the comparison that decides it is enclosed, in Phase 4. | **Reasoned** — 2c is explicit that a change here is a finding to chase, not a win |

## What board A is, and the split

Board 1 is the whole circuit on one 124.46 × 33.02 mm piece of the Kemo board, and it does
not fit the enclosure. Board A is the same circuit, split by what the noise argues for rather
than by what fits on one piece:

- **board A** — the input, the buffer, the bias and the output stage: everything the signal
  touches, and nothing that switches or rectifies;
- **the power board** — the 9 V input, D1, the bulk capacitance, R1/C2 and the 78L33. This is
  the split the 2b finding argues for: what the supply draws stays out of the analogue ground;
- **the control board** (board B in the enclosure) — the Pico, MIDI and the relay driver.

The size of board A is the enclosure's, not a number chosen here: `enclosure/src/layout.py`
places it at 18 × 20 holes, **45.72 × 50.8 mm**, and the codec's breakout sits above it on
two 16-pin socket strips which `layout.py` seats at hole (1, 2) — so those holes (columns 1
and 10, rows 2–17) are not board A's to use.

### What board 1 did that board A does not

The first job was to test whether board 1 is overkill. Its choices split cleanly:

**Noise-loaded, and kept:**

- the input coupling capacitor film rather than ceramic (2a measured the ceramic's distortion);
- decoupling at the op-amp's pin with the return beside it;
- one ground point, with every ground on its own wire to the star tag;
- the input's own screened cable, screen bonded at the jack end only;
- the switch kept off the highest-impedance node.

**Convenience, and dropped:**

- **50 holes along the strips.** The Kemo board is 100 mm wide and board 1's layout uses the
  whole 50-hole row; nothing about the circuit needs 124 mm. Board A is the enclosure's plate.
- **three ground buses stitched with three long links.** Board 1 has ground on rows 0, 5 and
  10, joined by links at (1,0)–(1,5), (23,5)–(23,10) and elsewhere. That is a routing
  convenience — it lets each part reach a nearby ground without a long lead — not a noise
  feature. On board A the ground is reached by the part's own lead and one link per net.
- **rows 2 and 13 left empty as spacers.** Board 1 keeps signal rows apart from the supply and
  bias rows by leaving gaps. On board A that separation is bought by *distance between the
  high-impedance nodes and the codec's digital row and the control board*, which is the
  separation that has an argument behind it, rather than by blank rows.
- **18 links and 22 cuts for a circuit with 15 parts.** Board 1 pays for its long layout in
  links and cuts, because a part that reaches across the board has to fly over the strips
  between. Board A is small enough that most nets are one strip, which is a difference in
  build effort and in the number of joints, not in noise.

## Where board A stands (2026-10-10, unfinished)

`stripboard/board_a.py` is **not finished and does not draw yet**. What it holds is the
analysis, and running it prints what is still wrong:

- the **outline**: 18 x 20 holes = 45.72 x 50.8 mm, taken from
  `enclosure/assets/kicad/board_a.kicad_pcb`'s Edge.Cuts and from `enclosure/src/layout.py`;
- the **codec's keep-out**: its two 16-pin socket strips are columns 1 and 10, rows 2-17
  (`layout.py` seats the breakout at hole (1, 2)), and its right-hand row's pads land at
  (10, 9), (10, 12), (10, 14), (10, 15) and (10, 16). Those holes are not board A's;
- a **placement of all 15 parts** that no two of them overlap, that keeps clear of those
  holes, and that no part's body sits over another part's lead or pad;
- the **cuts** that placement needs, derived from the rule below.

What is not done is the **links**: the cuts leave several nets in more than one piece, and
each piece needs a wire on the component side to join it. That is the last step, and it is
the step where every attempt so far has run out of free holes.

### The one hard constraint, which took the longest to see

A strip is a conductor, so any two pins that land on one strip are joined. A DIP-8 socket's
pins are 2.54 mm apart, so **two of them always share a strip**, and where those two are on
different nets the strip must be cut. The cut has to be at a hole, and a cut at a pin's own
hole disconnects that pin from its strip -- so the pin must reach its net through a hole
beside it. The socket's moulding is 10.16 mm across against pin rows 7.62 mm apart: it
overhangs each row by 1.27 mm, half a hole, so the hole beside a pin *is* free. That is what
makes the placement above legal, and it is the constraint that decides where the socket can
go at all: the pins whose strips must be cut have to be in the column whose outside is free
of the codec and of the other parts.

Getting this wrong is what `stripboard/board1.py` avoids by accident -- none of its 22 cuts
lands on a pin hole (checked), because its socket has room around it that board A does not.

### What is left

1. the links for the nets the cuts leave in pieces (the script lists them);
2. the three drawings -- copper with the cuts, components, and the wiring as labelled stubs
   with which wire goes from which component to what. `stripboard/stripboard.py` already
   draws wire stubs from the pad list (`Sheet.wires`), so this is the last piece of work once
   1 is done;
3. then the enclosure sandbox and the four `board_a_*` renders follow the outline above.

## Regenerating

```bash
python3 stripboard/nets.py       # the netlist itself
python3 stripboard/board1.py     # check board 1, rewrite its two drawings
python3 stripboard/board_a.py    # check board A's parts and cuts; prints what is left
```
