# The Pico ↔ Core host UART protocol

**Status:** draft 2, **agreed and in force 2026-10-06 as version 2.0** — the review's eight points
stand and U8 is decided (both below). The firmware (`firmware/src/protocol.c`, flashed as
`bb6dde1`) and `pedald` (`devices/common/rootfs/usr/local/lib/pedald/protocol.py`) both speak it,
the bench loopback passed against the flashed firmware — its refusal check included — and the live
pair holds a 2.0 session on vip. A different major is refused with `ERROR` rather than half-spoken.
Evidence: [bench-results/2026-10-06-draft2-swap-bench.md](../bench-results/2026-10-06-draft2-swap-bench.md).
This is the contract for plan Phase 3 step 3, and it
is kept here because both ends live here: the Pico firmware (`firmware/`) and the pedal service
(Phase 3.2). The Core-side port is Phase 3 step 4 (see Transport); the port is not part of this
contract. Engine control is not here either — that is namchain's protocol 2 over TCP, and the
pedal service speaks it.

## What the link carries, and what it never carries

Carries:

- events from the physical controls: footswitches, the panel, DIN MIDI in, and (if fitted) the
  expression jack — one vocabulary, one message (CLAUDE.md: footswitch and MIDI events produce
  identical UART messages)
- the little the Pico needs to display and to hold the bypass relay: the rig name and position,
  health, audio-ready.

Never carries (D2, D4):

- rig documents, models or IRs, or any app traffic — those go over TCP to the pedal service
- engine control (that is protocol 2), codec registers (the Core host owns I2C), or anything
  that puts the link in the audio path.

Debug text does not belong on this link: the firmware prints to its USB CDC, the service to its
journal.

## Transport

- UART, 8N1, no parity, no flow control.
- **115200 baud** to start. Worst-case frame is 6.1 ms (see Timing); a real event is under 1 ms.
  If step 4's measurements show the event-to-sound budget needs it, both ends move together and
  this line changes.
- Pico side, on the bench: UART0, **GP0 = TX, GP1 = RX**. (The pins, the fault each lead
  produces and how to check it are in `devices/common/pedal-interface.json`, which
  `scripts/diag` checks against: docs/diagnostics.md.) The panel wiring is step 5's business.
  RX is pulled up, because a floating RX invents bytes.
- Core host side: a UART on the 40-pin header that carries **nothing but this link**: no kernel
  console, no getty, no SysRq. On piv, header pins 8/10 are `ttyAMA0`, and its kernel console is
  there (`console=ttyAMA0,115200`), so step 4 either moves the console or takes another UART. A
  console would put boot messages on the Pico's RX, and a Pico that resets holds its TX low,
  which a console reads as a break: the start of a SysRq. Both ends are 3.3 V.
- On **vip** the header UART is RP1's UART0 (`serial@30000`, pins 8/10 = `ttyAMA0`) and the console
  is elsewhere (`ttyAMA10`), so the link has the port to itself. The stock device tree ships that
  node `status = "disabled"`, and `enable_uart=1` in the boot partition was not enough to bring it
  up after a card rewrite on 2026-10-05 — so the pedal enables it itself: `pedal-uart.service`
  loads `devices/common/rootfs/etc/pedal/uart/uart0-enable.dts` before `pedald.service` starts.
  That is the same runtime-overlay arrangement the codec uses, and for the same reasons. If
  `/dev/ttyAMA0` is missing, that unit is where to look:
  [bench-results/2026-10-05-header-uart-disabled.md](../bench-results/2026-10-05-header-uart-disabled.md).
- Byte order: little-endian for multi-byte integers. A string is a `str8`: one length byte, then
  that many bytes of UTF-8, not NUL-terminated.

## Framing

```
 offset   0      1      2      3      4 .. 3+len     4+len  5+len
        +------+------+------+------+-------------+------+------+
        | 0xA5 | 0x5A | type | len  | payload     | crcL | crcH |
        +------+------+------+------+-------------+------+------+
```

- `0xA5 0x5A` is the sync pair. It may occur inside a payload; the CRC is what makes that
  harmless.
- `len` is 0–64. A longer payload is a protocol error (drop the frame).
- `crc` is **CRC-16/CCITT-FALSE** (polynomial 0x1021, init 0xFFFF, not reflected, no final xor)
  over `type`, `len` and `payload`, sent little-endian. Check value: `"123456789"` → `0x29B1`.
  Both ends must agree on this; it is the one thing worth a test vector. (Draft 1 said "over
  `type` and `payload`"; both implementations have always included `len`, which protects it.)
- Resync: after a bad CRC or a bad length, resume scanning for the sync pair at the byte after
  the first sync byte. A frame is dropped silently — validity is the only acknowledgement at
  this layer.
- Frames are the only thing on the wire. No text, no echo.

## Session

The Pico boots in milliseconds; the Core host takes ~20 s to have audio (plan 1.7). So the Pico
hunts:

1. The Pico sends `HELLO` at boot, then every 1 s until answered.
2. The Core answers `WELCOME` and immediately sends `STATE`.
3. The session is up. Any valid frame resets the 1 s link timer.
4. On 1 s without a valid frame, both ends drop the session and the Pico returns to step 1.
   **The Core re-establishes on any valid frame, not only on `HELLO`**: it answers a frame that
   arrives while it thinks the session is down by sending `WELCOME` and `STATE` again. Once the
   Pico's session is up the firmware never sends `HELLO` again — it holds the session open with
   `PING`s and answers the Core's — so a Core that waited for a `HELLO` after dropping its half
   would wait for ever, while its own `PONG` replies kept the Pico up. That is not hypothetical:
   on vip (2026-10-04) `/status` read `session: false` while the Pico's console read `session=1`
   and a steady stream of `pong` lines, and neither end could escape on its own. The firmware's
   `WELCOME` handler is idempotent, so re-`WELCOME`ing is safe in both directions. (Measured
   rule, not a proposal: `pedald` implements it and the bench needs it.)
5. **A `HELLO` is answered with `WELCOME` and `STATE` every time, session or not** (2026-10-06).
   The other half of the same asymmetry: a Pico that resets sends `HELLO`, and those `HELLO`s are
   themselves valid frames that keep the Core's link timer alive, so a Core that answered only the
   first one would leave the rebooted Pico hunting until the Core was restarted — the same
   deadlock with the ends swapped. Answering every `HELLO` costs one `WELCOME` per second while a
   Pico hunts, and the far end's `WELCOME` handler is idempotent, so nothing is disturbed.
6. **With no session the Pico answers only `HELLO`, `WELCOME` and `ERROR`.** A `PING`, `STATE` or
   `ACK` that reaches the Pico while it holds no session is ignored, so a Core it has refused
   cannot keep it half-alive; its own `HELLO` every second is unaffected. The Core keeps rule 4's
   re-establishment — a Pico whose session outlived a service restart holds it with `PING`s and
   will never send `HELLO` again, which is the deadlock rule 4 exists for — but it refuses a
   `HELLO` from another major and drops the session it holds (below). The two rules are not
   symmetric on purpose: each end refuses to be propped up by a peer it cannot read, and neither
   gives up the recovery path that was measured.

`HELLO` and `WELCOME` both carry `version_major` and `version_minor`. Same major is required. A
different major is a protocol error: the end that sees it sends `ERROR` (code 1, its own version
and the other's in the text) and holds no session; the Pico shows a fault and keeps its local
controls, and with no session the relay follows the link-down rule. A newer minor is fine:
unknown message types are ignored, and unknown bytes at the end of a payload are ignored.

**What a mismatch costs, measured rather than assumed** (2026-10-06). Draft 1's premise —
nothing outside the bench speaks it — died when `pedald` went into service, so draft 2 moved the
major to 2 and both ends refuse rather than half-speak. A pair that ignored the version would not
lose frames: the Core's `STATE` name and the Pico's `HELLO` firmware string are the only fields
that differ, and a draft-1 reader takes the `str8` length byte for the first character while a
draft-2 reader takes the first character for a length. The rig name is then wrong on the panel
and the firmware version wrong in the log, with everything else working — which is exactly the
failure that would waste an afternoon. Refusing is one `ERROR` a second while the pair disagrees,
and `pedal-diag` names it (`link.no_session`, plus the two versions in the line above it).

**Which end goes first.** Flash the Pico before deploying the service. New firmware with the old
service still deployed is refused at the Pico: `ERROR`, no session, the relay holding bypass, and
the pedal simply silent until the deploy. The other order is the worse one — the deployed
firmware is draft 1, whose `WELCOME` handler prints a version mismatch and **keeps the session it
already has**, so the new service sees a session, sends draft-2 `STATE`, and the panel shows a
garbled rig name until the flash. That is the afternoon the major exists to prevent, and it is
available only to whoever swaps the ends the other way round.

## Messages

| Type | Name | Direction | Payload |
|---|---|---|---|
| 0x01 | `HELLO` | Pico → Core | `ver_major`, `ver_minor`, `caps` u16 LE, `fw_version` str8 |
| 0x02 | `WELCOME` | Core → Pico | `ver_major`, `ver_minor`, `heartbeat_ms` u16 LE, `service_version` str8 |
| 0x03 | `EVENT` | Pico → Core | `seq`, `source`, `kind`, `a`, `b` |
| 0x04 | `ACK` | Core → Pico | `seq` |
| 0x05 | `STATE` | Core → Pico | `flags`, `rig_index` i8, `bank_index` i8, `bank_size` u8, `rig_name` str8 |
| 0x06 | `PING` | either | `nonce` |
| 0x07 | `PONG` | either | `nonce` |
| 0x08 | `ERROR` | either | `code`, `text` str8 |
| 0x09 | `LOG` | Pico → Core | reserved |
| 0x0A | `CFG` | Core → Pico | reserved |
| 0x0B | `BATTERY` | Pico → Core | `psu_present` u8, `rail_mv` u16 LE — proposed (battery meter, plan Phase 4) |
| other | — | — | ignore |

**Version 2.0 is this document**, and it is a wire change, not a formality. Draft 2's changes
were first written to keep 1.x, on the premise that nothing outside the bench spoke draft 1;
`pedald` had spoken it in service since 2026-10-04, so the major went to **2** instead: a
half-swapped pair is then refused rather than left trading frames it reads wrongly (what a
mismatch actually costs is under Session, and how the swap is made is under Testing).

`caps` bits: 0 relay, 1 MIDI DIN in, 2 display, 3 expression jack, 4–7 footswitch count
(0–15). The service uses them to refuse a mapping the board cannot honour instead of silently
doing nothing.

`ERROR.code`: **1 is a version mismatch**, the only one either end sends, and the field is a
`str8` text naming both versions ("service speaks 2.0, Pico 1.0"). The code space is otherwise
reserved; a code a reader does not know is a log line, not a fault.

`fw_version` is `git describe --always --dirty` of the tree the firmware was built from
(`working-across-repos.md`, rule 5).

`STATE.flags`: bit 0 `audio_ready`, bit 1 `engine_muted` (the engine's `engine.mute`; draft 1
called it `engine_bypass`, but the relay is the only bypass), bits 2–3 `health` (0 unknown, 1 ok,
2 degraded, 3 fault). `rig_index` is -1 when the service has no rig. `rig_name` is truncated to
48 bytes on a UTF-8 boundary. Every string is a `str8`, so any message can grow at its end: a
receiver ignores trailing bytes.

### EVENT kinds

| Kind | Name | `a` | `b` |
|---|---|---|---|
| 0x01 | `rig_up` | — | — |
| 0x02 | `rig_down` | — | — |
| 0x03 | `rig_select` | index | — |
| 0x04 | `bank_up` | — | — |
| 0x05 | `bank_down` | — | — |
| 0x06 | `bank_select` | index | — |
| 0x07 | `bypass_set` | 0/1 | — |
| 0x08 | `bypass_toggle` | — | — |
| 0x10 | `cc` | CC number | value 0–127 |
| 0x11 | `pc` | program 0–127 | bank 0–127 |
| 0x12 | `expression` | jack index | value 0–127 |

`source` is provenance: 0 unknown/bench, 1 footswitch, 2 MIDI DIN, 3 panel button or encoder,
4 service (tests). **The semantic message is `kind`, `a`, `b` — the same event from a
footswitch and from MIDI is the same message**; `source` exists for diagnostics and for the
MIDI-learn UI, and the service's mapping tables key on `kind`, never on `source`.

Raw MIDI arrives as `cc`/`pc` because the mapping (a trigger → an action) is the pedal service's
table, not the Pico's — that is what makes USB MIDI a firmware-only change later (debt register).

**Footswitches send what a MIDI controller would** (draft 2, U8; **decided 2026-10-06**).
Footswitches 1–3 send `cc` 80, 81 and 82, the general-purpose switch controllers, with `b` 127
on press and 0 on release. The service's map turns every `cc` and `pc` into an action
(`pedal-service.md`); by default 80 is `rig_down`, 81 `rig_up`, and 82 is the assignable one. A
press on the pedal and the same controller from the MIDI Commander are then the same message,
byte for byte apart from `source`. The semantic kinds stay for what only the Pico can say: the
panel's choices (step 7), and `bypass_set` for the panic bypass, whose long press stays local.
The decision changes the firmware only, and only when 3.5 builds the switches: `pedald` already
ships this map (`DEFAULT_CC` in `mapping.py`). `source` stays on every event, so a map that wants
to treat a footswitch differently from the same controller over MIDI can key on it later without
a wire change.

Kind 0x12 exists only while the expression-jack debt entry survives.

## Reliability

Events are the only thing here that is not idempotent, so:

- **One `EVENT` is in flight at a time.** The Pico keeps it until it is `ACK`ed. If no `ACK`
  arrives within 20 ms, it sends the same frame again, up to 5 times, then drops it and counts a
  lost event. With one in flight, events arrive in the order they happened; with several, a
  retransmitted one could land after a later one (`bypass_set` 1 after a 0, an old `cc` value
  after a new one).
- **Behind it, the Pico queues** in order, 16 deep. When the queue is full, a new value for a
  controller already waiting in it (`cc` *n*, `expression` *n*) replaces the waiting one, since
  the newest value is the one that matters; anything else is dropped and counted. The firmware
  today refuses a new event while one is pending, which is enough for the bench's console; the
  queue comes with step 5, with the switches and MIDI.
- The Core **dedupes on `seq`**: a repeat of the last `seq` it applied is `ACK`ed again and not
  re-applied, so a lost `ACK` cannot double-step a rig. **The dedupe belongs to the session**: the
  Core forgets it when it sends `WELCOME`, because a Pico that reboots starts its `seq` again.
- **An `EVENT` still unacknowledged when the session drops is dropped** and counted lost. It is
  not sent after the reconnect: a press must not act seconds after it was made.
- `STATE` is idempotent. The Core sends it on every change, at least once a second, and after
  any `EVENT` — so the Pico converges after a link flap without any request. It is never
  acknowledged.
- Supersession is the service's rule, not the link's (D10: one switch in flight, a newer request
  replaces the pending one). The link keeps order; the service decides what a burst means.

## Failure and safety

- **Link down** (1 s without a valid frame): the Pico shows it (LED/display, steps 5 and 7). What
  the relay does then is the pedal service's relay rule (`pedal-service.md`), proposed and yours
  to decide: bypass once the link has been down for 5 s, longer than a service restart, so a
  service crash never clicks the relay but a hung or rebooting Core host doesn't hold the pedal
  silent. Draft 1's "leave the relay where it is" is kept there as the alternative.
- **Boot and power loss**: the relay's de-energised state is bypass (step 6); the Pico energises
  it only after a `STATE` with `audio_ready`. That is a physical rule, not a protocol one, and it
  survives a dead Pico and a dead service. A Core host that reboots while the Pico stays powered
  is the link-down rule's case.
- **Panic bypass** (long press) is a Pico-local action; it is also sent as `bypass_set` so the
  service and the display agree.
- **Service down must never mean audio down** (D4): the service is not in the audio path, so this
  link dying cannot stop the engine. What the Pico loses without a service is rig switching, not
  sound.

## Timing

At 115200, 10 bits per byte:

| Frame | Bytes | Time |
|---|---|---|
| `ACK`, `PING`, `PONG` | 7 | 0.6 ms |
| `EVENT` | 11 | 1.0 ms |
| `STATE`, 24-character rig name | 35 | 3.0 ms |
| longest possible | 70 | 6.1 ms |

Events add about a millisecond to D10's 50 ms; that budget belongs to the service and the
engine. Heartbeats at 250 ms with nothing else happening are about 0.4% of the link.

## Open, and deliberately not settled here

- The baud rate, if step 4 measures that 115200 is too slow (it will not be, for events).
- MIDI channel: `cc`/`pc` ignore it today (one controller). A second controller needs a field,
  and a minor version bump. **Settled 2026-09-28** (`docs/pedal-service.md`): ignored for now;
  the reserved `CFG` carries a channel filter when a second controller makes it matter.
- 14-bit CC and expression: 7 bits today; the Commander's expression sends CC11/CC4, which is
  fine. The pedal's own jack would want more resolution if it survives the debt register.
- `LOG` and `CFG` bodies are reserved, not specified.
- Whether `STATE` should carry more engine detail (`engine.status`'s issues, overruns). The
  answer is probably: no — health is for the panel, detail is for the app.

## Testing

- `firmware/tools/echo-test.py` proved the UART and the wiring (step 1). It needs
  `FW_ECHO=1 firmware/build.sh`. Evidence: `bench-results/2026-09-28-pico-uart-echo.txt`.
- `firmware/tools/protocol-test.py` is the frame-level loopback: it plays the service side
  and checks the session, heartbeats both ways, an EVENT whose ACK is deliberately dropped
  (retransmit, then no further copies), STATE, link-down recovery, and since 2026-10-06 a
  `WELCOME` from another major being refused with `ERROR` and no session.
  Both ends implement this document now — the firmware (`firmware/src/protocol.c`, flashed as
  `bb6dde1`) and `pedald` (`devices/common/rootfs/usr/local/lib/pedald/`, design:
  `docs/pedal-service.md`), whose own suite is `devices/common/test-pedald` (194 tests, no Pico
  needed). The swap ran on 2026-10-06, and the loopback with it: it was run **on vip** rather than
  through the Debug Probe, because the probe's UART lead would not make contact at the Pico's pins,
  and it passed every check against the flashed firmware; `pedald` was applied in the same stop.
  Evidence: `bench-results/2026-10-06-draft2-swap-bench.md` (the run's transcript, and the two
  measurements that found a crossed signal pair), and `bench-results/2026-09-28-pico-protocol-loopback.txt`
  for draft 1 on the Mac bench.
- It also sends a frame header whose length swallows the start of a good `STATE`, and checks
  that the `STATE` still arrives (Resync, U3). The firmware before U3's fix fails that check.

## Claude's review, 2026-09-28

Checked against both ends as built (`firmware/src/protocol.c`, `firmware/tools/protocol-test.py`),
against the Core hosts, and against the pedal service's design. The shape is right, and draft 2
keeps it: a sync pair and a CRC, a versioned handshake that tolerates a newer minor, heartbeats
both ways, acknowledged events with a provenance byte, idempotent `STATE`, and nothing on the
wire but frames. The bench evidence is good: exact, and honest about what it doesn't cover.
What changed:

**U1. The CRC covers `len`.** Draft 1 said "over `type` and `payload`"; both ends have always
included `len`, and should, since it protects the length. Text only; no wire change.

**U2. A string at the end of a payload stopped `STATE` growing.** The name ran to the end of the
frame, so a field added after it would read as part of the name, while the session rules
promise that trailing bytes are ignored. Every string is now a `str8`. This is the one wire
change, and nothing outside the bench speaks draft 1.

**U3. The firmware didn't resync as the text says.** After a bad length or CRC it carried on from
the next byte instead of rescanning from the byte after the first sync byte, so one corrupted
`len` swallowed the good frames behind it. `protocol-test.py`'s decoder does it right, and said
it mirrored the firmware. Fixed in the firmware on this branch (compile-checked, not flashed),
with a bench check that fails on the firmware before the fix.

**U4. Several events in flight could arrive out of order.** Draft 1 said presses go "as they
happen", while the firmware keeps one in flight and refuses the rest. With retransmission,
several in flight can land out of order. Draft 2: one in flight, and a queue behind it.

**U5. Dedupe across a Pico reboot.** The Pico's `seq` starts again at 0; a Core that remembered
the last few from before would acknowledge new events and drop them. The dedupe now belongs to
the session. And an event pending when the link drops is dropped rather than applied late: the
firmware resumed retrying it after the reconnect (fixed on this branch).

**U6. The Core-side port must be the link's alone.** On piv, header pins 8/10 are `ttyAMA0`,
which carries the kernel console, so the link either needs the console moved or another UART. The
link's UART must carry nothing else; plan 3.4 now says so, and on vip the console is on
`ttyAMA10`, so pins 8/10 have the port to themselves.

**U7. `engine_bypass` was the engine's mute.** Renamed `engine_muted`, so "bypass" means one
thing: the relay.

**U8. Footswitch and MIDI messages weren't identical.** `CLAUDE.md` asks for identical UART
messages, and the handoff wanted them to converge in the Pico. Draft 1's footswitches sent
`rig_up` while a MIDI "next" button could only arrive as `cc` or `pc`, so the two met nowhere
unless the service's map could turn a `cc` into `rig_up`. Proposed, **yours to choose**: the
footswitches send what a MIDI controller would (`cc` 80–82), and the service's map, which D4
gives the service, turns every trigger into an action. The other way to make it true is for
the Pico to translate MIDI into the semantic kinds with a map the service sends over `CFG`: two
places that must agree, where this has one.

**Decided 2026-10-06: the footswitches send `cc` 80–82**, so a press on the pedal and the same
button on a controller are one message apart from `source`, and the mapping stays in the one place
D4 puts it — the service's table — rather than in a `CFG` map the Pico must keep in step. `source`
is what keeps the choice open: it is provenance today, and a map that wants a footswitch to mean
something different from the same controller over MIDI can key on it later with no wire change.
`pedald` needs no change for the decision (`DEFAULT_CC` in `mapping.py` already maps 80 and 81,
with 82 assignable); the firmware half lands with 3.5, when there are switches to send it.
