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
| 5 | JST S2B-XH-A | C157931 | $0.07 | Does a fan's plug fit it? |

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
  (the tool's Shapes tab), which is the screen's window.
- Coated, in the owner's colour, matte black: the finished pedal will be, and whether a socket
  or a lamp fits its hole depends on the coat. If a bare case is ordered instead, take the
  0.4 mm back off every diameter.
- Printed, since 2026-11-17: the pedal's name on the face, from
  `enclosure/print/tayda-1590dd-side-a.pdf` (box-design.md, "The print on the face"). Tayda
  prints the file as it is sent and does not check it, and its form asks the owner to confirm
  three things about the file before it will save it.
- About $20 for the case and its drilling, before the printing and postage.

The table is `python3 enclosure/src/box_layout.py --tayda`, for Tayda's own case (its drawing
A-5141; Hammond's differs by a millimetre or so in places): 30 round holes and the window,
diameters already with the 0.4 mm added. If the model changes, print it again.

**Tayda's tool draws the 1590DD upright**, the face 117 mm wide and 185 mm high (seen in the
tool itself on 2026-11-16; the table before that date had the pedal on its side, and was
wrong). So the pedal is turned a quarter turn anticlockwise to fit: side A is the face with
the pedal's right-hand end at the top, **B the pedal's right wall** (the mic), **C its rear
wall** (the sockets and the air inlet), **E its front wall** (fan B), **D its left wall**
(fan A). The walls are drawn folded out flat from the face, so on C the face is to the right
and the lid's edge to the left, and on E the other way round. In the tool's picture the
sockets on C belong nearer the picture's left edge, fan B's holes on E about the middle, fan
A's at the right-hand end of D, and the screen's window in the lower left of the face.

**In the owner's Box Tool account** (2026-11-17), none shared:

| What | Number | Holds |
|---|---|---|
| Drill template "Pedal box test case 2, two fans" | 37366 | **The table below**: 30 holes and the window, read back from the tool's own picture and equal to the table, none marked red |
| Drill template "Pedal box test case 1" | 37365 | The design before 2026-11-17: one fan on the front wall, six small inlet holes. Kept, not for ordering |
| Box job "Pedal box test case 1, matte black" | 4909 | The case, **A-5925, 1590DD matte black, $14.99**, and the drilling, A-5141-CST-DR1, with drill template 1. **To be replaced** by a box job with template 2 and the print |

Tayda's page for A-5925 says matte black can take longer to make than other colours. Still to
do there: the UV print template (the owner uploads the file and confirms it), a box job with
drill template 2 and the print, then "Create Order", quantity 1, which fills the shop's
basket; the owner checks out.

One hole is close to an edge: the USB-C socket's, 1.4 mm from the tub's rim as drilled.
Tayda's ±1 mm on the walls could leave that strip under a millimetre wide.

```
== for Tayda's Box Tool: 1590DD, the tub 33 mm high outside
   side  what                          X       Y    drill
   A     screen window, 99 x 59     -16.2   -29.8    rectangle 59.4 wide, 99.4 high
   A     encoder                    -24.8    41.8    7.6
   A     button 1                     0.2    35.8    7.9
   A     button 2                     0.2    51.8    7.9
   A     lamp 1                       9.2    35.8    3.7
   A     lamp 2                       9.2    51.8    3.7
   A     footswitch 1                25.8   -69.0    12.4
   A     footswitch 2                25.8     0.0    12.4
   A     footswitch 3                25.8    69.0    12.4
   C     USB-C power                 -9.9   -49.2    10.4   1.4 mm from the side's edge
   C     MIDI in                     -8.6   -13.2    6.9
   C     out                         -5.0    35.8    11.8
   C     EXT FS                      -5.0    54.4    11.8
   C     guitar in                   -5.0    73.2    11.8
   C     air in                      -6.5   -36.2    9.4
   C     air in                      -6.5   -24.7    9.4
   D     air out (fan A)             28.8     0.5    8.4
   D     air out (fan A)             36.2     8.0    8.4
   D     air out (fan A)             43.8     0.5    8.4
   D     air out (fan A)             36.2    -7.0    8.4
   D     fan A screw                 26.2    10.5    3.4
   D     fan A screw                 46.2    -9.5    3.4
   E     air out (fan B)             -0.5   -23.8    8.4
   E     air out (fan B)             -8.0   -31.2    8.4
   E     air out (fan B)             -0.5   -38.8    8.4
   E     air out (fan B)              7.0   -31.2    8.4
   E     fan B screw                -10.5   -21.2    3.4
   E     fan B screw                  9.5   -41.2    3.4
   B     mic                         -7.8     0.0    22.4
   B     mic screw                  -17.6    -9.9    3.6
   B     mic screw                    2.2     9.9    3.6
```

## 3. Anywhere: the fans

| Qty | Part | For |
|---|---|---|
| 3 | 25 × 25 mm, **6 or 7 mm thick**, 5 V, two-wire fan (Sunon's MF25060V2-1000U-A99 is 6 mm; sold loosely as "2506" or "2507 5V"). With an XH2.54 two-pin plug if it can be had, or bare leads and a bought XH lead | Two in the case and one spare. **Not 10 mm thick**: fan A, on the left wall, has 9 mm to footswitch 1. Check which wire is + before it is plugged in: the Pi board's pin 1 is +5 V |
| 8 | M2.5 × 12 mm screws and nuts | Two hold each fan |

## Not on this order

The boards themselves (step 6), the flat cables (their type is fixed at layout), and the block
and pad for the processor (optional; sized once the test case is in hand).
