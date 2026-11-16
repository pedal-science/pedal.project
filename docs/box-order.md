# The box: what to order for the test case (2026-11-16)

Prepared for the owner, who places every order. It covers step 3 of the plan in
[box-design.md](box-design.md) (a drilled case with the real sockets in it) and the two checks
pedal-codec's plan still needs parts for. Prices and stock are JLCPCB's parts list on 2026-11-16;
LCSC's basket shows today's, and its minimum for a part may be more than the number here.

## 1. LCSC: the parts that go in the case

| Qty | Part | LCSC | Each | For |
|---|---|---|---|---|
| 4 | Neutrik NMJ6HCD2, ¼″ socket | C368502 | $3.27 | Three in the rear wall, one spare. With a meter on the first: is the chrome ferrule joined to the sleeve contact? |
| 1 | Neutrik NCJ6FA-H, combo XLR and ¼″ | C368458 | $3.06 | The right wall. The tightest fit in the case |
| 3 | XKB PJ-324M0, 3.5 mm socket | C2884986 | $0.55 | MIDI in. With a plug and a meter: which terminal is tip, which ring? |
| 5 | SHOU HAN TYPE-C 16PIN L8.35 | C5379909 | $0.16 | USB-C, behind its ⌀10 mm hole |
| 2 | Bourns PEC11R-4215F-S0024, encoder | C143790 | $2.33 | Holds the control board; its body height sets the board's distance from the face |
| 5 | Kinghelm KH-12X12X12H-TJ, button | C18186459 | $0.06 | Two in the face |
| 10 | Everlight 204-10SURD/S530-A3, 3 mm red lamp | C99772 | $0.04 | Two in the face. To compare: Kingbright WP710A10YD, yellow (C5139867), XINGLIGHT XL-304SYGC, yellow-green (C2895469) |
| 2 | ZHOURI 2.54-2*20, 40-pin socket | C2977589 | $0.32 | On the dummy Pi board: is the Pi 11 mm from it? |
| 5 | JST S2B-XH-A | C157931 | $0.07 | Does the fan's plug fit it? |

About $25 before postage and VAT.

## 2. Tayda: the case, drilled

- The case: **1590DD Style Aluminum Diecast Enclosure, A-5141**, $9.99 bare (the coated colours
  were listed at $15.99). Its drilling: **A-5141-CST-DR1**, $4.50, up to 40 holes.
- Tayda's order is made in its Box Tool (drill.taydakits.com), with an account under the same
  email as the Tayda shop account: a drill template, then a box job, then "Create Order", which
  fills the shop's basket. Its guides:
  [coordinates](https://www.taydaelectronics.com/enclosure-drill-service-guide),
  [ordering](https://www.taydaelectronics.com/enclosure-modification-ordering-guide-v1).
- Tayda's rules, from those guides: millimetres from the centre of each side's full outside, X
  to the right and Y up; no hole under 3 mm; **add 0.4 mm to every diameter for a powder-coated
  case** (they drill before coating); ±0.5 mm on the face and ±1 mm on the sides; rectangles
  with corners down to 0.5 mm radius, which is the screen's window.
- No printing on this one: there is no artwork yet.

The table is `python3 enclosure/src/box_layout.py --tayda`: 31 round holes and the window,
diameters already with the 0.4 mm added. Side A is the face seen from above with the rear wall at
the top, B the rear wall, D the front wall, E the right wall. **The signs on B, D and E are read
from Tayda's unfolded picture, not tried in the tool: check each side in its preview** (the
sockets' holes on B belong near the lid's edge, the fan's on D, the mic's on E).

```
== for Tayda's Box Tool: 1590DD, the tub 33 mm high outside
   side  what                          X       Y    drill
   A     screen window, 99 x 59     -29.8    16.2    99.4 x 59.4 rectangle, corners 0.5
   A     encoder                     41.8    24.8    7.6
   A     button 1                    35.8    -0.2    7.9
   A     button 2                    51.8    -0.2    7.9
   A     lamp 1                      35.8    -9.2    3.7
   A     lamp 2                      51.8    -9.2    3.7
   A     footswitch 1               -69.0   -25.8    12.4
   A     footswitch 2                 0.0   -25.8    12.4
   A     footswitch 3                69.0   -25.8    12.4
   B     USB-C power                -49.2     9.9    10.4
   B     MIDI in                    -13.2     8.6    6.9
   B     out                         35.8     5.0    11.8
   B     EXT FS                      54.4     5.0    11.8
   B     guitar in                   73.2     5.0    11.8
   B     air in                     -39.2     3.1    4.9
   B     air in                     -32.2     3.1    4.9
   B     air in                     -25.2     3.1    4.9
   B     air in                     -35.8     8.6    4.9
   B     air in                     -28.8     8.6    4.9
   B     air in                     -21.8     8.6    4.9
   D     air out (fan)              -31.2     0.5    5.9
   D     air out (fan)              -23.8     0.5    5.9
   D     air out (fan)              -27.5     7.0    5.9
   D     air out (fan)              -35.0     7.0    5.9
   D     air out (fan)              -38.8     0.5    5.9
   D     air out (fan)              -35.0    -6.0    5.9
   D     air out (fan)              -27.5    -6.0    5.9
   D     fan screw                  -21.2    10.5    3.4
   D     fan screw                  -41.2    -9.5    3.4
   E     mic                          0.0     7.8    22.4
   E     mic screw                   -9.9    17.6    3.6
   E     mic screw                    9.9    -2.2    3.6
```

## 3. Anywhere: the fan

| Qty | Part | For |
|---|---|---|
| 2 | 25 × 25 × 10 mm, 5 V, two-wire fan with an XH2.54 two-pin plug (sold as "2510 5V XH2.54"; Winsinn's is one) | The front wall. Check which wire is + before it is plugged in: the Pi board's pin 1 is +5 V |
| 4 | M2.5 × 16 mm screws and nuts | Two hold the fan |

## Not on this order

The boards themselves (step 6), the flat cables (their type is fixed at layout), and the block
and pad for the processor (optional; sized once the test case is in hand).
