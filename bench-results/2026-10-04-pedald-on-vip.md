# pedald on vip: the pedal service's first run, and the three faults between here and there

**Date:** 2026-10-04
**Question:** does the service from [docs/pedal-service.md](../docs/pedal-service.md) run on the
Core host — the Pico link, resume, the bank and `/status` — without touching the audio path?

## Result

Yes. `pedald` v1 is installed on vip (`pedald.service`, commit `783a8de` then `dcaf0e2`), the
link is up in both directions, `/status` answers over the LAN, resume is saving, and the engine
and codec came through the deploy unchanged. Three faults were found on the way, one of them a
real hole in the protocol's prose.

## What is running

| | |
|---|---|
| The service | `pedald 0.1`, unprivileged (`User=pedal`, uid 988), `ProtectSystem=strict`, only `/var/lib/pedal` writable, token through `LoadCredential` |
| The link | `/dev/ttyAMA0` 115200: `session true`, `frames_ok` rising, `frames_bad 0`; the Pico's console shows `session=1` and both `ping N -> pong` and `pong N` (both directions) |
| `/status` | `401` without the token, `200` with it: `{service, engine, link, bank, bypass}`, engine `running`/`ok`, `rig_name 'New Rig'` |
| Resume | `last.json` written by pedald at the quiet window (`generation 1, params_applied 0, rig 'New Rig'`), `last.prev.json` kept, both owned by `pedal` |
| The engine | `running`, `health ok`, blocks ~760/s, `xruns 0`, `guard_trips 0`, card 0 `wm8960` |
| `pedal-resume` | retired: unit and script gone, its `ExecStartPre` is now `pedald seed` |
| The bank | empty (`size 0`): the library holds no stored rigs yet, so `rig_up`/`rig_down` have nothing to step to. That is v3's upload API, not a fault |

## What the tests do and do not cover

`devices/common/test-pedald`: **114 tests**, all passing. The link over a pty, the engine
against an in-process fake, the HTTP server with `http.client`, the protocol's codec
differential-fuzzed against `firmware/tools/protocol-test.py`'s decoder. Plus a local
end-to-end harness (`build/pedald-smoke.py`, gitignored): a real `namchaind` (`--backend null`),
a pty standing in for the Pico, and the whole path — HELLO → WELCOME + STATE, `/status`, an
EVENT moving the engine's rig, and resume saving it.

The unit tests need `pty`, `http.client` and `urllib`, so they run on the Mac, not on vip.
What they check from anywhere is that the service's modules import nothing vip lacks.

**The Core host is `python3-minimal`** — no `termios`, `http.server`, `socketserver`, `hmac`,
`urllib` (checked on vip). The design says "Python 3, standard library only", which is only
true of the *full* standard library, so the service works around the two that matter: the UART
is configured with `stty` and read with `select`, and the HTTP server is hand-rolled (bearer
compared in constant time — `hmac.compare_digest` does not exist there — and it fails closed on
an empty token). The alternative, adding `libpython3-stdlib` to the image, is one line in
`devices/vip/packages` and a reimage; not taken yet.

## The three faults

1. **`engine.status` nests its report** (`{"ok": true, "status": {...}}`) while `rig.get` puts
   `document` at the top level. The daemon read the counters from the wrong level, so the engine
   looked reachable and empty at once.
2. **A unit mismatch in the save rule**: the daemon passed seconds to `Resume.tick`, which
   measures the 2 s quiet window in milliseconds — a window of 2000 seconds, so resume never
   wrote. Found by the local end-to-end, which is the only place it shows.
3. **The session deadlock, which is the interesting one.** Once the Pico's own session is up,
   the firmware never sends `HELLO` again: it holds the session open with PINGs (250 ms) and
   answers ours. So a Core that ever drops its half — which the first second after `WELCOME`
   can do if the Pico's first PING is a moment late — waits for a `HELLO` that cannot come,
   while its own `PONG` replies keep the Pico up for ever. Measured on vip: the Pico read
   `session=1` and a stream of `pong` lines while `/status` read `session: false`, and neither
   end could escape. Any valid frame while down now re-establishes the session (the firmware's
   `WELCOME` handler is idempotent), which is a reading of "the Core may also re-`WELCOME`"
   that the contract's step 4 does not spell out; `uart-protocol.md` should say it.

   One consequence worth knowing: a service that **restarts while the Pico's session is up**
   never sees a `HELLO`, so `/status`'s `pico` object stays empty until the Pico itself resets —
   the link comes back (by the paragraph above), but the firmware's version is a fact only a
   `HELLO` carries. Seen on vip after the second apply: `session true`, `frames_bad 0`,
   `pico {}`.

## The deploy

`devices/vip/apply` is gated on the host being idle (rule 8), and `namchaind` counts as busy, so
the engine was stopped for each apply and started again — about a minute of silence each time,
after which it resumes `last.json`. The apply installs the service, creates the `pedal` user
(`systemd-sysusers`), retires `pedal-resume`, and restarts `pedald` only: the engine is not
restarted by it, and the codec and the rig were unchanged by the deploy.

`devices/vip/check`: *vip matches devices/vip and it is in force*. The applied stamp reads
`dcaf0e2-dirty` because the lock file was still uncommitted when the second apply ran; the next
apply on a clean tree re-stamps it.

## Next

- **The event path on the board is unproven** only because the library has no stored rigs: a
  press has nothing to load. The path itself is proven locally (EVENT → `rig.load` → the
  engine's rig changes). With one rig in `/var/lib/pedal/library/rigs/`, pressing `e` on the
  Pico's USB console should change the rig.
- v2 is the ready set (`rig.ready_set`/`rig.switch`) once namchain's M3 answers; until then the
  service switches with `rig.load`, which D10 keeps off the stage.
- ljoss's "my document wins" on connect (R6) still needs deciding before the footswitches
  change rigs under the player.
