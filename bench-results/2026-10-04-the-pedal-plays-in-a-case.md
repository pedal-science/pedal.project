# The pedal plays, assembled, in a case — with the Pico on the link

**Date:** 2026-10-04, evening (the owner played it earlier the same evening)
**Question:** the parts have all been on the bench separately. Do they work as one pedal — the Core
host, the codec, the jacks and the Pico together, in a case, played through?

## Result

Yes. The pedal plays.

| | |
|---|---|
| Enclosure | a **temporary plastic box**, standing in for the aluminium case. The rear wall carries **IN, OUT L and OUT R** in the Neutrik jacks, in the arrangement the aluminium case will use |
| Power | vip's own **USB-C** supply lead comes through a hole in the rear wall straight into the Pi's USB-C port. No panel-mount extension yet |
| Pico | powered from one of vip's **USB-A** ports into its micro-B, and its **UART** is on vip's header (`ttyAMA0`, GP0 → pin 10, GP1 → pin 8, GND) |
| The owner's report | the codec works perfectly, `namchaind` works perfectly, ljoss sends rigs, it sounds great through the case, rigs can be edited and switched with no glitches and no delays, and the latency feels like zero (subjectively) |

The engine and the service agree, read from vip while the owner's rig was loaded:

| Check | Result |
|---|---|
| `namchaind` | `running`, `ok`, `hw:CARD=wm8960,DEV=0`, 48000 Hz / q64, `xruns 0`, `guard_trips 0`, `issues: []`, `device_lost 0`, `memory_locked true` |
| Rig | one chain, "Guitar", rig name **"New Rig"**, `rig_source: applied` — ljoss's document, arrived over TCP (1 connection) |
| Load | 106,622 blocks rendered, `worst_percent 20.34` (271 µs of the 1333 µs period), 0 over deadline, 0 over 90% |
| Memory | model budget 300,808 bytes used of 458,752, `over: false`; 52 models and 1,538 IRs in the library |
| `pedald` | `active`; `pedald 0.1 up: link /dev/ttyAMA0, http on 0.0.0.0:47820` |
| The link | `pedald: Pico says hello: fw '0.1', protocol 1.0, caps 0x0000` |
| Resume | `pedald: saved /var/lib/pedal/library/rigs/last.json (generation 1, params_applied 0, rig 'New Rig')` |

So the whole chain the plan has been building towards is one working thing on the bench: guitar into
the case's IN jack → the WM8960 → `namchaind` → HPL → the output fixture in the case → the amp. And
beside it, the pedal service is up on the Pico's link, writing the rig the app chose. The service's
own evidence — the link in both directions, `/status`, the three faults found getting there and the
deploy — is [2026-10-04-pedald-on-vip.md](2026-10-04-pedald-on-vip.md); this entry is about the
pedal as a whole.

## What this does not show

Everything here is either the owner's ear or a single snapshot of two daemons. None of it is a
measurement against the plan's gates:

- **Switching rigs is still the app's path, not the pedal's.** There are no footswitches, no MIDI
  in and no relay yet (3.5, 3.6), so the Pico's only job today is the link and its console. The
  switches the owner made went ljoss → `namchaind`.
- **The switching path is the cold one.** `rig.apply` measured 25–35 ms on piv, inside D10's 50 ms,
  but E1 found the first **170–340 ms** of a cold or silent-prewarm switch sounds wrong (up to
  +15 dBFS off). "No glitches" is the owner's ear, not the glitch detector, and no switch was timed
  at the jack. D10's gate is a switching soak, and it belongs to 3.8.
- **The latency claim is subjective**, as the owner says. Nothing has been measured end to end
  through the codec in this arrangement.
- **`transitions_started` is 0 on this `namchaind`.** The service was (re)started and the tree
  re-applied at 21:27:25 UTC, seconds before the snapshot, so this instance adopted the resumed rig
  and has switched nothing since. The owner's editing session was on the instance before it.
- **The Pico's firmware is `fw '0.1'`**, which no current checkout's `git describe` produces
  (both give a commit hash). Reflash from a known commit before trusting firmware-side numbers, as
  [2026-10-04-rewire-faults-and-the-pico-console.md](2026-10-04-rewire-faults-and-the-pico-console.md)
  says.
- **The Pico's power route through a reboot is untested.** It is on vip's USB-A, which is option 1
  of Phase 3.6's test: a Pi switches its USB-A power, and may cut it during a reboot or at shutdown.
  Until that is run, the relay rule cannot lean on "the Pico stays up".
- **The case is not the aluminium one**, and nothing is panel-mounted: the jacks are in a plastic
  rear wall, the display, footswitches, MIDI and the toggle are not fitted, and the analogue side
  still runs without board 1 (no input buffer, no output stage of its own — see
  [2026-10-04-case-first-sound-end-to-end.md](2026-10-04-case-first-sound-end-to-end.md)).

## Why it is worth recording anyway

It is the first time the pedal has been *played* rather than tested: a guitar into the case's own
jack, the rig edited and switched from the app while playing, and the Pico sitting on the link
underneath it all, powered from the Core host. Every earlier entry is a part under test; this one is
the assembled thing, and it is the state the plan's "Next session starts with" now describes.

It also quietly closes two plan items and gives a third its bench:

- Phase 3.4 — the Core host's link UART — is in service: `ttyAMA0` carries the frames, and it is
  `pedald`, not a test script, on the other end.
- Phase 3.2's v1 — the pedal service — is deployed and running on vip, with the link up.
- Phase 3.6's Pico power question now has its wiring on the bench, in the first of its two forms.
