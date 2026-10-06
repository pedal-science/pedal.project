# The input stage's scale, its clipping, and what 48 V would do to the jacks

**Date:** 2026-10-06
**Question:** ljoss's level campaign (`ljoss/bench-results/2026-10-06-level-scales/`) measured
what namchain's level numbers mean in the physical world, on the input as it is wired **today** —
jack tip straight to LIN1, sleeve to ground. Board 1's buffer is due to replace that. So: re-do
the measurements once it exists? Can hardware stop an SSL's line output clipping the line input?
How should a guitar be tested, and is the SSL good enough to stand in for one? What do active
pickups do to this input? And what happens if 48 V phantom power is connected to a jack by
mistake?

**In one line:** the campaign's numbers hold and are the reference for the rebuilt stage, but the
plan inherits one wrong sentence from them — a lower PGA cannot buy headroom at the jack when the
converter's input is what clips — and the Line pad needs two resistors' worth of change if it is to
take an interface at 0 dBFS.

Nothing here is new bench work. The measurements are ljoss's, in
`ljoss/bench-results/2026-10-06-level-scales/README.md` (the analysis) and `Tools/levels/` (the
apparatus); the arithmetic, the datasheet reconciliation and the recommendations are this entry's.
Where a number is inferred rather than measured, it says so.

---

## What the campaign measured

| | |
|---|---|
| clip point at the interface's output | **−11.25 dBFS**, and soft rather than abrupt |
| the jack then, from the interface's own calibration | **+2.72 dBu** = 3.06 V peak = 2.16 V rms |
| so the converter's input is full scale at | **1.0 V rms** (2.83 V peak) **at LIN1** — for this wiring, the same node as the jack — which is 2a's datasheet figure |
| input noise floor, interface connected and silent | **−88.0 dBFS(A)** |

The calibration block in ljoss's `dataset.json` is the citable form: `input_clip_dbfs: -11.25`,
`input_full_scale_dbu: 2.719`, `pedal_input_offset_db: 11.781`, `input_floor_dbfs: -87.97`. The
finer evidence is the campaign's 0.75 dB ladder, which is what this entry leans on — "unclipped"
being an unclipped sine at the played level after the interface's +11.78 dB:

| played, at the interface | pedal reports | unclipped would be | difference |
|---|---|---|---|
| −13.50 dBFS | −4.73 dBFS rms | −4.73 dBFS rms | 0.00 dB |
| −12.00 | −3.23 | −3.23 | 0.00 |
| **−11.25** | −2.64 | −2.48 | **−0.16**, and 17,939 frames pinned on the *negative* rail |
| −10.50 | −2.26 | −1.73 | −0.53 |
| −9.75 | −1.97 | −0.98 | −0.99 |
| −9.00 | −1.74 | −0.23 | −1.51 |
| −8.25 | −1.55 | +0.52 | −2.07 |
| −7.50 | −1.43 | +1.27 | −2.70 |
| −6.00 | −1.14 | +2.77 | −3.91 |
| 0.00 | −0.57 | +8.77 | −9.34 |

Two consequences to keep separate, because they are easy to conflate:

- the campaign measured the **codec's** scale, a fixed fact about the WM8960;
- it could not measure the **buffer's** scale, because there is no buffer yet.

**The knee in that table is this entry's load-bearing fact, and it does not depend on the pedal's
own files**: the interface's digital loopback supplies the played level, and the pedal's reported
level supplies the other side. The input is linear to −13.5 dBFS, starts clipping the negative rail
at −11.25, and is 9.3 dB down by 0 dBFS. So the campaign's single `input_clip_dbfs: -11.25` is where
compression *starts* — the right number for a meter's warning, and not the point at which the input
becomes unusable.

### An anomaly in the same run, recorded so nobody builds on it

The campaign's 0 and −6 dBFS segments do not survive a second look: **a hard rail cannot produce
the pair of numbers they report.** A positive-rail-clamped sine reads at most −1.07 dBFS even at
twice full scale, and 41% of frames pinned while the RMS sits 1.5 dB *above* a clean full-scale
sine is not something rail clipping explains at any depth. Three further facts from the same run:

- the pedal's `playback.wav` and `capture.wav` agree **in every measure taken** at every step of the
  ladder — identical RMS, peak and pinned counts, not merely similar — which is what a pass-through
  rig would give, but the rig applied was `Levels` (0, −12 and +12 dB gains). Either the recorded
  files are not the two streams `meta.json` says they are, or the ladder's captured segments are not
  the segments the rig processed;
- the engine reported **`output` identical to `input`** at every level, including the gain rig;
- at 0 dBFS the capture's own true peak is +0.37 dBFS while its sample peak is +0.04 dBFS.

None of it touches the scale above, but the campaign's pinned-frame counts should be read as a
pointer to the input's limits rather than as a measurement of them until a session re-runs the
ladder against the fix. The campaign's own recommendation for the clip counter — count against the
converter's positive rail — is the first thing to try.

One correction to the calibration while we are here: the interface's own output level was not
recorded, and the numbers imply different values — the knee plus a 1.0 V rms full scale puts 0 dBFS
at 3.6 V rms on the pin, while the SSL 2+ Mk II's specified maximum is +14.5 dBu, 4.13 V rms. Note
the output level the way the 2a walkthrough notes input gain, and the volt-per-dBFS figure stops
being ambiguous.

---

## 1. Yes, re-do them — and the first measurement is the input's own clip point

The codec's numbers stand; what has to be re-measured is everything downstream of the jack.

1. **The clip point at the jack, per switch position.** The campaign's 0.75 dB ladder around the
   knee was the right instrument (`--fine-levels "-13.5,-12,-11.25,-10.5,-9.75,-9,-8.25,-7.5"`).
   Repeat it with a meter on the jack as well, so "full scale is 1.0 V rms at LIN1" becomes "full
   scale is 3.06 V peak at the jack on Line, 0.92 V peak on Inst".
2. **Whether the codec's input front end is really 1.0 V rms, and what the PGA does to it.** Drive
   LIN1 from the SSL through a series resistor and find the clip knee; set the PGA to −6 dB and
   find it again. If the knee moves, the PGA precedes the converter's input and the plan's
   "lower the PGA for hotter pickups" works. If it does not move, the PGA follows it and only the
   pad can rescue a hot source. Ten minutes with the SSL and the meter settles it.
3. **Low-level THD and noise at both switch positions, 20 Hz–20 kHz.** This is the one thing the
   present wiring structurally cannot measure. At unity gain a guitar never leaves the top of the
   op-amp's range; the Line pad puts node A around 1 V, and the OPA2197's input stage changes over
   about 3 V from the negative rail, which is the region the 2b review argued about. Measure it at
   milliamp-level signals rather than inferring it.
4. **Noise floor per position**, jack shorted, and with a guitar lead in and nothing at its far end.
   Expect a decibel or two more than 2a's −88 dBFS(A) from the 680 kΩ pair and the switch.
5. **The Line pad's ratio, measured rather than nominal.** 330k/(680k+330k) = 0.327, −9.72 dB, is
   what the parts say. Question 2 turns on it.

Then repeat the whole campaign with the buffer in, and update ljoss's calibration block
(`input_clip_dbfs`, `input_full_scale_dbu`) so the app's meter maths follows the hardware.

Do **not** re-do the node-level accuracy, the meter offsets, the RMS floor or the clip counter's
blindness. Those are ljoss-side and engine-side facts, and a buffer in front of the codec does not
touch them: the clip counter still counts samples at 1.0f while a 24-bit converter's positive rail
is 0.99999994f. Worth fixing while the input is on the bench anyway, since a rebuilt input is
exactly when someone will drive it into the rail deliberately.

The output path is worth re-running too, cheaply. The campaign's −28.6 dB for DAC → interface is a
fact about the fixture, the headphone level and the interface's minimum gain, not about the engine.

## 2. Line in: yes, two resistors, and there is a 2.6 dB gap today

The measured contract is what matters, not the BOM's:

- the SSL can deliver **+14.5 dBu at 0 dBFS** (4.13 V rms, 5.84 V peak);
- the pedal's input is full scale at **+2.72 dBu** (1.0 V rms, 2.83 V peak at the codec's pin);
- and the input's knee is **soft**, so the interface goes past it by about 6 dB before 0 dBFS
  (the ladder above: compression starts at −11.25 dBFS and is 9.3 dB down by 0 dBFS).

The other limit in the path is the op-amp. The OPA197/2197's output swing is 110 mV from either
rail typical, 95 mV minimum, into 10 kΩ ([TI SBOS737](https://www.ti.com/lit/gp/opa2197)), so on
9 V with the 2.9 V bias the follower runs out at about ±3.0 V — 2.1 V rms, 3.0 V peak, 8.9 V peak
at the jack behind the pad. That is within 0.2 dB of where the codec's 1.0 V rms puts the same
node, so **in Line the two limits arrive together and neither has margin over the other**; in Inst
the codec is the tighter one (2.83 V peak at the pin against the op-amp's 3.0 V).

What the pad decides. The codec's own contract, which is what the pad has to satisfy, is simply
**1.0 V rms at its pin**, and the pad scales the jack's volts into it; the numbers below take the
interface's specified maximum, +14.5 dBu (4.13 V rms) at 0 dBFS:

| volts at the jack | as designed → codec sees | 220 kΩ → codec sees |
|---|---|---|
| 4.13 V rms = **the interface at 0 dBFS** | 1.35 V — **2.6 dB over the limit** | 1.01 V — **6.6 dB of margin** |
| 3.06 V rms = where the pedal clips today | 1.00 V — at the limit | 0.75 V — 2.5 dB under |
| 1.23 V rms = +4 dBu, a pro nominal level | 0.40 V — 8 dB under | 0.30 V — 10.5 dB under |
| 0.32 V rms = −10 dBV, a consumer nominal | 0.10 V — 20 dB under | 0.08 V — 22.5 dB under |

So:

- **as designed**, the pad is about 2.6 dB *short* against the interface's specified maximum, so a
  0 dBFS line source still clips — though 8.6 dB less deeply than the unbuffered input clips today
  (11.2 dB past the knee, from the ladder), which is what the buffer buys even before the pad is
  touched;
- **changing the 330 kΩ to 220 kΩ** gives ratio 0.245, **−12.2 dB**, input impedance 920 kΩ (the
  "about 1 MΩ" claim survives), and 6.6 dB of margin — enough for the extra-loud setting and for a
  consumer device that happens to run hot. That number is against the *specified* maximum; the
  bench measurement in question 1 item 1 is what either confirms it or moves the resistor.

What that costs: 2.5 dB on every line source, which still leaves a consumer nominal level 23 dB
above the codec's full scale, so the noise penalty is confined to sources quieter than −33 dBV
nominal. It does not transfer to Inst — 680 kΩ in series with a *passive* pickup puts an external
pole at 680 kΩ × 500 pF ⇒ 470 Hz (cable capacitance being the assumption, since the guitar's own
5 kΩ source and 1 m of screened cable are not measured here), which is unusable for a magnetic
pickup. Keeping the pad in a switch position rather than sharing it with Inst is what keeps both
positions honest. A third position — Inst ×1, Active −10 dB, Line −12 dB — would cover everything
with one panel hole, since the switch is already the gain switch.

Not hardware, and free: inputs have a gain trim for exactly this. If the app ever gains a
reference-level control, "input full scale = +2.7 dBu" is the number it wants, and ljoss's
recommendation to draw headroom against the device's own clip point is what turns 2.4 dB of
overdrive into something visible instead of a healthy-looking 0 dBFS.

### One correction to the plan

`plan.md`'s 2b review says a lower PGA buys headroom at the jack: "the PGA goes below 0 dB (to
−17.25 dB), so −3 dB gives 2 V peak and −6 dB 2.8 V peak, which is about where the OPA2197 runs
out of swing below its 2.9 V bias."

The campaign's data says otherwise for the input as wired. The knee at −11.25 dBFS is a property
of the **analog input** — it begins with the *negative* rail pinning, at a level where nothing
downstream has done anything yet — so the PGA, which follows the input in the WM8960's path
(LINPUT1 → input PGA → boost → ADC), cannot restore what has already been flattened. The op-amp has
the swing for 2.83 V peak at the codec's pin, and the converter's 1.0 V rms full scale is where the
input stops being linear, so the converter is the limit in both switch positions.

The reading that fits everything: **−3 or −6 dB of PGA helps a source that would otherwise clip at
the converter's input, and does nothing at all for one that has already clipped the input stage.**
Only attenuation ahead of the converter moves the ceiling, which is what the pad and the Inst/Line
switch are for. Measurement 2 above decides it in ten minutes; until then, treat the plan's
sentence as unverified — and note that its "2.8 V peak" is the op-amp's swing, which is also where
the converter stops, so the two cannot be told apart by arithmetic alone.

## 3. Guitar: two different jobs, and the SSL does the first one very well

The finished input is a follower behind a 1 MΩ, so a guitar is *voltage* into a high impedance with
negligible loading. A low-impedance known source is therefore the right instrument for most of what
needs measuring, with one real exception.

**The SSL is adequate, and better than adequate, for:**

- **calibrating the scale** — the volts at the jack that equal the engine's full scale. 2a did the
  equivalent for the codec with a known meter reading at 0 dBFS; do it again at the jack and the
  whole table is anchored.
- **headroom and clipping**, including the clip counter — the campaign's 4×-oversampled true peak
  and pinned-frame counts are the right readouts.
- **switch, jack and tip-switch behaviour** — the no-input noise floor, and the pop the tip-switch
  ground wire is there to stop, are both measurable with a cable and no source.
- **shape realism**, which is where "known guitar pickup characteristics" fits: `signals.py`'s
  plucked burst, and the campaign's real guitar DI at a 16.8 dB crest factor. That crest factor is
  exactly the number that makes a peak meter and an amp model disagree, and it is why the 0 dBFS
  *sine* reading above misleads. Feed the DI **file** rather than a synthetic shape when the crest
  factor is what is being tested.

**It is not adequate for one thing, and it is the interesting one:** it cannot show that a passive
pickup's own impedance is being ignored, because its output is ~2 kΩ (2a put it there from the
−3 dB-at-1.5-kHz response into the codec's capacitance) and the pedal's input is 1 MΩ. Two ways to
close that, in increasing order of honesty:

- **A series resistor.** SSL out → 100 kΩ → pedal in. With a 1 MΩ input that is 0.83 dB at DC and
  0.83 dB at every frequency, so any *shape* change is the input loading its source. Compare that
  sweep with the direct one. It is a poor stand-in for a pickup's inductance but a good stand-in
  for "a high-impedance source", which is the mechanism at issue.
- **The real guitar, played hard.** Record the pedal while someone plays: medium strum, hard strum,
  and the same guitar through a buffered pedal into the same input, then compare the two captures'
  spectra. A pickup's resonant peak is what a load would flatten, and this measures it within a
  fraction of a decibel. It is the only test that says "a guitar sounds right into this", and it
  doubles as the acceptance test for the tip-switch grounding — plug in and out and listen.

Do **not** try to make the SSL *emulate* a pickup electrically. Its low output impedance is what
makes it convenient, and the effort would go into re-measuring a loading effect that 1 MΩ has
already made negligible. The acceptance question is a real guitar through the finished stage.

## 4. Active pickups: the 1 MΩ is not the problem — the input's full scale is

In peak volts at the jack, with full scale at 3.06 V peak on Line and 0.92 V peak on Inst
(3.06 × 0.327):

| source | typical peak | Inst (×1) | Line (×0.327) |
|---|---|---|---|
| passive single coil | 0.1–0.5 V | fits | very quiet |
| hot humbucker | 1–2 V | at or over the limit | fits |
| **active, 9 V** | **4–9 V** | **~5× over** | fits, to 10 V peak |
| active with an onboard boost | to 15 V | far over | at the limit |

So an EMG-class pickup presents a low output impedance to a 1 MΩ input, which is exactly the case a
follower wants, and the old "Hi-Z" concern does not apply — the loading is a non-issue, and cable
capacitance is a non-issue because the pickup is already buffered. What *is* a problem is that they
are typically 10–15 dB hotter than a passive pickup, so they clip the Inst position by 10 dB or
more. Two caveats on using Line for them as a workaround:

- **A passive guitar must never be judged through Line**, for the 470 Hz reason above. An active
  pickup's ~10 kΩ source will not care about the 680 kΩ; a passive one very much will.
- **A 9 V active pickup's worst case is a fresh battery**, so specify the pedal at that level, not
  at 7 V.

The clean hardware answer is the third switch position from question 2: pad the instrument path by
10 dB *before* the op-amp. The Line pad does the job today as a workaround with a caveat, not as
the intended "active" setting.

## 5. Phantom power into the jacks: the input survives, the output is the exposed one

Neither jack has a DC path to ground inside the pedal, so the coupling capacitors are what stands
between 48 V and the active parts, and their ratings decide the outcome. (Both are in
[bom.md](../docs/bom.md): the input's 100 nF is 63 V PET film, the output's 10 µF is a 50 V
bipolar electrolytic.)

**Input, 48 V at the tip.** Tip → 100 nF **63 V** → node A, which sits at the 2.9 V bias through
330 kΩ. The capacitor blocks the DC and the op-amp's pin sees no potential difference across it, so
there is no path into the OPA2197's protection diodes at all. The capacitor sees the full 48 V,
inside its 63 V rating, and the 1 MΩ to ground brings the tip back to 0 V in about five seconds
(1 MΩ × 33 nF) after the cable comes out.

What would be noticed is behaviour, not damage:

- **The tip-switch wire to ground makes the pedal present a short to the phantom supply** for the
  moment a plug goes in. The NMJ6HF-S's tip switch is break-before-make on insertion — a plug glides
  over it — so it is a transitory short, and the source's 6.8 kΩ feed resistors hold it to about
  7 mA. The phantom rail sags, and whatever else shares that supply gets a click.
- The tip sits at 48 V until the 1 MΩ bleeds it, so **unplugging pops**, and plugging in pops for
  the same reason.

**Output, 48 V at the tip.** This is the one to check afterwards. Tip → 100 Ω → **10 µF bipolar,
50 V** → HPL. Nothing in the pedal reverse-biases it (the phantom's return is the sleeve, which is
the pedal's 0 V), but it settles at very nearly the whole 48 V — 48 µA through the 1 MΩ bleed
between pulses, 0.5 mV across the 100 Ω — which is **1.9 V inside its rating**. Its codec-side
terminal is then held 46 V away from HPL's 1.65 V operating point, and that voltage rides on the
capacitor's leakage current into the codec's output pin. Through a good bipolar in the steady state
that is microamps, shunted by the pin's protection structures; with a hot or reverse-biased part it
is not, and the capacitor is at its rating. Plausible that it survives; not specified, and the
failure mode is a leaking, heating capacitor that takes the codec's output pin with it.

The drill, which is the honest answer to "what would happen":

- **Assume the input is fine and the output capacitors need verifying** before the pedal goes back
  into service: measure DC at each tip and across each output capacitor with the pedal unpowered,
  after the bleed has had time to work, and confirm the parts are what they were. A tip that does
  not settle to ~0 V means a suspect capacitor.
- **The thing that would actually hurt is a cable with phantom on one end and a microphone on the
  other.** That is the ordinary accident, and it is not this pedal's problem to solve — but it is
  why the 2a walkthrough's "48 V off" check exists and should stay in every later procedure.
- **If the pedal ever gains an onboard phantom supply** for D5's mic stage, input protection becomes
  a design item in its own right. Nothing in the pedal as it stands is damaged by 48 V arriving: the
  parts that meet it are a 63 V film capacitor and 1 MΩ of resistance.

---

## What to do next, in order

1. Build the buffer, then **measure its clip point and the Line ratio at the jack** (question 1,
   items 1–2). Ten minutes with the SSL and the meter, and it settles the PGA question.
2. Use that measurement to **decide the pad ratio** — 220 kΩ for the Line position if an interface
   at 0 dBFS is to fit (question 2) — and consider the third switch position for active pickups
   (question 4).
3. Re-run `Tools/levels/campaign.py` with its `levels` and `amp` rigs, and update ljoss's
   calibration block so the app's meter maths follows the hardware.
4. Record the results as a dated entry here, and correct `bom.md`'s input-stage section (the Line
   ratio, and the PGA sentence) and `plan.md`'s 2b review when the measurement confirms which way
   the PGA behaves.

## Sources

- `ljoss/bench-results/2026-10-06-level-scales/README.md` — the campaign's findings, tables and
  recommendation; `index.html` beside it is the same with charts; `dataset.json` in each run holds
  the calibration block quoted above.
- `ljoss/Tools/levels/` — the apparatus: `sslgen.c`, `signals.py`, `analysis.py`, `campaign.py`,
  `report.py`, `page.py`.
- [TI SBOS737](https://www.ti.com/lit/gp/opa2197) (OPA197/OPA2197/OPA4197) — the output swing from
  rail (110 mV typical, 95 mV minimum, into 10 kΩ) that sets the op-amp's ±3.0 V in question 2.
- [codec-bringup-2a.md](../docs/codec-bringup-2a.md) — the codec's measured full scale (1.0 V rms),
  the −93.5 dBFS(A) floor, and the SSL's output impedance.
- [codec-bringup-2c.md](../docs/codec-bringup-2c.md) — the shunt swap and the legs that come after
  the buffer is built.
- [bom.md](../docs/bom.md) — the input stage's parts and values, and the corrected figures from the
  2b review.
- `plan.md` — Phase 2b's early findings and the review against 2a, including the PGA sentence this
  entry questions.
