# The box, designed to be made

Written 2026-11-14, at the owner's request, and **agreed by the owner the same day** ("Decided").
The first pass of the mechanical model is in "The model so far"; what it still needs from the
owner is in "Needed from the owner".

The prototype in the 1590DD works, and it taught what the format needs. It is also hand-wired,
hand-cut and unfinished: no input buffer, mono out, no mic input, no MIDI, the encoder and buttons
not wired. The next step for this format is not a board that fits that prototype. It is a design
that could be built again, for friends, in an evening and without a soldering marathon: boards made
and populated by a board house, a case drilled and printed by a service, and everything plugging
together.

The picture is [diagrams/box-concept.png](diagrams/box-concept.png). Positions in this file are in
the case layout's frame: x from the left inside wall, y from the rear inside wall, in mm, and z up
from the base plate. The case's sizes are in "Which 1590DD" below: there are two, and the
layout is checked in both.

## What it is

The same pedal as the prototype, in the same case:

- a Hammond 1590DD, used tub-up: the tub's floor is the face, the flat lid is the base plate;
- the 4.3″ DSI screen in the face with the Pi 5 on its back, rear left;
- three footswitches across the front, 69 mm apart, 29 mm from the front wall;
- a rotary encoder with a 35 mm knob and two lit buttons, rear right;
- guitar in, stereo out, a mic input, MIDI in, an external dual footswitch, USB-C power.

## Rules the design follows

1. **No wire is made by hand.** Every hand-soldered joint is a part's own pin or lug going into a
   board, or onto a bought, pre-crimped lead. Everything else is a bought cable that plugs in.
2. **Force goes into the case, not into a board.** Every socket and switch is held to the case by
   its own nut or screws. The boards hang from those parts and carry no load.
3. **The case needs only what a drilling service does**: round holes, and one rectangular window
   for the screen. No filing, no nibbling.
4. **The analogue circuit is on its own board with its sockets on it**, at the far end of the case
   from the screen and the Pi, joined to the digital side by one cable.
5. **Sealed and silent if the measurement allows it.** The heat goes into the aluminium case
   first; a fan and vents are the fallback, decided by a test on the prototype.
6. **The Pi 5 stays a bought module**, unplugged and replaced in a minute.

Rule 2 reverses the prototype's "nothing mounted through the case, everything on flying leads".
That rule was right for a hand-built prototype and is what makes it slow to build. A socket
soldered to a board and nutted to the wall is how made pedals are built: a kick on the plug goes
through the nut into the wall.

## The boards

Three boards, and each hangs from parts that are already fixed to the case, so the case needs no
extra screw holes for them.

| Board | Where | Held by | Carries |
|---|---|---|---|
| **Audio board** | Rear right and the right end of the front strip: about 60 × 104 mm (x 112–172, y 2–106), near the base plate | The three ¼″ sockets' nuts on the rear wall and the mic socket's two screws on the right wall | Guitar in, EXT FS and stereo out on the rear wall; the mic combo socket on the right wall; the guitar buffer, the mic preamp, the codec (TAC5212), the output stage, the bypass relay, the analogue supplies. Nothing digital but the codec's own lines |
| **Pi board** | Under the Pi, as a HAT: about 71 × 71 mm (x 12–83, y 2–73) | The Pi's 40-pin header and the Pi's mounting holes | The USB-C power socket and the MIDI 3.5 mm socket on the rear wall; the RP2350 with its flash and crystal; the MIDI optocoupler; the HAT+ ID EEPROM; the plugs for the footswitches, the control board and the link. A cut-out under the Pi's processor for the heat block |
| **Control board** | Under the face, rear right, above the audio board | The encoder's nut | The encoder and the two buttons, and one cable to the Pi board |

- **The link** between the Pi board and the audio board is one short flat cable across the front
  of the Pi: the audio clocks and data (I2S), I2C, 5 V, 3.3 V, ground, the two EXT FS lines and
  the relay's control. It is the only place the two boards' grounds meet.
- **The footswitches** keep their solder lugs and get bought two-wire leads, soldered to the lugs
  (six joints) and plugged into the Pi board's front edge. A strip board with board-pin
  footswitches would remove those joints; it is decided when the parts are chosen.
- **Why the Pi board is a HAT.** The Pi hangs from the screen with its header pointing at the base
  plate, and a board on that header sits 4.4 mm above the base plate, the same height as the
  audio board. No 40-way ribbon is needed, which the fit study found had nowhere to go: its plug
  and socket together stand 14 mm, more than the space under a footswitch.
- **Why two boards and not one.** One board would be held by the sockets on two walls and by the
  Pi's header at once, and could not be put in. Two boards each go in their own way (the audio
  board tilts into the rear wall, the Pi board pushes onto the header), and the flat cable takes
  up the difference. It also keeps every digital part off the analogue board.

### Heights

| Level above the base plate | What is there |
|---|---|
| 0–2.8 mm | Under the boards: pin ends, trimmed |
| 2.8–4.4 mm | The boards |
| 4.4–17 mm | Sockets on the audio board (the ¼″ socket is 15.7 mm tall, so they reach 19.7 mm); low parts elsewhere |
| 14–27 mm | The footswitch bodies, sunk 16 mm below the face as the owner chose, with their lugs pointing sideways |
| 20–30 mm | The control board, the encoder's body, the buttons |
| 3–27 mm | The mic socket's barrel on the right wall, so nothing sits on the face above it |

Under a footswitch there is about 9 mm above a board: room for surface-mount parts, not for a
socket or a plug.

## The sockets

| Socket | Where | Part type | Why there |
|---|---|---|---|
| Guitar in | Rear wall, x ≈ 162 | ¼″, board-mounted, metal bush and nut, switching (plug detect) | At the corner furthest from the Pi. Its sleeve is the one bond between circuit ground and the case |
| EXT FS | Rear wall, x ≈ 144 | ¼″ stereo, board-mounted, insulated bush | Dual footswitch leads are ¼″. Its two lines are slow, filtered where they enter, and cross the link to the RP2350 |
| Stereo out | Rear wall, x ≈ 125 | ¼″ stereo, board-mounted, insulated bush | As the prototype |
| Mic | Right wall, y ≈ 34–60 | Combo XLR/¼″, board-mounted, behind the wall, two screws from outside | **Not between the rear sockets**: its flange is 26 mm wide and the rear wall has 56 mm to the right of the Pi, which three ¼″ sockets fill. It sits behind the wall with nothing poking through, so the board can still tilt into the rear wall |
| MIDI in | Rear wall, x ≈ 76, under the Pi | 3.5 mm stereo, board-mounted, threaded bush and nut | 8 mm tall, so it fits in the 11 mm under the Pi where a ¼″ socket cannot. On the digital board, beside its optocoupler |
| USB-C power | Rear wall, x ≈ 40, under the Pi | USB-C socket, board-mounted | See "Power" |

The rear ¼″ sockets are 18.7 mm apart, set by the socket's 18.2 mm body. That takes ordinary
plugs but not three wide "pancake" plugs side by side. The mic socket's fit in a 30 mm wall is the tightest thing in the
design: a 24 mm hole leaves 3 mm above and below, and its board must sit at exactly the height the
socket sets. It is the first thing the mechanical model checks. If it fails, the mic socket becomes
a panel part on a bought lead.

## Power

**Proposed:** the USB-C socket is on the Pi board and feeds the Pi through the 40-pin header, as a
HAT+ power supply does, with input protection on the board. Any USB-C supply then gives 5 V at up
to 3 A, which is enough for the Pi with nothing in its USB ports, the screen and the boards. This
removes the panel-mount USB-C extension and its cut-out, and puts the split between the Pi's
current and the audio board's supply on a board we control.

It changes a decision of 2026-10-01 (hardware-handoff.md, "Power"): power through the Pi's own
socket, so the Pi negotiates 5 A and keeps its input protection. The alternative keeps that
decision and the bought extension lead, which is also a plug-in part. The owner chooses.

The analogue supplies stay as pedal-codec's design has them: from the 5 V through a load switch,
filter and low-noise regulators, on the audio board.

## Which 1590DD

"1590DD" is two different cases, from the makers' own drawings:

| | Hammond 1590DD | Tayda 1590DD (A-5141) | The prototype (a Hammond, the owner says), measured |
|---|---|---|---|
| Outside, with lid | 188 × 120 × 37 mm | 190.5 × 121.5 × 37.4 mm (listed as 188 × 119 × 37.5) | recorded as 188 × 119 × 37.5 |
| Inside height | **32.0 mm** | **30.5 mm** | 30 mm |
| Wall | **2.5 mm**, the same at both ends: the draft is on both faces | **2.2 mm** | about 2.3 mm (the owner) |
| Inside at the face | 179.26 × 112.26 mm | 178.5 × 109.5 mm (its outside at the floor less two walls) | 178.26 × 110.26 mm |
| Lid screws | six: the corners and the middle of each long side | four, in the corners | six pillars |

So the wall is 2.5 mm at most in either, and Neutrik's 3 mm limit for the mic socket is met. The
walls do not thicken toward the face, as an earlier note here said.

The prototype's case is a Hammond (the owner, 2026-11-14). Its measured 30 mm is 2 mm under the
drawing's 32.0 and is not explained; nothing depends on which is right, because **the layout has
to fit a shallow case anyway**: Tayda's drilling service drills Tayda's case, which is 30.5 mm,
and that is the first route to a made case. So the layout is checked in Tayda's case, in
Hammond's as drawn, and in Hammond's at 30 mm. Hammond's middle pillars come 7 mm in from the
long walls; Tayda's case has none.

## Heat

The Pi's processor faces the base plate, 13.5 mm above it. **Proposed:** an aluminium block on the
base plate with a soft thermal pad on top, meeting the processor when the base goes on, so the
whole 1590DD is the heatsink. The case has about 680 cm² of surface; 8 W into it is a rise of
roughly 15–20 °C over the room by a first estimate. Bought fanless aluminium Pi 5 cases, which are much
smaller, are reported to hold a fully loaded Pi 5 at about 60–77 °C. No fan means no vents, no
dust, no fan noise in the room or on the supply, and two fewer things to cut.

**What is already measured** (vip, `bench-results/`):

| When | Where | Load | Temperature |
|---|---|---|---|
| 2026-10-08 | before the box | an hour's playing through the codec | 53.8–58.2 °C |
| 2026-10-10 | before the box | a heavy rig, five ten-minute arms (the rigpa soak) | 56.5–63.7 °C |
| 2026-10-10 | before the box | every render core full (T11) | 80.4 °C |
| 2026-11-07 | **in the box** | a heavy rig from the same harness, five ten-minute arms (the compact-layout soak) | **68.1–71.9 °C** |

Never throttled in any of them, and the clock stayed at 2400 MHz. So the box, as it was on
7 November with no vents, costs about 10 °C over October's set-up and sits about 10 °C under the
80 °C the test below asks for. That night the Pi had **a heatsink covering its chips and no fan**
(the owner). This is the baseline the test has to beat, so no new baseline run is needed.

**The heatsink changes the test.** The block above was sized for a bare processor. With a
heatsink already on the Pi, the test is to join the heatsink's top to the base plate: thermal pad
alone if the gap is a few millimetres, a piece of aluminium bar with a pad on it if it is more.
The gap is measured with a lump of Blu-Tack on the heatsink, the base closed on it and opened
again. For the design itself the same idea may replace the block: a flat-topped bought heatsink
and a pad, with no made metal part at all.

The estimate above is not a measurement. **The test** is on the prototype, before anything else is
designed: a block and a pad between the processor and the base plate, the case closed, the engine
running a heavy rig for an hour, the temperature logged. If it stays well under 80 °C, the design
is sealed. If not, a 30 mm fan on the Pi's fan header and a row of round vent holes in the rear
wall and the base plate go in, and the fan runs only when warm.

## Noise

- The inputs are at the right rear; the screen, its ribbon, the Pi and the USB-C supply are at the
  left. The guitar's 1 MΩ node is a few millimetres of board from the socket to the buffer, with
  no lead at all.
- The audio board has its own ground, joined to the digital ground only through the link, and to
  the case only at the guitar socket.
- The RP2350 is on the Pi board. The encoder, buttons and footswitches never come near the audio
  board; EXT FS does, as two filtered slow lines along its edge.
- What was measured on the prototype still applies: the hum that mattered came from the supply's
  mains connection, not from inside the box (bench-results/2026-10-13-input-hum-and-the-host-supply.md).
- **To check in the box:** Wi-Fi and Bluetooth range from inside a metal case with only the screen
  window for the antenna to see through. The prototype is the test.

## The case, made by someone else

| Route | What it does | Minimum | Fits? |
|---|---|---|---|
| **Tayda's drill and print service** | Drills a stock 1590DD on the face and the walls from a hole table (up to 40 holes an order), powder-coats, UV-prints the legends | One | Round holes, yes. The screen's window is reported by builders as a "line cut" in its template tool; unconfirmed, so one test case is ordered first |
| **CNC from our own model** (JLCCNC, PCBWay) | Mills a 1590DD-shaped tub and base from solid | A few | Anything, including bosses for the boards and the heat block as part of the base. Priced by quote from a CAD file; expect several times a drilled Hammond |
| **Hammond's own modification service** (through DigiKey) | Holes, cut-outs, tapping, printing on their enclosures | 25 | Later, if this is ever made in numbers |

The design keeps to the first route's limits (rule 3), so the cheapest route stays open and the
second is there if the window cannot be cut.

## What is not chosen

- **A Compute Module 5 on a carrier board** would make the whole pedal one board with every socket
  on it. It is also a much larger design (the Pi's power, the screen's high-speed lines, storage),
  and a fault on a first board would cost the whole pedal. The Pi 5 as a module is the lower risk.
  It is the obvious next generation once this one works.
- **One L-shaped board with a ribbon to the Pi**, as pedal-codec's box-board.md first described.
  It needs standoffs screwed through the face to hold its long end, and the ribbon's sockets do
  not fit under the footswitches.

## Decided (owner, 2026-11-14)

The owner agreed the concept as proposed:

1. Sockets soldered to the boards and nutted to the case (rule 2), not on flying leads.
2. An audio board, a Pi board and a control board.
3. Power through the Pi board. This is for this design; the prototype keeps the 2026-10-01
   arrangement that hardware-handoff.md describes.
4. Sealed and block-cooled first; a fan only if the heat test says so.
5. EXT FS as a ¼″ socket between out and in.
6. The Pi 5 stays; the Compute Module is for later.

Also his: the footswitches stay where the case drawing has them, sunk 16 mm.

## The model so far

`enclosure/src/box_layout.py` holds every part as a block and checks that none share space, in
Hammond's case, in Tayda's, and in the prototype as measured.
[diagrams/box-layout.png](diagrams/box-layout.png) is its plan and a section, drawn in Tayda's.
2026-11-14: **no collisions in any of the three.** What it shows:

- **The mic socket fits.** Neutrik's NCJ6FA-H is 25 × 25 mm behind the wall and 24.5 mm deep,
  with its centre 12.5 mm above its board (Neutrik drawing 20004521). With the audio board's top
  4.0 mm above the base plate, its pins end 0.5 mm above the base plate and its top is 1.5 mm
  below the face in Tayda's case, 3.0 mm in Hammond's, 1.0 mm at the measured 30 mm. The audio
  board's height is set by this socket.
- **Its cut-out is round**: a 22 mm hole and two 3.2 mm screw holes, which a drilling service
  can do.
- **Its wall is thin enough**: 2.2 or 2.5 mm against Neutrik's limit of 3 mm.
- **Three ¼″ sockets fit the rear wall, with little to spare.** The chosen socket (Neutrik
  NMJ6HCD2) is 18.2 mm wide, not the 16 mm first assumed, so the three sit 18.7 mm apart at
  x = 125.0, 143.7 and 162.4. That leaves 1.9 mm to the Pi's Ethernet socket and 1.3 mm to
  Hammond's corner pillar (2.5 mm in Tayda's case). A slimmer socket would ease it, but none is
  stocked where the boards are assembled.
- **The socket is 15.7 mm tall**, not 12, so its top is at 19.7 mm. The control board above the
  out and EXT FS sockets clears them by 0.7 mm in a 30 mm case, 1.2 mm in Tayda's and 2.7 mm in
  Hammond's as drawn. The second button, 10 mm deep, clears the guitar socket by 0.3, 0.8 and
  2.3 mm. A shallower button, or the button moved off the socket, removes the tightest of these.
- **The Pi board stops at x = 83**, which leaves 1.1 mm to Hammond's middle pillar.
- **The MIDI socket fits under the Pi**: 8 mm tall in an 11 mm gap, 2 mm to the side of the Pi's
  HDMI sockets.
- **Under the footswitches there is 10 mm or more** above the audio board.

Still estimates in the model: the USB-C socket, the control board, the screen module's frame
(Waveshare publish no outline), the processor's position on the Pi, and Hammond's pillars' reach
(taken from the 101.07 mm between its middle pair).

## Parts chosen so far

The parts that set the case's holes, each from its maker's drawing and found at LCSC on
2026-11-14 (stock and price as the parts database had them that day):

| Use | Part | LCSC | Stock | Price | Hole in the case |
|---|---|---|---|---|---|
| Guitar in, EXT FS, stereo out | Neutrik NMJ6HCD2: ¼″ stereo, switched, board-mounted, chrome ferrule and nut from outside. 18.2 × 15.7 mm, 20.6 mm behind the wall, axis 7.53 mm above the board | C368502 | 795 | $3.27 | ⌀11.4 mm, its centre 11.5 mm above the base plate |
| Mic | Neutrik NCJ6FA-H: combo XLR and ¼″, board-mounted, behind the wall | C368458 | 667 | $3.06 | ⌀22 mm and two ⌀3.2 mm, its centre 16.5 mm above the base plate |
| MIDI in | A PJ-392-type 3.5 mm stereo socket with a threaded bush and nut (HOOYA PJ-392A, or CAX PJ-392-AG). Drawing still to read | C2939164, or C49274303 | 346, 826 | $0.37, $0.32 | ⌀6 mm (to confirm) |
| Footswitch leads, on the Pi board | JST S2B-XH-A, side entry, 6.1 mm high, for bought two-wire XH leads | C157931 | 66,327 | $0.07 | none |

One ¼″ part serves all three places. Whether its chrome ferrule is joined to its sleeve contact
is not on the drawing and is checked with a meter on the first one, since the guitar socket is
meant to be the one bond to the case.

Still to choose, with what is known:

- **USB-C power socket.** Ordinary board-edge sockets (LCSC has them in hundreds of thousands)
  are 7.35 mm long and overhang the board by about a millimetre, which leaves the socket's mouth
  about a millimetre inside a 2.5 mm wall. A USB-C plug needs the mouth nearly flush with the
  outside. So this wants a long-bodied socket, and a ⌀9.5–10 mm round hole in place of a slot.
- **The encoder.** Alps EC11E types are stocked in thousands (C361167, C370970, C202365 among
  them); which one depends on shaft length, detents and bush, read from Alps' drawing.
- **The two buttons.** Either the owner's 15 mm panel buttons on bought leads, or lit switches on
  the control board that poke through round holes. The owner's taste decides; see the model's
  note on depth above.
- **The flat cables and their connectors** (Pi board to audio board, Pi board to control board),
  and **the 40-pin socket** under the Pi. Common parts; not yet picked by number.

## Needed from the owner

- **For the heat test:** the gap between the top of the Pi's heatsink and the base plate, by the
  Blu-Tack method in "Heat". Then thermal pad of about that thickness, or a piece of aluminium
  bar and a thinner pad; and vip switched on. The logging is run from a session.
- **The two buttons:** keep the panel buttons, or board-mounted ones through round holes.

## Plan

Each step ends with something the owner can look at or hold. Board work is in `pedal-codec`; the
case, the firmware and the device configuration are here.

| Step | What | Done when |
|---|---|---|
| 1 | **The heat test** on the prototype: block, pad, closed case, an hour's heavy rig, the log in `bench-results/` | Sealed or fan is decided from a number |
| 2 | **Parts and the mechanical model** (started: `enclosure/src/box_layout.py`). Every socket, switch and connector chosen with its datasheet drawing and its LCSC number; the case, the Pi, the screen and the three boards modelled in `enclosure/` in plan and section; the assembly order walked through in the model | The mic socket's fit, every height and the order of assembly are shown to work, and the model gives the board outlines and the hole table |
| 3 | **A test case.** One 1590DD drilled, coated and printed from the hole table; dummy boards cut from card or printed, with the real sockets, tried in it | The owner has a made case that everything fits |
| 4 | **Schematics**: the audio board cut from pedal-codec's phase 2 sheets, the Pi board new, the control board; ngspice for what changed | The owner has reviewed the PDFs |
| 5 | **Layouts**, four layers for the audio board, checked in the model | DRC clean; the owner has reviewed the plots and the boards in the case model |
| 6 | **Order** the boards, assembled. Agents prepare; the owner orders | Ordered |
| 7 | **Bring-up**: the boards on the bench, then in the case; the firmware moved to the Pi board's pins; the codec's overlay and configuration in `rtpi` and here | The pedal plays, every control works |
| 8 | **Measure in the box**: noise, heat, Wi-Fi range, a kick on each plug | Numbers in `bench-results/` |
| 9 | **The build guide and the bill**: every step with a photo, the time it took, the cost of one. Then a second pedal is built from the guide alone | A second pedal exists |

## Sources

- [Tayda: enclosure drill service guide](https://www.taydaelectronics.com/enclosure-drill-service-guide),
  [UV printing service](https://m2.taydaelectronics.com/hardware/enclosures/enclosure-uv-printing-service.html)
- [DigiKey: Hammond custom enclosures](https://www.digikey.com/en/supplier-centers/h/hammond-manufacturing/custom-enclosures) (the 25-piece minimum)
- [Hammond: 1590DD drawing](https://www.hammfg.com/files/parts/pdf/1590DD.pdf),
  [Tayda: 1590DD drawing A-5141](https://www.taydaelectronics.com/datasheets/files/TAYDA-A-5141.pdf)
  and [its listing](https://www.taydaelectronics.com/hardware-tools/enclosures/1590dd-style/1590dd-style-aluminum-diecast-enclosure.html)
- [Neutrik NMJ6HCD2](https://www.neutrik.com/en/product/nmj6hcd2) and its [drawing](https://www.neutrik.com/media/8582/download/st-nmj6hcd2.PDF?v=3)
- [JLCCNC: enclosure machining guide](https://jlccnc.com/blog/cnc-enclosure-guide)
- [Raspberry Pi: heating and cooling Raspberry Pi 5](https://www.raspberrypi.com/news/heating-and-cooling-raspberry-pi-5/),
  [Akasa Pi-5 Pro review](https://bret.dk/akasa-pi-5-pro-raspberry-pi-5-case-review/),
  [a passive case review](https://www.linuxlinks.com/raspberry-pi5-desktop-mini-pc-passive-cooling-right-way/)
