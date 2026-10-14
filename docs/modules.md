# The pedal as pluggable modules

Written 2026-10-11, at the owner's request. **A proposal, not a decision**: nothing else in the
repository has been changed to match it. The map is
[diagrams/modules.html](diagrams/modules.html): every module, every cable, its connector and its
pinout, and a check, run in the page, that the ground wiring is a tree. Open it in a browser. This
file is the reasoning behind it.

The aim is that each circuit is its own small board, joined to the rest by keyed, latching cables.
Then any board can be unplugged and tested alone, fixed, or replaced by a new version without
rewiring the rest, and the plugs cost nothing in noise. Stripboard sketches of the boards to
build now are in [module-boards.md](module-boards.md). They follow this map's pinouts and its
ground tree. The mic preamp and the isolated 9 V supply are not drawn: neither has a circuit yet.

## The modules

### 1. The 9 V power board: yes, and smaller

It keeps the switched DC socket's wiring, the 1N5817, the 100 µF bulk capacitor, and the battery
meter's top resistors. It gives up R1 and C2, the 100 Ω + 100 µF filter. That filter belongs to the
op-amp, so it moves onto the input board, where its return sits beside the op-amp. The power board's
job becomes "protect the 9 V and hand it on". Any 9 V source can then stand in for it at the bench,
such as a battery clip on a test lead. Phase 4's isolated DC-DC converter becomes a drop-in
replacement with the same plug (P1 in the map).

**Might it go away?** "Use the codec's 5 V" is the right instinct about *where* the supply should
come from. Take it from the codec carrier, not on a separate wire from the Pi, so that it stays in
the tree. That makes it a jumper on the carrier: the analogue rail comes either from P1 (9 V) or,
filtered, from the 5 V that already arrives for the codec's VIN.

The input board runs from 5 V as it stands. Its bias is a third of the rail: 1.6 V at 5 V, against
2.9 V at 9 V. But it loses most of its headroom. At 5 V it clips about 1 dB above the codec's full
scale (PGA at 0 dB), against about 6 dB at 9 V. A hot pickup with the PGA turned down would then
clip in the buffer before the codec. With the jumper, comparing the two is an A/B test, not a
rewire.

Today's tests bear on this. The input's hum followed the **Pi's mains connection**, not the
buffer's supply: board 1 was on a battery throughout. So putting the buffer on the Pi's 5 V isn't
expected to add hum by that route. The rail's own ripple is what the carrier's filter is for.

**Check this before building it.** The handoff's battery scheme puts the socket's switch in the
battery's **−** lead, and has the barrel's centre at +9 V. Your Cioks is centre-negative: in board
1's stage 2, the sleeve is +9 V. A standard switched 2.1 mm socket breaks its switch from the
**sleeve** contact. So on this pedal it is the battery's **+** that goes through the switch:

- battery + → switch lug → sleeve contact → the 1N5817 → the rail;
- battery − → ground.

The one 1N5817 then protects both sources. Find which contact your socket's switch breaks from with
the meter before trusting either version.

### 2. The input buffer: yes, with two notes

- **The toggle is an SPDT on-on**: a common lug and two throws. An SPST switch has only two lugs.
- **Its three wires are the 1 MΩ node.** In today's tests, removing the toggle and its leads took
  14 dB off the hum
  ([bench-results/2026-10-11-first-sound](../bench-results/2026-10-11-first-sound/README.md)). So
  this board must sit directly behind the IN jack and the toggle. Keep the toggle's leads as short
  as the panel allows, and twisted. Otherwise the connector on them just adds a few more
  centimetres of antenna.
- **A later version could move the pad to a low-impedance node**: the follower first, then the pad,
  then the op-amp's spare half as a second buffer. The switch would then carry a low-impedance
  signal. That change stays inside the module, with the same plugs.
- **Check the toggle's bushing with a meter** against every lug before bolting it into an aluminium
  panel. If the bushing is on the common, a bonded panel would short the input, and a floating one
  would make the whole panel part of the 1 MΩ node.

### 3. The output: yes

It is three parts: the 10 µF bipolar capacitor, the 100 Ω in series, and the 1 MΩ bleed to
ground. Use one board per channel. They are identical, so they swap.

Since 2026-10-14 the ring gets the same three parts, from ground, so a TRS lead into a balanced
input is impedance-balanced ([balanced-outputs.md](balanced-outputs.md), step 1). That makes six
parts per board and a four-way jack cable.

The trade-off is two connector pairs for six passive parts. If you want fewer joints in the
output path, put both networks on the codec carrier and run the jack cables from there. The grounds
don't change.

### 4. The codec: yes, on a carrier, and the carrier is the audio star

The SparkFun board goes into two 16-pin socket strips on a carrier, as board A planned. The carrier
holds every connector the codec has, plus its analogue ground bus.

Its link to the Core is ten wires today (the table in
[codec-bringup-2a.md](codec-bringup-2a.md), stage 4). What each one is for:

- **3.3 V**: the codec's digital supply. It also powers the 24 MHz oscillator.
- **5 V**: VIN, which the board's own regulator turns into AVDD, the analogue supply.
- **I2C (SDA, SCL)**: control. The driver writes the codec's registers here, which is how the mixer
  file reaches it.
- **I2S, four wires**:
  - BCLK, the bit clock (3 MHz), and LRCLK, the frame clock (48 kHz). Both come *from* the codec,
    because it is the clock master.
  - ADCDAT carries the recorded audio to the Pi; DACDAT carries playback to the codec.
- **Two grounds.**

There is no master-clock (MCLK) wire. The codec makes its own clock from its 24 MHz oscillator,
which is why it has to be the I2S master. So the "clock" on your list is BCLK and LRCLK. In the map,
all ten ride one 14-way ribbon (D2), with a ground beside every clock and data wire.

The carrier also holds 2c's options as jumpers instead of rewiring:

- VIN from the Pi's 5 V, or from a 78L05 on the 9 V side (leg 1);
- AVDD from a 78L33 after the AVDD-ISO cut (leg 2);
- the case bond.

It also has test points on LIN1, HPL, HPR and GND.

### 5. The Pico: yes, and your understanding is what was measured

The Pico's 5 V comes from the Pi's header through a 1N5817 into VSYS. That is because the Pi's
USB-A power was measured to drop during a reboot, and the header's 5 V does not (2026-10-05). Two
details:

- Use **pin 4**, which leaves pin 2 to the codec's VIN alone, as the BOM says.
- The USB lead then carries only the console and flashing.

In the map, the UART, the 5 V and one ground travel together as LINK (D3). If the USB lead is also
plugged in, there are two ground routes between the Pi and the Pico. That is a loop, but a
digital-only one, and the map reports it as harmless to the audio. Keep that lead beside LINK, or
unplug it after flashing. The Debug Probe on the Pico's 3-pin SWD connector can flash it as well.

### 6. The others

- **Core breakout.** The Pi's 40-pin header goes to one keyed ribbon, plugged once. Every other
  board gets its own keyed cable from the breakout.
  - Moving between vip and piv is one ribbon.
  - The test points go here: BCLK, LRCLK, both data lines, SDA and SCL.
  - Optional: a Qwiic port (I2C, the one place Qwiic belongs) and a header for a Debug Probe to
    listen to the link.
  - If the I2S run proves too long, fold the breakout into the codec carrier's digital end.
- **Bypass relay.** It goes on its own board beside the jacks, not on the Pico's board (board B in
  the enclosure model). That keeps the guitar's signal off the control board, and the
  high-impedance runs short.
  - Only the coil's two wires go to the control board, and they carry no ground. The BC337 on the
    control board switches the coil's low side; the 1N4148 sits across the coil on the relay board.
  - The relay switches the jack side of the input capacitor, which the guitar drives. The 1 MΩ node
    stays on the input board.
  - Its audio sockets have the modules' own pinouts, so without it the jack cables plug straight
    into the input and output boards.
- **MIDI in.** The opto board ([bom.md](bom.md)'s circuit), beside the DIN socket, with three wires
  to the control board.
- **Panel looms.** Each runs from the panel parts to one connector on the control board:
  - the footswitches with their LEDs (100 nF across each switch, at the switch);
  - rigpa's encoder and back button;
  - the expression jack.
- **Later:**
  - the isolated 9 V supply (Phase 4's single-cable option);
  - the mic stage (D5), into the codec carrier's second input;
  - perhaps a Qwiic temperature sensor for Phase 4's heat soak.
- **The display** is two cables from the Pi, HDMI and USB, run together.

## Grounding

Your two questions first, then the rules the answers come from.

### Where do the output jacks' grounds go?

Twist the sleeve wire with the tip, and take both to the output board. The output board's ground
then goes back to the codec carrier in the same cable as HPL (or HPR).

So the sleeve does end at the codec's ground, and that **is** the star: in this design the star is
the codec carrier's analogue ground bus. The sleeve does not also get its own wire to the star. If it
did, it would reach the star two ways, which is a loop. The map's first "Try a mistake" shows it.

Why the codec? The ADC measures the audio, and the DAC produces it, relative to the codec's own
ground. Any voltage between "the star" and "the codec's ground" is therefore in the audio. With the
star at the codec, that voltage is zero by construction.

### How many grounds between boards, and should the codec or the Pico have their own?

Each pair of boards is joined by ground in **exactly one cable**. Inside that cable, use as many
ground wires as you like. The codec's ribbon has six, one beside each clock and data wire, because a
3 MHz bit clock needs its return right beside it. That is what codec-bringup-2a's "run the pin 39
ground beside BCLK" was doing.

All the GND pins on one board are the same net: the board's ground plane joins them. Which ones you
use decides where the return current flows, not how many grounds there are. What you must not have
is a **second route**: for example, a separate wire from the codec or the Pico to a star tag, as
well as the cable that already joins it to the Pi.

- **The codec** gets its ground from the Pi through its digital cable only, on its J4 GND pins. Its
  analogue side reaches the audio boards only through the carrier's bus, on J5's GND pin. The codec
  board's own ground plane joins the two. It is the one place where the Pi's side meets the audio
  side.
- **The Pico** gets its ground from the Pi through LINK, and passes it on to everything it drives.
  It never touches the audio star. So the relay coil's 28 mA, and the LEDs' currents, stay on the
  digital side.

### The rules

The map checks the first; the rest are what it is built from.

1. **One tree.** Every board has exactly one cable that carries ground, pointing towards the root.
   The audio boards hang off the codec carrier, and the codec carrier and the control board hang
   off the Pi. The Pi is the root: it is where the USB-C supply's 0 V enters.
2. **The audio star is on the codec carrier.** Each audio board reaches it in the cable that carries
   its signal. This is the existing star rule ("each item on its own wire, nothing daisy-chained"),
   with the modules as the items. A jack's sleeve is part of its module, not a separate item.
3. **The Pi's side and the audio side meet once,** inside the codec board.
4. **A signal travels with its return:** twisted, or screened, on neighbouring pins of the same
   connector, from the jack to the module, and from the module to the codec.
5. **Some cables carry no ground at all:**
   - the relay coil cable: the coil's low side is switched on the control board;
   - the MIDI DIN wires: the opto isolates them, and DIN pin 2 stays unconnected;
   - the battery-sense wires: each has a high-value resistor at the power end, and its few
     microamps return through the tree;
   - the toggle's wires: they are the 1 MΩ node.

   A board that is wired to two sides of the tree must be joined by ground to only one of them.
6. **Filter a supply where it is used.** The cables between boards carry protected but unfiltered
   9 V. The input board filters its own supply, and the carrier regulates the codec's.
7. **The case touches nothing**, except, if you fit it, one bond (below).

### The case

The plan leaves this open (Phase 4: float the case, or bond it to the star at one point). Today's
tests give the case a job.

The hum on the 1 MΩ node needed a mains-referenced return path. The Pi's Class II supply provided
one through its Y-capacitor: tests 7 and 8 show the hum come and go with the Pi's mains connection.
In effect, the pedal's whole ground was being driven at mains frequency relative to the room. A
metal case bonded to the circuit's ground is a shield at the circuit's own potential, which is what
that mechanism calls for. **Expect the bonded case to win, and measure it.**

Make the bond a jumper on the codec carrier, so that the comparison is an A/B test, not a rewire.
Then make sure nothing else bonds the case:

- the plastic jacks;
- the nylon standoffs (the Pi's mounting holes are grounded);
- the USB-C panel socket's metal: insulate its flange;
- the display's frame, if it is on its HDMI/USB ground: nylon screws;
- the DC socket, and the DIN socket's shell;
- the toggle's bushing.

Each of these alone is harmless. Any one of them plus the jumper is a loop through the case. The
map's mistakes 3 and 4 show it.

### The screened input cable

Today the input cable's braid is bonded at the jack only, and the jack's sleeve has its own wire to
the star. In the modular build, **the braid is the sleeve's return**. It is bonded at the jack's
sleeve and at pin 1 of the input board's connector, and there is no separate sleeve wire.

The "one end only" rule existed because the braid would otherwise have been a second path beside
the sleeve wire. With no sleeve wire, the braid is the only path. A coaxial braid used as the
return also has no loop area.

There is a purist alternative: a 2-core screened cable, with the second core as the return and the
screen bonded at the module end only.

### On the bench

A plugged-in Debug Probe joins the Mac's ground to the pedal. With the SSL on the same Mac measuring
OUT L, that makes a loop through the audio star; the map's bench toggle shows it. Unplug the probes,
or run the Mac on battery, for noise measurements. In today's tests, the Mac's mains earth alone
moved the hum by 3 dB.

## Connectors

There are three good sets, and the map's "Connectors" choice shows each one on every cable.

| | **A: JST-XH + IDC (recommended)** | **B: JST-PH (STEMMA) on breakouts** | **C: no-crimp at the panel** |
|---|---|---|---|
| Pitch | 2.5 mm. Fits 2.54 mm stripboard and breadboards: the 0.04 mm per pin is taken up by the holes on short headers. Past about 8 ways it adds up to 0.3 mm, so use a true 2.54 mm connector (Molex KK 254) there | 2.0 mm. Needs a breakout board, or 2 mm-pitch board | 5.08 mm pluggable terminal blocks for the panel looms, which fit every other stripboard hole. XH between boards |
| Rating (JST's datasheets) | 3 A at AWG 22, 250 V; takes AWG 30–22 | 2 A at AWG 24, 100 V; takes AWG 32–24 | Far more than needed |
| How it holds | A shrouded, keyed header with a lock | The same, smaller | A screw clamp in a keyed plug |
| Making leads | Crimp, or buy pre-crimped pigtails and solder the free ends | As XH | No crimping: strip the wire and screw it in |
| Choose it if | You build on stripboard: everything plugs directly into it | You prefer small connectors and are making breakouts anyway | You would rather not crimp the panel wiring |

These go with every option:

- **IDC box headers and ribbon** for the Pi's 40-pin header (D1) and the codec's 14 wires (D2). A
  box header's two rows sit in adjacent holes, so on stripboard you can't separate them with a
  spot-face cutter. Either:
  - cut between the holes with a knife;
  - mount the header on pad-per-hole board;
  - use a ready-made Pi breakout ("T-cobbler" style);
  - or, for D2, use a single-row 14-way KK 254.
- **JST-SH** for what it is standard for. That means the Debug Probe's leads (the Pico 2 WH's SWD
  connector and the Pi 5's UART connector are already JST-SH), and the optional Qwiic port.

Not for these cables:

- **Qwiic / STEMMA QT (JST-SH, 1.0 mm).** Each one needs a breakout, because the headers are
  surface-mount. They carry 1 A on AWG 28–32 wire, and hold by friction. Above all, the connector
  *means* "I2C at 3.3 V". A Qwiic sensor plugged into an audio socket, or 9 V into a Qwiic port, is
  the mistake that would be waiting.
- **Grove.** It is Seeed's own 2 mm connector: close to JST-PH, but not reliably mating with it.
  Don't mix the two.
- **Dupont jumper leads**, for anything permanent. They have no latch and no key, and they work
  loose. Stage 6's adapter going in 180° round was this class of mistake. They are fine on the
  breadboard.

### Pinout conventions

The map's pinouts follow these:

- Pin 1 is GND on every module connector, as on Qwiic.
- A signal sits beside its ground, and supply pins go at the far end.
- **A plug that carries a supply must not fit a socket where it would do harm.** On most boards that
  means a pin count no signal connector on the board uses. For example:
  - the carrier's 9 V socket is 2-way, and its outputs are 3-way with the third pin unused;
  - the relay coil's plug is 3-way, with its middle pin unused, so it can't go into the relay
    board's 2-way audio sockets;
  - the battery's plug is 3-way, so it can never go into the 9 V board's 2-way output socket. There
    it would bypass the socket's switch, and the adapter could charge it.

  Where pin counts do repeat on a board, the pinouts are arranged so that swapping the plugs is
  harmless. OUT L and OUT R are the obvious case. Others: on the control board, the relay, MIDI and
  battery-sense plugs are all 3-way; on the 9 V board, the DC socket, battery and sense plugs are.
- **A smaller plug can be forced into a larger shrouded header,** one pin off. If a plug doesn't
  click home, it is in the wrong socket.
- Label both ends of every cable with its ID from the map, and label each header with the same ID.

### Does contact plating matter for noise?

Not at these impedances. A contact is 10–20 mΩ (JST's figures), in series with:

- a buffer's output;
- a 100 Ω resistor;
- or an input of 10 kΩ or more.

XH and PH contacts are tin-plated. That is fine for a pedal whose plugs are mated a few times and
then left, if each cable is tied down near its connector so that stomping on the pedal doesn't work
the contacts. If one connection will be plugged and unplugged all the time, make that one gold. KK
254 is sold gold-plated.

## Building and testing with modules

- **Make test leads once:**
  - a battery clip on the input board's plug (pins 1 and 4) with a lead on pin 2, so the board
    runs alone;
  - a **shorting plug** for the codec's IN1 (pins 1 and 2 joined). That is 2a's shorted-input noise
    test without touching the codec;
  - a 1 kΩ source plug;
  - XH-to-crocodile-clip leads, and XH-to-breadboard leads.
- **Bring each new board up the same way:** power it alone from the bench, check its DC points, then
  plug it into the pedal.
- **Mounting:** nylon standoffs, at least two per board. Tie every cable down near its connector.
- **Routing:**
  - Keep the audio cables away from the Pi, the USB-C power lead, the display's cables and the relay
    coil's pair.
  - Where they must cross, cross at right angles.
  - In the 1456RH3, keep the audio cluster together in one corner: the jacks, the relay, the input
    and output boards, the codec carrier and the 9 V board. Put the Pi and the display wiring at
    the other end, and the Pico between the footswitches and the Pi.

## What it would change elsewhere (not done)

- **Board A becomes four small boards** (input, two outputs, 9 V) plus the codec carrier. That also
  takes its routing problem off the table: one 18 × 24 board had to carry every net past the codec's
  socket strips ([board-a-netlist.md](board-a-netlist.md)).
- **Board B becomes the control board,** and the relay moves off it to its own board by the jacks.
- **The star tag becomes the codec carrier's ground strip,** with every connector's pin 1 on it.
- **The input's screened cable** becomes coax, with its braid as the return.
- **The handoff's and the BOM's battery wiring**: the switch goes in the + lead on a
  centre-negative socket, once a meter confirms it.
- **`stripboard/nets.py`** gains the module boundaries as its `carries=` splits, and its pads become
  connector pins.

## Open, and what the modules make measurable

- **The case,** floating or bonded: the carrier's jumper.
- **The analogue rail,** 9 V or 5 V from the carrier: a jumper.
- **VIN** from the Pi, or from the 78L05 (2c leg 1): a jumper.
- **The I2S run** over the ribbon and the breakout. Listen for crackle, and scope BCLK at the
  carrier's test point. The codec board's own 10 Ω series resistors are already in those lines.
- **The toggle's bushing:** one meter check.
