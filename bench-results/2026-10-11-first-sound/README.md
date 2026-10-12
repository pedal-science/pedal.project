# First sound through board 1's breadboard, and the noise that came with it

2026-10-11, bench with the SSL 2+ Mk II on the Mac, board 1 on the breadboard, the WM8960 on
`vip`. The owner had plugged a guitar and amp in and heard "a lot of noise"; the SSL was
attached to measure what was actually there. This is what the measurement says.

## The chain as measured

```
Mac (sox)  ──▶  SSL 2+ Mk II output 1  ──▶  pedal IN jack  ──▶  board 1 (Line or Inst)
                                                                      │
                                                       codec LIN1 ◀───┘  (the follower's output)
                                                              │
                                                     namchaind on vip, document "Standard"
                                                              │
   SSL 2+ Mk II input 1  ◀──  pedal OUT L jack  ◀──  codec HPL (via the 10 µF + 100 Ω fixture)
```

The engine's document at the time was **not** idle: ljoss had loaded a rig called `Standard` at
11:30 (`pedald`'s log: `saved … rig 'Standard'`, `params_applied` climbing 25 → 37), and it is

```
in → gain +24 dB → nc.nam SD-1 (bypassed) → fx.amp.tonestack (bypassed)
   → nc.nam Deluxe Reverb (bypassed) → out
```

so the engine was a bare 16× amplifier of whatever reached the codec's ADC.

## What the engine saw and sent (its own level meter, `namchainctl levels`)

| When | codec ADC, L | codec DAC, L |
|---|---|---|
| as found, Line, rig live | peak −35.0, rms −42.0 dBFS | rms −18.0 dBFS |
| engine muted | peak −34.2, rms −40.9 | −200 (silence) |
| −30 dBFS 1 kHz tone into the pedal, Line, engine muted | peak −26.3, rms −32.2 | −200 |
| switch flipped to Inst | rms −54.9 | −200 |

Two things fall out of that table: the +24 dB gain node turns an input hum of ≈ −41 dBFS rms
into a continuous **−18 dBFS rms** at the codec's output, and muting the engine does not change
the input at all (−42.0 → −40.9), so the input hum is not crosstalk from the output.

## What the SSL measured at the pedal's output (input 1, 2-channel capture)

| State | unweighted RMS | A-weighted RMS | largest lines |
|---|---|---|---|
| engine live (`noise-as-found.wav`) | **−58.6 dBFS** | −69.4 dBFS(A) | 49.8 Hz −67.1, 99.6 −67.3, 100.3 −65.9, 249.8 −66.5 |
| engine muted (`noise-engine-muted.wav`) | **−98.1 dBFS** | −98.4 dBFS(A) | nothing above −107 |

A 39.5 dB difference: every audible decibel of that noise is the engine's output, and with the
engine muted the pedal's output is at the interface's own floor.

## The round trip works, both halves

`roundtrip.sh` sends a 1 kHz tone out of the interface's output 1 and records all eight of its
capture channels; `analyse-roundtrip.py` reports the tone's level per channel.

| capture | ch0 (analog in 1) | ch2, ch4, ch6 (the interface's own loopback) |
|---|---|---|
| engine live, 8 ch (`roundtrip-line.wav`) | 1 kHz **−63.7 dBFS**, rms −46.8 | 1 kHz −63.0 |
| engine live, 2 ch (`roundtrip-line-2ch.wav`) | 1 kHz **−65.4 dBFS**, rms −57.8 | — |
| engine **muted**, 8 ch (`crosscheck-muted.wav`) | 1 kHz **−133.6 dBFS** (no tone), rms −86.1 | 1 kHz −63.0 |

- The interface's own loopback puts the tone it was sent at −63.0 dBFS, so the pedal's round trip
  is within 1–2 dB of the level that went in: **audio passes in and out**, and board 1 → LIN1 and
  HPL → OUT L are both connected.
- The muted row is the control that identifies the channels: ch0 and ch1 are the analog inputs
  (the tone does not appear on ch0 when the engine cannot pass it), ch2/ch4/ch6 are the
  interface's playback loopback, ch3/ch5/ch7 are silent.

**Measurement caveat found here:** the same signal reads **11–12 dB higher** when the interface
is opened at eight channels instead of two (−46.4 vs −58.6 dBFS rms, the hum lines moving
together). It is the interface's own front end, not the pedal, so the noise figures in this file
are the 2-channel ones.

## The hum on the input, and which way it comes in

A 20 s capture of the codec's own ADC at **Inst**, with the engine muted
(`adc-inst-hum.wav`, from `namchainctl record`):

```
unweighted RMS  -54.20 dBFS     A-weighted  -65.04 dBFS(A)     peak -45.25 dBFS
49.8 Hz -57.54   99.6 -66.87   100.3 -65.71   1500.0 -71.74   2250.0 -77.04
```

The flip Line → Inst (in the level log, `level-watch-ab.txt`, 13:21:46: a full-scale click, peak
0.0 dBFS — the switch's break-before-make transient) took the input from **−40.9 to −54.9 dBFS
rms**: Inst is **14 dB quieter**, not 9.7 dB louder.

That direction is the evidence. In this input stage the follower's node is:

- at **Inst**, node A: shunted to the cable and the outside world by C5 — 31.8 kΩ at 50 Hz —
  in parallel with R5 + R6 = 1.01 MΩ to the bias;
- at **Line**, node B: behind R5, so 712 kΩ to the same place, in parallel with R6 = 330 kΩ.

So a hum **voltage in series with the cable** (a ground-loop EMF between the interface and the
pedal) would be divided by the pad and be **9.7 dB louder at Inst** — the opposite of what was
measured. A hum **current injected at the node** (or a bounce of the board's own ground or bias,
which sees the same two impedances) is about **17–20 dB louder at Line**, and 14 dB is what the
meter shows. The hum is therefore being picked up at the high-impedance input node and its
wiring, not arriving down the cable.

It is also 40 dB above 2a's bench floor (−93.5 dBFS(A) with LIN1 shorted, −77 dBFS with the
interface attached), so it is a breadboard layout problem to fix rather than a wiring error to
hunt for: short leads at the switch and U1's + input, distance from mains leads and the supply,
and the soldered board's shorter tracks.

## The switch, and the interface's cable, are both innocent

Four more readings, all at the codec's ADC with the engine muted (`level-watch-ab.txt`):

| configuration | the follower's node | input, rms |
|---|---|---|
| switch fitted, lever at Line | B — 225 kΩ at 50 Hz | −40.9 dBFS |
| switch fitted, lever at Inst | A — 30.9 kΩ | −54.9 dBFS |
| switch **removed**, SW-L jumpered to SW-C (so permanently Line) | B — 225 kΩ | **−54.6 dBFS** |
| that, with the interface's lead **out** of the input jack | B — unshunted | **−53.8 dBFS** (with it in: −54.0) |

- **The switch was 14 dB of it.** The same node, the same impedance, 14 dB less hum once the
  switch and its three leads are out of the circuit. A toggle's lever is bonded to its bushing and
  frame, and that assembly *is* the switch's common — so the lever is a metal rod wired onto the
  follower's input, and the higher-impedance Line tap divides its current worse. Removing it drops
  node B to the Inst figure.
- **The interface's cable contributes nothing.** Unplugged, the input reads −53.8 dBFS; plugged it
  reads −54.0. There is no ground loop through the Mac and the SSL, and the pickup is local to the
  node on the breadboard rather than arriving down the cable — which also rules out the
  series-EMF model for good, in the same direction the Inst/Line pair did.
- **A hand is 20 dB of it.** The bursts at 13:26:09–13:27:05 (peak 0.0 dBFS, rms −2, about 45 s)
  and 13:35:48–55 (−34 dBFS, then −9.5) are hands on the node and on the plug: the body couples
  the field straight into a 200 kΩ node.
- Predictions still to test: jumper **SW-I** (node A, 30.9 kΩ) instead → ≈ −71 dBFS if the hum is
  a current divided by the node's impedance; and jumpering the node to the board's **0 V** → the
  codec's own floor if the board's ground is quiet.

## Files

| File | What it is |
|---|---|
| `noise-as-found.wav`, `noise-engine-muted.wav` | 15 s and 10 s at the interface's input 1, engine live then muted |
| `compare-2ch.wav`, `compare-8ch.wav` | the same signal captured at two and eight channels (the 11 dB caveat) |
| `roundtrip-line.wav`, `roundtrip-line-2ch.wav`, `crosscheck-muted.wav` | the round trip, eight channels, two channels, and the muted control |
| `adc-inst-hum.wav`, `adc-inst-hum-meta.json` | the codec's own ADC, 20 s at Inst, via `namchainctl record` |
| `level-watch-ab.txt` | the engine's levels every two seconds across the switch flip |
| `roundtrip.sh`, `analyse-roundtrip.py`, `watch-levels.sh` | how each measurement was taken |
| `tone-1k-m30.wav`, `tone-1k-m50.wav`, `tone-1k-m60.wav` | 1 kHz at −30, −50 and −60 dBFS peak, in output 1 only |

---

**The captures this file describes were deleted on 2026-10-11**, at the owner's instruction, once
the report had been read: 43 wav files, 260 MB. The tables above are the record of what they held;
the log's closing note says what went and what it costs to re-run anything that needed them.
