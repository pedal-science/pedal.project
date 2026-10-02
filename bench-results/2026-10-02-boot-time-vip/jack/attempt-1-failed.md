# The jack end, attempt 1: failed, and why

2026-10-02. The first attempt at closing plan 1.7's jack end produced a number that would have
been wrong, so it is recorded rather than deleted.

## What was done

- `tools/measure-audio.py --device "SSL 2+ Mk II" --seconds 300` recorded the interface while a
  220 Hz tone at −20 dBFS was played out of the same interface.
- At the same time `tools/measure-boot.py` watched vip's debug UART, so the boot and the audio
  were on one monotonic clock.
- The owner pulled vip's USB-C about 30 s into the recording and plugged it back in.
- The boot itself was clean and is in `serial.log`: first bootloader byte at `T+24.077`
  (`power-on-reset 1`), kernel at `T+37.027`, so 12.95 s of pre-kernel time — the same as the
  earlier plug pulls. vip's journal: namchaind started at 5.76 s of kernel time, the rig
  published at 7.23 s.

## What the recording showed

The tone was present for the **whole** recording — a rock-steady −22.5 dBFS, including the five
seconds when vip had no power at all. The presence intervals only wobbled by a few dB at 41-43 s,
nowhere near the pull.

## Why: the interface's own loopback, and `-c 2` picked it

Recording all eight of the SSL 2+ Mk II's input channels while the tone played:

| channel | RMS | 220 Hz |
|---|---|---|
| 1 | −76.7 dBFS | −107.4 dBFS |
| 2 | −95.3 dBFS | −135.6 dBFS |
| 3-8 | −18.7 dBFS | −15.6 dBFS |

So the **analog inputs 1 and 2 were silent** — the pedal's output was not reaching the interface
at all — and channels 3-8 carried our own playback back into the recording, because the SSL
2+ Mk II loops its playback out onto those input channels. `sox -c 2` had grabbed a pair of
those, so the "tone" that seemed to survive the power cycle was the interface talking to itself.

The earlier "round trip confirmed" check was wrong for the same reason: it showed that the tone
was being *recorded*, not that it came *through* the pedal. A signal path is only proved by the
pedal changing it — which is exactly what the power pull did, and it changed nothing.

## What changed in the tool

`tools/measure-audio.py` now records `--channels N` (use 8 on this interface) and reports every
channel separately, each with its own onsets and presence intervals, and prints one line per
channel. A channel whose tone never changes across a power cycle is the interface, not the pedal.

## What is still open

- Whether vip's output reaches the interface at all (headphone out, cable, the interface's gain,
  physical input 1 or 2).
- The measurement itself: rerun once the pedal is on a channel that changes when it loses power.
