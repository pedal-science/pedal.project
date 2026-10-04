# The case's jacks and output fixture: DC checks on the bench

**Date:** 2026-10-04
**Question:** with the IN and OUT L jacks wired and their pins in the breadboard, is the output
fixture's DC path what the schematic says — and are the odd readings taken earlier a fault in the
fixture or an artefact of what was plugged into it?

## Method

- Meter on the 2 MΩ range for resistances (so `0.009` below is 9 kΩ); continuity for the checks
  that should be a wire.
- The star is the ground rail of the breadboard the codec sits on.
- **Unpowered:** no supply on vip at all, not `poweroff` (a Pi's 5 V header pin stays live).
- The codec's `HPL` lead pulled out of the breadboard, so only the fixture is in the path.
- Repeated with the output's cable to the SSL's input 1 back in place, to show what attached gear
  does to the same reading.

## Results

| Measure | Expected | Read |
|---|---|---|
| OUT L tip lug → fixture node, continuity | beep | **beep** |
| fixture node → ground rail, 2 MΩ | 1.0 MΩ (the bleed is fitted) | **1.0 MΩ** |
| fixture node → ground rail, 2 MΩ, **SSL cable in** | the SSL appears in parallel | **9 kΩ** |

Earlier readings, taken with the guitar in the input **and** the SSL cable in the output, were
**7 kΩ** for the second row and **126 kΩ** for the first. Neither was the pedal:

- A passive guitar pickup is 6–8 kΩ, and on an unpowered codec its path can still reach the output
  node through the chip's protection structures.
- The SSL's input network sits across the jack tip, and its ground comes back up the cable's shield,
  so the meter measures the interface rather than the wiring.
- The 126 kΩ was a probing artefact — the lug beeps, so the tip wire was never in doubt.

The second row moved from 7 kΩ to 9 kΩ between the two runs, which is what removing either the
guitar or the 48 V phantom feed (6.8 kΩ each) would do; 9 kΩ is an ordinary line-type input
impedance.

## Conclusion

The output fixture's DC path matches the schematic: the tip reaches the fixture node, and the node
reaches the star through the 1 MΩ bleed alone. Nothing here needs changing.

**For every later check: nothing plugged into the jacks.** A cable takes the tip and the sleeve out
to another device, and the meter then measures that device. The plug is only for identifying lugs,
with its far end free.

**Check the SSL's phantom switch is off** before its cable goes back in — see build-board1.md's
rules — because 48 V arrives on the tip through the 6.8 kΩ feed resistors and stands across the
fixture's 10 µF the wrong way round.

Still to measure, same method:

- input side: tip → LIN1, sleeve → star, tip switch → sleeve, and the screen bonded at the jack only
- output side: ring → star
- OUT R when it is wired, and strip pins 2–4 as they are used
- then powered: HPL ≈ 1.65 V DC, output jack tips ≈ 0 V once the 10 µF has charged, IN tip ≈ 0 V
  with no plug in
