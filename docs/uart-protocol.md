# The Pico ↔ Core host UART protocol

**Status:** draft 1, 2026-09-28. This is the contract for plan Phase 3 step 3, and it is kept
here because both ends live here: the Pico firmware (`firmware/`) and the pedal service
(Phase 3.2). The Core-side port is Phase 3 step 4 (a header UART, Console on ttyS2 32/33,
UART1 on pins 8/10); the port is not part of this contract. Engine control is not here either —
that is namchain's protocol 2 over TCP, and the pedal service speaks it.

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
- Pico side, on the bench: UART0, **GP0 = TX, GP1 = RX**. The panel wiring is step 5's business.
  RX is pulled up, because a floating RX invents bytes.
- Byte order: little-endian for multi-byte integers. Strings are UTF-8, not NUL-terminated;
  the length comes from the frame.

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
  over `type` and `payload`, sent little-endian. Check value: `"123456789"` → `0x29B1`.
  Both ends must agree on this; it is the one thing worth a test vector.
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
4. On 1 s without a valid frame, both ends drop the session; the Pico returns to step 1 and the
   Core waits for a `HELLO` (it may also re-`WELCOME` on seeing one).

`HELLO` and `WELCOME` both carry `version_major` and `version_minor`. Same major is required. A
different major is a protocol error: the Core sends `ERROR` and stops talking; the Pico shows a
fault, keeps its local controls, and keeps the relay where it is. A newer minor is fine: unknown
message types are ignored, and unknown bytes at the end of a payload are ignored.

## Messages

| Type | Name | Direction | Payload |
|---|---|---|---|
| 0x01 | `HELLO` | Pico → Core | `ver_major`, `ver_minor`, `caps` u16 LE, `fw_version` string |
| 0x02 | `WELCOME` | Core → Pico | `ver_major`, `ver_minor`, `heartbeat_ms` u16 LE, `service_version` string |
| 0x03 | `EVENT` | Pico → Core | `seq`, `source`, `kind`, `a`, `b` |
| 0x04 | `ACK` | Core → Pico | `seq` |
| 0x05 | `STATE` | Core → Pico | `flags`, `rig_index` i8, `bank_index` i8, `bank_size` u8, `rig_name` string |
| 0x06 | `PING` | either | `nonce` |
| 0x07 | `PONG` | either | `nonce` |
| 0x08 | `ERROR` | Core → Pico | `code`, `text` string |
| 0x09 | `LOG` | Pico → Core | reserved |
| 0x0A | `CFG` | Core → Pico | reserved |
| other | — | — | ignore |

Version 1.0 is this document.

`caps` bits: 0 relay, 1 MIDI DIN in, 2 display, 3 expression jack, 4–7 footswitch count
(0–15). The service uses them to refuse a mapping the board cannot honour instead of silently
doing nothing.

`STATE.flags`: bit 0 `audio_ready`, bit 1 `engine_bypass`, bits 2–3 `health` (0 unknown, 1 ok,
2 degraded, 3 fault). `rig_index` is -1 when the service has no rig. `rig_name` is truncated to
48 bytes on a UTF-8 boundary. A receiver ignores any trailing bytes, so `STATE` can grow.

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

Raw MIDI arrives as `cc`/`pc` because the mapping (PC → rig, CC → parameter) is the pedal
service's table, not the Pico's — that is what makes USB MIDI a firmware-only change later
(debt register).

Kind 0x12 exists only while the expression-jack debt entry survives.

## Reliability

Events are the only thing here that is not idempotent, so:

- The Pico keeps each `EVENT` until it is `ACK`ed. If no `ACK` arrives within 20 ms, it sends
  the event again, up to 5 times, then drops it and counts a lost event.
- The Core **dedupes on `seq`** over the last 8 sequence numbers: a repeat is `ACK`ed again and
  not re-applied. A lost ACK therefore cannot double-step a rig.
- `STATE` is idempotent. The Core sends it on every change, at least once a second, and after
  any `EVENT` — so the Pico converges after a link flap without any request. It is never
  acknowledged.
- Events do not queue on the Pico: presses are sent as they happen, and supersession is the
  service's rule (D10: one switch in flight, a newer request replaces the pending one).

## Failure and safety

- **Link down** (1 s without a valid frame): the Pico shows it (LED/display, steps 5 and 7) and
  **leaves the relay where it is**. A broken link is not evidence that audio is broken, and
  cutting a working audio path is the worse failure.
- **Boot and power loss**: the relay's de-energised state is bypass (step 6); the Pico energises
  it only after a `STATE` with `audio_ready`. That is a physical rule, not a protocol one, and it
  survives a dead Pico, dead service and a booting Core host.
- **Panic bypass** (long press) is a Pico-local action; it is also sent as `bypass_set` so the
  service and the display agree.
- **Service down must never mean audio down** (D4): the service is not in the audio path, so this
  link dying cannot stop the engine. What the Pico loses without a service is rig switching, not
  sound.
- The relay/link-loss policy above is the recommendation; the *decisions* around failure modes
  are step 2's (`docs/pedal-service.md`): **the relay stays where it is on link loss**, and
  `audio_ready` energises it at boot only.

## Timing

At 115200, 10 bits per byte:

| Frame | Bytes | Time |
|---|---|---|
| `ACK`, `PING`, `PONG` | 7 | 0.6 ms |
| `EVENT` | 10 | 0.9 ms |
| `STATE`, 24-character rig name | 34 | 3.0 ms |
| longest possible | 70 | 6.1 ms |

Events add under a millisecond to D10's 50 ms; that budget belongs to the service and the
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
  over the Debug Probe and checks the session, heartbeats both ways, an EVENT whose ACK is
  deliberately dropped (retransmit, then no further copies), STATE, and link-down recovery.
  The firmware implements this document today (`firmware/src/protocol.c`); the service end is
  still a test script until the service is built (design: `docs/pedal-service.md`, its v1).
  Evidence:
  `bench-results/2026-09-28-pico-protocol-loopback.txt`.
