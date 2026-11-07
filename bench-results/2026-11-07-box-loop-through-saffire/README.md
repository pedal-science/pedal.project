# The box, looped through piv's Saffire (2026-11-07)

The first end-to-end test of **box** (vip as its Core, `fleet/builds/box.json`): a signal from an
audio interface into the pedal's IN, through `namchaind`, and out of the pedal's OUT back into the
interface.

## The setup

- **Interface:** Focusrite Saffire 6 USB on **piv** (`hw:CARD=USB`, 48 kHz, S24_3LE, 4 out / 2 in,
  full-speed USB).
- **Saffire output 2 → box IN.** Box OUT (the one fitted jack, OUT L) → **Saffire input 2**.
- **vip** as found: namchain `eba5eef` (17 commits behind), `devices/vip` applied at `cee2ad6`
  (behind `40b84f1`), kernel `…-qled2-trimmed`, which is not the one `components.lock` names. Nothing
  was deployed for this test.
- Every step ran under `scripts/host-lock --host vip`. Rigs went over TCP with ljoss's token
  (`tools/nc.py`). ljoss stayed connected throughout, and its "New Rig" was put back at the end.

## Results

**The box works end to end** once one wire was fixed: the codec's HP_L was not connected to the
output board properly (found by Rik with a meter; it read its 1.62 V bias at the codec's pin).

| Leg | Result |
|---|---|
| Saffire out 2 → box IN → codec LINPUT1 | **Works.** A −10 dBFS 1 kHz tone arrives at −12.1 dBFS RMS / −9.1 peak, clean (no 50 Hz, nothing else in the band) |
| The Saffire alone (out 2 straight into in 2) | Flat 40 Hz–18 kHz, THD+N −64.9 dB, −17.4 dB end to end at its gain setting, noise −100 dBFS. The reference for the rows below |
| Whole loop, pass-through rig at 0 dB, after the fix (`data/fixed-pass.result.json`) | **Works.** −23.9 dB end to end, so **the pedal itself is about −6.5 dB**, which is Headphone 115 (−6 dB). Flat within 0.7 dB from 40 Hz to 10 kHz, −1.4 dB at 15 kHz, −1.9 dB at 18 kHz. THD+N **−56.3 dB** (h2–h5 all below −78 dB). Noise in the quiet tail −98.9 dBFS, against the Saffire's own −100.3: the pedal adds almost nothing, and the 50 Hz hum seen before the fix has gone |
| namchaind, `Standard.json` (SD-1, VT-40, SVT 8x10, EQ, cab IR) | **Works.** It loads with nothing missing or trimmed, the tone is seen at every node, and at the Saffire it has the rig's sound: heavy harmonics and a cab's response (+15–17 dB at 100–250 Hz, −22 dB at 6 kHz, −33 dB at 10 kHz, relative to 1 kHz). Worst block 31–34% of the deadline; 0 new xruns, 0 over deadline, 0 guard trips, 0 failed nodes; cost 0.48 of a core, verdict `fits` |
| Before the fix: codec HP_L → box OUT → Saffire input 2 | Nothing arrived. Input 2 recorded −81 dBFS RMS, almost all of it 50 Hz hum, with or without the engine running |

The latency in the result files (`lag_ms`, about 300 ms) is the gap between `arecord` and `aplay`
starting, not the pedal's. This method can't measure the pedal's latency.

### Feedback through the Saffire's direct monitor

With `Standard.json` loaded and nothing playing, the output howled at full scale (+0.3 dBFS): one
steady tone that moved between runs (2309 Hz, then 3331 Hz), with no hum and no hiss. The engine's
input carried it at −50 dBFS. `engine.mute` dropped the input to −72 dBFS, and unmuting brought it
straight back (`tools/fb.sh`). So it was a loop. The pass-through rig, at −6.5 dB per trip, never
sustains it, and neither does ljoss's "New Rig" (+12 dB: −59 dBFS out with no signal). A high-gain
rig does.

**The loop ran through the Saffire's input 2, not through the pedal.** The Saffire's monitor mix was
already fully on playback. Rik moved the pedal's output to **input 1**, and the pass-through
measurement came out the same (−23.5 dB, flat, THD+N −56.7 dB: `data/in1-pass.result.json`). With
Standard idle, the engine's input then stayed at its floor (−71 dBFS against −72.6 muted,
`tools/fb2.sh`), so no loop was left. Input 2 leaks into output 2 inside the Saffire, by some route
the monitor knob doesn't control. **Loop through input 1.** The Standard result in the table was
taken on input 2, so its harmonics and response include some of that feedback.

### What a high-gain rig makes of the idle input

On input 1, with no signal, Standard still puts out −9 dBFS peak (−20.5 dBFS RMS in the engine's own
`engine.record` of the playback). The capture under it is −83 dBFS RMS, so the rig's gain at idle is
about +62 dB. The capture has the engine's **750 Hz family**: lines at multiples of 48000/64 Hz, the
period rate (3000, 3750, 4500, 5250, 6000 Hz and up, with 2250 Hz the strongest at the Saffire).
These were found at −109 to −110 dBFS in
[2026-10-12-codec-input-noise.md](../2026-10-12-codec-input-noise.md). This rig makes them audible.
A noise gate before the amps, or less gain, would hide them; reducing them at the source belongs
with that note's work, not here.

### The output: where it stopped (before the fix)

With `namchaind` stopped, vip played 440 Hz at −10 dBFS straight to the codec (`aplay`). At the same
time piv played 1 kHz into IN and recorded both Saffire inputs (`tools/split.sh`, `tools/tones.py`).
vip's capture had the 1 kHz at −12 dBFS. Saffire input 2 had no 440 Hz at all (−58 dB of its
power), only hum.

On the codec side everything is as it should be. The mixer matches
`devices/common/rootfs/etc/pedal/codec/wm8960.mixer`: Left/Right Output Mixer PCM on, Headphone 115,
Playback 255. DAPM has `HP_L` and `HP_R` **On** with bias On. So the break is after the codec's pins.
The Saffire looped onto itself was clean (above), which ruled out it and the cable. With a 200 Hz
tone passed through the engine, Saffire input 2 got only a trace at about −89 dBFS. That pointed to
an open circuit with only stray coupling across it, not a short. Rik found it with the meter: HP_L
was not properly connected to the output board.

### The input went quiet under a long-running namchaind

Before `namchaind` was restarted (it had been up 15 h 39 min, with 2 xruns), the same Saffire tone
read only about −71 dBFS at the engine's input, the same as no signal. After the restart it read
−9.1 at once. Two things changed between those readings: the restart, and the Saffire had then been
used for a while longer. So this does not prove the engine's capture had gone dead, but it is the
likelier reading. The log shows no `pcm_read` error (docs/audio-dma-irq.md). Worth watching for: run
`tools/poll.sh` against an engine that has been up for hours before restarting it.

## Files

- vip was power-cycled for the fix. After it came back, ljoss pushed its rig again by itself, and
  that rig was restored after each test (`tools/restore.sh`).
- `tools/`: the control client, the play-and-record script that runs on piv (`loop.py`: lead,
  1 kHz tone, gap, 20 Hz–20 kHz log sweep, quiet tail), and the per-step wrappers.
- `data/`: the loop results (`pass*.result.json`), engine status, and `Standard.json`'s load reply
  and per-node levels.
