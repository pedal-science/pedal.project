# Bill of materials

Every part the pedal needs that isn't already on the bench, grouped by what it's for. Prices are
CPC's, per unit and ex VAT, checked on 2026-09-24, and the order codes go straight into CPC's Quick
Add. Where a part waits on a decision, the **Status** column says which one.

| Status | Meaning |
|---|---|
| **in hand** | Arrived from CPC (as of 2026-09-30) |
| **due** | Ordered, not arrived |
| **later** | Not designed yet, so there's no part to buy |
| **to buy** | Decided, not ordered yet. Not from CPC unless a code is given |

Some quantities are CPC's minimum order rather than what the build needs. The notes say where.
The analogue values were settled by the Phase 2b review on 2026-09-27
([plan](../plan.md#phase-2--the-codec-and-the-analogue-stages)), against 2a's measurements.

## Already on the bench

- `vip` (Pi 5) and `piv` (Pi 500), the SSL 2+, the SparkFun WM8960 breakout (stock, unchecked), the
  ST7789 display with its encoder, the spare enclosure, the Cioks DC7 and the MIDI Commander. The
  RP2350-USB-A is on its way.
- The **spare enclosure is the bench pedal since 2026-10-04**: a temporary plastic box whose rear
  wall carries IN, OUT L and OUT R in the Neutrik jacks, standing in for the aluminium case until it
  arrives (plan Phase 4).
- Basic open-frame 6.35 mm jacks. The Neutrik jacks under Building replace them in the build.
- Jumper leads, and black hook-up wire.

## Pico, prototyping and MIDI in

| Part | CPC code | Qty | £ each | For |
|---|---|---|---|---|
| Raspberry Pi Pico 2 WH (Pico 2 W with headers) | SC21692 | 2 | 6.30 | The control surface, and one for experiments. The W keeps Pico WiFi possible (D2) |
| Raspberry Pi Debug Probe | SC20014 | 1 | 10.00 | SWD flashing and debugging, and a USB-UART for testing the Pico link |
| 830-point breadboard with 140 pre-cut jumper wires (Pro Signal) | PC02882 | 2 | 4.24 | Prototyping, plus a spare |
| 40-way 2.54 mm pin header strip (Multicomp Pro) | CN21901 | 2 | 0.93 | The WM8960 board's two rows (16 pins each), and the RP2350 board |
| H11L1M optocoupler (onsemi, DIP-6) | SC17297 | 2 | 0.35 | MIDI in, plus a spare |
| 5-pin 180° DIN panel socket (Deltron 650-0500) | CN00073 | 1 | 3.52 | MIDI in |
| 1N4148 diodes, pack of 50 | SC07296 | 1 | 0.69 | MIDI in, the relay's flyback diode, clamps on the expression input |
| 220 Ω 1% metal film, pack of 50 | RE03741 | 1 | 1.08 | MIDI in, LED resistors |
| 1 kΩ 1% metal film, pack of 50 | RE03722 | 1 | 1.38 | MIDI pull-up, the relay transistor's base, LED resistors, the expression filter |
| 100 nF X7R ceramic, 2.5 mm pitch | CA10727 | 10 | 0.08 | Decoupling, and the 100 nF across each footswitch |

All of these have arrived: £41.11 of the order's £117.19.

### MIDI in: the circuit these parts make

The input side follows the MIDI 1.0 electrical specification (CA-033, 2014). Only the pull-up
depends on the receiver's 3.3 V supply.

- DIN pin 4 → 220 Ω → the H11L1M's LED anode. The LED's cathode goes to DIN pin 5.
- A 1N4148 sits across the LED the other way round (its cathode on the anode side), so a
  miswired cable can't reverse-bias the LED.
- DIN pin 2, the cable shield, stays unconnected at an input, so the controller's ground never
  reaches the pedal's. Pins 1 and 3 are unused.
- The H11L1M runs from the Pico's 3.3 V, with 100 nF across its supply pins. Its open-collector
  output has a 1 kΩ pull-up to 3.3 V and feeds a Pico UART RX pin at 31 250 baud, 8N1, with no
  inversion: current in the loop turns the output low, which is a UART 0, and an idle loop leaves
  it high.
- Take the pin numbers from the H11L1M datasheet.

## Analogue input (Phase 2)

| Part | CPC code | Qty | £ each | Status | Notes |
|---|---|---|---|---|---|
| OPA2197IDR dual op-amp (SOIC-8) | SC17175 | 2 | 1.80 | due | Rail-to-rail in and out, 5.5 nV/√Hz. On back order until 4 Oct, and CPC is sending it separately. The draft named the OPA1642, which CPC doesn't sell. The 2b findings explain why the bias point matters more than which of these you pick |
| SOIC-8 to DIP-8 adapter, pins fitted (Aries LCQT-SOIC8-8) | PC02100 | 2 | 1.85 | in hand | Carries the OPA2197 in an 8-pin socket, so op-amps can be swapped. The op-amp is soldered onto it at 1.27 mm pitch |
| 8-pin DIL socket | SC06498 | 2 | 0.22 | in hand | Takes the adapters |
| 100 nF PET film, 63 V, 5 mm pitch | CA06944 | 10 | 0.09 | in hand | Input coupling. Sold in tens |
| 680 kΩ 1% metal film, pack of 50 | RE04997 | 1 | 1.23 | in hand | The top of the Line pad |
| 330 kΩ 1% metal film, pack of 50 | RE04995 | 1 | 1.08 | in hand | The bottom of the Line pad |
| 10 kΩ 1% metal film, pack of 50 | RE03723 | 1 | 2.12 | in hand | The bias divider |
| 1 MΩ 1% metal film, pack of 50 | RE03725 | 1 | 1.16 | in hand | The output bleed resistors |
| 100 kΩ 1% metal film, pack of 50 | RE03724 | 1 | 1.08 | in hand | The relay transistor's base pull-down |
| 100 Ω 1% metal film, pack of 50 | RE03721 | 1 | 1.08 | in hand | Output resistors, the RC filter on the buffer's supply |
| Toggle switch, SPDT on-on, gold contacts (Multicomp Pro 1MS1T1B1M1RE) | SW02844 | 1 | 1.31 | in hand | The Inst/Line switch. Gold contacts, because it switches a small signal |
| Single-core screened cable, 1.6 mm, 100 m reel | CBBR4177 | 1 | 7.29 | in hand | For the high-impedance run from the input jack to the buffer |
| Input jack | — | — | — | in hand | One of the five Neutrik jacks under Building |

### The input stage these parts make

This follows the 2b early findings: unity gain for an instrument, a pad for Line, and a bias point in
the middle of the op-amp's input range.

- Jack tip → 100 nF film → node A. From A, 680 kΩ to node B, then 330 kΩ from B to the bias. The
  input sees about 1 MΩ in either switch position.
- The Inst/Line switch connects one half of the OPA2197, wired as a follower, to A (Inst, ×1) or to
  B (Line, ×0.33, −9.7 dB). Its output goes to the WM8960 board's LINPUT1 pad. The board's own
  100 Ω, 47 nF and 1 µF isolate it and block the DC. The 47 nF is ceramic and distorts; 2c swaps
  LIN1's for film (plan 2b).
- The bias is about 2.9 V: two 10 kΩ in series from the filtered 9 V (after the 1N5817, 100 Ω and
  100 µF), and one 10 kΩ to ground with 10 µF across it. The op-amp runs from the same filtered
  9 V, with 100 nF at its supply pins. The unused half is a follower tied to the bias.
- With the codec's PGA at 0 dB, full scale at the jack is about 1.4 V peak on Inst and 4.3 V peak on
  Line. For hotter pickups, lower the PGA in the mixer file: −6 dB gives 2.8 V peak on Inst.
- Wire the input jack's tip switch contact to ground. With nothing plugged in, the input then sits at
  0 V, which keeps it quiet and stops the pop when you plug in.

## Analogue output (Phase 2)

| Part | CPC code | Qty | £ each | Status | Notes |
|---|---|---|---|---|---|
| 10 µF 50 V bipolar electrolytic (Panasonic) | CA09815 | 5 | 0.29 | in hand | HP_L/HP_R coupling, each with a 100 Ω and a 1 MΩ from the packs above. The build needs two, but CPC's minimum is five. 2a's measurements need this stage too, to keep the codec's 1.65 V bias off the SSL 2+ |
| Output jacks | — | — | — | in hand | Two of the five Neutrik jacks under Building |

## Power (Phases 2 and 4)

| Part | CPC code | Qty | £ each | Status | Notes |
|---|---|---|---|---|---|
| 2.1 mm DC socket, panel mount, **switched** (Cliff FC681445 or a switched equivalent) | PL17192 | 1 | 1.60 | in hand | The 9 V input, and the battery disconnect: a switched socket's third contact opens when a plug is inserted, taking the battery out of circuit. Confirm the FC681445 is the switched version; if not, pick one. Check that it keeps 0 V off a metal case, which the star ground depends on |
| 9 V battery snap (PP3 clip) | — | 1 | — | to buy | The battery − runs through the DC socket's switch to the star ground, so the barrel disconnects the battery. Its wires can be reversed, so the battery + goes through a 1N5817 (below). The meter's 680 kΩ + 330 kΩ divider is already in hand (Analogue input) |
| 1N5817 Schottky diode | SC07407 | 3 | 0.10 | in hand | Reverse-polarity protection on the 9 V barrel and on the battery (two), and the diode into the Pico's VSYS from vip's header — Phase 3.6's form 2, **wired and tested 2026-10-05: the Pico keeps running through a vip reboot and a shutdown** (form 1, the USB-A port, does not: see the USB-A cable below). Band towards VSYS. With the battery option all three are used — no spare |
| 100 µF 25 V electrolytic (Panasonic FR) | CA09947 | 10 | 0.11 | in hand | 9 V bulk capacitance, the buffer's RC filter. Sold in tens |
| 10 µF 50 V electrolytic (Panasonic FC) | CA09903 | 10 | 0.18 | in hand | Decoupling for the bias and the regulators. Sold in tens |
| L78L33ACZ, 3.3 V 100 mA (TO-92) | SC16361 | 2 | 0.26 | in hand | AVDD from the 9 V side in 2c. The second one could later take the whole codec board off the host's rails |
| L78L05ABZ, 5 V 100 mA (TO-92) | SC15743 | 5 | 0.21 | in hand | The option for 2c that needs no cutting: feed the board's VIN from the 9 V side. CPC's minimum is five |
| M3 solder tags, pack of 100 | CN22127 | 1 | 0.83 | in hand | The star-ground point |
| Raspberry Pi 45 W USB-C power supply | — | 1 | — | in hand | vip's supply. It offers 5.1 V at 5 A by USB PD, which vip asks for itself. The DC7 v1's USB-A (1 A) isn't enough; it stays for the MIDI Commander |
| USB-C panel-mount extension, female panel socket to male plug | — | 1 | — | to buy | The 5 V input on the rear panel, plugged into vip's own USB-C, so vip negotiates 5 A and keeps its input protection. It must be a full USB-C extension (all pins, not power-only or USB 2.0) rated 5 A ("100 W", e-marked), about 20–30 cm, ideally with a right-angle plug. Its mounting (two-screw flange or nut) sets the panel cut-out. The layout must leave room for the plug at vip's port (Phase 4) |
| USB-A to micro-B cable, short, right-angle micro-B | — | 1 | — | in hand | The Pico's 5 V from one of vip's USB-A ports, and reflashing from vip if it carries data. **In use on the bench since 2026-10-04** (powering the Pico and carrying its console). **The 2026-10-05 test rules it out as the Pico's power**: vip's USB-A rail is switched off through a reboot (the Pico restarted — 48,930 s of uptime → 20 s). It stays for the console and flashing; the power is form 2, which holds through both a reboot and a shutdown and which should take its 5 V from **pin 4** so the codec's VIN keeps pin 2. `scripts/pico-power-test`, [bench-results/2026-10-05-pico-power-test.md](../bench-results/2026-10-05-pico-power-test.md) |

## Control surface (Phase 3)

| Part | CPC code | Qty | £ each | Status | Notes |
|---|---|---|---|---|---|
| Footswitch, DPDT momentary, solder tags (Multicomp Pro MC7105) | SW05660 | 3 | 4.23 | in hand | CPC's only momentary stomp switch, and it clicks. Pedal-parts shops sell silent soft-touch SPST ones |
| Bypass relay, DPDT, 5 V coil (Panasonic TQ2-5V) | SW02508 | 1 | 2.40 | in hand | Gold-clad contacts suit small audio signals. The coil draws 28 mA. Wire it so that de-energised means bypass (Phase 3.6) |
| BC337-40 NPN transistor (TO-92) | SC15771 | 5 | 0.06 | in hand | The relay driver: 1 kΩ from the GPIO to the base, 100 kΩ from base to emitter so the relay stays off while the Pico boots, and a 1N4148 across the coil. It switches fully from 3.3 V, which a 2N7000 isn't guaranteed to do. CPC's minimum is five |
| 5 mm LED, red diffused (Kingbright L-7113ID) | SC08044 | 10 | 0.11 | in hand | Sold in tens |
| 5 mm LED, green diffused (Kingbright L-7113GD) | SC08045 | 10 | 0.11 | in hand | Sold in tens |
| 5 mm LED panel clip (Broadcom HLMP-0103) | SC08868 | 4 | 0.26 | in hand | |
| Expression jack | — | — | — | in hand | One of the five Neutrik jacks under Building, if the debt register's decision keeps it. Its 1 kΩ and 100 nF filter is in hand |
| Knob for the display module's encoder | — | 1 | — | later | Depends on the shaft |

## Building

| Part | CPC code | Qty | £ each | Status | Notes |
|---|---|---|---|---|---|
| 6.35 mm TRS jack, switched, plastic body and nut (Neutrik NMJ6HF-S) | CN26782 | 5 | 0.83 | in hand | IN, OUT L, OUT R, expression, and a spare. Being plastic all round, the case never becomes a ground path. Fits a panel under 3 mm thick. On the outputs, wire the ring to ground, so a TRS cable into a balanced input picks up less hum. Later, the switches on the expression and OUT R jacks can tell the Pico whether a cable is in |
| Stripboard, FR4, 100 × 160 mm (Kemo E005) | PC01603 | 2 | 3.98 | in hand | Buffer and power on one, MIDI and the relay driver on the other |
| 6-pin DIL socket | SC15351 | 10 | 0.17 | in hand | For the H11L1M. CPC's minimum is ten |
| 20-way 2.54 mm socket strip | CN14539 | 5 | 0.43 | in hand | Seats the Pico (two strips) and the codec board (two cut to 16), so either can be swapped out. CPC's minimum is five |
| Hook-up wire, 7/0.2 stranded, 100 m, orange | CB21508 | 1 | 7.85 | in hand | A second colour beside the black you have |
| FR4 sheet, unclad, 3 mm, green, 200 × 300 mm | — | 1 | 15.89 inc VAT | to buy | The mounting plate: screwed to the base plate, with everything inside standing on it, so nothing electrical touches the case. FR4 because it's stiff and barely absorbs moisture. Choose the green FR4, not the yellow "3240". [AliExpress](https://www.aliexpress.com/item/1005005176647131.html), checked 2026-10-01 (sale price until 7 Oct); CPC and Farnell sell only 1.6 mm. Cut to about 175 × 105 mm with notches for the lid-screw bosses; the outline comes from the model |
| Nylon standoffs and screws, M2.5 (vip) and M3 (stripboards) | — | — | — | to buy | Nylon, so vip's grounded mounting holes and the stripboards' screws can't connect anything to the case. Countersunk nylon screws from under the plate into female standoffs; heights chosen with the layout |
| Panel hardware | — | — | — | later | Chosen with the enclosure layout (Phase 4) |

## Not designed yet

- The mic stage (D5): the jack, a preamp or the codec's mic path, and whether to offer phantom power.
- Cooling, if Phase 4's heat soak inside the enclosure calls for it.
- Tools aren't listed here.

## Total

Everything with a part number was ordered from CPC: 41 lines, £117.19 ex VAT (£140.63 with VAT).
As of 2026-09-30 it has all arrived except the OPA2197, which is back-ordered until 4 Oct.
