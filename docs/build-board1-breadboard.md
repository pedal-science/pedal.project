# Board 1 on the breadboard

The first half of building board 1 (the 9 V supply, the input buffer and the output stage). Prove
the circuit on the breadboard, get first sound through it, then solder it with
[build-board1.md](build-board1.md). Decided 2026-10-01: the breadboard is quick to change, and the
stripboard is then built once, as practice for the tighter enclosure board (board A). Written
2026-10-01, in the same way as [codec-bringup-2a.md](codec-bringup-2a.md): you do the hands-on work,
Claude checks readings and photos and runs the software.

**What the breadboard is for, and what it isn't.** It proves the circuit: voltages, levels, the
Inst/Line switch, and first sound through `namchaind`. It isn't for the noise measurements. Long
breadboard rows and loose leads pick up hum a soldered board won't, so Phase 2's "noise floor at
each stage" is measured on the soldered board.

**The op-amp can wait.** Everything up to stage 6 is done without it (CPC, due 4 Oct).

The placement is [breadboard/board1.py](../breadboard/board1.py). It takes its netlist from
[stripboard/board1.py](../stripboard/board1.py), so the two builds are the same circuit, and running
it checks the placement against that netlist and redraws the picture:

```bash
python3 breadboard/board1.py
```

---

## The placement

![Board 1 on the breadboard](../breadboard/board1.svg)

Columns 1–63, rows **a–e** above the centre channel and **f–j** below it. The five holes a–e of a
column are joined, and so are f–j. The rails: **T+** (top, red) carries the filtered supply VF,
about 8.7 V. **T−** (top, blue) and **B−** (bottom, blue) are ground, joined by one jumper at the
left. **B+** is unused.

| Part | Value | Holes | Notes |
|---|---|---|---|
| D1 | 1N5817 | anode c55, cathode c50 | Band towards column 50 |
| C1 | 100 µF 25 V | + a50, − T− | Stripe (−) into the rail |
| R1 | 100 Ω | d50–d46 | |
| C2 | 100 µF 25 V | + b46, − T− | |
| C3 | 100 nF ceramic | b20, T− | Decoupling at U1 pin 8 |
| R2 | 10 kΩ | T+, a27 | |
| R3 | 10 kΩ | c27–c23 | |
| R4 | 10 kΩ | a23, T− | |
| C4 | 10 µF 50 V | + g15, − B− | |
| U1 | OPA2197 on its adapter | pins 1–4 in f20–f23, pins 8–5 in e20–e23 | Across the channel, pin 1 at **f20** (bottom left). Stage 6 |
| C5 | 100 nF film | g5–g7 | |
| R5 | **680 kΩ** | h7–h11 | The Line pad's top: node A to node B |
| R6 | **330 kΩ** | i11–i15 | The Line pad's bottom, to the bias: node B to the bias |
| C6, C7 | 10 µF bipolar | h30–h31, h38–h39 | Either way round |
| R7, R9 | 100 Ω | g31–g35, g39–g43 | |
| R8, R10 | 1 MΩ | i35, B−; i43, B− | |

Jumpers: a20–T+, a46–T+, i20–i21, b21–b22, b23–f15, j23–B−, and T−–B− at column 2.

Wires off the breadboard: **V9** a55, **STAR** T−, **IN** j5, **SW-I** j7, **SW-L** j11,
**SW-C** j22, **LIN1** j20, **HPL** j30, **HPR** j38, **OUT-L** j35, **OUT-R** j43. They go where
[build-board1.md](build-board1.md)'s "Off-board wires" table says.

- **Keep clear of the adapter.** Its board overhangs its pins by about 1.5 mm, so rows d–g of
  columns 19–24 stay empty apart from U1's own pins. The checker enforces this.
- **Don't cut the leads short.** Bend them to fit and leave the spare length, so the same parts can
  move to the stripboard afterwards.
- **Wire ends.** Breadboard holes take solid wire. For the jacks, switch and DC socket, solder a
  male-ended jumper lead or a short piece of solid wire onto each lug. Tinned stranded wire frays in
  the contacts.
- **A stranded core into a breadboard.** The screened cable's core is stranded too, so it gets a pin
  the same way. Strip about 20 mm of jacket; cut the screen back flush with the jacket and heatshrink
  the cut — it is bonded to the jack's sleeve lug at that end only and connects to nothing here, and
  a second ground connection is what made the 90 Hz comb — then strip and tin ~3 mm of core, solder
  it to one pin cut off the 40-way header strip, and heatshrink that joint. Push the pin into a
  **free hole in the column** the target pin sits in, never the target's own hole, and anchor the
  cable so a tug pulls the anchor rather than the pin. Leave the cable long enough to reach the
  soldered board later: the pin is cut off then and the core soldered to the pad instead.
- **The star point.** Every ground returns to one place, each item on its own wire, and nothing else
  joins two grounds together — a second path is what put the 90 Hz comb beside the codec's floor
  (2b). The breadboard's **ground rail** is that place for now: it is one node, so give each ground
  wire's pin its **own hole**, never two in one. Bridge the rail if yours is split half way, and tie
  the top and bottom rails at **one** point only — tie them at both ends and you have built the loop
  you were avoiding. Check it end to end with the meter: it should beep, and read well under an ohm.
  Keep noisy loads off it. The soldered build uses the M3 tag on board A's front corner instead; if
  the wires still end in pins by then, common a 1×8 socket strip along one stripboard row and bolt
  the tag beside it, so every ground wire plugs into its own socket.

---

## Rules

The same as [build-board1.md](build-board1.md#rules-for-the-whole-build): nothing powered while
you change anything, the Cioks outlet is centre-negative, never ground HPL/HPR/OUT3, keep the four
high-impedance input wires short, and one ground point at the star tag.

---

## Stage 1: parts and terminals

- [ ] [build-board1.md](build-board1.md) stage 1: meter-check the parts.
- [ ] [build-board1.md](build-board1.md) stage 2: find the jack, DC socket and switch lugs, and
      confirm +9 V on the DC socket's sleeve.

> **▶ Tell Claude:** the lug map and the 9 V reading.

## Stage 2: the breadboard

Use the spare breadboard. The codec board stays where it is.

- [ ] **Check the rails run the full length.** Continuity from column 1 to column 63 along each of
      the four rails. Many 830-point boards split each rail in the middle. If yours does, bridge the
      gap on T+, T− and B− with a short jumper.
- [ ] Check that T+ and T− don't beep to each other. They shouldn't on a new board.

## Stage 3: the supply

- [ ] Fit D1, C1, R1, C2 and C3, and the jumpers a46–T+ and T−–B−.
- [ ] Wire the DC socket's **sleeve** (+9 V) lug to **a55**, and its **centre** (0 V) lug to the M3
      star tag. Wire the tag to the **T−** rail.
- [ ] Cioks on. Measure against the star tag:
  - a55: about 9 V
  - column 50 (C1's +): about 0.2–0.3 V less
  - the T+ rail: the same again

> **▶ Tell Claude:** the three voltages.

## Stage 4: the bias, the input and the outputs

Cioks off.

- [ ] Fit R2, R3, R4, C4 and the jumper b23–f15. Cioks on, and measure **column 23, top half** (it
      will be U1 pin 5): expect about **2.9 V**, a third of T+. Cioks off.
- [ ] Fit the jumpers a20–T+, i20–i21, b21–b22 and j23–B−.
- [ ] Fit C5, R5, R6, C6, R7, R8, C7, R9 and R10.
- [ ] Wire the jacks, the switch and the star tag as in
      [build-board1.md](build-board1.md) stage 6: sleeves (and the outputs' rings) to the tag, the
      input jack's tip switch to its sleeve, the screened cable's screen to the jack sleeve only.

## Stage 5: check it all before the op-amp exists

Cioks on, op-amp not fitted. Measure the holes U1's pins will go into, against the star tag:

| U1 pin (hole) | Expect |
|---|---|
| 8 (e20) | about 8.7 V |
| 4 (f23) | 0 V |
| 5 (e23) | about 2.9 V |
| 3 (f22) | **the lower of the two positions, always.** The meter loads the node it is on, so what it reads depends on its own input resistance: at Inst it sits on node A and reads `Vbias × Rm/(Rm + 1.01 MΩ)`; at Line it sits on node B and reads `Vbias × Rm/(Rm + R6)`. Worked with Vbias = 2.95 V: **Rm = 1 MΩ → Inst ≈ 1.50 V, Line ≈ 2.24 V**; **Rm = 10 MΩ → Inst ≈ 2.67 V, Line ≈ 2.86 V**. So Line is the higher reading at any meter. **Measure Rm from the pair:** `Rm = 1.01 MΩ × V_Inst/(Vbias − V_Inst)`. **Measured 2026-10-11:** bias 3.0 V, pin 3 at Inst 1.55 V and at Line 2.30 V — Rm = 1.08 MΩ, and the Line figure is within 10 mV of what that Rm predicts, so this board's input network is the netlist's. **The −9.7 dB pad is an audio figure and no DC voltmeter can show it** — these readings only identify which position the toggle is in and what the meter is loading. The unambiguous test is on the ohms range, power off: **f22 to the bias hole e23 reads 1.01 MΩ at Inst and 330 kΩ at Line** (measured: 1.01 MΩ and 330 kΩ, so the switch, R5 and R6 are all in circuit and the Inst pad's joint is sound), and the toggle's middle lug beeps to the SW-I wire (j7) at Inst |

Then, Cioks off: about **1 MΩ** from each output jack's tip to ground, and no continuity from HPL
(j30) or HPR (j38) to ground.

> **▶ Tell Claude:** the readings and a photo from above, square on. Claude checks the photo
> against the placement.

## Stage 6: the op-amp

- [ ] Solder the OPA2197 onto the adapter as in [build-board1.md](build-board1.md) stage 8. The
      Aries board has bare tinned pads — two rows of four at 1.27 mm, with the vias between them.
      Which adapter pin is pin 1 is not readable off the board (the chip sits across the pin
      columns), so find it by continuity before soldering: the pad under the chip's **dot** lead
      beeps to exactly one of the eight pins, and that pin is pin 1. Solder the chip in that
      orientation.
- [ ] Cioks off. Press the adapter across the channel, **pin 1 at f20** — the chip's **dot end
      pointing left**, so pin 1 is in f20 (bottom-left of the group) and pin 8 in e20 (top-left,
      the T+ hole). The adapter fits 180° the wrong way, and that feeds the chip's V− from T+ and
      its V+ from ground: the rail then collapses to about 1 V, both outputs sit near 0.5 V, and
      R1 gets hot.
- [ ] Cioks on. **f20** (pin 1) and **e21** (pin 7) both at the bias — **3.0 V** on this board —
      and e20 (pin 8) at the rail, **9.0 V**. Note that pin 3 is *not* a good place to read the
      bias once the op-amp is in: its node still sees the meter's own 1 MΩ, so it keeps reading
      the loaded 1.55 V / 2.3 V whereas the follower's output sits at the true bias.

> **▶ Tell Claude:** a photo of the soldered adapter before it goes in, then the three voltages.

## Stage 7: the codec, and first sound

As [build-board1.md](build-board1.md) stages 9 and 10, with the breadboard in place of the board:
LIN1 (j20) → codec LIN1, codec HPL → j30, codec HPR → j38, codec GND → the star tag, and nothing
else joining the two. Claude moves `namchaind` to the codec (asking first, and not during Phase 1's
soak). Amp volume low, guitar in at Inst, play, then try Line.

If something needs changing, change it here and tell Claude. The layout files are updated before
anything is soldered.

---

## Results

| What | Value | Date |
|---|---|---|
| Rails split in the middle? | | |
| V9 / C1 / T+ | | |
| Bias (e23, U1 pin 5) | **3.0 V** — a third of T+, and the figure Stage 5's two pin-3 readings are measured against | 2026-10-11 |
| Pin 3 (f22), Inst / Line | **1.55 V / 2.30 V** — Inst is the lower of the two, always, because its reading looks through R5 + R6 while Line's looks through R6 alone | 2026-10-11 |
| Pin 3 ↔ pin 5 on ohms, Inst / Line | **1.01 MΩ / 330 kΩ** — 3:1, power off. This is the check that identifies the toggle's position without depending on the meter, and it proves R5 is in circuit | 2026-10-11 |
| Meter's own input resistance | **≈ 1.08 MΩ**, from the bias and the Inst reading. Stage 5's earlier "2.9 V / 2.5 V" assumed 10 MΩ and was wrong; the expected values are in ratio form now | 2026-10-11 |
| Output jacks, HPL / HPR | **1 MΩ** from the left output jack's tip to ground (R8), and **no continuity** from HPL or HPR to ground. The right jack is not wired yet; it gets the same 1 MΩ check (R10) when it is | 2026-10-11 |
| Op-amp outputs (f20 / e21) | **3.0 V / 3.0 V** — both followers sit at the bias, and e20 (pin 8) at the 9.0 V rail. The chip had been reverse-supplied first (the adapter 180° out) and survived | 2026-10-11 |
| Adapter orientation | Pin 1 is found by continuity, not by eye: the pad under the chip's dot lead beeps to one pin, and **that** pin goes to f20 with the **dot end pointing left**. Inserted the other way round the chip's V− is fed from T+ and its V+ from ground, the rail collapses to about 1 V and R1 gets hot — that happened once, here, and cost nothing | 2026-10-11 |
| First sound | | |
| Changes for the soldered board | **R5 = 680 kΩ (the pad's top), R6 = 330 kΩ (the pad's bottom, to the bias)** — the build docs and the breadboard drawing had these transposed until 2026-10-11 and the board was built from them, which makes Line −3.5 dB instead of −9.7 dB. The fix is to swap the two resistors: same holes, no rewiring. `docs/bom.md` had the values right all along ("from A, 680 kΩ to node B, then 330 kΩ from B to the bias") | 2026-10-11 |
