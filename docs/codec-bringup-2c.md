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

**One command does all of this, and draws the graphs**: `scripts/codec-input-noise.py`, which takes
the host's lock, records the engine's own capture while it runs, stops `namchaind` for the two
`arecord` arms, starts it again and puts the mute back as it found it, and writes
`bench-results/<date>-codec-input-noise/` — a page with a spectrum and an octave-band chart per arm,
the numbers, and the state of the host around the run. `--state "…"` is the line that says what was
wired. `--arms engine` does the first arm alone, which needs no interruption at all. Use it unless
you need a capture it does not make; the manual recipe below is what it does, and is still the way
to do something else.

`arecord` and `python3` are both in the host image (`devices/vip/test-offline-apply` checks for
them). The engine holds the card, so stop it for the capture, and put everything on the host through
the lock — one measurement at a time:

    scripts/host-lock -- ssh vip 'systemctl stop namchaind'
    scripts/host-lock -- ssh vip 'arecord -l'                  # the card's name, and its formats
    scripts/host-lock -- ssh vip 'before=$(dmesg | wc -l); \
        arecord -D hw:wm8960 -f S32_LE -r 48000 -c 2 -d 60 /var/tmp/2c-leg0.wav; rc=$?; \
        dmesg -T | tail -n +$((before + 1)); exit $rc'         # the capture, and what the kernel said
    scripts/host-lock -- ssh vip 'systemctl start namchaind'
    scripts/status                                             # running/ok again, xruns unchanged

**`arecord` can die on this platform** with `pcm_read: read error: Input/output error` — the RP1's
DMA controller rejecting a descriptor on the I2S capture channel, not a fault in the wiring. The
`dmesg` wrap above is what makes that visible, and
[docs/audio-dma-irq.md](audio-dma-irq.md#when-the-capture-dies-pcm_read-inputoutput-error) is the
page about it. `scripts/codec-input-noise.py` does the same wrap and retries the arm for you.

**24-bit, not 16:** a −93 dBFS floor sits below 16-bit's last bit. This card answers
`--dump-hw-params` with `FORMAT: S16_LE S24_LE S32_LE` — **no `S24_3LE`** — so a plain `arecord`
wants `-f S32_LE`, which is also what `namchaind` takes and what the engine's own recordings carry;
`scripts/codec-input-noise.py` reads the card's list and picks in that order. Channel 0 is LIN1,
which is the default the analysis reads.

Then on the Mac:

    scp vip:/var/tmp/2c-leg0.wav bench-results/
    python3 scripts/codec-noise.py bench-results/2c-leg0.wav

That prints the DC offset, the unweighted and A-weighted RMS in dBFS and µV at 1.0 V rms (2a's
convention), the peak, and the largest lines below 1 kHz and between 1 and 20 kHz — so a comb or a
whine arrives as a frequency rather than as a number that moved. Its `--selftest` checks the
weighting against the standard's own figures before you trust it on a capture. Give the capture and
its analysis to `scripts/noise-document.py` for the graphs and the page — a manifest of captures is
all it takes.

**Read the band, and then read the raw.** The unweighted and A-weighted figures are band-limited to
20 Hz–20 kHz, as every earlier reading of this converter is; where a capture's raw (unbanded) level
sits well above its band figure, most of its power is outside the audio band and the number is not
describing hiss. `scripts/codec-input-noise.py` and `scripts/noise-document.py` both report the raw
figure beside the others for exactly that reason (2026-10-12's `arecord`-alone arm: −92.4 dBFS in
band, −83.0 raw).

### Ground discipline, the same for every leg

- One path between the pedal and the interface: the audio cable from the output jack. No USB between
  the interface and the Core host, no second supply, nothing else joining the two grounds.
- **Record how the Core host itself is powered — its mains supply or its own battery** (added
  2026-10-13). That row moved **28 dB** of 50 Hz at LIN1 in the day's twenty runs: −71.8 dBFS
  (258 µV) on the Pi's USB-C supply against −98.5 (12 µV) on a battery pack, same board, same guitar,
  same 9 V battery on the analogue rail, two runs each. A mains brick's output is isolated at DC and
  not at 50 Hz, so its Y-capacitor puts the current into the pedal at the host's own 0 V.
  [bench-results/2026-10-13-input-hum-and-the-host-supply.md](../bench-results/2026-10-13-input-hum-and-the-host-supply.md)
  has the table and the mechanism.
- Record which legs had that cable connected. **That row moves more than any change to board 1's own
  supply leg will** — leg 1 below — which is the comparison it was written for; it does *not* move
  more than the host's supply does (3–8 dB for the cable against 28 dB for the host, measured
  2026-10-13, so the line was scoped to the leg it was about rather than left as a general claim).
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
