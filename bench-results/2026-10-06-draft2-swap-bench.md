# The draft-2 swap, on the board: flash, loopback, deploy

2026-10-06, same session as [2026-10-06-draft2-in-code.md](2026-10-06-draft2-in-code.md). That
file wrote draft 2 into both ends and left three things owing: the Pico's flash, the bench
loopback, and the deploy. All three are done, and the live pair holds a **2.0 session**.

## What was done

1. **Flashed the Pico** from the committed tree, `bb6dde1`, over its own USB (`firmware/flash.sh`,
   picotool). The console then read `proto: hello sent (v2.0 caps=0x0000)` where the old firmware
   read `v1.0` — and the loopback's `HELLO` later carried `firmware='bb6dde1'`, so the binary
   names its commit (`working-across-repos.md`, rule 5).
2. **Ran the loopback** (`firmware/tools/protocol-test.py`) against the flashed firmware —
   every check passed, including the new one. Transcript below.
3. **Deployed the service**: `devices/vip/apply` with `namchaind` stopped (it refuses while the
   engine runs), which restarted `pedald` with the 2.0 code, then `namchaind` back up.
   `devices/vip/components.lock` moved to `bb6dde1` and is committed with this file.

## The loopback ran on vip, not on the Mac bench

The documented setup is the Debug Probe's UART bridge on the Mac. It was abandoned after the
probe's receive lead read nothing in two placements: yellow on the pin the user believed was GP0,
and then yellow on the very pin orange was proven to be on. The cable itself is good — shorting
the two leads' tips looped a pattern back byte-for-byte — so the fault was **contact at the
Pico's pins**, not the lead or the port. Meanwhile the orange lead's direction was proven the
other way: twelve `PING` frames written out of the probe reached the Pico, which logged and
answered each one.

So the loopback was run **on vip**, with the Pico's UART back on its header:

```sh
scp firmware/tools/protocol-test.py vip:/var/tmp/
ssh vip "sudo systemctl stop pedald; \
         sudo python3 /var/tmp/protocol-test.py /dev/ttyAMA0 /dev/ttyACM0; \
         sudo systemctl start pedald"
```

This is arguably the better test of the two: `/dev/ttyAMA0` is the production port, and the
script's termios setup is portable enough to run there. `pedald` has to be stopped for it,
because two readers on one tty steal each other's bytes.

**A crossed signal pair is the failure to know about.** Putting the Pico's two UART leads back
the wrong way round (GP0 on header pin 8, GP1 on pin 10) kills the link in **both** directions at
once, and neither end says anything useful: the Pico's `frames ok` stays at 0 and vip reads no
bytes at all, because each end's TX is fighting the other's TX while both receivers listen to
inputs. It was isolated with two measurements: reading `/dev/ttyAMA0` (silence), then writing ten
`WELCOME` v2.0 frames out of it and watching the Pico's console (no `session up`, `frames ok`
unchanged). Swapping the pair fixed it immediately.

## The run's output

```
probe:   /dev/ttyAMA0
console: /dev/ttyACM0

PASS HELLO received
      v2.0 caps=0x0000 firmware='bb6dde1'
PASS HELLO is version 2.x -- major=2
PASS session up on the Pico
PASS Pico PING received
      pico ping nonce=1, pong sent
PASS our PING answered -- payload=b'Z'
PASS STATE printed on the console
PASS a good frame behind a bad length survives (resync)
PASS EVENT received after the console trigger
      event seq=0 source=bench kind=rig_up
PASS EVENT is rig_up from the bench
PASS unacknowledged EVENT retransmitted -- retry seq=0
PASS retransmit noted on the console
PASS no further copies after the ACK
      proto: frames ok=41 bad=1 events lost=0 session=1 rig=1 name='resync ok'
PASS no events lost -- proto: frames ok=41 bad=1 events lost=0 session=1 rig=1 name='resync ok'
PASS Pico drops the session and hunts again
PASS link down noted on the console
PASS session back up
PASS a WELCOME from another major is refused with ERROR -- payload=b'\x01\x1cPico speaks 2.0, service 1.0'
PASS the console says version mismatch
PASS the refused session stays down
PASS session back up after the refusal

all checks passed
```

The one bad frame is the test's own: it deliberately sends a header whose length swallows the
start of a good `STATE` to prove the resync rule.

## After the deploy

- `pedald`: `Pico says hello: fw 'bb6dde1', protocol 2.0, caps 0x0000` — a live 2.0 session.
- `scripts/diag --host vip`: `the Core→Pico UART link is up: a session, and not one bad frame`.
- `scripts/status`: `namchaind: running, ok, hw:CARD=wm8960,DEV=0, 48000 Hz / 64, xruns 0, guard
  trips 0`; `devices/vip/components.lock: matches the host`; `devices/vip: applied bb6dde1`.

**And the mismatch was observed for real, for free.** In the second between the Pico's flash and
`pedald`'s restart, the *old* service read the same `HELLO` and logged:

```
pedald: Pico says hello: fw '\x07bb6dde1', protocol 2.0, caps 0x0000
```

— the `str8` length byte (0x07) taken as the first character of the version, exactly the failure
[uart-protocol.md](../docs/uart-protocol.md) describes, and the only visible symptom of a pair
that ignored the version would have been. It also shows why the major was worth bumping: the old
end accepted that session without a word.

## What this does not show

- Nothing about the footswitches, DIN MIDI or the `cc` 80–82 rule: there are no switches yet
  (3.5 builds them), so nothing on the pedal exercises that path.
- Nothing about the relay (3.6) — not fitted, so the link-down rule is untested at the jack.
- No soak through the new protocol: the session has been up for minutes, not an hour. A soak
  belongs with 3.8 anyway, when there is switching to soak.
- The Debug Probe's UART route is still unproven on this Pico: the lead's contact failed twice,
  and the bench procedure should be re-tried from a clean, unpopulated pin row before it is
  trusted again.
