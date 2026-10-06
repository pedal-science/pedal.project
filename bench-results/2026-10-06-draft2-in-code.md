# Draft 2 is in both ends: the Pico link goes to protocol 2.0

2026-10-06. Plan 3.3's last two pieces, in one session: **U8 decided** (the footswitches send
`cc` 80–82 — recorded in `docs/uart-protocol.md`, `plan.md` and `docs/pedal-service.md`), and
then **the draft-2 wire itself**, written into the firmware and `pedald` together, with the
version bumped to **2.0** so that a half-swapped pair is refused instead of garbled.

**The board half landed later the same day** — flashed, loopback run, service deployed:
[2026-10-06-draft2-swap-bench.md](2026-10-06-draft2-swap-bench.md). Everything below marked "not
verified yet" was the state before that.

Nothing on the board changed: vip still runs the draft-1 pair, and the swap is a stop of its own
(see "What is not verified", below).

## What changed

**The wire** (draft 2's only wire change): every string is a `str8` — one length byte, then that
many bytes. `HELLO.fw_version`, `WELCOME.service_version`, `STATE.rig_name` and now
`ERROR.text`. Firmware in `firmware/src/protocol.c`, service in
`devices/common/rootfs/usr/local/lib/pedald/protocol.py`.

**The version is 2.0** at both ends (`PROTO_VERSION_MAJOR`, `protocol.VERSION_MAJOR`), and a
different major is a protocol error rather than a session: each end answers a mismatched
`HELLO`/`WELCOME` with `ERROR` (code 1, the two versions in the text) and holds no session. Why
the major and not 1.x: a pair that ignored it would not lose frames — the rig name and the
firmware string are the only fields that differ, and each draft reads the other's as garbage in
exactly those two places. A pedal showing the wrong rig name with a link that says it is fine is
the failure that costs an afternoon; an `ERROR` a second is not.

**Two session rules were made explicit, because they were half-implemented:**

- **A `HELLO` is answered with `WELCOME` and `STATE` every time**, session or not. `pedald`
  answered only the first, which left the *other* half of the 2026-10-04 deadlock in place: a
  Pico that resets sends `HELLO`, and those `HELLO`s are themselves valid frames, so the Core's
  link timer never expired while the Pico hunted for a `WELCOME` that never came. It only looked
  as if it worked because the two 1-second timers raced; a Pico reboot could have wedged the link
  until `pedald` restarted.
- **With no session, only `HELLO`, `WELCOME` and `ERROR` are answered.** A `PING`, `STATE` or
  `ACK` that arrives while the receiver holds no session is ignored, so an incompatible pair goes
  quiet on both sides instead of one end propping up a link the other has refused.

The firmware's `PROTO_STATE_ENGINE_BYPASS` became `PROTO_STATE_ENGINE_MUTED`, finishing U7 on the
Pico's side (the service already had it), and its `STATE` log line says `muted=`.

`pedal-diag` now names a version mismatch as the **first** likely cause of `link.no_session` when
the two versions differ — its report already carried the Pico's, and `pedald`'s `/status` now
carries the service's own (`link.protocol`), because "frames with no session" is exactly what a
half-swapped link looks like.

## What was verified here (Mac, no board)

- **`firmware/build.sh` builds clean.** `protocol.c` and `main.c` recompiled with no warnings;
  `build/pedal-firmware.uf2` is 67,072 bytes.
- **`devices/common/test-pedald`: 194 tests — 186 pass, 1 skipped, 7 errors.** All 7 errors are
  `test_link.LinkOverPty`, and all of them are in `setUp`: `pty.openpty()` raises
  `OSError: out of pty devices` in the sandbox this ran in. The same call fails outside the tests
  (`python3 -c "import pty; pty.openpty()"`), so they are environmental. **They need one run
  outside this harness to be called green.**
- The protocol suite alone (37 tests) and the diagnostics suite (68 tests) pass, including the
  new ones: a wrong-major `HELLO` is refused with `ERROR` code 1 and no `WELCOME`; a matching
  `HELLO` after a refusal still brings the session up; a wrong-major `HELLO` drops a session
  already held; `STATE` with trailing bytes decodes the name and ignores the rest; a short
  `STATE` does not invent a name; `0x0B` (`BATTERY`, Phase 4's) is ignored; and the diag report
  names the mismatch.

## What is not verified, and what it needs

- **The bench loopback has not run against the 2.0 firmware.** `firmware/tools/protocol-test.py`
  is updated for draft 2 and has a new check for the refusal itself (a `WELCOME` from major 1
  must draw `ERROR`, the console must say `version mismatch`, and the session must stay down).
  Its `wait_line` also now looks only at text arriving *after* the call — before, the second
  "session up" check was satisfied by the first one's output, so that check was vacuous.
- **The Pico is not reflashed.** It reports `fw '0.1'`, which no checkout's `git describe`
  produces, so flash it from a known commit as part of the swap.
- **Nothing is deployed.** The two ends must move in **one stop**, and the **Pico goes first**:
  flash it, run the loopback (its `WELCOME`/`STATE` come from the script, not from `pedald`), then
  apply `devices/` to vip and restart the service. That order matters, and the doc now says why:
  new firmware with the old service deployed is refused at the Pico — silent, relay on bypass,
  until the deploy — where the other order would leave the old firmware holding a session and
  showing a garbled rig name, because draft 1's `WELCOME` handler keeps the session it has.
- `devices/common/apply` refuses while `namchaind` is running, so the stop is also when the
  pending `dtoverlay-locked` change (2026-10-06) goes on the card.

## How to finish

```sh
cd pedal.project
firmware/build.sh && firmware/flash.sh          # the Pico, from a known commit (Debug Probe)
firmware/tools/protocol-test.py                 # the loopback: all checks, refusal included
# then, in the same stop and with namchaind stopped:
devices/vip/apply                               # takes the lock, backs up, applies, checks
scripts/components-lock                         # record what the host now runs
```
