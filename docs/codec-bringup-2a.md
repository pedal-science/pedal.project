# 2a on piv: bringing up the WM8960, stock

A walkthrough of [plan.md](../plan.md) Phase 2a for you to follow at the bench. You do the hands-on
work. Claude does the software on piv and works out what your readings mean. Written 2026-09-27.

**How to use it.** Work through the stages in order and tick the boxes. Each **▶ Tell Claude** marks
where to stop and paste readings, a photo, or a question into the session. At those points Claude
checks the result before you go on, updates the handoff, and runs the next piece of software. If
anything looks, smells or measures wrong, stop, unplug, and ask. Nothing here is urgent.

**What 2a delivers.** The codec board, still stock, running as a sound card on piv with the codec as
clock master. Its mixer state kept as code. Its input and output measured with the SSL 2+ as the
instrument. An hour's soak on it. Those measurements are the numbers 2b's design review is waiting
for.

When vip arrives, the wiring moves across unchanged. It has the same SoC and the same 40-pin header,
and the overlay and mixer state carry over too.

---

## What you need

| Item | Have it? | Used in | Notes |
|---|---|---|---|
| Soldering iron and solder | yes | 2 | |
| Breadboard | yes | 8 | For the jack sockets and the output fixture. The codec board doesn't go in it |
| **Multimeter** with continuity, resistance, DC volts and AC volts | ? | 1, 3, 5, 6, 8 | Essential. A **Hz** range helps in stage 6 but isn't needed |
| **2.54 mm pin header**, 2 × 16 pins | yes | 2 | Both rows on the board have **16** pins. If the strip lying beside the board in `references/wm8960-photos/top.jpeg` is yours, you can start now |
| Female-to-female jumper leads, about 12 | yes | 4 | piv's header to the codec board. Short ones, 10–20 cm |
| Female-to-male jumper leads, about 6 | yes | 8 | From codec pins into the breadboard. Without them, push a short piece of header into the breadboard and use female-to-female leads |
| Two 6.35 mm jack sockets, with short wires soldered on so they sit in the breadboard | yes (the basic open-frame ones) | 8 | Socket A takes the signal from the SSL. Socket B takes the signal back to it |
| **TRS** jack-to-jack cable | yes | 8 | SSL out 4 → socket A. TRS, so the SSL's cold (ring) output isn't shorted to ground |
| **TS** (mono, guitar) cable | yes| 8 | Socket B → SSL input 2. TS on purpose: in the SSL's balanced input it ties the ring to ground, which is the right way to feed it an unbalanced signal |
| 2 × 10 µF capacitor, 2 × 100 Ω, 2 × 1 MΩ | **in the order** | 8b, 9 | The output fixture. Any electrolytic ≥ 10 µF rated ≥ 10 V will do, fitted with **+ towards the codec**. Any resistor of 47–220 Ω for the 100 Ω, and 100 kΩ–1 MΩ for the bleed |
| Headphones | yes | 8c (optional) | A first listen before the parts arrive |
| Nice to have | yes, flux, desoldering braid, side cutters, blu-tack (I have put the header in the breadboard and put the WM8960 on its short pins | | Flux, desoldering braid, side cutters for the header strip, Blu-Tack to hold the header square while you solder, a magnifier (or phone camera) to inspect joints. An oscilloscope isn't needed |

### What can you do before the order arrives?

Nearly all of it. Only the **output side** needs the order, and only the 10 µF capacitors, 100 Ω
and 1 MΩ resistors. Everything else in the order is for 2b and later.

| Stage | Without the order |
|---|---|
| 1 Inspect with the meter | yes |
| 2 Headers | yes, if you have any 2.54 mm pin strip |
| 3–7 Wire, power, I2C, overlay, mixer | yes |
| 8a, 9 Input side: SSL → codec, measure the ADC | yes |
| 8b, 9 Output side: codec → SSL, the DAC, round-trip latency | **needs the capacitors and resistors** (or any you have lying around) |
| 8c A first listen on headphones | yes, optional |
| 10 Hour-long soak | yes. The soak counts xruns and overruns. It doesn't need the output connected |

---

## Rules for the whole session

1. **Unplug piv's power before changing any wiring.** A Pi 5's 5 V header pin stays live after
   `poweroff`. Plug back in only after you've checked the wiring.
2. **piv's GPIO is 3.3 V and not 5 V tolerant.** The only things that touch a 5 V pin are the
   codec's VIN (**pin 2**) and, since 2026-10-05, the Pico's VSYS feed through its 1N5817 — take
   that one from **pin 4**, the other 5 V pin, so pin 2 keeps the codec's lead alone. Pins 1 (3.3 V),
   2 (5 V), 3 (SDA) and 5 (SCL) are neighbours: a second lead in pin 2 sits a lead's width from the
   codec's I²C and its digital supply.
3. **HPL, HPR and OUT3 sit at about 1.65 V DC.** That's the board's capless design. **Never connect
   OUT3 to ground.** It's a driven output, and grounding it shorts it. Never connect HPL or HPR to
   the SSL without the capacitor in the fixture.
4. **SSL 2+: 48 V phantom off** on both inputs, and **INST off** on input 2.
5. **Levels start low.** The codec's line input is full scale at about 1 V rms. Claude starts test
   signals at −40 dBFS and works up from there.

---

## Stage 1: inspect the board with the meter, unpowered (plan 2a.1)

Orientation for this whole document: **component side up, as in `top.jpeg`**. The row with GND,
BCLK, DLRC … is on the left, and LIN1, HPL, OUT3 … is on the right.

### 1.1 Nothing is shorted

- [x] Resistance from **VIN** to **GND**. A reading that starts low and climbs is capacitors
      charging, which is normal. Wait for it to settle.

Result: infinite

- [x] **3V3** to **GND**, the same way.

Result: infinite

- [x] **AVDD** (right-hand row) to **GND**, the same way.

Result: infinite

Anything that stays under about 50 Ω means don't power it up.

### 1.2 SPKVDD jumper (confirms the photo)

- [x] Continuity **SPKVDD** ↔ **VIN**: expect a **steady beep**. It's bridged to VIN.

Result: Steady beep.

- [x] Continuity **SPKVDD** ↔ **3V3**: expect **none**.

Result: None.

### 1.3 Map the input components (LINPUT1 first)

Above the codec chip are three rows of six parts: **top row capacitors, middle row resistors (dark
bodies), bottom row capacitors**. Number the columns **1–6 from the left**. Each input is
`pad → 100 Ω → node → 47 nF to GND`, and `node → 1 µF → codec`. What we want to know is **which
physical parts belong to which input**, because 2b or 2c may swap a 47 nF.

A tip on beeps: a meter beeps briefly while it charges a capacitor. Count only **steady** beeps.

For **LIN1**:
- [x] Continuity from the **LIN1** pad to each end of each resistor in the middle row. One end of
      one resistor beeps steadily. Note its column.
- [x] Resistance across that resistor: expect **about 100 Ω**. Measured in circuit, it may read a
      little different.
- [x] From that resistor's **other** end, find which capacitors it has continuity with: one in the
      top row and one in the bottom row. Note both.
- [x] Of those two capacitors, the one whose far end beeps to **GND** is the **47 nF shunt**. The
      other is the **1 µF coupling** capacitor.

Result: LIN1: Goes with resistor 4. Goes with capacitors 4 and 4. top capacitor's far end beeps to GND.

Result: No resistance found across resistor 4 - I just see 0 on my meter. Continuity test beeps and shows a reading of 100 - but I don't know what that means.


Then, if you have the patience, do **RIN1** next (it's reserved for the mic, D5), and after that the
other four.

Result: RIN1: Goes with resistor 3. Goes with capacitors 3 and 3. top capacitor's far end beeps to GND.


Result: No resistance found across resistor 3, as with 4.

> **▶ Tell Claude:** the 1.1 readings, 1.2's results, and for each input you mapped:
> "resistor column n, shunt top/bottom column m, coupling top/bottom column k". Claude updates the
> handoff's input table from physical positions instead of the unverified R/C numbers.

---

## Stage 2: fit the headers

- [ ] Cut two 16-pin lengths from the strip.
- [ ] Fit them with the **short** ends through the board from the **underside** (the unlabelled,
      jumper side), and solder on the **component side**. The long pins then point down, which is
      what the 20-way socket strips on the stripboard will take later. Female jumpers fit them
      either way.
- [ ] Tack one pin at each end first, check the header is square to the board, then do the rest.
      About 2 seconds per joint. You want shiny cones, not balls.
- [ ] Check neighbouring pins for bridges. There should be **no** continuity between neighbours,
      except where both are GND: on the left row, pins 10–11 and 15–16 (counting from the top).
      Top to bottom, the left row is: GND, BCLK, DLRC, DDAT, ALRC, ADAT, SCL, SDA, 3V3, GND, GND,
      SPKVDD, VIN, EN, GND, GND.
- [ ] Repeat 1.1 to be sure the soldering didn't short anything.

Leave the Qwiic connector unused. piv is the only I2C master on this bus.

> **▶ Tell Claude** (optional): a photo of the joints, if you'd like a second opinion.

---

## Stage 3: find pin 1 on piv's header

On the Pi 500, the 40-pin header is on the back. Numbering is the standard Pi layout: **odd pins
in one row, even pins in the other, pin 1 = 3.3 V, pin 2 = 5 V**. Check which end is pin 1 by
measuring before you trust a diagram. A slip of a meter probe between the 5 V pins and a GPIO can
kill the Pi, so:

- [x] piv powered, nothing connected to the header.
- [x] Push a female jumper onto a corner pin and measure DC volts **at the lead's other end** against
      a GND pin, reached through another lead. **Don't probe the header itself.**
- [x] Find the corner where one row reads **3.3 V** and its neighbour in the other row reads **5 V**.
      That's pins 1 and 2. Pin 4 is also 5 V and pin 6 is GND.

The pins we use:

```
          3V3  (1) (2)  5V        ← VIN
  SDA   GPIO2  (3) (4)  5V
  SCL   GPIO3  (5) (6)  GND       ← GND
               (7) (8)
          GND  (9) (10)
               ...
BCLK   GPIO18 (12)      on the even row
               ...
DLRC   GPIO19 (35) (36)
               (37) (38) GPIO20   ADAT  (data into piv)
          GND (39) (40) GPIO21    DDAT  (data out of piv)
```

Pin 12 is the 6th pin of the even row. Pins 35–40 are the last three pairs at the far end from pin 1.

> **▶ Tell Claude:** "pin 1 is at the … end". Claude has already checked that GPIO18–21 are unused
> on piv and that I2C1 (GPIO2/3, `/dev/i2c-1`) is enabled.

---

## Stage 4: wire it (plan 2a.2)

- [ ] `sudo poweroff` piv (or ask Claude to), wait for it to stop, then **unplug its power**.
      While it's off, `namchaind` isn't playing.

| Codec board pin (left row) | piv header pin | What |
|---|---|---|
| GND (row pin 1) | **6** GND | Main ground |
| VIN | **2** 5 V | Feeds the onboard LDO → AVDD, and SPKVDD (the speaker amp stays off in software) |
| 3V3 | **1** 3.3 V | DCVDD, DBVDD and the 24 MHz oscillator |
| SDA | **3** GPIO2 | I2C1 |
| SCL | **5** GPIO3 | I2C1 |
| BCLK | **12** GPIO18 | Bit clock, **from** the codec |
| DLRC (DACLRC) | **35** GPIO19 | Frame clock, **from** the codec |
| ADAT (ADCDAT) | **38** GPIO20 | Recorded audio into piv |
| DDAT (DACDAT) | **40** GPIO21 | Playback audio out of piv |
| GND (row pin 10 or 11) | **39** GND | A second ground, beside the I2S leads |
| **ALRC (ADCLRC)** | **not connected** | See below |
| EN, SPKVDD, the other GNDs | not connected | EN is pulled up on the board |
| Right-hand row | nothing yet | Stage 8 |

**Why ADCLRC is left off.** The Pi's I2S has one frame clock pin for both directions (GPIO19). The
WM8960 has two, ADCLRC and DACLRC. The overlay in stage 6 tells the codec to run its ADC from
DACLRC and turns the ADCLRC pin into a GPIO (`wlf,gpio-cfg`, the ALRCGPIO bit), and to keep that one
clock running for recording as well (`wlf,shared-lrclk`). Wiring ADCLRC as well would put two
outputs on one pin. This settles the handoff's open "separate RX/TX frame clocks" question.

Lead practice:
- [ ] Keep the leads short, and run the pin 39 ground lead alongside BCLK, the fastest signal
      (3 MHz). Twisting them loosely together helps.
- [ ] Use colours consistently: red 5 V, orange 3.3 V, black GND. It helps the photo check.
- [ ] Check every row of the table once more, pin by pin.

> **▶ Tell Claude:** a photo of both ends, with the pin 1 end of the header visible. **Don't power up
> until Claude has looked.**

---

## Stage 5: power up, check the rails and I2C

- [ ] Plug piv in. The codec board's **PWR LED** should light straight away. If it doesn't, or piv
      doesn't boot, unplug and go to "If something goes wrong".
- [ ] Measure DC volts against GND at the codec board's pins:
  - **VIN**: expect about 5.0 V (4.8–5.2)
  - **3V3**: expect about 3.3 V
  - **AVDD** (right-hand row): expect about 3.3 V from the onboard LDO

> **▶ Tell Claude:** the three voltages. Claude then:
> - installs `i2c-tools` on piv (it'll ask first)
> - runs `i2cdetect -y 1` and looks for **`1a`**.
>
> The WM8960 is **write-only** on I2C, so registers can't be read back: the driver keeps a cache of
> what it wrote. The board's 2.2 kΩ pull-ups sit in parallel with the Pi's own 1.8 kΩ, about 1 kΩ in
> all. That's fine for bring-up, and a D8 candidate for later (the I2C jumper).

---

## Stage 6: the device-tree overlay (plan 2a.3). Mostly Claude

The Ubuntu kernel on piv already has the WM8960 driver, simple-audio-card and a
`wm8960-soundcard` overlay. **The stock overlay is wrong for this board.** It makes the Pi the clock
master (`i2s_clk_producer`) and assumes a 12.288 MHz MCLK. Here the codec must be the master, with
its own 24 MHz oscillator.

Claude writes a small overlay instead:
- the Pi's I2S as clock **consumer** (`i2s_clk_consumer`, RP1 `i2s@a4000`)
- a **24 MHz** fixed clock as the codec's MCLK, so its driver sets the PLL for 48 kHz
- `bitclock-master` and `frame-master` on the **codec**
- `wlf,shared-lrclk` and `wlf,gpio-cfg`, for the single frame clock described in stage 4
- only the widgets in use: a line in on LINPUT1 and headphones on HP_L/HP_R. No speaker, so ALSA's
  power management never switches the class-D amplifier on.

**As done (2026-09-27):** the overlay is `devices/piv/rootfs/etc/pedal/codec/wm8960-codec-master.dts`.
It is **not** in `config.txt`. `pedal-codec.service` compiles it and loads it with `dtoverlay` at
boot, before `namchaind`, then applies the mixer state. The reasons:
- it lives in the device tree that `devices/piv/apply` installs and `pedal-device revert` undoes
- kernel updates replace `/boot/firmware/current/overlays`, and they can't remove it
- it can't stop piv booting.

The `wlf,gpio-cfg` property was left out: ADCLRC isn't wired, so what the codec drives on it doesn't
matter. The WirePlumber rule in stage 7 is also needed.

**Your part: the clock check.** While Claude runs a recording:
- [ ] DC volts on **BCLK** and on **DLRC**, each against GND. **About 1.6 V** means it's toggling (a
      50% square wave averages to half the rail). **0 V or 3.3 V** means it's stuck.
- [ ] If your meter has a Hz range, DLRC should read **48.00 kHz** and BCLK **3.072 MHz** (or 1.536
      or 2.304 MHz, depending on the word length the driver picks).

> **▶ Tell Claude:** the readings. Done when the card shows up in `/proc/asound/cards` and a short
> recording with nothing connected gives low, plausible noise, not all zeros and not full-scale
> garbage.

---

## Stage 7: mixer state as code (plan 2a.4). Claude

Kept in `devices/piv/rootfs/etc/pedal/codec/wm8960.mixer` and applied by `pedal-codec` at boot:
- ALC **off**, 3D **off**, speaker outputs **off**, OUT3 **off**
- LINPUT1 → input PGA at 0 dB → boost at 0 dB → ADC. The boost stages are noisier than the PGA
- DAC → output mixer → HP_L and HP_R, at a moderate headphone volume.

Nothing for you to do.

**As found:** the desktop's WirePlumber opened the new card after boot and overwrote the mixer, with
Capture at +30 dB and Headphone muted. `devices/piv/rootfs/etc/wireplumber/wireplumber.conf.d/50-pedal-ignore-codec.conf`
disables the card for WirePlumber. It matches by `device.name`, because `alsa.card_name` didn't
match. `pedal-codec` also waits for udev and runs `alsactl store`, so udev's own restore writes the
same values.

---

## Stage 8: connect the SSL 2+

Leave the existing **out 3 → in 1** loopback cable where it is. Stage 9 uses it to measure the SSL's
own limits, so the codec's numbers can be read against them.

- [ ] SSL input 2: **48 V off, INST off**, gain **fully anticlockwise**. Note where it is and don't
      touch it again until stage 9 is done.

`namchaind` holds the SSL 2+ exclusively, so Claude stops it while measuring and starts it again
afterwards.

### 8a. Input side (can do now)

- [ ] **Socket A** on the breadboard: **tip → codec LIN1** (a female-to-male lead to the right-hand
      row), **sleeve → codec GND**. Leave the ring unconnected. A mono socket does that for you.
- [ ] If you are feeding LIN1 from the case's screened cable rather than a jumper lead, its stranded
      core needs a pin soldered on first: see "A stranded core into a breadboard" in
      [build-board1-breadboard.md](build-board1-breadboard.md).
- [ ] Every ground — the sockets' sleeves, the outputs' rings, the codec's GND — gets its own wire
      into the breadboard's ground rail, which stands in for the star tag at this stage: see
      "The star point" in [build-board1-breadboard.md](build-board1-breadboard.md).
- [ ] **The input is line level here, not Hi-Z.** LIN1 is the codec's line input, so a guitar plugged
      straight into the jack sees the codec's input impedance rather than the 1 MΩ the finished pedal
      presents. That is fine for measurement work, which is all driven from the SSL's output. Playing
      through it meanwhile, anything **buffered** in front of the pedal stands in — a buffered-bypass
      pedal, not a true-bypass one, which just wires the guitar through to LIN1. A series resistor is
      not a fix: it raises what the guitar sees but divides the signal into the codec and rolls the
      top off against the cable. The real front end is board 1's follower
      ([build-board1.md](build-board1.md), parts in [bom.md](bom.md)); why it is a follower at all,
      and why the Inst/Line switch pads level instead of impedance, is in
      [hardware-handoff.md](hardware-handoff.md).
- [ ] Don't plug the SSL in yet. First calibrate the SSL's output: connect **SSL out 4 → TRS cable →
      socket A** with **LIN1 disconnected**. Claude plays a 200 Hz tone at a known level. You read
      **AC volts** between socket A's tip and sleeve.

  > **▶ Tell Claude:** the AC reading. That gives volts per dBFS for the SSL's output, so every
  > later number can be given in volts at the codec's pin.

- [ ] Reconnect LIN1. Claude brings the level up in steps and records at each one.

### 8b. Output side (needs the parts)

Build this for **HPL**. HPR is the same, if you want to check both.

```
HPL ──┤+ 10µF ├──[100 Ω]──┬── socket B tip
                          │
                        [1 MΩ]
                          │
codec GND ────────────────┴── socket B sleeve
```

- [ ] With piv running, measure DC volts at **HPL**: expect about **1.65 V**. At **socket B's tip**:
      expect about **0 V** once the capacitor has charged (a few seconds).
- [ ] Only then connect **socket B → TS cable → SSL input 2**.

> **▶ Tell Claude:** both DC readings before you plug in.

### 8c. Optional: a first listen on headphones (no parts needed)

The board is designed for capless headphones, using OUT3 as their return.

- [ ] A separate TRS socket: **tip → HPL, ring → HPR, sleeve → OUT3 only**. Nothing else may touch
      that sleeve, and above all not GND.
- [ ] Claude temporarily enables OUT3 as the headphone return and plays something quiet. Put the
      headphones on only after it has started.
- [ ] Afterwards, Claude puts OUT3 back off (stage 7's state) and you remove the socket.

---

## Stage 9: measurements (plan 2a.5). Claude runs, you watch

Measured at 48 kHz. Claude writes the tool, and the results go in this repo and the handoff.

| Measurement | Path | Needs |
|---|---|---|
| **Instrument baseline**: noise, THD, frequency response | SSL out 3 → in 1 (the loopback) | now |
| ADC frequency response, 20 Hz–20 kHz | SSL out 4 → LIN1 → codec | now |
| ADC THD at −1 dBFS (of the codec) | same | now |
| **ADC noise floor, A-weighted, input shorted** | LIN1 pad to GND | now. You move one lead: LIN1 off socket A, and a jumper from LIN1 to GND |
| ADC noise with the SSL connected but silent | SSL out 4 → LIN1 | now. The realistic case |
| DAC frequency response, THD, noise | codec HPL → fixture → SSL in 2 | 8b |
| **Round-trip latency** (`namchain-latency`) | codec HPL → fixture → socket B → TS cable → socket A → LIN1 | 8b. The codec loops back to itself |

The first readings for 2b: the codec's input full scale in volts at the pin, its noise floor in µV
A-weighted, and THD. The 2b early findings predict about **1 V rms** and **about 20 µV**.

---

## Stage 10: an hour-long soak on the codec (plan 2a.6). Claude

`namchaind` pointed at the WM8960 card (2 in, 2 out) with the usual A2-Full + cab rig, for an hour,
with the Phase 1 gates: 0 driver xruns, 0 deadline overruns, 0 guard trips. It can run before the
output parts arrive. Afterwards, piv goes back to the SSL 2+ unless you decide otherwise.

---

## If something goes wrong

| Symptom | Likely cause |
|---|---|
| PWR LED off | VIN, 3V3 or GND lead on the wrong pin, or pin 1 identified wrongly. **Unplug first** |
| piv won't boot with the board connected | A short on 5 V or 3.3 V. Unplug, and repeat 1.1 with the leads connected but piv unplugged |
| `i2cdetect` doesn't show `1a` | SDA and SCL swapped, no 3.3 V at the board, or a lead on pin 3/5 not seated |
| `pedal-codec` fails: `card wm8960 did not appear`, and `dmesg` says `wm8960 1-001a: Failed to issue reset` **with error −121** (`EREMOTEIO`, a NACK) | The bus works and **nobody answers at `0x1a`**: the board is unpowered in its digital domain (**3V3 on pin 1** — the I2C interface is in the DBVDD domain), out of its socket strips, or its SDA/SCL leads are out. A **−110** (`ETIMEDOUT`, the controller's 1.024 s timeout after every address) is the other fault: a **held** line, i.e. wiring. The two are easy to confuse and are not the same thing (2026-10-05) |
| The card appears, but recording hangs or gives an I/O error | No clocks. The codec isn't master or its PLL isn't set up. Stage 6's meter check tells which |
| Clocks present but the recording is all zeros | The ADAT lead, or the ADC not following DACLRC (the `wlf,gpio-cfg` setting) |
| One channel right and the other wrong, or channels swapped | DLRC and ALRC mixed up at the board |
| Hum or buzz | The ground lead, or the TRS/TS choice on the cables. Tell Claude what you changed last |
| A crackle every few seconds | Leads too long, or BCLK without the ground beside it |

## Results

Filled in as we go.

| What | Value | Date |
|---|---|---|
| VIN / 3V3 / AVDD resistance to GND | all open circuit (no shorts) | 2026-09-27 |
| SPKVDD → VIN confirmed | yes; SPKVDD ↔ 3V3 open | 2026-09-27 |
| LINPUT1 parts (resistor / shunt / coupling position) | column 4: resistor 4 (~100 Ω), shunt top 4, coupling bottom 4 | 2026-09-27 |
| RINPUT1 parts | column 3: resistor 3 (~100 Ω), shunt top 3, coupling bottom 3 | 2026-09-27 |
| VIN / 3V3 / AVDD with power | 5.0 / 3.28 / 3.27 V | 2026-09-27 |
| I2C address seen | 0x1a only, on i2c-1 | 2026-09-27 |
| BCLK / DLRC | 1.83 / 1.64 V DC (toggling); 48 kHz stereo capture confirmed by data rate | 2026-09-27 |
| SSL out 4: V rms at a stated dBFS | 1.5 V at −1 dBFS (±0.05, meter 200 V range), so 0 dBFS ≈ 1.7 V rms; 200 Hz | 2026-09-27 |
| Codec input full scale (V rms at LIN1) | **1.0 V rms** (datasheet; loop and noise consistent). The meter's 0.81 V was its 200 V range at low volts. Gains and dB figures are unaffected | 2026-09-27 |
| ADC noise, input shorted (µV, A-weighted; dBFS) | **−93.5 dBFS(A), ≈21 µV A-weighted** at 1.0 V FS; −90.6 dBFS (≈30 µV) unweighted 20 Hz–20 kHz; no hum. With the SSL connected: −77 dBFS, a 90 Hz comb from the SSL/piv ground loop | 2026-09-27 |
| ADC THD at −1 dBFS | THD −72 dB, THD+N −68 dB at −0.7 dBFS; THD −76 dB at −8.7 dBFS (1 kHz, headphone B). The first run's −53 dB was a bad joint plus out 4's source impedance | 2026-09-27 |
| ADC frequency response (−3 dB points) | from headphone B at −15 dBFS: flat to 5 kHz (−0.1 dB), −1.0 dB at 15 kHz, −1.7 dB at 20 kHz; SSL loop −0.06 dB at 20 kHz. Out 4 (≈2 kΩ source) gave −3 dB at ≈1.5 kHz | 2026-09-27 |
| DAC full scale (V rms at the fixture) | **1.0 V rms** (datasheet): codec out → fixture → LIN1 is −0.4 dB, so out ≈ in. The meter's 0.45 V was wrong. Flat 20 Hz–20 kHz within 0.1 dB | 2026-09-27 |
| DAC noise and THD | THD −80 to −82 dB from 0 to −3 dBFS (1 kHz). Noise ≤ −76.5 dBFS(A) (≤ 150 µV at 1.0 V FS): an upper bound, set by the SSL/piv ground loop (90 Hz comb, 50 Hz, a 16 kHz line), not the DAC | 2026-09-27 |
| Codec loop THD (HPL → fixture → LIN1, −3 dBFS) | −78 dB at 100 Hz, −65 at 1 kHz, −58 at 4 kHz: rises 6 dB/octave, the 47 nF ceramic shunt (plan 2b) | 2026-09-27 |
| Round-trip latency | converter path (DAC → HPL → LIN1 → ADC, buffering removed) **55–57 frames, 1.15–1.18 ms**; raw at q64 ×6 periods 185 fr (3.85 ms), ×4 periods 183 fr (3.81 ms). namchain-latency, loop via the fixture into socket A | 2026-09-27 |
| Hour-long soak | **clean**: 21:01–22:01, namchaind on hw:wm8960 (2 in/2 out), q64 × 6 periods, GVT52 + ORNG 412 cab; 2 702 221 blocks (750/s, none missing), 0 xruns, 0 guard trips, 0 render errors, 0 device lost; CPU 35–39 °C. LIN1 shorted, SSL unplugged | 2026-09-27 |
