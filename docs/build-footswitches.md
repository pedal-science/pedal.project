# The footswitches, in the small case

2026-10-27. The big case (Hammond 1456RH3) is paused; the pedal is being made to work in the small
one first. The Pi, the codec, the output board (OUT L only), the input, the USB-C extension and
three footswitches are in it, and the Pico is wired to the Pi. This page wires the three
footswitches to the Pico, and nothing else of the control surface: no LEDs, relay, MIDI, encoder or
screen.

The board is `stripboard/module_boards.py`'s `footswitch_board()`, drawn as
[stripboard/module-boards/footswitch-pico.svg](../stripboard/module-boards/footswitch-pico.svg): the
full control board (`control.svg`) cut down to the Pico, its link to the Pi and one 4-way XH header.
Its pins are the control board's, so nothing moves when that board is built.

## The circuit

Each footswitch joins one Pico pin to ground **at rest** and opens while it is pressed. The box was
built that way (COM to NC; "As built in the box", below), and the firmware reads it so: a pin that
goes high is a press (`PRESS_OPENS` in `firmware/src/footswitch.c`; 0 there is the other sense, for
a loom wired COM to NO). The Pico's own pull-up takes the pin to 3.3 V while the switch is open, so
the board needs no resistors; a 100 nF capacitor across each
switch, soldered on the switch's lugs, takes the worst of the contact bounce and anything the lid
wiring picks up, and the firmware debounces the rest (10–20 ms) (`docs/hardware-handoff.md`,
"Footswitches").

| Net | Pico physical pin | GPIO | Board | Lid |
|---|---|---|---|---|
| FS1 | **14** | GP10 | FS pin 2 | in the box, footswitch **2** (middle), COM lug; one leg of C2 (100 nF) |
| FS2 | **15** | GP11 | FS pin 3 | in the box, footswitch **3** (right), COM lug; one leg of C3 (100 nF) |
| FS3 | **16** | GP12 | FS pin 4 | in the box, footswitch **1** (left), COM lug; one leg of C1 (100 nF) |
| GND | **13** (and 3, 8, 18, 23, 28, 33, 38) | — | FS pin 1 | footswitch 1, 2 and 3, **NC** lug in the box; the other leg of C1, C2 and C3 |

Pin 13 is the Pico ground on the FS header's own strip; the Pico joins all eight of its grounds
inside itself. The board's net names (FS1–FS3, the order of the header's pins) are the board's and
do not move. **Which switch is 1, 2 or 3 is the player's, left to right**, and the firmware maps
each to the pin its wire landed on (`pins[]` in `firmware/src/footswitch.c`). Switch 1 sends `cc`
80, 2 sends 81 and 3 sends 82 (`docs/uart-protocol.md`, U8), and `pedald`'s map decides what each
means. The panic bypass is a long press on switch 3, the right-hand one.

## The FS connector, pin by pin

A JST-XH 4-way header on the board (B4B-XH-A), and a 4-way XH housing on the loom. Pin 1 is the
square pad, at the top of the header in the drawing.

As built in the box:

| FS pin | Net | Goes to | Firmware's switch (cc) |
|---|---|---|---|
| 1 | GND | the **NC** lug of pole A on each switch, jumped from switch to switch | — |
| 2 | FS1 (GP10) | footswitch **2** (middle), **COM** lug of pole A | 2 (cc 81) |
| 3 | FS2 (GP11) | footswitch **3** (right), **COM** lug of pole A | 3 (cc 82), and the panic long-press |
| 4 | FS3 (GP12) | footswitch **1** (left), **COM** lug of pole A | 1 (cc 80) |

The design drew GND to the NO lugs and FS pins 2–4 to switches 1–3 in order. The box differs in
both. Rather than rewire the lid, the firmware takes the box as it is (decided 2026-11-07). A loom
built to the original drawing needs `pins[] = {10, 11, 12}` and `PRESS_OPENS 0`.

So the loom is four wires from the plug: the ground runs to the nearest switch and is then jumped
from switch to switch, and each switch's signal wire runs back beside it ("a loom, the ground
among the switch wires", the map's C4). Use 24–26 AWG stranded (XH crimps take 22–28), black for
GND, and leave enough length to open the lid with the plug in.

At each switch, solder the 100 nF across the same two lugs as the wires (COM to NC in the box),
legs short.
Pole B is not used; leave its three lugs bare.

### Finding COM and NO on the MC7105

The switches are Multicomp Pro MC7105 (DPDT momentary, solder tags; `docs/bom.md`): six lugs, two
poles of three. Its datasheet draws the lugs only as a picture, so find them with a meter rather
than from a guess — it takes a minute per switch:

1. On continuity, pick one pole (one line of three lugs). The middle lug is normally COM.
2. Not pressed: COM beeps to one end lug. That is **NC**; leave it.
3. Hold the switch down: COM now beeps to the other end lug instead. That is **NO**.
4. Check that no lug beeps to the switch's body or the lid. The case stays out of the ground scheme
   (`docs/hardware-handoff.md`, "Power").

All three switches must be wired the same way, and the firmware has to be told which (`PRESS_OPENS`).
In the box each is closed at rest and open while pressed. Found on the bench 2026-11-07: all three
read "down" at rest and "up" while held.

**What the closed-at-rest wiring costs.** A loom that comes unplugged reads as all three switches
held. At power-up the firmware takes a switch that is already held as no press, so nothing
happens. If the plug comes out while the pedal runs, though, that is three presses and, a second
later, the panic bypass. With the NO wiring an unplugged loom is simply silent. Each closed switch
also passes the pull-up's current, about 60 µA, which is nothing here.

## The link connector, D3

The board's other header is the map's D3, the Pico's link and its power. If the Pico's present lead
to the Pi has a 1N5817 in it, take that diode out: the board carries its own (D4, band towards
VSYS), and two in series cost the Pico 0.3 V.

| D3 pin | Net | Pico | Pi header |
|---|---|---|---|
| 1 | GND | pin 3 (and every ground) | pin 6 (or any ground) |
| 2 | TX | pin 1, GP0 | pin 10, RXD |
| 3 | RX | pin 2, GP1 | pin 8, TXD |
| 4 | 5 V | pin 39, VSYS, through D4 | pin 4, 5 V |

Pin 4, not pin 2: pin 2 is the codec's VIN, and the header's 5 V stays up through a Pi reboot,
which is why the Pico takes it (`plan.md` 3.6, measured 2026-10-05). The USB console lead can stay
in the Pico's micro-B socket.

## Checking it

Before the Pico goes in its sockets, with a meter on the board: FS pin 2, 3 and 4 each beep to the
Pico socket's pin 14, 15 and 16, and FS pin 1 to pin 13. With the loom plugged in, each of FS pins
2–4 reads open to pin 1 until its switch is pressed.

With the Pico in and powered: pins 14–16 read 3.3 V at rest and 0 V pressed. The firmware
(`firmware/src/footswitch.c`) turns their pull-ups on, takes a reading that holds for 10 ms, and
prints `fs: 1 down` and `fs: 1 up` on its USB console; `?` there prints all three. A press sends
`cc` 80, 81 or 82 with 127 and its release the same with 0, and the service acts on the press only.
**A 1 s press on footswitch 3 is the panic bypass**, and another takes it off: it is sent as
`bypass_set`, and drives the relay once there is one (step 6). HELLO's caps say three
footswitches.
