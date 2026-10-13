# The codec's input noise — 2026-10-13

`scripts/codec-input-noise.py` on `vip`, 20 s per arm, analysed from 2 s in. State, as the owner described it: **LIN 1 wired to input board LIN1, input board GND to Codec GND. 9V battery + to V9, codec GND to battery -. U1 pin 3 short REMOVED. input board IN to jack tip, board GND to jack sleeve. 20cm TS cable in the jack, other end in the guitar, volume and tone at 10, player touching the strings. SW-C jumpered to SW-I (Inst). No output device connected, Cioks out. Core on battery (no mains power)**.


The graphs and the audio are in [index.html](index.html); every number is in [noise-numbers.json](noise-numbers.json); the engine and host state before, during and after is in [state.json](state.json). The captures are in `captures/` and the playable copies in `audio/`, both untracked.

| arm | what it is | unweighted | A-weighted | 50 Hz | raw (unbanded) | peak | rms | rms (A) |
|---|---|---|---|---|---|---|---|---|
| `engine-muted` | Engine running, muted — the pedal's normal state | -88.10 dBFS | **-91.00 dBFS(A)** | -97.5 dBFS | -87.44 dBFS | -73.56 | 39.4 µV | 28.2 µV |
| `playback-open` | Engine stopped, a silent playback stream open | -84.99 dBFS | **-87.50 dBFS(A)** | -97.7 dBFS | -84.28 dBFS | -70.98 | 56.3 µV | 42.2 µV |
| `capture-only` | Engine stopped, capture only (no playback stream) | -90.64 dBFS | **-94.94 dBFS(A)** | -97.6 dBFS | -89.55 dBFS | -68.47 | 29.4 µV | 17.9 µV |

The quietest arm reads **-90.64 dBFS** unweighted, inside the bench test's codec-only bar of -75 ± 3 dBFS.


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

- The engine: `active` before, `active` after; mute `False` → `False`; xruns `2` → `0`.
- Card `hw:wm8960`, format `S32_LE`, 20 s per arm, channel 0 = LIN1.
- Kernel `7.0.0-1017-raspi-realtime-numaemu3-dmaidle1-trimmed`.
- Arms run: engine, playback, alone.
- Attempts: engine 1, playback 1, alone 1.
- Kernel messages during the `arecord` arms: none.

## Running it again

    scripts/codec-input-noise.py --state "what is wired this time"

It takes the Core host's lock, stops `namchaind` for the `arecord` arms, starts it again afterwards and puts the mute back as it found it. `--arms engine` alone needs no interruption at all: the engine records its own capture while it runs.
