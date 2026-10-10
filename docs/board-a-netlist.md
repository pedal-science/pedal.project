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

Board 1's own data had **R5 = 330k and R6 = 680k**, and that pair is the transposition. The
topology was right — the switch's common is the follower's input, its Inst throw is node A
past C5 and its Line throw is node B between R5 and R6 — but the values were the wrong way
round: R5 is the 680 kΩ *top* of the Line pad and R6 the 330 kΩ *shunt* from node B to the
bias. The BOM says so directly ("the 680 kΩ … the top of the Line pad", "the 330 kΩ … the
bottom of the Line pad"), and the network says so numerically: at 1 kHz, with C5 = 100 nF and
a 10 kΩ source, **R5 = 680k / R6 = 330k gives Inst ×1.00 and Line 0.324 (−9.8 dB)**, while
R5 = 330k / R6 = 680k gives Line 0.667 (−3.5 dB). Inst is ×1 either way, because the follower's
input is node A itself and nothing divides the signal there; the jack sees R5 + R6 = 1.01 MΩ
at Inst and R5 ∥ R6 ≈ 222 kΩ at Line in both cases, which is why the mistake is audible only
on Line, and only as "the pad is loud".

So the values have been exchanged in the netlist and in `stripboard/board1.py`,
`stripboard/board_a.py` and `docs/build-board1*.md`, and an earlier note here had it
backwards: it is the values it called the original (top 680k) that the BOM's −9.7 dB needs,
and its "Inst ≈ 0.81" was wrong — the Inst position is not a division of the signal at all.
**Anyone who built from the sheets before this fix has R5 and R6 the wrong way round**; it is
the same footprint in the same holes, so it is a straight swap of the two parts, with no
rewiring and no cut changes.

Two pads moved with the netlist extraction, because a cut strip cannot carry the switch's
common to `U1.3`: `SW-C` is on U1.3's row-3 strip and `SW-I` on node A's row-6 piece, which is
what `docs/build-board1.md`'s off-board table now says.

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

### How big board A has to be

The 18 x 20 outline was a guess, so it was treated as one: outlines of 18 x 20, 20 x 20,
22 x 20, 18 x 26, 18 x 30, 22 x 26 and 22 x 30 holes were each searched for a placement and a
routing, for a bounded time each.  **None closed.**  That is a statement about the search as
much as about the board -- the same routers cannot route board 1, which is built and working --
but it does say one useful thing: **the board is not short of area.**  Every one of those
outlines has hundreds of free holes; what they lack is free *rows and columns between the
parts*, which more area does not create.  The stage needs a placement with its routing
corridors reserved, which is what the taller 18 x 24 outline starts to do: it gives the output
stage its own band (rows 16-23) clear of the codec's pads at column 10, which is the one
improvement the extra height actually bought.

### Where the codec goes

It stays **above board A**, but no longer seated in it.  `enclosure/src/layout.py` seats its two
16-pin socket strips at hole (1, 2), which is what costs the board columns 1 and 10 for rows
2-17.  Moving the module off board A altogether is not free either: the nearest position that
does not overlap board A, the Pi or board B is 55 mm from the input, and that puts a long lead
on the codec's *input* side -- the one thing board A's placement exists to avoid.

So: **the codec keeps its position above board A, on taller standoffs, and comes down on short
fly leads instead of through socket strips.**  Its ground is its own wire to the star.  That
keeps the LIN1 lead short, frees the whole 18 x 20 holes for the analogue stage, and is neutral
for noise -- 2a's comb was a *second* ground path, which this does not add.  It is what the
search above needs: with those two columns reserved, no placement routed; without them, the
board has the copper its wires need.

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

`stripboard/board_a.py` **draws**, and the placement now carries the rule the routing kept
asking for: **every lead and pad hole has a hole beside it a wire may end in**, and no two
neighbouring leads of different parts sit on different nets. `stripboard/_place.py` measures
both. The placement before this pass had **three** leads with no hole beside them at all — the
two input coupling capacitors' inner leads, each boxed in by its neighbour's body, and a 1M
resistor's lead on the bottom edge with both gaps beside it cut — and no cut or link can free
a lead like that, which is why three routing attempts failed on a placement with no geometric
errors. The output stage is what moved: its six parts now stand in one band at row 16, at
x = 0, 3, 5, 7, 12 and 14, with the input chain's lower half at x = 8. **That cost nothing in
area**: the outline is unchanged.

Two things are settled and should not be redone:

- **a defect in the checker, fixed.** `stripboard.copper` unioned holes along a row and,
  through the links, between rows, but never within a column — so a part lying down a column
  (a resistor's leads are in different rows, and its own body joins those two strips) was
  never credited with joining them, and nothing could be reported as shorted down a column.
  `board1.py`, built and measured, checks out unchanged with the fix.
- **rule 3b: a link may only be soldered where its own net already is.** A wire end joins the
  hole's piece of strip, so a link ending in a hole on another net's strip is a short, and
  rule 2's union-find cannot report it because the union the link makes is what hides it.
  Board 1 obeys this on all eleven of its links; a router that ignores it produces shorts no
  check will catch.

What is not finished is still the **connectivity**: with the 27 cuts this placement needs, the
checker reports **12 nets in more than one piece and no two nets joined**. The placement is
legal and the copper is sound; the wires are not placed.

Three things were settled in the pass after that, and the third is the one that matters:

- **a part's lead span now comes from its footprint.** `stripboard.py` used to hold a radial
  electrolytic to two holes of lead span, and the band search that produced this placement was
  scoring a 10 µF electrolytic as *four* holes -- a part nobody sells, with a body the checker
  cannot draw. The span is now the footprint's pad pitch in holes (`EL` in `stripboard.py`):
  2.0-2.5 mm, so **one hole**, i.e. the two leads are neighbours. `board1.py`, built and
  measured, checks out unchanged with the tighter rule (its electrolytics were always
  neighbours), and `board_a.kicad_pcb` carries `CP_Radial_D5.0mm_P2.00mm` for C4 and
  `CP_Radial_D6.3mm_P2.50mm` for C6/C7 -- which is where the numbers come from;
- **a wire is a wire.** The checker now puts each link in the holes it runs over, not only in
  the two it ends in, so a wire crossing a lead, a pad or another part's body is an error; and
  two wires of *one* net may be soldered in one hole, because that is how a run that has to
  turn is built. Board 1 still checks out unchanged;
- **the exits rule, in `stripboard/_place.py`.** This is the rule the routing kept asking for
  and the placement search never had, and it is asked of the checker and the layout data rather
  than of a copy of either. For every net: can a wire -- running only over free holes, ending
  in a lead or in the free hole beside a pad -- reach every piece of the net? A piece with no
  free hole in it, and no path of free holes to another piece, is a piece no builder can wire.
  **This placement fails it**, on IN_A, IN_B, GND_A, HPL, HPR, OUT_L_N and OUT_R_N, and the
  failures are structural, not a router running out of effort: row 15, the output band's only
  way out, carries GND_A; column 11, U1.3's only exit, dead-ends on row 1; row 21 is V9_RAW
  from end to end and blocks the output nets' way down. `stripboard/_route.py` agrees, with the
  checker's own `copper()` as its only oracle and no hand-rolled predicate anywhere: it places
  what it can (IN_A, IN_B, BIAS, BIAS_MID, VF, OUT_L) and then reports **no route** for the
  rest, naming the copper that refuses the wire's end. 7 of the 12 splits are GND_A, the net
  with the longest way to travel and the star at the bottom edge.

`enclosure/src/layout.py` has **not** yet been changed, so the enclosure model still seats the
codec on board A — see "Which tool produced which answer" above for why it should not.

- the **outline**: 18 x 24 holes = 45.72 x 60.96 mm (`board_a.py`'s `W, H`; the KiCad file
  and `enclosure/src/layout.py` still carry the old 18 x 20 = 45.72 x 50.8 mm and have not
  been moved yet — that step waits on the check passing);
- the **codec's keep-out**: its two 16-pin socket strips are columns 1 and 10, rows 2-17
  (`layout.py` seats the breakout at hole (1, 2)), and its right-hand row's pads land at
  (10, 9), (10, 12), (10, 14), (10, 15) and (10, 16). Those holes are not board A's;
- a **placement of all 15 parts** that no two of them overlap, that keeps clear of those
  holes, and that no part's body sits over another part's lead or pad;
- the **cuts** that placement needs, derived from the rule below.

What is not done is the **links**: the cuts leave several nets in more than one piece, and
each piece needs a wire on the component side to join it. That is the last step, and it is
the step where every attempt so far has run out of free holes.

### Which tool produced which answer

Both were asked the same question — "is there a legal layout of the analogue stage on board A
with the codec's socket strips seated on it?" — and the answer is only as good as the tool:

| Tool | Result | What it is worth |
|---|---|---|
| greedy router (`stripboard/route.py`'s predecessor, and `solve.py`) | **0 of 3000 placements routed** | evidence about how tight the board is, not proof: a greedy join takes the shortest run it can reach and never undoes it, so it fails on boards that are merely awkward |
| backtracking router (`stripboard/solve.py`, A* per net, nets hardest-first, undo on dead ends) | **0 of ~3700 placements routed**, within a 60 000-node budget | the same answer from a stronger tool, so the conclusion is worth more — but it is still a bounded search, not a proof |

Neither router is trusted to say "impossible"; both are trusted to say "not found within the
effort given". The codec going on its own standoffs is a design decision taken on that
evidence, not a proof that the seated variant cannot be built.

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
python3 stripboard/board_a.py    # check board A's parts, cuts and links; prints what is left
python3 stripboard/_place.py     # the placement rules: spare holes, neighbouring nets, exits
python3 stripboard/_route.py     # route each net, hardest first, and say where it cannot
python3 stripboard/_corridors.py # the corridor plan, as a drawing
```

`_place.py` and `_route.py` are the tools that answer questions about a placement rather than
checking a board: `_place.py` says whether the placement *can* be wired, `_route.py` wires it
and says where it cannot. Neither is trusted to say "impossible"; both are trusted to say "not
found, and here is the copper that stopped it".
