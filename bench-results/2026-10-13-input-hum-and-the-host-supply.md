# 2026-10-13 — the input's 50 Hz hum, and the Core host's own supply

Twenty runs of `scripts/codec-input-noise.py` on one bench, in one day — and eleven more that evening,
in the last section here, which correct a further wiring fault and carry the number to keep. Every
run's page, numbers and state are in [`../noise-tests/`](../noise-tests/); this
file is the reading of them, including three things that were read wrongly at the time and are
corrected below.

**Three results.**

1. **The input chain costs nothing measurable above the codec — once the mains is out of it.** With a
   guitar on a 20 cm cable, the Inst throw and vip on a USB battery pack, the engine arm reads
   **−88.10 and −88.64 dBFS unweighted, −91.00 and −91.32 dBFS(A)** against the same day's
   codec-alone baseline of −89.33 / −91.39. From 125 Hz to 20 kHz it is the codec's own floor band
   for band; take the two surviving mains lines out arithmetically and it reads −88.95 / −89.49
   against −89.33.
2. **The Core host's own supply is worth 28 dB of 50 Hz at the input.** Same board, same guitar, same
   9 V battery on the analogue rail, same state — vip on its USB-C mains supply gave a 50 Hz line of
   258 µV, on a second mains supply 426 µV, and **on a battery pack 12–13 µV**. Two runs each,
   agreeing to 1 dB.
3. **The 50 Hz voltage at LIN1 scales with the follower's input-node impedance at a roughly constant
   current.** 1.01 MΩ → 10 mV, 40 kΩ → 331 µV, shorted → under 1 µV: a 25× impedance change and a
   29.6 dB change, against 28 dB predicted for a fixed current of 6–10 nA.

## The twenty runs

Each row is one run; "one change" is what differs from the row above it. The engine arm is the
pedal's normal state (`namchaind` running, muted, recording its own capture); every run's three arms,
graphs and audio are in that run's directory.

| run | time | one change | engine unweighted | engine dB(A) | 50 Hz | total |
|---|---|---|---|---|---|---|
| 1 | 23:59 | LIN1 shorted at the codec's own pin — the baseline | −89.33 | −91.39 | −127.9 | 34.2 µV |
| 2 | 00:05 | + board 1's GND wire | −89.89 | −91.96 | −127.5 | 32.0 µV |
| 3 | 00:08 | + the LIN1 wire; board unpowered, node open | −62.18 | −82.70 | −65.7 | 778 µV |
| 4 | 00:18 | + the board powered, node still open | −35.10 | −51.02 | −40.0 | 17.6 mV |
| 5 | 00:37 | 9 V battery; node shorted at the board; no jack | −73.67 | −80.77 | −99.4 | 207 µV |
| 6 | 07:19 | + jack and 20 cm cable; board **unpowered** (battery switch off) | −68.95 | −84.28 | −74.7 | 357 µV |
| 7 | 07:21 | board powered again | −85.32 | −87.26 | −123.1 | 54.2 µV |
| 8 | 07:27 | + a guitar on the 20 cm cable | −85.21 | −87.18 | −117.5 | 54.9 µV |
| 9 | 07:29 | player touching the strings | −85.28 | −87.25 | −112.7 | 54.5 µV |
| 10 | 07:40 | + output board, SSL and hifi amp; battery return on the input board's GND | −63.72 | −84.54 | −66.8 | 651 µV |
| 11 | 07:42 | repeat of 10 | −63.67 | −84.69 | −66.3 | 655 µV |
| 12 | 07:45 | battery return moved to the codec's GND | −85.56 | −87.54 | −119.3 | 52.8 µV |
| 13 | 07:48 | player not touching | −85.49 | −87.47 | −119.2 | 53.1 µV |
| 14 | 07:57 | 2 m TS cable instead of the 20 cm TRS | −85.83 | −87.94 | −108.2 | 51.1 µV |
| 15 | 08:38 | player touching | −85.58 | −87.67 | −111.1 | 52.6 µV |
| 16 | 16:05 | **pin-3 short removed**; Inst throw; guitar actually in circuit; host on mains | −65.52 | −86.33 | −69.6 | 530 µV |
| 17 | 16:06 | player touching | −67.85 | −87.80 | −71.8 | 405 µV |
| 18 | 16:15 | **host on a USB battery pack** | −88.10 | −91.00 | −97.5 | 39.4 µV |
| 19 | 16:19 | repeat of 18 | −88.64 | −91.32 | −98.5 | 37.0 µV |
| 20 | 16:36 | host on an Anker mains supply | −64.82 | −87.11 | −67.4 | 574 µV |

The runs before 5 are the morning's: the codec alone (1, 2), the signal wire into an undriven node
(3) and the same node with the board powered (4), which is where the 1 MΩ node's pickup first showed
at −51 dB(A).

## The host's supply, measured five ways

Same state as run 16/17 throughout (guitar on the 20 cm cable, Inst, 9 V battery on the analogue
rail, Cioks out), only the host's power changed:

| host's power | 50 Hz | 100 Hz | 150 Hz | total | dB(A) |
|---|---|---|---|---|---|
| battery pack (run 19) | **−98.5 (12 µV)** | −109.1 | −133.2 | 37.0 µV | −91.32 |
| Pi 45 W USB-C supply (run 17) | −71.8 (258 µV) | −76.3 | −111.1 | 404.9 µV | −87.80 |
| Anker USB-C supply (run 20) | −67.4 (426 µV) | −77.2 | **−85.4** | 573.9 µV | −87.11 |
| Pi supply **+ the SSL on the output** (runs 10/11) | −66.8 / −66.3 (457/485 µV) | −74.7 | −89.2 | 651/655 µV | −84.5/−84.7 |

Read from the left: the mains reference itself is the 28 dB; the *brand* of brick is 4 dB in the
wrong direction; and a second mains-referenced box on the output was worth another few dB. Note the
Anker's 150 Hz at −85.4 against the Pi supply's −111.1 — a 26 dB difference in a harmonic the other
supply did not produce, which is the signature of a peakier mains current and may be the field off
the supply's own lead rather than its leakage; moving the supply and its lead away is the test that
separates those, and it has not been run.

This is the 2026-10-11 finding reproduced in a different configuration and 2.4 dB larger (25.6 dB
there, on node B with the interface connected): **mains at the Core host restores the hum, batteries
remove it**. The mechanism is in
[docs/hardware-handoff.md § Power](../docs/hardware-handoff.md) — a mains supply's output is isolated
at DC but not at 50 Hz, because the Y-capacitor that keeps its switching noise off the mains also
ties the output's common mode to it. The current enters at the 0 V of the host's own supply, and
returns through the room or through any other mains-referenced box joined to the pedal.

**A common-mode choke does nothing at 50 Hz.** Its impedance is 2πfL, so 47 mH is 15 Ω against a loop
whose impedance is megohms of capacitance. The choke belongs to the isolated converter's 50–300 kHz
hash, which is the job the handoff gives it. For the 50 Hz current the levers are: remove the mains
reference, reduce the number of mains-referenced boxes in the loop, and keep the current off the
conductor the signal uses as its reference.

## What the input costs

Engine arm, run 18 against run 1, per octave band. The bottom row is the two mains lines taken out of
run 18 arithmetically:

| | 32–63 | 63–125 | 125–250 | 250–500 | 500–1k | 1–2k | 2–4k | 4–8k | 8–16k | 16–20k | total |
|---|---|---|---|---|---|---|---|---|---|---|---|
| codec alone (1) | −112.9 | −111.8 | −110.1 | −107.8 | −103.0 | −102.0 | −99.4 | −96.5 | −93.5 | −96.4 | −89.33 |
| guitar, host on battery (18) | −95.6 | −103.3 | −109.1 | −107.8 | −100.7 | −100.8 | −99.1 | −96.6 | −93.5 | −96.4 | −88.10 |
| difference | +17.3 | +8.5 | +1.0 | 0.0 | +2.3 | +1.2 | +0.3 | +0.1 | 0.0 | 0.0 | +1.2 |
| run 18 less the 50 and 100 Hz lines | — | — | — | — | — | — | — | — | — | — | **−88.95** |

So the board, the jack, 20 cm of cable and a guitar add nothing above 125 Hz, and everything they do
add is the two mains lines. The capture-only arm agrees with the codec alone to 0.3 dB, and the
**playback-open arm is the one gap left**: a flat +4.5 dB from 500 Hz to 20 kHz against run 1's
playback arm, in both battery-host runs, while the engine and capture-only arms sit on the floor.
That is a codec-state effect with a silent playback stream open, not an input-path one, and it is in
a diagnostic arm rather than the pedal's normal state.

## Three corrections to earlier readings

1. **Runs 8, 9 and 12–15 measured the buffer's ground, not a guitar.** Every one of their state lines
   says "U1 pin 3 shorted to board ground", and the owner confirmed on 2026-10-13 that the jumper was
   still fitted. Pin 3 is the follower's input and IN reaches it through R5, so the guitar sat behind
   680 kΩ into a grounded node and never entered the circuit. This also explains the ≤0.8 dB that
   "player touching the strings" changed in those runs. **The guitar entered the circuit at run 16.**
   The runs remain valid as measurements of the buffer and its ground — the 50 Hz they show at
   −108…−119 is the ground, not an instrument.
2. **The 4 dB the board appeared to cost is not a fixed voltage in the board-to-codec ground return.**
   That was the reading offered from runs 7–15, where the node was shorted at the board. Runs 16 and
   18 then measured the *same* path with a guitar attached and the HF bands came back 1.0–3.5 dB
   **quieter** than with the node shorted, so the excess follows whatever is connected at the
   follower's input — which means the shorted-node reference may itself have contributed to it, and
   the pin-3 shorting jumper is a suspect. A cleaner shorted-node reference, made with the shortest
   possible link, has not been measured.
3. **The choke correction above** is a correction to advice given during the session, not to a
   reading.

## The kernel, on all twenty runs

Five `dma2chan3 is non-idle!` messages in twenty runs — runs 3, 8, 9, 10 and 16, all in the
`playback-open` arm — and in every case the capture completed on its first attempt: all twenty runs
record `attempts: engine 1, playback 1, alone 1`, no arm was retried, and no run has a
`Bad descriptor` or `IRQ with no descriptors` line. The wraps are in each run's
`dmesg-<arm>.txt`. The three captures that had an event were checked for a dropped, zeroed or
duplicated block inside the analysed window and found clean. The first 2 s of the playback arm sits
23 dB above the settled floor (−61.6 against −84.5 dBFS), so `--skip 2` is cutting exactly the window
a start-of-stream race would land in.

Two further readings that belong to the kernel rather than the wiring: the `capture-only` arm's
sub-audio drift, which the pages flag as 7.5–9.6 dB outside the audio band in runs 7–15, was absent
in the 16:00 runs (0.7–1.1 dB), and the 2 m cable cost about 9 dB on the 50 Hz line against the 20 cm
one (−119 in runs 12/13 against −108/−111 in 14/15) with no change to any broadband band.

## Open

- **Which throw runs 16–20 were in.** Their state lines say `SW-C jumpered to SW-I (Inst)`, which is
  what the owner was asked to set; asked on 2026-10-13, the owner described those runs as being in
  **Line**. The two records disagree and it has not been resolved. The check needs no run: power off,
  meter U1 pin 3 to the bias hole at (21, 4) — **1.01 MΩ is Inst, 330 kΩ is Line**
  ([docs/build-board1.md:232](../docs/build-board1.md#L232)). It matters because the two positions are not
  equivalent for hum: with a guitar attached the Inst throw puts the source's own impedance straight
  across the follower's input (1.01 MΩ ∥ (C5 + 10 kΩ) ≈ **40 kΩ** at 50 Hz), while the Line throw
  puts 680 kΩ in series with the source and leaves the tap undamped (330 kΩ ∥ 722 kΩ ≈ **226 kΩ**) —
  5.6× higher, so of order 10–15 dB more hum at the same current, against 9.7 dB *less* signal.
  With an empty jack the ranking flips (1.01 MΩ against 222 kΩ), which the finished pedal's tip
  switch makes moot. Either way the next run is the other position, and it is a free test of the
  current-source model: if Line comes back 10–15 dB worse, the model holds; if the two are the same,
  the model is wrong about where the hum enters.
- **The Cioks has never been connected** in any of these twenty runs. The analogue rail has been a 9 V
  battery throughout, so the leg the isolated-outlet scheme rests on — a mains-powered brick with an
  isolated output feeding the buffer — is still unmeasured, and it is the leg the finished pedal will
  use.
- **The host's supply distance test.** Move the mains supply and its lead a metre from the guitar and
  the pedal, change nothing else, re-run: if the 150 Hz line falls, part of run 20 was the field off
  the lead rather than leakage through the supply.
- **The playback arm's flat +4.5 dB**, above.
- **The generated pages misread a live input.** The template compares the quietest arm against the
  bench test's codec-only bar of −75 ± 3 dBFS and says the codec block would be painted; with a
  guitar on the input and the host on mains, run 16's page says "6.5 dB outside". That bar assumes a
  shorted input, so the sentence is a misattribution whenever a source is connected — the same trap
  runs 10/11 fall into. The state line is the only thing that distinguishes the two cases, and the
  wording is generated by `scripts/noise-document.py`.

## How it was measured

`scripts/codec-input-noise.py` on vip: three arms, 20 s each, analysed from 2 s in, channel 0 = LIN1,
dBFS at 1.0 V rms full scale, 20 Hz–20 kHz unweighted and A-weighted, with the raw unbanded RMS
alongside. It takes the Core host's lock, stops `namchaind` for the `arecord` arms, restores it
afterwards, and records the kernel, the attempts and the owner's state line in `state.json`. The pages
and graphs come from `scripts/noise-document.py`, which checks its own RMS against
`scripts/codec-noise.py` for every capture (0.00 dB on all sixty) and recomputes each run's figures
from the same captures this file quotes. The captures and the playable copies stay out of git, by a
`.gitignore` in each run's directory; the numbers, pages, states and kernel messages are tracked.

## The evening's runs, 21–31 — a further fault, and the corrected board's number

The owner kept going after this file's twenty runs and made eleven more, and found **another wiring
fault**: `SW-C` and `LIN1` were **swapped on board 1**, now corrected. Their own state lines date the
discoveries — run 25 is `SW-C _actually_ jumpered to SW-I (Inst)`, run 31 is `LIN 1 _actually_ wired
to input board LIN1` — which means runs 21–30 were made with the swap in place. In that state the
follower's *output* drives the input network (so the node is actively driven and its pickup is
shorted) while the codec's ADC input sits on the op-amp's + input.

**So run 30's excellent figure is the mis-wired state, not the pedal.** Its 32–63 Hz band is 27 dB
below run 29's and its 125–250 Hz band 20 dB below, with every band above 4 kHz unchanged — an input
path that is not connected, rather than a quieter input. Run 29 (same state, amp not connected) reads
−76.24 unweighted; run 30 (amp connected **and powered**) reads −90.42 with 50 Hz at −106.1.

**Run 31 is the first measurement of the corrected board, and it is the number to keep**: engine
**−86.53 dBFS unweighted, −89.92 dBFS(A)**, 50 Hz at **−93.7 (20 µV)**, 47.2 µV total; playback
−90.38 dB(A); capture-only −90.85 dB(A). That is 1.5 dB(A) above the codec with its own input shorted
at its pin (run 1, −91.39) — with a guitar at 10/10 on a 20 cm cable, the Out L circuit wired and
connected to a powered hifi amp, and the host on an **Apple charger** (a third mains brick; its 20 µV
is far below the Pi 45 W supply's 258 µV, but nothing about it is comparable yet, because the wiring
changed underneath it — a clean trio in one state is still the test).

Two things the evening's numbers say that the afternoon's did not:

- **The hum no longer tracks the input node's impedance.** From an empty node with no jack (−73.6) to
  a guitar plugged in (−77.9) it moves **4.3 dB**, against **31.8 dB** in the afternoon (open node
  −40.0, guitar −71.8); and the Line → Inst change dated at run 25 moves it **0.7 dB**. So the
  node-pickup model that fits runs 4, 16 and 17 does not explain the evening, and the Inst/Line
  prediction in the "Open" list above is **not supported** by these runs.
- **A powered amp on the output may be worth a lot** (run 30, up to 27 dB in the LF bands), but that
  is confounded with the fault. The clean pair is run 31's exact state with the amp in and out.

The state-line lesson repeats a third time: the line records what was *intended*, the board holds what
is, and the corrections are dated only where the owner noticed them. Runs 16–24 were most likely in
**Line** despite their lines saying Inst — which is what the owner said at the time — so their numbers
are Line numbers, and the toggle's effect is still unmeasured in a state whose wiring is certain.

## The same evening: it plays, and it plays heavy rigs without a glitch

Not a noise measurement, and the best result of the day. The owner play-tested **two deliberately
ridiculous rigs** — NAM captures that are already amp+cab, stacked into one another: `Bob` (an Ampeg
SVT VR / 8×10 / Beta52A into a YA AMPG 410 HS Mix 02 cab, then a Fender Super Reverb EQ, then an
Ampeg VT-40) and `Standard` — editing on the fly, playing, and switching rigs: **no glitches**, 0
xruns, 48 kHz at 64-frame periods, engine `running`, DSP 73%. Screenshot:
[2026-10-13-two-heavy-rigs-playtest.png](2026-10-13-two-heavy-rigs-playtest.png).

Two things in that panel are worth knowing rather than worrying about: the engine reports
**`Health warn`**, and it tells the UI that one node "is charged the unknown cost 0.050 of a core".
The unknown-cost row is the cost table's known open item (`devices/vip/cost.json`'s provenance, and
`pedal-measure`'s job to fill the rows this device has no number for) — it is the engine being honest
about a number it does not have, not a fault seen in playing. The warn is not explained by this file
and is left as an observation.


