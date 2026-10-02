# 1.7's jack end: how the pedal's output was measured

2026-10-02. `../results.md` has the numbers; this is what each run here was and what it proved.

## The chain that was measured

```
Mac (sox, 220 Hz)  ──▶  SSL 2+ output  ──▶  socket A  ──▶  codec LINPUT1
                                                                  │
                                                          engine: last.json rig
                                                                  │
    SSL 2+ input 1  ◀── 100 Ω ◀── 100 µF (+ to codec) ◀── codec HPL
                (1 MΩ to ground)
```

The tone is played by `tools/measure-audio.py` out of the same interface it records, so both ends
of the run are on one monotonic clock, and the boot comes from `tools/measure-boot.py` on the
debug UART.

## The runs, in order, and what each one settled

| run | what it was | outcome |
|---|---|---|
| `patch-check` (in `..`), `patch-check2`, `patch-check3`, `hum-test` | recording the interface with and without the pedal's output connected | **the interface's own loopback is on inputs 3-8** — a tone "through the pedal" that survived vip's power cycle was the SSL talking to itself. A finger on the cable tip proved input 1 works |
| `line-check` | 1 kHz played straight to `hw:CARD=wm8960` with `namchaind` stopped (`aplay`) | the codec's DAC, output stage and the HPL fixture all work: −41.9 dBFS on channel 1, 52 dB above the floor |
| `input-check` | the SSL's tone into the pedal's input | nothing came back: the pedal's input side was dead |
| `guitar-check` | `namchainctl record` inside the engine, guitar played | capture peak −71 dBFS: the engine heard nothing |
| `touch-check` | the same, with a finger on the input | still nothing — LIN1 was not reaching the ADC |
| `guitar-check2`, `guitar-check3` | after the guitar lead was reseated in LIN1 | **−22 dBFS**: the input path was fine all along; the lead had come out |
| `chain-check` | the full chain, tone in and out | channel 1 carries the tone at −29.4 dBFS: input → rig → codec → fixture → jack |
| `boot-run` | **the measurement**: tone playing, both captures running, one plug pull | `channel1-tone.tsv` is channel 1's 220 Hz level per 0.5 s; `serial.log` is the boot; `audio.log` is the analysis |

Controls checked on vip before blaming wiring: `Capture Switch` on, `Capture Volume` 23, `ADC PCM
Capture Volume` 195, `Left Boost Mixer LINPUT1 Switch` on, `Left Input Mixer Boost Switch` on —
so the codec's capture path was correctly configured throughout.

## Caveats this measurement carries

- The fixture's 100 µF coupling cap makes both ends of the tone's envelope soft: it discharges
  through the interface's 10 kΩ in about a second, and charges again in about a second. So the
  onset is quoted to about a second, not to a millisecond.
- **HPR is not wired.** Only the left half of the fixture exists, so only channel 1 carries
  anything; that is Phase 2's board 1 work, not 1.7's.
- The tone comes back through a real rig (a slimmed Ampeg model and a cab), so its level wobbles
  between about −30 and −46 dBFS as the model's dynamics move. The presence test in
  `channel1-tone.tsv` is therefore a gate (−45 dBFS with tonality better than −5 dB), not a
  silence detector.
- Power-on itself — the instant the supply is applied — is still not on the wire; the run's
  numbers are anchored to the bootloader's first byte, as in `../results.md`.

## What was deleted

Thirteen WAV files, 460 MB, the raw captures of the runs above. The `audio.log` in each directory
keeps that run's full analysis (per-channel onsets and presence intervals), `boot-run/channel1-tone.tsv`
keeps the measurement's derived trace, `guitar-check/engine/meta.json` keeps the rig the engine
was running, and `../results.md` keeps the numbers.
