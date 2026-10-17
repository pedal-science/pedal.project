# Balanced outputs

Written 2026-10-14, at the owner's request. The question: what would it take to add two
balanced outputs beside OUT L and OUT R, so a player can use an amp and a PA at the same time?

**Decided the same day (D15 in `plan.md`):** male XLR plus impedance-balanced 1/4"; step 1 now;
the XLRs silent in panic bypass; a −20 dB pad. Step 1 is in the output-board layouts
([module-boards.md](module-boards.md)) and the module map. **Still open:** where the case bonds to
0 V, which is measured first ([The case bond](#the-case-bond-balanced-outputs-force-the-decision)).
Step 2's driver is drawn, simulated and laid out (2026-10-17): the schematic is
`schematic/balanced-output/` with its wiring table `schematic/balanced-output.py`, the simulation is
[bench-results/2026-10-17-balanced-output-sim](../bench-results/2026-10-17-balanced-output-sim/README.md),
and the stripboard is XLR L and XLR R in [module-boards.md](module-boards.md). Simulating it changed
two things, both below: a 1 kΩ in front of the mute, and a 10 Ω between each output capacitor and
its pin.

## In short

- **Use male XLR sockets, not the NCJ6FI-S.** The NCJ6FI-S is a *female* XLR with a TRS jack in its
  centre. Female is the input gender, and a standard XLR cable won't connect a female output to a
  mixer. A combo socket is the right part for the chalked **Mic IN**.
- **The 1/4" jacks can be properly balanced on TRS for three parts each, all in hand** (step 1).
  A TS cable then gets an unbalanced output and a TRS cable gets a balanced one. Nothing has to be
  detected or switched, and neither cable can be wrong, so the confusion you were worried about
  can't happen.
- **The XLRs need a small driver board** (step 2): two op-amp halves per channel from the 9 V rail.
  It also has to handle four things the question didn't ask about: **phantom power**, **the boot
  thump**, **mic level**, and **where pin 1 goes**.
- **Fit a ground lift on each XLR.** Lifts aren't only for transformers. Using the amp and the PA
  at the same time is the textbook ground loop, and you'd hear it in the *amp*.
- **Balanced outputs force the case-bond decision** that `hardware-handoff.md` left for Phase 4.
  This page argues for bonding at the root, the Pi end, rather than on the codec carrier.
- **Drill the XLR holes when the rear wall is drilled**, even if the board comes later.

## Your assumptions, challenged

### "NCJ6FI-S, so each balanced output takes XLR or TRS": not for an output

The NCJ6FI-S is a Combo I part: a 3-pole **female** XLR with a 1/4" stereo jack, solder cups and no
switching contacts. Two problems on an output:

1. **Gender.** An XLR cable has a female end and a male end. The female end goes onto a source's
   male socket, and the male end goes into a destination's female socket. So a mixer's input is
   female, and an output has to be male. A female output needs a male-to-male cable or a gender
   changer, which a venue won't have. This is why combo sockets are only made female: they are
   inputs.
2. **It looks like an input**, beside the Mic IN on the chalk plan. Someone will plug a mic into it.

The flexibility you wanted is kept, just on two sockets: XLR on the male socket, and balanced TRS
on the 1/4" jack for the same channel (step 1). **Use a combo socket for Mic IN**, where it takes a
mic on XLR and a line source on TRS. That is the job it was designed for. The NCJ9FI-S, the
same Combo I socket with a switched jack, is the better choice there (see bom.md, "Not designed
yet").

### "Separate sockets for balanced and unbalanced": yes, and the 1/4" jacks become both

Keep the 1/4" jacks and add the XLRs. Step 1 makes each 1/4" jack correct for both kinds of cable,
so there is no setting to get wrong and nothing to auto-detect. Your worry about a TRS cable that
gets an unexpected balanced output goes away, because the result is fine either way: into a
balanced input it's balanced, and into an unbalanced input the input's sleeve grounds the ring and
it behaves exactly like TS.

### "Both at once": yes, but it's two signals on four sockets, not four outputs

The WM8960 has two DAC channels. XLR L and OUT L carry the same signal at linked levels, and the
pad is the only difference between them. If the amp and the PA need different signals (amp
without a cab, PA with one), use L and R as two mono outputs: route the rig's no-cab path to L
and the cab path to R, then plug OUT L into the amp and XLR R into the PA. More than two
independent signals would need a different codec, which is out of scope here.

## What "properly balanced" means

**Balance comes from impedances, not from the signal.** A balanced receiver subtracts cold from
hot. Hum and RF picked up along the cable, and the voltage between the two boxes' grounds, arrive
on both conductors as the same voltage (common mode), and the subtraction cancels them. That only
works if both conductors have **the same impedance to ground** at each end. If one leg's impedance
differs, the same induced current makes a different voltage on each leg, and that difference is
now part of the signal.

The signal itself doesn't have to be symmetric. Put all the signal on hot and return cold to ground
through an identical impedance, and the output is fully balanced. This is called
*impedance-balanced*. That is how Bill Whitlock's AES papers on balanced interfaces define balance,
and why IEC 60268-3 tests an input's common-mode rejection with a deliberately unbalanced source
instead of a perfect one.

Most of the implementations you've heard are "not properly balanced" fail in one of these ways:

1. **The pin 1 problem.** The shield (pin 1) is wired to the circuit's ground on the board instead
   of to the case at the connector. The shield's current then flows through the audio ground. This
   is Neil Muncy's 1995 JAES paper, and AES48 says how to avoid it. It is the most common fault,
   and this pedal is exposed to it because its case floats.
2. **Mismatched legs.** Examples: a build-out resistor on hot only; cold tied straight to ground;
   or ±20% electrolytic capacitors in each leg, sized so that their reactance dominates at 50 Hz.
3. **Treating symmetry as the goal** and leaving the impedances to chance.
4. **Outputs that don't survive** phantom power or a TS plug.

## Step 1: the 1/4" jacks, impedance-balanced on TRS

**Today's plan** (bom.md, the NMJ6HF-S row) wires the ring to ground. That already helps, because
the receiver then reads hot against the pedal's own ground, carried on the ring. But the legs don't
match:

- hot is 100 Ω plus 10 µF, which is 333 Ω at 50 Hz;
- cold is 0 Ω.

Against a typical line input, with about 20 kΩ of common-mode impedance, that rejects about
**35 dB** at 50 Hz.

**Proposal: give the ring the same network, mirrored.** The ring connects through 100 Ω and a
10 µF bipolar capacitor to ground, with 1 MΩ to ground on the ring side. That is the tip's network
with ground in place of HP_L. Any remaining mismatch then comes only from tolerances:

| Capacitors | Rejection at 50 Hz |
|---|---|
| ±20%, as bought | about 50 dB |
| Two paired within 5% on a meter | about 60 dB |

Pair the capacitors from the five in hand: the build needs four (a tip and a ring per output).

How each cable behaves:

| Cable | Result |
|---|---|
| TS | The plug's sleeve shorts the ring contact to the sleeve, so the network goes from ground to ground and does nothing. Unbalanced output, as today. |
| TRS into a balanced input | Impedance-balanced. |
| TRS into an unbalanced input | Behaves as TS. |
| TRS headphones | Right ear silent, as today. |

- **Level:** unchanged. All the signal is on hot, and the codec's full scale is 1.0 V rms
  (+2.2 dBu).
- **In bypass:** OUT L's tip is the guitar itself, so the legs no longer match and rejection gets
  worse. It still works, which is enough for a fallback.
- **Cost:** three parts per output board, and a third wire in the jack cable. **Done 2026-10-14:**
  the output boards in [module-boards.md](module-boards.md) carry the ring network, the jack
  cables (A7, A8, A9) are four-way, the bypass relay passes the ring straight through, and
  [bom.md](bom.md) no longer says "ring to ground". The prototype case's jacks
  (`schematic/case-wiring.py`) are still wired ring-to-sleeve, as built, until they are rewired.

## Step 2: the XLR outputs

### Connector

Use a **male, metal, D-size** socket: the Neutrik NC3MD-LX. It needs a 24 mm round cutout, has a
metal housing with a ground contact to the panel, and has an option to tie pin 1 to the chassis.
Check the flange size and screw spacing on Neutrik's own drawing before marking the wall.

Unlike the plastic 1/4" jacks, the XLR is *meant* to touch the case:

- Its shell bonds the plug's shell to the case, for RF.
- Pin 1 reaches the case through the lift switch, at a lug on one of the connector's screws.
  Leave the connector's own pin-1-to-shell option unfitted, or the lift switch does nothing.
- The 1456RH3 is painted, so clear the paint under the flange and under the lug.

**A metal XLR does not decide the grounding.** It joins the *plug's shell* to the case, and
nothing else. Pin 1 is a separate solder cup, and the pedal's 0 V meets the case only through
the case bond, which is one wire. So every grounding choice stays a wire or a switch after the
holes are drilled:

| Choice | How it stays open |
|---|---|
| Pin 1 on the case, or not | The lift toggle, on the panel. Each measurement can be taken both ways in a few seconds |
| The case bonded to 0 V, or floating | A wire with a ring lug at the case end, fitted or not |
| Where it bonds: the root or the codec carrier | Where that wire's other end lands |

The one thing the metal shell commits to: a cable that ties its plug shell to its shield (most
don't) reaches the case directly, so with the case bonded, the lift can't break that cable's
shield. While the case floats, that changes nothing.

**Why not the NC3MAH, to defer more?** It is plastic, so the shell question goes away, but there
is no decision left to defer: everything above is already a wire. The NC3MAH is a horizontal
PCB-mount part, so it needs a board fixed square behind the wall, where the modules here are
panel parts on cables. A plastic socket on a stage pedal is also the part that breaks when a cable
is yanked. The NC3MD-LX it is.

### The driver: one channel, from the 9 V rail

The values are provisional, in the same sense as bom.md's input stage. References are the
schematic's and the stripboard's (one numbering across the pedal).

```
input   HP -- C16 10 µF bp -- C_IN -- R28 9.1 kΩ -- TAP -- R29 1 kΩ -- VREF   (the pad divider, always fitted)
pad     an on-on toggle, SW3: its common (PADCOM) to C_IN on Line, to TAP on Mic
        PADCOM -- R30 1 kΩ -- X;   X -- R31 100 kΩ -- VREF;   X -- A+
mute    K2 (TQ2-5V), both poles in parallel: COM to X, NC to VREF. De-energised = muted.
hot     A is a unity follower.
        A out -- R34 100 Ω -- H -- C17 47 µF 63 V bp -- HC -- R41 10 Ω -- pin 2;  pin 2 -- R36 100 kΩ -- GND
cold    B is a unity inverter: A out -- R32 10 kΩ 0.1% -- B-;  B- -- R33 10 kΩ 0.1% -- B out;  B+ = VREF
        B out -- R35 100 Ω -- CN -- C18 47 µF 63 V bp -- CC -- R42 10 Ω -- pin 3;  pin 3 -- R37 100 kΩ -- GND
clamps  H and CN each: a 1N5817 to the filtered 9 V and a 1N5817 from GND (D8-D11)
pin 1   lift toggle, 10 nF across it, to a lug on the case at the connector. Never the board's ground.
VREF    R38/R39 47 kΩ / 47 kΩ from the filtered 9 V, C19 100 µF to GND: 4.5 V, rising over about 2.4 s.
supply  +9 V -- R40 100 Ω -- filtered 9 V, C20 100 µF and C21 100 nF to GND (as on the input board)
pad     −20 dB: 1 kΩ / (9.1 kΩ + 1 kΩ). Input high-pass 1.9 Hz (simulated).
```

Why it is built this way:

- **Symmetric drive.** Hot follows the input and cold is its inverse, so codec full scale gives
  2.0 V rms between pins 2 and 3 (+8.2 dBu). That is 6 dB more than step 1. The second op-amp half
  is needed anyway to give cold a matching impedance, so the symmetry costs nothing.
- **Balance comes from matched legs:** the same 100 Ω (1%), capacitors paired to 5%, and the same
  op-amp. The 0.1% inverter resistors set only the symmetry, which matters much less. With matched
  legs, the receiver's own rejection becomes the limit, not the pedal.
- **An op-amp, not a passive network on HP_L.** The codec is a retired breakout with no spare. An
  XLR goes to stage boxes, with phantom power, long cables, static and miswired adapters. A socketed
  op-amp is the part that should take that abuse. The op-amp also makes room for the pad, the mute
  and the 6 dB.
- **Why not a THAT1646 or DRV134?** These are cross-coupled drivers that behave like a transformer:
  the level stays the same whether cold is used or grounded. They are built for split supplies, and
  the analogue side has one 9 V rail. Running one from a single supply with a mid-rail ground is
  possible, but it is off the datasheets' main path. Two op-amp halves are simpler, and every part
  of their behaviour is known. Revisit if a ± rail ever appears.
- **The op-amp: OPA2197.** It is already on the BOM, rail-to-rail, and drives a long cable through
  100 Ω. One dual per channel, on a SOIC adapter in a socket, as on the input board; about 2 mA each
  from the 9 V.
- **The input taps HP_L at the carrier,** with its own 10 µF. The 1/4" output boards don't change.
- **R30, 1 kΩ in front of the mute.** The first version shorted the pad's output straight to VREF,
  which through C16 is a short across the codec's headphone amplifier at audio frequencies, the
  same amplifier that drives OUT L and OUT R. With R30 the mute is a 1 kΩ load, and it still takes
  the output down 86 dB (simulated).
- **The pad is one on-on toggle,** three wires: the divider is always fitted, and the toggle picks
  C_IN (Line) or its tap (Mic). The first version needed a two-pole toggle and four wires.

### Phantom power

A stage-box channel may have +48 V phantom switched on, on pins 2 and 3 through 6.8 kΩ each. The
output has to survive phantom left on, phantom being switched, and a cable hot-plugged into it:

- **The capacitors are 63 V and bipolar.** The DC across them reverses: about 44 V towards the
  connector with phantom on, and 4.5 V the other way with it off. Phantom can be as high as 52 V,
  hence 63 V.
- **The bleeds** (100 kΩ per pin, on the connector side) hold the pins at 0 V without phantom. With
  phantom on, each draws about 0.45 mA, well inside phantom's budget.
- **The clamps handle the dangerous case:** the pin shorting while a capacitor is charged to 45 V.
  That swings the driver side of the capacitor about 45 V negative, with the capacitor's whole
  charge behind it.
  - The Schottky diodes take that pulse. 1N5817s are already on the BOM, rated for a 25 A surge.
  - **R41 and R42, 10 Ω between each capacitor and its pin, limit it.** Without them the simulation
    put **69 A** through the clamp and asked 85 mA of the op-amp, past its ±65 mA limit; with them,
    3.7 A and 51 mA, and the driver side of the capacitor stays between −0.6 V and +5.2 V. They are
    matched (1 %) like the 100 Ω, so the balance doesn't change.
  - The 100 Ω keeps what is left out of the op-amp.
- **The 1/4" jacks' 10 µF 50 V capacitors are fine.** TRS line inputs don't carry phantom.

The SSL 2+ has 48 V phantom on its combo inputs, which makes it the test rig.

### Mute, the bypass relay, and thumps

A PA turns a thump into a bang. The thumps come from two places:

1. **The codec's VMID rising at power-up** (0 to 1.65 V), through the coupling capacitor. The
   bypass relay protects OUT L, because it is de-energised during boot, so the guitar goes
   straight to the jack. Today nothing protects OUT R.
2. **The 9 V rail coming up** and taking the drivers' outputs from 0 to 4.5 V. Starting VREF slowly
   (about 2.4 s) turns that step into a slow ramp, far below audio.

**A TQ2-5V on each driver board**, both poles muting in parallel:

- **Wiring:** its coil goes in parallel with the bypass relay's, driven by the same BC337 (cables
  C7 and C8, C1's pinout). Three coils at about 28 mA each is about 84 mA: within the BC337's
  rating, but check that its base drive still saturates it; the 1 kΩ base resistor may want to be
  470 Ω.
- **De-energised,** it shorts each driver's input to VREF. The input already sits at VREF through
  100 kΩ, so releasing the mute makes no step.
- **No new GPIO is needed,** and the XLRs follow the pedal: silent while it boots, in panic bypass,
  and in every failure the relay rule covers.

That means the PA gets silence, not the dry guitar, while the amp gets the dry guitar in bypass.
**Decided 2026-10-14:** silent. A raw guitar into a channel set up for a processed one is no
better than silence.

### Mic or line: the pad

At codec full scale the XLR delivers +8.2 dBu. A line input handles that easily, but many mic
preamps at minimum gain run out of headroom around that level, and stage boxes are mic inputs.

A **−20 dB pad** per output takes the maximum down to −11.8 dBu. −30 dB would take it to
−21.8 dBu, closer to a real microphone; the only difference is how far the engineer turns up the
channel's gain. −20 dB is chosen (2026-10-14) because it is easy to change: the pad is one 1 kΩ
resistor, and 330 Ω in its place gives about −29 dB, with nothing else on the board moving.

- **It goes at the driver's input,** so the output impedances, and with them the balance, never
  change.
- **It costs no measurable noise.** The op-amp's own noise is far below the codec's, so attenuating
  before the op-amp is harmless.
- **It can't be done in software:** the codec's output level is shared with the 1/4" jack on the
  same side.

### Ground lift

Lifts aren't only for transformer outputs. With active outputs, a lift is still the standard
remedy, and this pedal needs one for exactly the setup you want: an amp on OUT L and a PA on an XLR.

**The loop:**

1. The amp's mains earth reaches the amp's input sleeve.
2. That sleeve is OUT L's sleeve, which is the pedal's ground.
3. The pedal's ground reaches the case through the case bond.
4. The case is XLR pin 1, which reaches the mixer's mains earth.
5. The building's wiring takes it back to the amp.

**Where you hear it:** the XLR shrugs this off, because to the balanced input the loop is common
mode. The 1/4" output to the amp doesn't. There, the loop current flows in the very conductor the
amp uses as its reference. **So the lift is on the XLR, but you'd hear the hum in the amp.**

**What lifting does:** it breaks the loop. The signal still arrives, because the receiver reads hot
minus cold. The cable still shields, because its shield is still grounded at the mixer's end.

**How to fit it:**

- One small labelled toggle per XLR, since the two may go to different places.
- 10 nF across each switch keeps the shield grounded at RF.
- The lift doesn't help if a cable ties the plug's shell to its shield, because the pedal's shell
  touches the case. Most cables don't.

**Don't lift** when the XLR is the pedal's only connection to anything grounded, such as an
in-ear rig into a mixer. In that case pin 1 is the path that carries the supply's leakage current
away (next section).

### The case bond: balanced outputs force the decision

**Today:**

- The case is deliberately outside the ground scheme: plastic jacks and nylon standoffs.
- There is one optional bond, the jumper on the codec carrier.
- Whether to fit it is left for Phase 4 to measure.

**What a metal XLR changes:** with pin 1 on the case, the case becomes the mixer's ground. It then
needs one bond to the pedal's 0 V. Without it, the pedal floats against the mixer: the XLR still
works within the receiver's common-mode range, but the shield protects nothing, and the supply's
leakage current has no defined path.

**Where: I'd move the bond from the codec carrier to the root,** the Pi end where the USB-C supply's
0 V enters (the core breakout). The reason is the 2026-10-13 measurement: the host supply's 50 Hz
leakage current was worth **28 dB** of hum at the input
([bench-results/2026-10-13-input-hum-and-the-host-supply.md](../bench-results/2026-10-13-input-hum-and-the-host-supply.md)).
That current enters at the supply's 0 V and leaves through whatever grounded box is joined to the
pedal. With a mixer on the XLR:

- **Bond at the root:** the current flows from the supply's 0 V, through the Pi, the case and
  pin 1, to the mixer. It never touches the codec or the audio star.
- **Bond on the carrier:** the same current crosses from the codec's digital ground to its analogue
  ground inside the WM8960, the one place module-boards.md keeps them apart, before it reaches the
  case.

**This is an argument, not a measurement.** The test: `scripts/codec-input-noise.py` with a
grounded receiver on the XLR, comparing the bond at the root with the bond on the carrier, each
with the lift in and out. It may show that a mixer on the XLR *reduces* the input's hum, which
would be worth knowing.

### The panel

Each XLR output adds three parts to the rear wall: the XLR, the pad toggle and the lift toggle.

- **Fit:** the rear wall is 81.4 mm tall, and the vent band takes about 28 mm (Hammond's drawing,
  `imaginings/big-enclosure/enclosure/2720683.pdf`). A D-size flange should fit below the band, but
  check it against the drawing before marking.
- **Position:** put the XLRs beside OUT L and OUT R, so the pairs read as one channel each.
- **Drill now:** the holes are what's expensive to add later (the same reason the handoff fits the
  expression jack early).

### Parts for step 2, both channels

- **Connectors:**
  - 2 × NC3MD-LX
  - a 2-pair shielded cable from the board to the XLRs. Hot and cold are the twisted pair, and the
    shield goes to the case at the XLR end only.
- **Driver:**
  - 2 × OPA2197 on SOIC adapters, 2 × 8-pin sockets
  - 4 × 100 Ω 1% and 4 × 10 Ω 1%
  - 4 × 10 kΩ 0.1%
  - 4 × 47 µF 63 V bipolar, paired within 5 % (a 10 mm can; the layout allows for it)
  - 8 × 1N5817
  - 4 × 100 kΩ bleeds and 2 × 100 kΩ bias resistors
- **Input and pad:**
  - 2 × 10 µF bipolar (step 1 leaves one of the five in hand)
  - 2 × 9.1 kΩ and 4 × 1 kΩ
- **VREF and supply, per board:** 2 × 47 kΩ, 2 × 100 µF 25 V, 100 Ω, 100 nF.
- **Mute:** 2 × TQ2-5V, each with a 1N4148.
- **Board-side headers (JST XH):** per board a 5-way (input), a 2-way (XLR), two 3-ways (pad, coil).
- **Panel:** 2 × on-on toggles (pad), 2 × SPST toggles (lift), 2 × 10 nF 100 V film.

On the module map ([diagrams/modules.html](diagrams/modules.html)) these are two new audio boards,
XLR L and XLR R, one design built twice. Each one's only ground arrives from the codec carrier in
the cable that carries its signal and its 9 V (A11, A12: GND, HP, GND, +9 V, and a fifth way left
unused so it can't go into the carrier's 4-way or 3-way sockets), as the input board's does (rule
2). The XLR cables (A13, A14), the pad cables (A15, A16) and the coil cables (C7, C8) carry no
ground. The codec carrier and the control board don't have the sockets for A11, A12, C7 and C8 yet;
their layouts mark them absent until they do.

### Tests

- **Levels:** play 1 kHz at −1 dBFS.
  - On Line, the reading between pins 2 and 3 should be about 1.8 V rms, with about 0.9 V on each
    pin.
  - On Mic, it should be a tenth of that.
- **Phantom:** with the SSL 2+ as the receiver and its 48 V on:
  - pins 2 and 3 should sit at about 45 V, and the driver side shouldn't move;
  - switch phantom on and off while playing;
  - then short pin 2 to pin 1 with phantom on. This is the clamp test.
- **Boot:** record the SSL across a power-up and a reboot. There should be nothing above the noise.
  The simulation puts 0.6 mV between the pins when the mute releases, and nothing while it is held;
  a real pair of capacitors 5 % apart would add about 0.6 mV to the 0.56 V common-mode ramp at
  power-up.
- **The loop:** an amp on OUT L and the SSL on an XLR, lift in and out, measured at both. Then the
  case-bond comparison above.

## A DI box inside the pedal: on the record, not proposed

The owner has a two-channel DI box and might mount it inside the pedal, between the drivers and the
XLRs, for galvanic isolation. Noted here so the idea isn't lost.

**What it would change:**

- The pedal's ground and the mixer's would never meet. The loop with the amp couldn't form, and
  the lift would become a true transformer lift.
- It would take the PA's leg out of the leakage-current question entirely.

**What counts against it:**

- **Size.** The 1456RH3 has room, so this matters least.
- **Hum pickup.** A transformer is a magnetic pickup, and it would sit near the Pi's supply and any
  future isolated converter. That calls for distance and orientation, possibly a mu-metal can.
- **Fixed level.** A passive DI's output is mic level, which the pad already provides.
- **Power.** An active DI needs it.
- **Nothing extra.** It does nothing the lift and the bond can't do, unless measurement shows the
  loop is still audible with the lift in.

**A smaller version of the same idea:** a line-isolation transformer per channel on the XLR board,
between the driver and the pins. Not needed now.

## Decisions, 2026-10-14

1. **Male XLR (NC3MD-LX) plus impedance-balanced 1/4"**, not a combo socket. A combo socket (the
   NCJ9FI-S) is for Mic IN.
2. **Step 1 now.** Done in the layouts, the map and the BOM; the case's jacks are rewired when the
   output boards are built.
3. **The XLRs are silent in panic bypass**, and at boot.
4. **−20 dB pad.** One resistor changes it.
5. **The case bond: measured first.** The NC3MD-LX doesn't pre-empt it (see Connector).

## Still open

- Where the case bonds to 0 V: the root, the codec carrier, or not at all. The test is in
  [The case bond](#the-case-bond-balanced-outputs-force-the-decision).
- The sockets the drivers plug into: A11 and A12 on the codec carrier, C7 and C8 on the control
  board, and the BC337's base resistor for three coils.
- Compacting the driver board: 134.6 × 55.9 mm is a first layout, and rows 3–5 and 17–19 are
  mostly empty.
- The rear-wall positions, once the D-size flange is checked against the vent band.
