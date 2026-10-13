# The codec's input noise — 2026-10-13

`scripts/codec-input-noise.py` on `vip`, 20 s per arm, analysed from 2 s in. State, as the owner described it: **LIN 1 wired to input board LIN1, input board GND connected to Codec GND, input board not connected to power or jack tip or jack sleeve. input board SW-C jumpered to SW-L. **.


The graphs and the audio are in [index.html](index.html); every number is in [noise-numbers.json](noise-numbers.json); the engine and host state before, during and after is in [state.json](state.json). The captures are in `captures/` and the playable copies in `audio/`, both untracked.

| arm | what it is | unweighted | A-weighted | 50 Hz | raw (unbanded) | peak | rms | rms (A) |
|---|---|---|---|---|---|---|---|---|
| `engine-muted` | Engine running, muted — the pedal's normal state | -62.18 dBFS | **-82.70 dBFS(A)** | -65.7 dBFS | -62.18 dBFS | -55.01 | 778.3 µV | 73.3 µV |
| `playback-open` | Engine stopped, a silent playback stream open | -62.08 dBFS | **-82.61 dBFS(A)** | -65.8 dBFS | -62.07 dBFS | -54.73 | 787.3 µV | 74.1 µV |
| `capture-only` | Engine stopped, capture only (no playback stream) | -62.01 dBFS | **-82.48 dBFS(A)** | -66.1 dBFS | -62.23 dBFS | -52.04 | 793.2 µV | 75.2 µV |

The quietest arm reads **-62.18 dBFS** unweighted, **9.8 dB outside** the bench test's codec-only bar of -75 ± 3 dBFS — its “Codec input on its own” check would fail and paint the codec block for this.

**All 3 arms agree to within 0.2 dB A-weighted**, so none of this is the engine or the converter's stream state: whatever it is, it is common to all three and sits before the converter — the wiring at the input node.

## What it is compared with

| when | state | unweighted | A-weighted |
|---|---|---|---|
| 2026-10-11 | engine, 64-frame periods, muted | -75.72 dBFS | -75.29 dBFS(A) |
| 2026-10-11 | engine, 1024-frame periods, muted | -79.09 dBFS | -79.73 dBFS(A) |
| 2026-10-11 | arecord alone | -75.83 dBFS | -75.75 dBFS(A) |
| 2026-10-11 | arecord + silent playback | -79.74 dBFS | -79.86 dBFS(A) |
| 2026-09-27 | 2a's bench record, LIN1 shorted | -90.60 dBFS | -93.50 dBFS(A) |

The 2026-10-11 rows are the codec-only captures in [../2026-10-11-codec-noise-spectra/README.md](../2026-10-11-codec-noise-spectra/README.md); the 2a row is that bench's own record. The bench test's “Codec input on its own” check reads the same measurement against a bar of -75 dBFS ± 3, and paints the codec block when it fails (`devices/common/rootfs/usr/local/lib/benchtest/catalog.py`).

## The run

- The engine: `active` before, `active` after; mute `False` → `False`; xruns `0` → `0`.
- Card `hw:wm8960`, format `S32_LE`, 20 s per arm, channel 0 = LIN1.
- Kernel `7.0.0-1017-raspi-realtime-numaemu3-dmaidle1-trimmed`.
- Arms run: engine, playback, alone.
- Attempts: engine 1, playback 1, alone 1.
- Kernel messages during the `arecord` arms: in `dmesg-playback-open.txt`.

## Running it again

    scripts/codec-input-noise.py --state "what is wired this time"

It takes the Core host's lock, stops `namchaind` for the `arecord` arms, starts it again afterwards and puts the mute back as it found it. `--arms engine` alone needs no interruption at all: the engine records its own capture while it runs.
