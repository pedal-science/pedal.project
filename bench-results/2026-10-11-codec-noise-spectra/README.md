# The pedal's noise, as graphs — codec and Core only

**Open [index.html](index.html) in a browser.** It is the document: one spectrum and one
octave-band chart per capture, the numbers beside them, and each capture's octave-band table.

The captures themselves are **gone**, and with them the page's play buttons — the only part of it
that needed the files. They were deleted on 11 October once this report had been read: 43 wav files,
260 MB, from the session directory, plus the 22 MB of normalised copies the buttons played. The
graphs, the numbers and `noise-numbers.json` are the record, and `make-document.py` is kept as the
method. It reads the captures, so it cannot be run until they are measured again.

## What was measured

The measurements that need nothing plugged in: the WM8960 codec on its jumpers to the Core host,
**LIN1 shorted to the codec's own GND**, the whole input and output circuits disconnected, the Pico
removed, nothing attached. So everything on the page is the pedal's own noise.

| capture | state | unweighted | A-weighted |
|---|---|---|---|
| `engine-p64` | engine running, 64-frame periods — the pedal's normal state | −75.72 dBFS | **−75.29 dB(A)** |
| `engine-p1024` | engine running, 1024-frame periods | −79.09 dBFS | **−79.73 dB(A)** |
| `arecord-alone` | engine stopped, no playback stream open | −75.83 dBFS | −75.75 dB(A) |
| `arecord-playback` | engine stopped, silent playback stream open | −79.74 dBFS | **−79.86 dB(A)** |
| `hum-reference` | *not* codec-only: board 1 at node B, everything on mains | −49.55 dBFS | −65.33 dB(A) |

The two findings the graphs are for:

- **The 750 Hz comb.** With 64-frame periods the spectrum has a line at every multiple of 750 Hz
  right across the band; those are 48 kHz ÷ 64, the engine's own period rate. At 1024-frame periods
  the family moves to 46.875 Hz and its harmonics and the floor improves 4.4 dB A-weighted — the
  engine at 1024 matches the converter with no engine at all (−79.73 against −79.86).
- **No hum in the codec-only captures.** There is no 50 Hz line in any of the first four spectra.
  Hum appears only in the reference, which is the one with board 1 attached: 50 Hz and its
  harmonics, 25 dB above what the same node gives on battery power.

Numbers are in [noise-numbers.json](noise-numbers.json); the page and every graph are built by
[make-document.py](make-document.py), which reuses the same Welch method as
`scripts/codec-noise.py` and checks its RMS against that tool. The raw captures are one directory
up in [../2026-10-11-first-sound/](../2026-10-11-first-sound/), where
[troubleshooting-log.md](../2026-10-11-first-sound/troubleshooting-log.md) holds every test of the
session in order.

## Rebuilding

    /Users/rik/.dsh/dsh-runtimes/dsh-primary-runtime/dependencies/python/bin/python3 make-document.py

numpy and Pillow come from the harness runtime; the system python3 has neither. **The captures it
reads were deleted**, so this only runs again if the five states are measured again — it also writes
the `audio/` files and the page's play buttons back when they are.
