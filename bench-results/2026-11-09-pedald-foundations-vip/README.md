# O2: pedald's foundations on vip: threads come back under churn — PASS

**pedald's thread count went from 3 to at most 9 under ten minutes of churn and back to 3.** Memory stayed at
22 MB (22.5 MB at most) and file descriptors returned from 15 to 9. 2026-11-09, on vip, from the Mac, with the
engine playing throughout: 0 xruns, 0 guard trips.

`churn.py` is the gate from `docs/pedal-service.md`, "Threads", plus abandoned event streams:

| Load, for 600 s | Count |
|---|---|
| Fresh connections, one `GET /status` each | 6557 (112 failed; the cap was full at times) |
| Requests on a kept connection | 8340 |
| Sockets dropped mid-request | 2721 |
| Sockets dropped mid-body | 1169 |
| Silent sockets, ended by the 5 s first-byte deadline | 195 |
| Event streams dropped with a reset | 287 (2 failed) |
| Bursts of 24 connections held for a second | 11, with 341 connections refused at the cap of 16 |
| Rig steps, `POST /event` | 30, all answered ok, all warm switches |

- **A listener on `/events` stayed connected throughout and heard all 30 steps** with no `resync`, while
  the streams around it came and went.
- **pedald used 1.8% of a core** while doing this (all of it on core 0, at nice 10).
- **Thread counts during the churn were 5 to 9**, with up to two streams open. `run/samples.json` has every sample.

`run/events-sample.sse` is the stream as a client sees it: `hello`, then for each press its `action` and one
`running`.

From the Mac, on the same day:

```
$ dns-sd -L vip _pedal._tcp
vip._pedal._tcp.local. can be reached at vip.local.:47820 (interface 11)
 api=2 engine=47810
```

## Real footswitches, 15:07 UTC

The Pico was reconnected at 14:48 (it had been unplugged, not at fault; fw `31a5c8d`, session up, 0 bad frames).
Each press and each release reached pedald once, on `f7e3764`. The stream is `run/footswitch-presses.sse`:

| Press | pedald received | `/events` said |
|---|---|---|
| Left | cc 80, 127 then 0 | `footswitch 1`, loaded Standard, warm |
| Middle | cc 81, 127 then 0 | `footswitch 2`, loaded Bob, warm |
| Right, short | cc 82, 127 then 0 | no action: nothing is mapped to it |
| Right, held | cc 82 and `bypass_set` 1 | bypass on, `source: footswitch` |
| Right, held again | cc 82 and `bypass_set` 0 | bypass off, `source: footswitch` |

The bank holds two rigs, so these presses can't show which way cc 80 and cc 81 step. Nothing here measured the
relay or the audio during the panic bypass.

**A slip while checking this.** Reading the Pico's console with a plain `cat /dev/ttyACM0` leaves the tty's echo on,
which sends the Pico's log back to it, and its bench keys `e`, `d` and `b` are real events. From 14:49:22 to 14:50:00
vip switched rigs about 1300 times and toggled bypass 5 times, with 0 xruns and 0 guard trips. It stopped when the
reader was killed, and an 8 s read after `stty raw -echo` caused 0 switches. Bypass was left on and was turned off with
one `POST /event`. Those keys stay live in the firmware.

## What this doesn't cover

- **The commits after the churn.** The gate ran on `6b7c001`. The two commits since (`9499387`, the session's
  clock, and `f7e3764`, reading status after a switch) changed the loop's order and add one status read per
  press. They were applied and exercised on vip, but the gate wasn't repeated.

## How to run it

Under `scripts/host-lock`, with a file holding vip's token:

```bash
python3 churn.py vip <token file> run 600
```

The token comes from `/etc/namchain/token` on the host. It restores the rig it started on, and it fails if it
can't read pedald's numbers, if the thread count doesn't return, if the cap was never reached, or if the listener
misses a step.
