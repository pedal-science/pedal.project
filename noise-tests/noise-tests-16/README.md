# The codec's input noise — 2026-10-13

`scripts/codec-input-noise.py` on `vip`, 20 s per arm, analysed from 2 s in. State, as the owner described it: **LIN 1 wired to input board LIN1, input board GND to Codec GND. 9V battery + to V9, codec GND to battery -. U1 pin 3 short REMOVED. input board IN to jack tip, board GND to jack sleeve. 20cm TS cable in the jack, other end in the guitar, volume and tone at 10, player not touching the strings. SW-C jumpered to SW-I (Inst). No output device connected, Cioks out.**.


The graphs and the audio are in [index.html](index.html); every number is in [noise-numbers.json](noise-numbers.json); the engine and host state before, during and after is in [state.json](state.json). The captures are in `captures/` and the playable copies in `audio/`, both untracked.

| arm | what it is | unweighted | A-weighted | 50 Hz | raw (unbanded) | peak | rms | rms (A) |
|---|---|---|---|---|---|---|---|---|
| `engine-muted` | Engine running, muted — the pedal's normal state | -65.52 dBFS | **-86.33 dBFS(A)** | -69.6 dBFS | -65.51 dBFS | -58.91 | 529.9 µV | 48.3 µV |
| `playback-open` | Engine stopped, a silent playback stream open | -65.47 dBFS | **-84.50 dBFS(A)** | -69.5 dBFS | -65.46 dBFS | -58.32 | 532.5 µV | 59.5 µV |
| `capture-only` | Engine stopped, capture only (no playback stream) | -65.52 dBFS | **-87.01 dBFS(A)** | -69.5 dBFS | -65.52 dBFS | -58.11 | 529.7 µV | 44.6 µV |

The quietest arm reads **-65.52 dBFS** unweighted, **6.5 dB outside** the bench test's codec-only bar of -75 ± 3 dBFS — its “Codec input on its own” check would fail and paint the codec block for this.


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
