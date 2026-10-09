# T7's service half, and a reboot during T8's storm (2026-10-09)

A press has no path into the service without the Pico, which is why T7's service half and T8's storm
have been waiting. `pedald` now takes one event over HTTP — `POST /event`, the link's own vocabulary
`{"kind": 1, "a": 0, "b": 0}` (= rig_up) — and hands it to the same `on_event` the UART reader
calls, so the mapping tables decide exactly as they do for a press. `scripts/measure-switch` drives
it from the Mac over WiFi, with a bank of two rigs built from the rig the pedal plays.

## T7's service half: PASS

Eight presses, one a second, each one stepping the bank, engine `9f3cbb6` (the charge in place),
`vip`, in `pedal-bench.slice` conditions (nothing else on the machine):

```
bank:        t7-a.json, t7-b.json (both the document the pedal plays)
before:      switches 0, xruns 0, issues 0; warm: t7-a.json on core 1, state warm, behind 0, dropped 0
press 1..8:  warm 1 cold 0 xruns 0      (every press)
after:       switches 8 (warm 8, cold 0), xruns 0, issues 0
             warm: t7-a.json on core 1, state warm, behind 0 (worst 1), dropped 0
```

**8 of 8 presses were handovers.** No press was a cold switch, no block was dropped, the warm
document stayed within a block of the device thread, and the warm set slid to the new neighbour after
every step (the rig left behind is what the next press reaches, and it is warm again by the time the
next press comes). That is T7's service half, and it is D10's promise — a press costs a fade, not a
compile — measured end to end through the service rather than at the engine.

## T8's storm: paced presses pass, and bursts are where it broke

**Paced, through the service, after the event path landed:**

| rate | presses | handovers | cold | xruns | dropped warm blocks | board |
|---|---|---|---|---|---|---|
| 1/s | 8 | **8** | 0 | 0 | 0 | fine |
| 2/s | 60 | **60** | 0 | 0 | 0 | fine |
| ~3/s (as fast as the HTTP round trip allows: 340 ms a request) | 59 | **59** | 0 | 0 | 0 | fine |

Every press at these rates is a **handover** — a fade, not a compile — with no xrun, no guard trip, no
block over the deadline and the warm document current (behind 0, worst 1, nothing dropped) throughout.
That is T8's ordinary case: faster than a person can press a footswitch, and it does not touch the
audio path.

**Bursts are different, and that is where the reboot happened.** The script's first storm fired ten
concurrent requests a second (a backgrounded `curl` each, then `wait`); it reached 1.8/s *on average*
and produced 9 cold switches out of 29 — the warming could not keep up with ten requests arriving at
once, so presses landed on rigs the engine had not finished compiling. The board rebooted during that
run (21:46:51, `Startup finished ... 20.118s`), which is why its numbers are void. The paced runs above
never rebooted it.

So the honest reading is: **the average rate is not the problem — the burst is.** Ten simultaneous
switches means ten compiles queued on the control thread at once, and on a 1 GB board with a
possibly-thin 5 V rail that is the heaviest thing this pedal has been asked to do. Ten at once is
also beyond the hardware: a footswitch is one press at a time, and even a MIDI storm into the mapping
is serialised by the link. T8's falsifier ("a press storm that leaves the warm set permanently behind")
was not demonstrated: the warm set recovered every time, and the cold switches it did produce were
answered by a switch, not by silence or an xrun.

## The cause of the reboot is still unknown, and now diagnosable

vip's journal was volatile (`Storage=auto` with no `/var/log/journal`), so the previous boot's tail —
the kernel's `Undervoltage detected!`, a thermal shutdown, a panic — went with the reboot it would
have explained, and the firmware's low-voltage flag (`hwmon rpi_volt in0_lcrit_alarm`, which
`pedal-diag` reads) is live-only and reads 0 afterwards. `devices/vip/rootfs/etc/systemd/journald.conf.d/persistent.conf`
turns the journal persistent and a tmpfiles entry creates `/var/log/journal` at boot, so the next
occurrence keeps its last minute. The lead remains power: the design calls for the Raspberry Pi 45 W
USB-C supply (docs/hardware-handoff.md) and the codec board's feed shares the 5 V rail; the owner's
check is the supply, the cable, and whether that rail sags when the CPU, WiFi and a compile run at
once.
