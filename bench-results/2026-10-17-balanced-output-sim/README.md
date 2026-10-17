# One balanced output channel, simulated (2026-10-17)

Written by `schematic/balanced-output-sim.py` (LTspice 17, batch mode). The circuit is `schematic/balanced-output/balanced-output.kicad_sch`; the design is [docs/balanced-outputs.md](../../docs/balanced-outputs.md). The op-amp is a behavioural model (10 MHz, rail-to-rail, no current limit), so read the numbers as the circuit's, not the part's.

## Gain, symmetry and the mute (1 kHz; the receiver is 10 kΩ per leg)

| Case | pin 2 − pin 3 | pin 2 | pin 3 | pin 2 vs pin 3 | phase, 3 vs 2 | −3 dB low | −3 dB high |
|---|---|---|---|---|---|---|---|
| Line | +5.83 dB | -0.19 dB | -0.19 dB | +0.000 dB | -180.0° | 1.88 Hz | — |
| Mic | -14.33 dB | -20.35 dB | -20.35 dB | +0.000 dB | -179.8° | 1.78 Hz | — |
| Line, muted | -86.13 dB | -55.25 dB | -55.25 dB | +0.000 dB | -1.6° | 18.84 Hz | — |

0 dB is the codec's own level at HPL (1.0 V rms at full scale), so Line's +6.02 dB is 2.0 V rms, +8.2 dBu, between pins 2 and 3.

## Rejection of a voltage between the two grounds

1 V between the receiver's ground and the pedal's; what appears between pins 2 and 3.

| C17 and C18 | at 50 Hz | at 1 kHz |
|---|---|---|
| matched | 211.0 dB | 236.5 dB |
| 5 % apart | 70.1 dB | 96.1 dB |
| 20 % apart | 59.2 dB | 85.2 dB |

The receiver here is ideal: in the room its own rejection adds to these, or limits them.

## Power-up, the mute, and signal

- Largest voltage between pins 2 and 3 while muted (9 V arriving, VMID rising): **0.00 mV**; largest common-mode voltage: 0.56 V, which a balanced input rejects.
- Largest voltage between pins 2 and 3 in the 5 s after the mute releases: **0.58 mV**.
- Then −1 dBFS at 1 kHz: 4.92 V peak-to-peak between pins 2 and 3 (2.46 V on pin 2, 2.46 V on pin 3).

## Phantom power, then a short

48 V through 6.81 kΩ onto each pin at 1 s; pin 2 shorted to pin 1 for 10 ms at 3 s. Capacitor ESR 0.5 Ω.

- Pin 2 settles at 44.9 V with phantom on.
- The driver side of C17 (node H) stays between -0.60 V and 5.18 V (the op-amp's rails are 0 V and 9 V).
- Peak current in D9 when pin 2 shorts: **3.7 A**, 1.77 mC in all; peak in D8 when phantom comes on: 0.5 mA.
- Peak current the op-amp would carry, through R34: **51 mA** (the OPA2197 limits at about ±65 mA).

