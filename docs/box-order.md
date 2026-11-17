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

## 2. Tayda: the case, drilled (ordered 2026-11-17)

- The case: **1590DD Style Aluminum Diecast Enclosure, A-5141**, $9.99 bare (the coated colours
  were listed at $15.99; matte black, A-5925, at $14.99). Its drilling: **A-5141-CST-DR1**,
  $4.50, up to 40 holes. The base plate (Tayda's "lid") is drilled by a separate service,
  **A-5141-CST-DRL**, $4.00, ±0.5 mm, chosen in the box job beside the first.
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
- **$27.49 before postage** (Tayda's shop, 2026-11-17): the case $14.99, its drilling $4.50, the
  base plate's $4.00, and the face's print, **A-5141-CST-UV**, $4.00. The box job also offers
  printing the white twice (A-99999-CST-UV-WH, $2.00 a side), which Tayda sells "only for some
  customers who want white to be more white"; not chosen.

The table is `python3 enclosure/src/box_layout.py --tayda`, for Tayda's own case (its drawing
A-5141; Hammond's differs by a millimetre or so in places): 18 round holes and the window in
the case, 8 in the base plate, diameters already with the 0.4 mm added. If the model changes,
print it again.

**Tayda's tool draws the 1590DD upright**, the face 117 mm wide and 185 mm high (seen in the
tool itself on 2026-11-16; the table before that date had the pedal on its side, and was
wrong). So the pedal is turned a quarter turn anticlockwise to fit: side A is the face with
the pedal's right-hand end at the top, **B the pedal's right wall** (the mic), **C its rear
wall** (the sockets and the air outlet), E its front wall and D its left wall (nothing on
either). The walls are drawn folded out flat from the face, so on C the face is to the right
and the lid's edge to the left. In the tool's picture the sockets on C belong nearer the
picture's left edge, and the screen's window in the lower left of the face.

**The base plate is Tayda's "Lid"**, drawn the size of the face. Tayda gives no orientation
for it. Every other side's coordinates are as seen from outside, so the lid's are taken as
seen from below, which puts the fan's eight holes in the lower left of the lid's picture. The
lid's corner screws are symmetric: it is fitted whichever way round puts the fan's holes under
the gap between footswitches 1 and 2, so a lid drawn the other way up still fits.

**In the owner's Box Tool account** (2026-11-17); the drill templates are not shared:

| What | Number | Holds |
|---|---|---|
| Box job "Pedal box test case 3, floor fan, printed, matte black" | 4918 | **The one to order**: the case, **A-5925, 1590DD matte black**; its drilling, A-5141-CST-DR1, and the base plate's, A-5141-CST-DRL, both from drill template 37371; the face's print, A-5141-CST-UV, from UV template 35359 |
| UV print template "Pedal box face, pedal.science" | 35359 | `enclosure/print/tayda-1590dd-side-a.pdf` on side A, CMYK and RDG White; uploaded and confirmed by the owner |
| Drill template "Pedal box test case 3, floor fan" | 37371 | **The table below**: 26 holes and the window, read back from the tool's own picture and equal to the table, none marked red |
| Drill template "Pedal box test case 2, two fans" | 37366 | Two 25 mm fans blowing out through the left and front walls. Superseded the same day, kept |
| Drill template "Pedal box test case 1" | 37365 | One fan on the front wall, six small inlet holes. Superseded, kept |
| Box job "Pedal box test case 1, matte black" | 4909 | The case and its drilling with drill template 1, no print. Superseded by 4918 and kept: it gets no quantity when the order is made |

Done there on 2026-11-17, on the owner's go-ahead: "Create Order" with quantity 1 against box
job 4918 and none against 4909, then "Add to Cart & Create Order", which reserved the order
(reservation 3734, "Awaiting order" on the Box Tool's dashboard) and put the four items in the
shop's basket at quantity 1 each: $27.49 before postage, Tayda's own total. The Box Tool opens
the basket in a new tab, which an agent's browser pane blocks; the dashboard's "Re-checkout @
Tayda" button makes the same link,
`https://www.taydaelectronics.com/direct/index/add/?product=<SKUs>&qty=<quantities>`, which can
be opened directly. The basket's quantities are left as they are: the Box Tool says a changed
quantity stops it matching the order to the reservation.

**Ordered by the owner the same day**, with DHL Express, VAT and duty paid, $26.04 and 2-4 days
in transit: $53.53 in all (the order number is in Tayda's email to the owner). The Box Tool's
dashboard then showed it received, as **box job 80927**, "awaiting production", with both
drillings against drill template 37371 and the print against UV template 35359, and counters for
Drilled (0/2), UV Printed (0/1) and QC Passed (0/1). Tayda raises any problem with a template on
that dashboard, not by email, so it is the place to look until the case ships. Tayda's page for A-5925 says the case may take 3-4 business days to make, and matte black
longer than other colours.

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
   C     air out                     -6.5   -36.2    9.4
   C     air out                     -6.5   -24.7    9.4
   Lid   air in (fan)               -34.8   -24.0    8.4
   Lid   air in (fan)               -43.8   -29.2    8.4
   Lid   air in (fan)               -43.8   -39.8    8.4
   Lid   air in (fan)               -34.8   -45.0    8.4
   Lid   air in (fan)               -25.7   -39.8    8.4
   Lid   air in (fan)               -25.7   -29.2    8.4
   Lid   fan screw                  -46.8   -22.5    3.4
   Lid   fan screw                  -22.8   -46.5    3.4
   B     mic                         -7.8     0.0    22.4
   B     mic screw                  -17.6    -9.9    3.6
   B     mic screw                    2.2     9.9    3.6
```

## 3. Anywhere: the fan, its filter and the feet

| Qty | Part | For |
|---|---|---|
| 2 | 30 × 30 × 10 mm, 5 V, two-wire fan (Sunon's MF30100V2-1000U-A99 is the kind: 4.7 cubic feet a minute, 21 dB(A)). With an XH2.54 two-pin plug if it can be had, or bare leads and a bought XH lead | One in the case and one spare. Its holes should be 24 mm apart; check against its drawing. Check which wire is + before it is plugged in: the Pi board's pin 1 is +5 V |
| 1 | A sheet of fan filter mesh about 1 mm thick, nylon or fine stainless (sold for 40 mm or larger fans; cut to 30 mm square) | Under the fan, clamped between it and the base plate |
| 4 | M2.5 × 16 mm screws and nuts | Two hold the fan through the base plate, the filter and the fan |
| 4 | Rubber feet, 5 mm tall or more | The base plate stands on them so the fan can breathe |

## Not on this order

The boards themselves (step 6), the flat cables (their type is fixed at layout), and the block
and pad for the processor (optional; sized once the test case is in hand).
