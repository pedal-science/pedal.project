# O3 on vip: files and the catalogue

2026-11-09, on `332a38b`, driven from the Mac by `check.py` under the host's lock (`run/check.json`). vip's
real library: 64 models and 520 IRs. Nothing of the test's stayed on the pedal: it ended on Bob, with the same
counts, and with its test files removed by ssh, since the API deletes no model or IR.

## Result

All of these passed:

- **Catalogue:** 27 templates checked against this engine's schema, none refused.
- **Listings:** nothing left to hash, and a second listing and a restart hashed nothing.
- **Download:** the sha256 of a downloaded model matches the listing and the `ETag`, and a matching `If-None-Match`
  is 304.
- **Upload:** a model and an IR from the Mac, stored and rescanned. A rig naming both played on the engine with no
  stand-ins.
- **Refusals:** an existing path is 412, no precondition is 428, a second file for an id is 409, a 44.1 kHz model is
  422, and a path out of the root is 400.
- **Audio:** 0 xruns and 0 guard trips.

## A press during uploads

Presses were sent to `POST /event` from the pedal itself, so the network isn't in the number, about ten a second.
Each one answers after the loop has run it and switched rig.

| | presses | median | p95 | max |
|---|---|---|---|---|
| Nothing else happening | 44 | 24.4 ms | 88.0 ms | 161.5 ms |
| During a 64 MiB upload | 185 | 24.3 ms | 60.6 ms | 144.9 ms |
| During 20 small uploads, each with a rescan | 32 | 25.9 ms | 103.7 ms | 125.3 ms |

The 64 MiB took 23.6 s over Wi-Fi, and pedald's memory rose 120 KB. A small upload took 0.23 s (median).

**This found a bug.** The first version fsynced the whole file at the end. One press then took 2200.8 ms, and the
Pico dropped its session and said hello again. An fsync of 64 MiB holds up the card's journal, and the loop's own
small fsync waits behind it. Flushing every 2 MiB as the file arrives (`332a38b`) removed it, and the session then
survived the whole run: 0 hellos.

Measured from the Mac over Wi-Fi, the same press took 626 ms (median) during the upload, against 44 ms idle. That
is the Wi-Fi link's queue, not the pedal.

## What this doesn't cover

- **A real footswitch during an upload.** The presses went through HTTP, which reaches the same loop.
- **Audio.** Nothing was connected to the pedal, so xruns are the only evidence that it kept playing cleanly.
- **Uploads while switching by MIDI, or several large uploads at once.**
