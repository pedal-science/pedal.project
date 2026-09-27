# Bill of materials

Every part the pedal needs that isn't already on the bench, grouped by what it's for. Prices are
CPC's, per unit and ex VAT, checked on 2026-09-24, and the order codes go straight into CPC's Quick
Add. Where a part waits on a decision, the **Status** column says which one.

| Status | Meaning |
|---|---|
| **basket** | In your CPC basket, not yet ordered |
| **later** | Not designed yet, so there's no part to buy |

Some quantities are CPC's minimum order rather than what the build needs. The notes say where.
The analogue values are provisional until the Phase 2b review
([plan](../plan.md#phase-2--the-codec-and-the-analogue-stages)) has 2a's measurements. If it moves
them, only resistor values change.

## Already on the bench

- `tib` (Tinker Board S), the SSL 2+, the SparkFun WM8960 breakout (stock, unchecked), the ST7789
  display with its encoder, the spare enclosure, the Cioks DC7 and the MIDI Commander. The
  RP2350-USB-A is on its way.
- Basic open-frame 6.35 mm jacks. The Neutrik jacks under Building replace them in the build.
- Jumper leads, and black hook-up wire.

## Pico, prototyping and MIDI in

| Part | CPC code | Qty | £ each | For |
|---|---|---|---|---|
| Raspberry Pi Pico 2 WH (Pico 2 W with headers) | SC21692 | 2 | 6.30 | The control surface, and one for experiments. The W keeps Pico WiFi possible (D2) |
| Raspberry Pi Debug Probe | SC20014 | 1 | 10.00 | SWD flashing and debugging, and a USB-UART for testing the `tib` link |
| 830-point breadboard with 140 pre-cut jumper wires (Pro Signal) | PC02882 | 2 | 4.24 | Prototyping, plus a spare |
| 40-way 2.54 mm pin header strip (Multicomp Pro) | CN21901 | 2 | 0.93 | The WM8960 board's two rows (16 pins each), and the RP2350 board |
| H11L1M optocoupler (onsemi, DIP-6) | SC17297 | 2 | 0.35 | MIDI in, plus a spare |
| 5-pin 180° DIN panel socket (Deltron 650-0500) | CN00073 | 1 | 3.52 | MIDI in |
| 1N4148 diodes, pack of 50 | SC07296 | 1 | 0.69 | MIDI in, the relay's flyback diode, clamps on the expression input |
| 220 Ω 1% metal film, pack of 50 | RE03741 | 1 | 1.08 | MIDI in, LED resistors |
| 1 kΩ 1% metal film, pack of 50 | RE03722 | 1 | 1.38 | MIDI pull-up, the relay transistor's base, LED resistors, the expression filter |
| 100 nF X7R ceramic, 2.5 mm pitch | CA10727 | 10 | 0.08 | Decoupling, and the 100 nF across each footswitch |

All of these are in the basket: £41.11 of its £117.19.

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
| OPA2197IDR dual op-amp (SOIC-8) | SC17175 | 2 | 1.80 | basket | Rail-to-rail in and out, 5.5 nV/√Hz. On back order until 4 Oct, so CPC may send it separately. The draft named the OPA1642, which CPC doesn't sell. The 2b findings explain why the bias point matters more than which of these you pick |
| SOIC-8 to DIP-8 adapter, pins fitted (Aries LCQT-SOIC8-8) | PC02100 | 2 | 1.85 | basket | Carries the OPA2197 in an 8-pin socket, so op-amps can be swapped. The op-amp is soldered onto it at 1.27 mm pitch |
| 8-pin DIL socket | SC06498 | 2 | 0.22 | basket | Takes the adapters |
| 100 nF PET film, 63 V, 5 mm pitch | CA06944 | 10 | 0.09 | basket | Input coupling. Sold in tens |
| 680 kΩ 1% metal film, pack of 50 | RE04997 | 1 | 1.23 | basket | The top of the Line pad |
| 330 kΩ 1% metal film, pack of 50 | RE04995 | 1 | 1.08 | basket | The bottom of the Line pad |
| 10 kΩ 1% metal film, pack of 50 | RE03723 | 1 | 2.12 | basket | The bias divider |
| 1 MΩ 1% metal film, pack of 50 | RE03725 | 1 | 1.16 | basket | The output bleed resistors |
| 100 kΩ 1% metal film, pack of 50 | RE03724 | 1 | 1.08 | basket | The relay transistor's base pull-down |
| 100 Ω 1% metal film, pack of 50 | RE03721 | 1 | 1.08 | basket | Output resistors, the RC filter on the buffer's supply |
| Toggle switch, SPDT on-on, gold contacts (Multicomp Pro 1MS1T1B1M1RE) | SW02844 | 1 | 1.31 | basket | The Inst/Line switch. Gold contacts, because it switches a small signal |
| Single-core screened cable, 1.6 mm, 100 m reel | CBBR4177 | 1 | 7.29 | basket | For the high-impedance run from the input jack to the buffer |
| Input jack | — | — | — | basket | One of the five Neutrik jacks under Building |

### The input stage these parts make (provisional)

This follows the 2b early findings: unity gain for an instrument, a pad for Line, and a bias point in
the middle of the op-amp's input range.

- Jack tip → 100 nF film → node A. From A, 680 kΩ to node B, then 330 kΩ from B to the bias. The
  input sees about 1 MΩ in either switch position.
- The Inst/Line switch connects one half of the OPA2197, wired as a follower, to A (Inst, ×1) or to
  B (Line, ×0.33, −9.7 dB). Its output goes to the WM8960 board's LINPUT1 pad. The board's own
  100 Ω, 47 nF and 1 µF isolate it and block the DC.
- The bias is about 2.9 V: two 10 kΩ in series from the filtered 9 V (after the 1N5817, 100 Ω and
  100 µF), and one 10 kΩ to ground with 10 µF across it. The op-amp runs from the same filtered
  9 V, with 100 nF at its supply pins. The unused half is a follower tied to the bias.
- With the codec's PGA at 0 dB, full scale at the jack is about 1.4 V peak on Inst and 4.3 V peak on
  Line.
- Wire the input jack's tip switch contact to ground. With nothing plugged in, the input then sits at
  0 V, which keeps it quiet and stops the pop when you plug in.

## Analogue output (Phase 2)

| Part | CPC code | Qty | £ each | Status | Notes |
|---|---|---|---|---|---|
| 10 µF 50 V bipolar electrolytic (Panasonic) | CA09815 | 5 | 0.29 | basket | HP_L/HP_R coupling, each with a 100 Ω and a 1 MΩ from the packs above. The build needs two, but CPC's minimum is five. 2a's measurements need this stage too, to keep the codec's 1.65 V bias off the SSL 2+ |
| Output jacks | — | — | — | basket | Two of the five Neutrik jacks under Building |

## Power (Phases 2 and 4)

| Part | CPC code | Qty | £ each | Status | Notes |
|---|---|---|---|---|---|
| 2.1 mm DC socket, panel mount (Cliff FC681445) | PL17192 | 1 | 1.60 | basket | The 9 V input. Check that it keeps 0 V off a metal case, which the star ground depends on |
| 1N5817 Schottky diode | SC07407 | 3 | 0.10 | basket | Reverse-polarity protection on the 9 V, the diode into the Pico's VSYS, and a spare |
| 100 µF 25 V electrolytic (Panasonic FR) | CA09947 | 10 | 0.11 | basket | 9 V bulk capacitance, the buffer's RC filter. Sold in tens |
| 10 µF 50 V electrolytic (Panasonic FC) | CA09903 | 10 | 0.18 | basket | Decoupling for the bias and the regulators. Sold in tens |
| L78L33ACZ, 3.3 V 100 mA (TO-92) | SC16361 | 2 | 0.26 | basket | AVDD from the 9 V side in 2c. The second one could later take the whole codec board off `tib`'s rails |
| L78L05ABZ, 5 V 100 mA (TO-92) | SC15743 | 5 | 0.21 | basket | The option for 2c that needs no cutting: feed the board's VIN from the 9 V side. CPC's minimum is five |
| M3 solder tags, pack of 100 | CN22127 | 1 | 0.83 | basket | The star-ground point |
| 5 V / 3 A input for `tib` and the Pico | — | — | — | later | Phase 4 |

## Control surface (Phase 3)

| Part | CPC code | Qty | £ each | Status | Notes |
|---|---|---|---|---|---|
| Footswitch, DPDT momentary, solder tags (Multicomp Pro MC7105) | SW05660 | 3 | 4.23 | basket | CPC's only momentary stomp switch, and it clicks. Pedal-parts shops sell silent soft-touch SPST ones |
| Bypass relay, DPDT, 5 V coil (Panasonic TQ2-5V) | SW02508 | 1 | 2.40 | basket | Gold-clad contacts suit small audio signals. The coil draws 28 mA. Wire it so that de-energised means bypass (Phase 3.6) |
| BC337-40 NPN transistor (TO-92) | SC15771 | 5 | 0.06 | basket | The relay driver: 1 kΩ from the GPIO to the base, 100 kΩ from base to emitter so the relay stays off while the Pico boots, and a 1N4148 across the coil. It switches fully from 3.3 V, which a 2N7000 isn't guaranteed to do. CPC's minimum is five |
| 5 mm LED, red diffused (Kingbright L-7113ID) | SC08044 | 10 | 0.11 | basket | Sold in tens |
| 5 mm LED, green diffused (Kingbright L-7113GD) | SC08045 | 10 | 0.11 | basket | Sold in tens |
| 5 mm LED panel clip (Broadcom HLMP-0103) | SC08868 | 4 | 0.26 | basket | |
| Expression jack | — | — | — | basket | One of the five Neutrik jacks under Building, if the debt register's decision keeps it. Its 1 kΩ and 100 nF filter is in the basket |
| Knob for the display module's encoder | — | 1 | — | later | Depends on the shaft |

## Building

| Part | CPC code | Qty | £ each | Status | Notes |
|---|---|---|---|---|---|
| 6.35 mm TRS jack, switched, plastic body and nut (Neutrik NMJ6HF-S) | CN26782 | 5 | 0.83 | basket | IN, OUT L, OUT R, expression, and a spare. Being plastic all round, the case never becomes a ground path. Fits a panel under 3 mm thick. On the outputs, wire the ring to ground, so a TRS cable into a balanced input picks up less hum. Later, the switches on the expression and OUT R jacks can tell the Pico whether a cable is in |
| Stripboard, FR4, 100 × 160 mm (Kemo E005) | PC01603 | 2 | 3.98 | basket | Buffer and power on one, MIDI and the relay driver on the other |
| 6-pin DIL socket | SC15351 | 10 | 0.17 | basket | For the H11L1M. CPC's minimum is ten |
| 20-way 2.54 mm socket strip | CN14539 | 5 | 0.43 | basket | Seats the Pico (two strips) and the codec board (two cut to 16), so either can be swapped out. CPC's minimum is five |
| Hook-up wire, 7/0.2 stranded, 100 m, orange | CB21508 | 1 | 7.85 | basket | A second colour beside the black you have |
| Standoffs and panel hardware | — | — | — | later | Chosen with the enclosure layout (Phase 4) |

## Not designed yet

- The 5 V input for `tib` and the Pico (Phase 4).
- The mic stage (D5): the jack, a preamp or the codec's mic path, and whether to offer phantom power.
- Cooling, if Phase 4's heat soak inside the enclosure calls for it.
- Tools aren't listed here.

## Total

Everything with a part number is in the basket: 41 lines, £117.19 ex VAT (£140.63 with VAT).
