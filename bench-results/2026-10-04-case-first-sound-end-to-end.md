# First sound through the case: guitar → input jack → codec → namchain → output → SSL

**Date:** 2026-10-04
**Question:** does the case's signal path work end to end — not just its DC continuity?

## Result

Yes. Guitar into the case's input jack, the output jack to the SSL's input 1, a rig loaded in
namchain: audible, and it "sounds pretty good" while playing. One test exercises the whole path —
the screened cable's core into LIN1, the codec both ways, the output fixture's AC path and its
10 µF/100 Ω/1 MΩ, both jacks, and every sleeve and screen.

## The knob that cost the time

The SSL's monitor mix was fully to the right, which monitors the computer's playback rather than
the live input, so the pedal was silent until it went fully left. Nothing was wrong with the pedal.

Two earlier readings fell out at the same time:

- The 7 kΩ on the fixture node was the guitar's pickup (6–8 kΩ) across the unpowered codec's
  protection paths — it went when the guitar did.
- No phantom power was ever on, so the fixture's 10 µF has not been reverse-biased.

## Next

- The input goes straight into LIN1, so the guitar sees the codec's input impedance for now. The
  1 MΩ follower is board 1's, and its only outstanding part is the OPA2197 (CPC, due 4 Oct).
  A buffered pedal in front stands in meanwhile.
- Remaining DC checks, same method as
  [2026-10-04-case-jack-and-fixture-dc-checks.md](2026-10-04-case-jack-and-fixture-dc-checks.md):
  the input side (tip → LIN1, sleeve → star, tip switch → sleeve, screen bonded at the jack only),
  the output ring → star, and OUT R when it is wired.
