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
5. **A fan and vents, and a way for the heat into the case as well.** The first version of this
   rule was "sealed and silent if the measurement allows it"; the owner chose on 2026-11-16 to
   assume a fan is needed and not wait for the measurement, and on 2026-11-17 chose one fan in
   the base plate, drawing in through a dust filter, with vents only in the rear wall ("Heat").
   Holes that turn out not to be needed are left for a later version to drop.
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
| **Audio board** | Rear right and the right end of the front strip: about 60 × 104 mm (x 112–172, y 2–106), near the base plate | The three ¼″ sockets' nuts on the rear wall and the mic socket's two screws on the right wall | Guitar in, EXT FS and stereo out on the rear wall; the mic combo socket on the right wall; the guitar buffer, the mic preamp, the codec (TAC5212), the output stage, the two bypass relays, the analogue supplies. Nothing digital but the codec's own lines |
| **Pi board** | Under the Pi, as a HAT: about 71 × 71 mm (x 12–83, y 2–73) | The Pi's 40-pin header and the Pi's mounting holes | The USB-C power socket and the MIDI 3.5 mm socket on the rear wall; the RP2350 with its flash and crystal; the MIDI optocoupler; the HAT+ ID EEPROM; the plugs for the footswitches, the control board, the link and the fan. A cut-out under the Pi's processor for the heat block |
| **Control board** | Under the face, rear right, behind the rear sockets: 37 × 47 mm (x 115.5–152.5, y 21.5–68.5), 7 mm below the face | The encoder's nut | The encoder, the two buttons with a lamp in front of each, and one flat cable to the Pi board |

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

### The link's pin order

Decided 2026-11-15, when the audio board's schematic was drawn
(`pedal-codec/hardware/audio-board/`, J1). The Pi board must match it. Pin numbers are the audio
board's socket's.

| Pin | Net | Direction | What it is |
|---|---|---|---|
| 1 | GND | | |
| 2 | I2S_BCLK | Pi → codec | Bit clock, 3.072 MHz at 48 kHz (Pi GPIO 18) |
| 3 | GND | | |
| 4 | I2S_FSYNC | Pi → codec | Frame clock (GPIO 19) |
| 5 | GND | | |
| 6 | I2S_TO_PI | codec → Pi | The codec's DOUT (GPIO 20, PCM_DIN) |
| 7 | I2S_FROM_PI | Pi → codec | The codec's DIN (GPIO 21, PCM_DOUT) |
| 8 | GND | | |
| 9 | SCL | Pi → codec | I2C1 (GPIO 3). The codec is at 0x50 |
| 10 | SDA | both | I2C1 (GPIO 2) |
| 11 | RELAY | RP2350 → audio board | High = effect, for both bypass relays. Not driven high until 10 s after the Pi's 3.3 V comes up, or the outputs thump (pedal-codec, box-board.md). Pulled down on the audio board, so no cable, or an RP2350 that is not driving it, is bypass |
| 12 | EXTFS_A | audio board → RP2350 | EXT FS tip, through 1 kΩ and 100 nF. The pull-up is on the Pi board |
| 13 | EXTFS_B | audio board → RP2350 | EXT FS ring, the same |
| 14 | +3V3 | Pi → audio board | The **Pi's** 3.3 V, not the RP2350's: it feeds the codec's IOVDD and switches the analogue supplies on, so they follow the Pi into standby (HAT+) |
| 15 | GND | | |
| 16 | +5V | Pi board → audio board | About 0.15 A: the op-amps, the codec's analogue supply and the two relay coils |

Why this order:

- **A ground on each side of each clock** and of the I2S data pair. The I2C pair has a ground on
  one side and RELAY on the other, which changes only when the pedal is switched. Five grounds in
  all, which is every conductor the eleven signals leave.
- **The supplies are at one end**, with a ground between them and the 5 V at the edge. The slow
  lines (RELAY, EXT FS) sit between the I2C pair and the supplies.
- **A cable put in the other way round puts no supply on a signal pin.** Mirrored, pin 16 lands on
  pin 1 and pin 14 on pin 3, which are both grounds: each supply is shorted to ground instead,
  which the Pi board's input protection and the Pi's own 3.3 V regulator have to survive. That
  matters because of the next point.
- **Each conductor carries one net; the Pi board's pin numbers are not yet fixed.** Both sockets
  are bottom-contact. Whether the Pi board's pin 1 or its pin 16 meets the audio board's pin 1
  depends on which way the two sockets face and on whether the bought cable has its contacts on
  the same side at both ends. That is settled when both boards are laid out, and written here.

Not on the cable: whether a plug is in the guitar socket (the codec reads the socket's contact on
its GPIO2, and the Pi reads the codec over I2C), and the codec's interrupt (a test point).

The audio board has 33 Ω in series with each of the four I2S lines at the codec. The Pi board
has its own at the header on the three the Pi drives (BCLK, FSYNC, I2S_FROM_PI), since they now
cross a cable.

### The control link's pin order

Decided 2026-11-16, when the Pi board's and the control board's schematics were drawn
(`pedal-codec/hardware/pi-board/` J4, `pedal-codec/hardware/control-board/` J1). Pin numbers are
the control board's socket's; which end of the Pi board's socket meets them is settled at layout,
as for the link above.

| Pin | Net | What it is |
|---|---|---|
| 1, 3, 5, 7, 9, 11, 15 | GND | A ground beside every signal |
| 2 | ENC_A | The encoder's A, to the RP2350's GPIO 2 |
| 4 | ENC_B | Its B, GPIO 3 |
| 6 | ENC_SW | Its push, GPIO 4 |
| 8 | BTN1 | Button 1, GPIO 6 |
| 10 | BTN2 | Button 2, GPIO 7 |
| 12 | LED1_OUT | Button 1's lamp, from GPIO 15 through 330 Ω on the Pi board, to the lamp's anode; the lamp returns to ground |
| 13 | LED2_OUT | Button 2's lamp, from GPIO 16, the same |
| 14 | | Spare, not connected |
| 16 | VDD | The RP2350's 3.3 V, for the control board's pull-ups |

The pull-ups and filters are on the control board, at the switches (A and B as Bourns draws them:
10 kΩ up, 10 kΩ in series, 10 nF; the pushes 10 kΩ up, 1 kΩ, 100 nF), so the lines are already
slow when they reach the cable. Mirrored, VDD (16) meets a ground (1); the RP2350's regulator
limits its current and shuts down when hot.

### The RP2350's pins

Decided 2026-11-16 with the Pi board's schematic. The firmware follows this table when it moves
to the Pi board (Plan, step 7); the footswitches and the link to the Pi keep the pins they have
on the Pico today (`firmware/src/footswitch.c`, `main.c`).

| GPIO | Net | What it is |
|---|---|---|
| 0 | MCU_TX | UART0 TX, to the Pi's GPIO 15 (RXD, header pin 10) through 1 kΩ |
| 1 | MCU_RX | UART0 RX, from the Pi's GPIO 14 (TXD, pin 8) through 1 kΩ |
| 2, 3 | ENC_A, ENC_B | The encoder |
| 4 | ENC_SW | The encoder's push |
| 5 | MIDI_RX | UART1 RX, from the MIDI optocoupler (H11L1); idle high |
| 6, 7 | BTN1, BTN2 | The two buttons |
| 8, 9 | FSX_A, FSX_B | EXT FS tip and ring, from the audio board; pulled up on the Pi board |
| 10, 11, 12 | FS2, FS3, FS1 | The three footswitches, on JST XH plugs, pulled up, with 1 kΩ and 100 nF |
| 13 | RELAY | Both bypass relays, high = effect; not before 10 s after the Pi's 3.3 V comes up |
| 14 | PI_3V3_SENSE | High while the Pi's 3.3 V is up (10 kΩ from it, 100 kΩ down) |
| 15, 16 | LED1, LED2 | The buttons' lamps, through 330 Ω |
| 17–25 | | Free |
| 26, 27 | CC1_SENSE, CC2_SENSE | ADC0 and ADC1: the USB-C socket's two CC lines, each through 10 kΩ with 100 nF. The higher of the two says what the supply offers: 0.25–0.61 V the USB default, 0.70–1.16 V 1.5 A, 1.31–2.04 V 3 A |
| 28, 29 | | Free |

From the Pi to the RP2350: GPIO 23 (header pin 16) holds it in reset while high, through a 2N7002
on its RUN pin; GPIO 24 and 25 (pins 18 and 22) are its SWDIO and SWCLK, through 330 Ω, so the Pi
programs it with no debug probe. Its USB and BOOTSEL are on test pads, for recovery only. The
Pi's GPIO 12 (pin 32) switches the fan, through a transistor on the Pi board: high is on.
GPIO 12 is also one of the Pi's PWM pins, so the same line can run it slowly.

**Still to write, at bring-up (Plan, step 7):** the firmware's reading of the two CC pins and a
message for it in [uart-protocol.md](uart-protocol.md), the pedal service's warning on the
screen when the supply offers under 3 A, and the fan's line in the device configuration
(`dtoverlay=gpio-fan,gpiopin=12` with a temperature, or `pwm-fan` on the same pin if the fan
is to run slowly; which, is tried on the bench with the real fan).

The RP2350 runs whenever the 5 V is up; the Pi's 3.3 V is off in standby. Every line between
them goes through a resistor, and the firmware keeps MCU_TX an input while GPIO 14 is low, so a
Pi in standby is not back-powered (HAT+).

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

Feeding the Pi through its header makes the Pi board a **Power HAT+** in Raspberry Pi's HAT+
specification, which requires it to pass current one way only and to survive the Pi's own supply
being plugged in as well. The Pi board does that with an eFuse (TI's TPS259470A) between the
socket and the Pi's 5 V, which also limits the current and slows the rise at plug-in, and its
overlay tells the Pi it may draw 3 A (pedal-codec, pi-board.md, decided 2026-11-16).

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

**Decided by the owner, 2026-11-16: assume a fan is needed, and don't wait for a measurement.**
The case gets a fan and vent holes now; if they turn out not to be needed, a later version drops
them. The Pi board keeps its hole under the processor, so the block described below can be fitted
or left out. What follows is first what the fan design is, then the reasoning and measurements
from before the decision, which still say how much the fan has to do.

### The fan and the vents

As the owner chose on 2026-11-17: one fan, in the floor between footswitches 1 and 2, drawing
air in through a thin dust filter, and vents only in the rear wall.

| | |
|---|---|
| Fan | One, 30 × 30 × 10 mm, 5 V, two wires. Sunon's MF30100V2-1000U-A99 is the kind: 80 mA, 4.7 cubic feet a minute, 21 dB(A), 9,500 rpm, by Element14's listing |
| Where | Lying on the base plate, between footswitches 1 and 2 (its centre 34.5 mm left of the case's centre line), 2.5 mm in front of the Pi board and so beside its plug, J9. Its top is 11 mm above the base plate; the footswitches' bodies end 14.5 mm above it |
| Filter | A 1 mm sheet of fan filter mesh, 30 × 30 mm, between the fan and the base plate, clamped by the fan's screws. It is inside the case, so it cannot be knocked off; cleaning it means taking the base off |
| Held by | Two M2.5 screws through the base plate, the filter and two of the fan's four holes (24 mm apart on a 30 mm fan), with nuts on top |
| Air in | Six ⌀8 mm holes in the base plate under the fan's blades, on a 21 mm circle: 302 mm² |
| Air out | Two ⌀9 mm holes in the rear wall, between the USB-C and MIDI sockets, at the height of the 11 mm gap between the Pi and the Pi board, where the processor is: 127 mm² |
| Plugged into | The Pi board's two-way JST XH plug (J9). The Pi's GPIO 12 switches it, so it runs only when the Pi is hot, and can be slowed by PWM on that pin (pedal-codec, pi-board.md, Decided 16) |

- **The air's path.** The fan pushes filtered air into the front of the case. The only planned
  way out is the rear wall's two holes, at the gap under the Pi. That gap is closed on its
  right by the Pi's USB and Ethernet sockets and on its front by the 40-pin socket, so the air
  reaches it round the socket's left end, passes over the processor and leaves at the rear.
- **The case runs at a slight pressure.** Every other opening (the sockets' holes, the window's
  edge, the buttons, the lid's seam) then leaks outward, so dust comes in only through the
  filter.
- **It needs a gap under the pedal.** The base plate stands on four rubber feet, 5 mm or taller,
  so the fan can breathe. On a pedalboard, any hook-and-loop strip must stay off the fan's 30 mm
  square; strips along the two short ends leave it clear.
- **The base plate is Tayda's lid**, drilled by a separate service (A-5141-CST-DRL, $4.00, ±0.5 mm).
  Tayda gives no orientation for the lid in its tool. Every other side's coordinates are as
  seen from outside, so the lid's are taken as seen from below. The lid's corner screws are
  symmetric, so it goes on whichever way round puts the fan's holes under the gap between
  footswitches 1 and 2.
- **The outlet is the narrow place.** 127 mm² of outlet against 302 mm² of inlet; that stretch of
  rear wall, 21 mm between two sockets and 11 mm high, has room for no more. How much air the
  fan moves through it is not calculated or measured; step 8 of the plan measures it.
- **Why 30 mm now.** Lying flat, the fan needs only 11 mm of height with its filter, and the
  floor between the footswitches and in front of the Pi board is 37 mm deep and free. A 30 mm
  fan moves about twice the air of a 25 mm one at the same speed, so it can run slower for the
  same cooling, which is quieter.
- **Why not the Pi's own fan header.** It wants a four-wire fan with its small plug. A two-wire
  fan switched by the Pi board is one transistor.
- **Noise on the supply.** The fan's 80 mA comes from the digital 5 V, with 10 µF at its plug.
  The audio board has its own regulators. Measured in the box with the fan running and stopped.
- **Earlier the same day** the design had two 25 mm fans blowing out, one on the left side panel
  and one on the front wall. The owner did not want a fan in the front wall, and chose this.

### The block, as an option

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
again.

**In the design the block passes through the Pi board.** The Pi board sits between the Pi and
the base plate, 11 mm from the Pi, so it has a hole under the processor, about 17 × 17 mm for a
15 × 15 mm block, and the block stands on the base plate and reaches up through it. That hole is
why the design cools the processor alone: a heatsink covering several chips, like the one on
the prototype's Pi, would need a hole its own size and would also be too tall for the 11 mm
between the two boards. The Pi ran its soaks bare at 48–53 °C on the bench (`plan.md`, the first
vip soaks), so the other chips are not expected to need help; the heat test in the finished
box is what confirms it. The prototype has no Pi board, so its test can keep the heatsink.

The estimate above is not a measurement. **The test** on the prototype (a block and a pad
between the processor and the base plate, the case closed, the engine running a heavy rig for an
hour, the temperature logged) was to decide sealed or fan before anything else was designed. The
owner's decision of 2026-11-16 means nothing waits for it. It is still worth an hour when the
parts are to hand, because it says whether the block is worth fitting alongside the fan.

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
| **Tayda's drill and print service** | Drills a stock 1590DD on the face and the walls from a hole table (up to 40 holes an order), powder-coats, UV-prints the legends | One | Round holes of 3 mm and up, yes. The screen's window too: Tayda's ordering guide says it cuts rectangles with corners down to 0.5 mm radius. It holds ±0.5 mm on the face and ±1 mm on the walls, and asks for 0.4 mm more on every diameter under a powder coat, so one test case is ordered first |
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
4. Sealed and block-cooled first; a fan only if the heat test says so. **Changed 2026-11-16**
   (below).
5. EXT FS as a ¼″ socket between out and in.
6. The Pi 5 stays; the Compute Module is for later.

Also the owner's: the footswitches stay where the case drawing has them, sunk 16 mm; and the two
buttons are **board-mounted**, on the control board, not panel buttons on leads.

## Decided (owner, 2026-11-16)

After looking over the three schematics (pedal-codec, plan.md):

1. **A lamp beside each button**, through its own hole in the face ("Parts chosen so far").
2. **Assume a fan**, with vents; unneeded holes are a later version's to drop. The Pi board
   keeps its 17 × 17 mm hole, so the block can be fitted or not ("Heat").
3. **Warn when the supply is poor**: the RP2350 reads what the USB-C supply offers ("The
   RP2350's pins").
4. **The mic input keeps its four 63 V capacitors only if they are needed**, and they are not:
   one 22 µF in each leg (pedal-codec, box-board.md, "Mic input").

## Decided (owner, 2026-11-17)

After seeing the drill template in Tayda's tool:

1. **One fan, in the base plate between footswitches 1 and 2, drawing in through a thin dust
   filter, with vents only in the rear wall** ("Heat"). It replaced, the same day, a design with
   two fans blowing out through the left side panel and the front wall, which the owner had
   asked for and then did not want a fan in the front wall.
2. **The pedal's name printed on the face**: pedal.science, small, to the right of the
   encoder, running from the rear toward the player with the tops of its letters toward the
   right edge, set as the website sets it ("The print on the face").

## The model so far

`enclosure/src/box_layout.py` holds every part as a block and checks that none share space, in
Hammond's case, in Tayda's, and in the prototype as measured.
[diagrams/box-layout.png](diagrams/box-layout.png) is its plan and a section, drawn in Tayda's.
2026-11-14, on 2026-11-16 with the fan and the longer control board, and on 2026-11-17 with two
fans, and again with one fan on the base plate: **no collisions in any of the three.** What it shows:

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
- **The socket is 15.7 mm tall**, not 12, so its top is at 19.7 mm, too close under the face
  for a board to sit above it. So **the control board is behind the rear sockets**, not over
  them: 37 × 47 mm (x 115.5–152.5, y 21.5–68.5), 7 mm below the face, with the encoder at
  (131, 30), the two buttons side by side in front of it at (125, 55) and (141, 55), and a lamp
  9 mm in front of each button, at (125, 64) and (141, 64). It clears the sockets by 0.5 mm and
  the mic socket by 1.5 mm or more. These positions are a proposal; the owner's were for the
  prototype's panel buttons.
- **The fan fits on the base plate**, 30 × 30 mm and 11 mm tall with its filter, between
  footswitches 1 and 2 and 2.5 mm in front of the Pi board, with 3.5 mm (Tayda) or 3.0 mm
  (Hammond at 30 mm) under the footswitches' bodies ("Heat").
- **The Pi board stops at x = 83**, which leaves 1.1 mm to Hammond's middle pillar.
- **The MIDI socket fits under the Pi**: 8 mm tall in an 11 mm gap, 2 mm to the side of the Pi's
  HDMI sockets.
- **Under the footswitches there is 10 mm or more** above the audio board.

Still estimates in the model: the control board's outline, the screen module's frame (Waveshare
give its size, 105.4 × 67.1 mm, but not where the window sits in it, so only the window is
modelled), the processor's position on the Pi, and Hammond's pillars' reach (taken from the
101.07 mm between its middle pair). Not walked through yet: the order of assembly.

## Parts chosen so far

The parts that set the case's holes, each from its maker's drawing and found at LCSC on
2026-11-14 (stock and price as the parts database had them that day):

| Use | Part | LCSC | Stock | Price | Hole in the case |
|---|---|---|---|---|---|
| Guitar in, EXT FS, stereo out | Neutrik NMJ6HCD2: ¼″ stereo, switched, board-mounted, chrome ferrule and nut from outside. 18.2 × 15.7 mm, 20.6 mm behind the wall, axis 7.53 mm above the board | C368502 | 795 | $3.27 | ⌀11.4 mm, its centre 11.5 mm above the base plate |
| Mic | Neutrik NCJ6FA-H: combo XLR and ¼″, board-mounted, behind the wall | C368458 | 667 | $3.06 | ⌀22 mm and two ⌀3.2 mm, its centre 16.5 mm above the base plate |
| MIDI in | XKB PJ-324M0: 3.5 mm stereo, board-mounted, lying flat, an M6 threaded nose 3.55 mm long with a nut. 11.5 × 6.45 mm, 10.7 mm behind the wall, axis 3.0 mm above the board | C2884986 | 1,316 | $0.55 | ⌀6.5 mm |
| USB-C power | SHOU HAN TYPE-C 16PIN L8.35: 16 contacts, four through-hole legs, 8.94 × 3.26 mm and 8.35 mm long, so its mouth reaches about 2 mm into the wall | C5379909 | 14,835 | $0.16 | ⌀10 mm, round |
| The Pi's 40-pin socket | ZHOURI 2.54-2*20: 2 × 20, 8.5 mm high | C2977589 | 37,783 | $0.32 | none |
| The two buttons | Kinghelm KH-12X12X12H-TJ: a 12 × 12 mm switch, its ⌀6.5 mm round stem 12 mm above the board, so 2.5 mm proud of the face. Not lit itself: a lamp stands in front of it | C18186459 | 4,819 | $0.06 | ⌀7.5 mm |
| The two lamps (2026-11-16) | Everlight 204-10SURD/S530-A3: a 3 mm red lamp, frosted, 2.0 V. Lens 3.0 mm, flange 4.0 mm and 1.0 mm thick, 4.2 mm of lens above the flange, so with its flange under the 2.5 mm face it stands 1.7 mm proud | C99772 | 35,965 | $0.04 | ⌀3.3 mm |
| Encoder | Bourns PEC11R-4215F-S0024: 24 detents, 24 pulses, push switch, 15 mm flatted shaft, M7 threaded bush with its nut and washer. Body 12.5 × 13.4 mm, about 7 mm behind the face | C143790 | 4,186 | $2.33 | ⌀7.2 mm |
| The two flat cables' sockets (four) | JUSHUO AFA07-S16FCC-00: 16-way, 1.0 mm pitch, 2.5 mm high, slide lock, for bought 16-way flat cables | C13744 | 19,214 | $0.11 | none |
| Footswitch leads, on the Pi board | JST S2B-XH-A, side entry, 6.1 mm high, for bought two-wire XH leads | C157931 | 66,327 | $0.07 | none |

One ¼″ part serves all three places. Whether its chrome ferrule is joined to its sleeve contact
is not on the drawing and is checked with a meter on the first one, since the guitar socket is
meant to be the one bond to the case.

The encoder is the part that holds the control board, so it needs a threaded bush. The Alps
EC11E types LCSC stocks in thousands have none (Alps' drawing shows a plain 7 mm boss), which
rules them out. The Bourns part gives one pulse per detent; the KY-040 in the prototype gives 20,
so the firmware's count changes by one constant.

The PJ-392 type first listed for MIDI stands upright on its board (its drawing shows the pins
out of its back), so it was the wrong kind for a rear wall; the PJ-324M0 lies flat. Its nose is
3.55 mm long, which leaves a nut only a millimetre of thread through a 2.5 mm wall. It may be
left without its nut, the nose sitting in the hole.

**How the buttons are lit: a lamp in front of each** (the owner, 2026-11-16). Lit switches tall
enough to reach through the face are stocked only in tens at LCSC (E-Switch's TL1265, ROCPU's
TPB02), and the switch chosen is plain, so the light is a separate part on the control board, 9 mm
in front of its button, through its own ⌀3.3 mm hole. It is soldered with the board already in
the case and the lamp pushed up into its hole, so its flange rests under the face and its height
sets itself (pedal-codec, control-board.md, Decided 5 and 6). Red, because it is fed from 3.3 V.
Still tried with a sample in the test case: the fit of the hole once coated, and the brightness.

The fan is not a board part and has no LCSC number: 30 × 30 × 10 mm, 5 V, two wires, with an
XH2.54 two-pin plug for the Pi board's J9, and a 30 mm square of filter mesh under it ("Heat";
[box-order.md](box-order.md)).

### The print on the face

The owner, 2026-11-17: the word pedal.science, small, in the space to the right of the encoder,
turned so that it runs from the rear toward the player with the tops of its letters toward the
pedal's right edge. It is set as the website sets its name in dark mode: DM Sans Bold with the
letters 0.03 em closer, "pedal" in the site's text colour (#cdc1c9, a warm off-white) and
".science" in its mark colour (#2a95a7). The type is 3.8 mm (about 11 point), which makes the
word 24.7 mm long with letters 1.9 mm high, centred 72 mm right of the face's centre on the
encoder's line.

`uv run enclosure/src/box_print.py` makes it: `enclosure/print/tayda-1590dd-side-a.pdf`, the
file Tayda's UV printing takes (a 117 × 185 mm page, outlines only, white ink under the colour,
as Tayda's guide asks), and [diagrams/box-face-print.png](diagrams/box-face-print.png), the
print on the drilled face as the player sees it. Not tried: how the two colours look printed
on a matte black coat, and whether the file passes Tayda's own checking tool, which wants a
login typed in.

**A risk the test case answers.** The Pi hangs from the screen, the Pi board from the Pi, and the
Pi board's two sockets must meet their holes in the rear wall. The chain's tolerance may be a
millimetre. The USB-C hole is round and oversize for that reason; the MIDI socket's nut then
fixes the board, and the screen must be free to settle behind its window before it is fixed.

## The case's holes

For Hammond's case, from `python3 enclosure/src/box_layout.py --holes hammond` (it prints Tayda's
too). Face holes are measured from the face's centre; wall holes along the wall from its centre
line, and down from the outside of the face. Centre lines are used because the walls slope.

| Where | Hole | Across | Up or down | Size |
|---|---|---|---|---|
| Face | Screen window | 30.1 mm left of centre | 17.6 mm toward the rear | 99 × 59 mm rectangle |
| Face | Encoder | 41.5 mm right | 26.1 mm toward the rear | ⌀7.2 mm |
| Face | Button 1, button 2 | 35.4 and 51.4 mm right | 1.1 mm toward the rear | ⌀7.5 mm |
| Face | Lamp 1, lamp 2 | 35.4 and 51.4 mm right | 7.9 mm toward the player | ⌀3.3 mm |
| Face | Footswitches 1–3 | 69.0 mm left, centre, 69.0 mm right | 27.1 mm toward the player | ⌀12 mm |
| Rear wall | USB-C power | 49.6 mm left of centre, seen from the player | 26.5 mm below the face | ⌀10 mm |
| Rear wall | MIDI in | 13.6 mm left | 25.1 mm below | ⌀6.5 mm |
| Rear wall | Out, EXT FS, guitar in | 35.4, 54.1 and 72.8 mm right | 23.0 mm below | ⌀11.4 mm |
| Rear wall | Air out, two | 36.6 and 25.0 mm left | 23.0 mm below | ⌀9 mm |
| Base plate | Air in, under the fan | Six on a 21 mm circle about a point 34.5 mm left of centre and 33.4 mm toward the player, seen from above | | ⌀8 mm |
| Base plate | The fan's two screws | 22.5 and 46.5 mm left | 45.4 and 21.4 mm toward the player | ⌀3.0 mm |
| Right wall | Mic | 9.1 mm toward the rear of centre | 18.0 mm below | ⌀22 mm, and two ⌀3.2 mm screw holes 9.9 mm out on a diagonal (which diagonal, from Neutrik's drawing) |

Twenty-six round holes and one window, under the 40 that one of Tayda's drill orders covers; the base plate's eight are a second, separate drill order ("Heat").
These are finished sizes. **For Tayda the same holes are printed as its Box Tool takes them** by
`python3 enclosure/src/box_layout.py --tayda`: per side, from the side's centre, with the 0.4 mm
Tayda asks for under a powder coat added to each diameter ([box-order.md](box-order.md) has that
table). This is a first table for a test case: the sockets hanging from the Pi (USB-C, MIDI) and
the air inlet between them move with the Pi, whose place is from the owner's measurements of the
prototype.

**Two things the drawings raise, for the test case to answer:**

- **The walls slope.** Tayda's drawing gives about 2.5–3° a side. Hammond's gives no angle; its
  inside is 1.9 mm a side wider at the rim than at the face, some of which is the step the lid
  sits in. A socket nutted flat to a sloping wall wants to tilt its board by that angle. Made
  pedals with board-mounted jacks in these cases live with it; here the audio board is also
  held on a second wall. If it strains, the fixes are a board that rests on posts and sockets
  left a turn loose until it is level, or a made case with a flat spot at each socket.
- **Tayda's lid has a rim** that stands about 4 mm up inside the walls (Hammond's is under
  2 mm). The audio board's sockets start 4.0 mm above the base plate, so in Tayda's case the
  board may need to sit half a millimetre higher, which the mic socket's 1.5 mm to spare allows.
  The fan lies on the plate inside that rim, about 4 mm clear of it.
- **Tayda's ±1 mm on the walls.** Three ¼″ sockets on one board must meet three holes, and the
  mic socket a fourth on another wall. Holes drilled in one setting should keep their spacing
  far better than ±1 mm; the test case shows whether they do.

## Needed from the owner

As of 2026-11-17, in the order they unblock things:

1. **The order for the test case**, in three baskets: [box-order.md](box-order.md). The Tayda
   one is set up in the owner's Box Tool account, matte black; it waits for the print file to
   be uploaded (Tayda's form asks the owner to confirm the file) and for the owner's go-ahead.
2. **Three measurements on the prototype**, which the model still estimates:
   - which screen it is (Waveshare's 4.3″ with touch or without), how far its frame reaches past
     the window on each of the four sides, and how thick it is behind the face;
   - on the Pi, the centre of the processor's metal lid from the two nearest board edges. It
     places the Pi board's hole;
   - the height of the lid's rim inside the walls of the prototype's case.
3. **When the parts come, two checks with a meter** (pedal-codec, plan.md, phase 4): on an
   NMJ6HCD2, whether the chrome ferrule is joined to the sleeve contact; on a PJ-324M0 with a
   plug in it, which terminal is the tip and which the ring.
4. **Optional, the heat test:** the gap between the top of the Pi's heatsink and the base plate,
   by the Blu-Tack method in "Heat"; then a thermal pad of about that thickness, or a piece of
   aluminium bar and a thinner pad; and vip switched on. The logging is run from a session.

## Plan

Each step ends with something the owner can look at or hold. Board work is in `pedal-codec`; the
case, the firmware and the device configuration are here.

| Step | What | Done when |
|---|---|---|
| 1 | **The heat test** on the prototype: block, pad, closed case, an hour's heavy rig, the log in `bench-results/`. **No longer waited for** (the owner, 2026-11-16: assume a fan). Still worth doing when the parts are to hand: it says whether the block is worth fitting as well | A number in `bench-results/` |
| 2 | **Parts and the mechanical model** (started: `enclosure/src/box_layout.py`). With the fan, the vents and the lamps since 2026-11-16, and one fan on the base plate since 2026-11-17; still to do: the three measurements in "Needed from the owner" and the order of assembly. Every socket, switch and connector chosen with its datasheet drawing and its LCSC number; the case, the Pi, the screen and the three boards modelled in `enclosure/` in plan and section; the assembly order walked through in the model | The mic socket's fit, every height and the order of assembly are shown to work, and the model gives the board outlines and the hole table |
| 3 | **A test case.** One 1590DD drilled and coated from the hole table; dummy boards cut from card or printed, with the real sockets, the lamps and the fan, tried in it. **The order is prepared** ([box-order.md](box-order.md)): the drill templates are in Tayda's tool and the print file is made, 2026-11-17; the owner places it | The owner has a made case that everything fits |
| 4 | **Schematics**: the audio board cut from pedal-codec's phase 2 sheets, the Pi board new, the control board; ngspice for what changed. **Done 2026-11-16**: the owner looked over all three, and the decisions of that day are drawn (pedal-codec, plan.md) | The owner has reviewed the PDFs |
| 5 | **Layouts**, four layers for the audio board, checked in the model | DRC clean; the owner has reviewed the plots and the boards in the case model |
| 6 | **Order** the boards, assembled. Agents prepare; the owner orders | Ordered |
| 7 | **Bring-up**: the boards on the bench, then in the case; the firmware moved to the Pi board's pins; the codec's overlay and configuration in `rtpi` and here | The pedal plays, every control works |
| 8 | **Measure in the box**: noise, heat and the fan's noise at each speed, Wi-Fi range, a kick on each plug | Numbers in `bench-results/` |
| 9 | **The build guide and the bill**: every step with a photo, the time it took, the cost of one. Then a second pedal is built from the guide alone | A second pedal exists |

## Sources

- [Tayda: enclosure drill service guide](https://www.taydaelectronics.com/enclosure-drill-service-guide)
  (coordinates, the 3 mm minimum, 0.4 mm for the coat, the tolerances),
  [its ordering guide](https://www.taydaelectronics.com/enclosure-modification-ordering-guide-v1)
  (the Box Tool, and rectangles with corners down to 0.5 mm),
  [UV printing service](https://m2.taydaelectronics.com/hardware/enclosures/enclosure-uv-printing-service.html)
- [DigiKey: Hammond custom enclosures](https://www.digikey.com/en/supplier-centers/h/hammond-manufacturing/custom-enclosures) (the 25-piece minimum)
- [Hammond: 1590DD drawing](https://www.hammfg.com/files/parts/pdf/1590DD.pdf),
  [Tayda: 1590DD drawing A-5141](https://www.taydaelectronics.com/datasheets/files/TAYDA-A-5141.pdf)
  and [its listing](https://www.taydaelectronics.com/hardware-tools/enclosures/1590dd-style/1590dd-style-aluminum-diecast-enclosure.html)
- [Neutrik NMJ6HCD2](https://www.neutrik.com/en/product/nmj6hcd2) and its [drawing](https://www.neutrik.com/media/8582/download/st-nmj6hcd2.PDF?v=3)
- LCSC's datasheets for the [USB-C socket](https://jlcpcb.com/partdetail/C5379909), the [MIDI socket](https://jlcpcb.com/partdetail/C2884986) and the [button switch](https://jlcpcb.com/partdetail/C18186459)
- [Everlight's drawing of the 204-10 lamp](https://mm.digikey.com/Volume0/opasdata/d220001/medias/docus/559/204-10SDRD%2CS530-A3.pdf)
  (the 204-10SDRD's sheet: the same package as the lamp chosen)
- [Waveshare: 4.3″ DSI display](https://www.waveshare.com/product/43h-800480-ips.htm?sku=24773)
  (the module's size), and the fan's figures from
  [Element14's listing of Sunon's MF30100V2-1000U-A99](https://www.element14.cn/en-CN/sunon/mf30100v2-1000u-a99/dc-fan-vapo-30mm-9500rpm-5vdc/dp/4382048)
- [Tayda: 1590DD lid drill service](https://www.taydaelectronics.com/1590dd-lid-custom-drill-enclosure-service.html)
- [Tayda: UV printing guide](https://www.taydaelectronics.com/uv-printing-service-guide-v1)
  (the artboard's size, the layers and the white ink's spot colour)
- [Bourns PEC11R datasheet](https://www.bourns.com/docs/product-datasheets/pec11r.pdf),
  [Alps EC11E15244G1](https://tech.alpsalpine.com/e/products/detail/EC11E15244G1/)
- [JLCCNC: enclosure machining guide](https://jlccnc.com/blog/cnc-enclosure-guide)
- [Raspberry Pi: heating and cooling Raspberry Pi 5](https://www.raspberrypi.com/news/heating-and-cooling-raspberry-pi-5/),
  [Akasa Pi-5 Pro review](https://bret.dk/akasa-pi-5-pro-raspberry-pi-5-case-review/),
  [a passive case review](https://www.linuxlinks.com/raspberry-pi5-desktop-mini-pc-passive-cooling-right-way/)
