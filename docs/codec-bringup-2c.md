# 2c: modify the codec and compare (bench walkthrough)

A walkthrough of [plan.md](../plan.md) Phase 2c, for you to follow at the bench. It is three
things: replace LIN1's 47 nF ceramic shunt with film and measure THD against frequency, try VIN
from a 78L05 on the 9 V side (needs no cutting), and only if that isn't enough, cut AVDD-ISO and
fit the external LDO. This is the procedure and the numbers it produces.

## What 2b already says to expect

From the review against [2a](codec-bringup-2a.md) (2026-09-27), so a leg's result isn't a surprise:

- **The LDO's noise isn't the bench limit.** With the board's own LDO fed from the Core host's 5 V,
  the input noise is already at the datasheet figure: −93.5 dBFS(A), ≈21 µV A-weighted. The
  78L05 trial is to beat **the enclosure**, not the bench — so expect leg 1 to change nothing, and
  treat a change as something to chase rather than a win.
- **Grounding is the bigger risk.** Sharing ground with the interface through the host put a 90 Hz
  comb at −86 dBFS, 7 dB over the codec's own floor. Any leg with an extra path between the pedal
  and the interface shows that comb, and the comb is what these legs are really measuring.

Their value on the bench is the negative result — proof the supply is not the limit — plus a route
already measured for Phase 4.

## The measurement

Two rows decide it, both from a capture of the codec's own ADC:

| Row | Setup | 2a's figure |
|---|---|---|
| noise floor, input shorted | LIN1 to GND, no cable | −93.5 dBFS(A), ≈21 µV |
| noise with the interface connected | SSL out → LIN1, silent | −77 dBFS, the 90 Hz comb |

### Capture

`arecord` and `python3` are both in the host image (`devices/vip/test-offline-apply` checks for
them). The engine holds the card, so stop it for the capture, and put everything on the host through
the lock — one measurement at a time:

    scripts/host-lock -- ssh vip 'systemctl stop namchaind'
    scripts/host-lock -- ssh vip 'arecord -l'                  # the card's name, and its formats
    scripts/host-lock -- ssh vip 'arecord -D hw:wm8960 -f S24_3LE -r 48000 -c 2 -d 60 /var/tmp/2c-leg0.wav'
    scripts/host-lock -- ssh vip 'systemctl start namchaind'
    scripts/status                                             # running/ok again, xruns unchanged

**24-bit, not 16:** a −93 dBFS floor sits below 16-bit's last bit. If the card refuses `S24_3LE`,
`--dump-hw-params` lists what it takes (`S24_LE` or `S32_LE` are the likely others). Channel 0 is
LIN1, which is the default the analysis reads.

Then on the Mac:

    scp vip:/var/tmp/2c-leg0.wav bench-results/
    python3 scripts/codec-noise.py bench-results/2c-leg0.wav

That prints the DC offset, the unweighted and A-weighted RMS in dBFS and µV at 1.0 V rms (2a's
convention), the peak, and the largest lines below 1 kHz and between 1 and 20 kHz — so a comb or a
whine arrives as a frequency rather than as a number that moved. Its `--selftest` checks the
weighting against the standard's own figures before you trust it on a capture.

### Ground discipline, the same for every leg

- One path between the pedal and the interface: the audio cable from the output jack. No USB between
  the interface and the Core host, no second supply, nothing else joining the two grounds.
- Record which legs had that cable connected. That row moves more than any supply change will.
- **Rule 1 applies to every leg:** nothing powered while you move a lead. Unplug the host's supply
  rather than trusting `poweroff`, because a Pi's 5 V header pin stays live.

## The legs, one change at a time

Change one thing, capture, and compare against the leg before it — not against 2a's absolute numbers,
which came from a different bench (piv, and no case wiring).

| Leg | The one change | Expect |
|---|---|---|
| 0 | as it is now: board VIN from the Core host's 5 V header, AVDD from the board's own LDO | ≈ −93.5 dBFS(A) shorted, and a comb once the interface is connected. This leg is the new baseline. |
| 1 | board VIN from a 78L05 on the Cioks 9 V instead of the host's 5 V (no cutting; five in hand) | no change, per 2b. A change here is a finding. |
| 2 | AVDD-ISO cut, AVDD from the 78L33 on the isolated 9 V (destructive — plan.md's third 2c item) | only if leg 1 shows something. The comparison that decides this one is enclosed, in Phase 4. |
| 3 | board 1's buffer on the isolated 9 V, its ground meeting the star at one point | the analogue isolation the handoff describes. Needs board 1 built; measure when it exists. |

Leg 0 *with* the interface connected is the 2b reproduction: if the comb has moved or gone, that is a
result about the case's ground scheme rather than about any supply.

## The shunt swap

LIN1's 47 nF ceramic (top row, column 4) becomes film — 47 nF PET keeps the 34 kHz corner, 4.7 nF
would do, and both are in the drawer. Measure with the codec's own loop (HPL → fixture → LIN1) at
−3 dBFS at 100 Hz, 1 kHz and 4 kHz, before and after, against 2b's rise: −78 dB at 100 Hz, −65 at
1 kHz, −58 at 4 kHz. Behind the buffer the board's own 100 Ω is still in series, so expect about
−71 dB at 1 kHz.

## Where the numbers go

Into `bench-results/` as a dated file, one capture per leg named for the leg (`2c-leg0-...wav`), with
the table above filled in. If a reading replaces one in 2a's results table, update that table too —
it is the record 2b reviewed against.
