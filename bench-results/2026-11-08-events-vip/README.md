# O1: namchaind's events on vip, with a subscriber and a 100 Hz knob — PASS

**The gate holds in every arm: 0 xruns, 0 blocks over the deadline, 0 over 90%, 0 guard trips. The
render core's rise is the knob's, not the events':** in a second run with a fourth arm, the same knob
with nobody subscribed took p99 from 28% to 30%, and adding the subscriber made it 31%, a point that is
inside the noise (its p99.9, worst block and tail were no worse than the knob's alone). Events cost the
control thread about 1.2% of a core. [The second run](#the-fourth-arm-the-knob-alone) is below.
namchain `453381a` (events, `docs/daemon.md` "Events"; pedal.project `docs/pedal-owns-state.md`, O1) on
vip, 2026-11-08 03:38 to 04:09 UTC, three ten-minute arms with the same heavy rig playing in all of
them (0.569 of the render core, two chains; `run/o1-heavy.json`), rigpa and pedald running as always.

| arm | gate | xruns / over deadline / over 90% / guard | load p50 / p99 / p99.9 / worst | blocks >= 40% | core 0 / 1 / 2 / 3 busy | namchaind CPU | namchaind PSS | MemAvailable | temp |
|---|---|---|---|---|---|---|---|---|---|
| base | PASS | 0 / 0 / 0 / 0 | 19% / 28% / 40% / 58% | 464 | 10.6% / 10.2% / 0.0% / 21.3% | 32.1% of a core | 30 MB | 731 MB | 67.0..69.2 °C |
| events | PASS | 0 / 0 / 0 / 0 | 21% / 31% / 47% / 61% | 853 | 16.5% / 10.6% / 0.0% / 23.1% | 37.6% of a core | 30 MB | 729 MB | 67.5..70.3 °C |
| base2 | PASS | 0 / 0 / 0 / 0 | 19% / 28% / 40% / 61% | 477 | 11.2% / 10.2% / 0.0% / 21.3% | 32.1% of a core | 30 MB | 732 MB | 67.0..70.3 °C |

What the events arm carried (`run/events.stream.json`): **60,000 `rig.patch` set_params** at 100 Hz
from one TCP connection, every one of them ramped (`smooth`), none refused; and a second connection
subscribed to every event, which received them as **11,998 coalesced `rig.params` frames** — 20 a
second, the 50 ms default — plus its starting `engine.state`: 4.0 MB in ten minutes, and **no
`resync`**. The engine counted 59,457 parameters applied on the render thread. namchaind's memory
did not move (30 MB PSS in every arm).

- **base and base2 agree** (p99 28%, the same tail): nothing drifted.
- **The events arm costs the control thread about 5.5% of a core** (32.1% → 37.6%, core 0 10.6% →
  16.5%): one request, one reply and one coalesced frame every 10 ms. Core 0 is the housekeeping core,
  where rigpa also runs.
- **Render p99 rose three points (28% → 31%) and the worst block from 58% to 61%.** This soak does not
  say how much of that is events: the arm also applied 59,457 ramps on the render thread, which a knob
  streamed at 100 Hz causes with or without a subscriber, and events are made and sent on the control
  thread, after the change. Telling the two apart needs a fourth arm — the knob with nobody
  subscribed. The plan asked for p99 "unchanged"; it is three points, inside the gate by a wide
  margin. The fourth arm, below, attributes it.

## The fourth arm: the knob alone

A second run (`run2/`, 2026-11-08 11:03 to 11:45 UTC, the same engine and rig, `run-o1 --arms
base,knob,events,base2`) with the knob arm between base and events: `o1-stream.py --no-subscriber`
sends the same 60,000 ramped `set_param`s at 100 Hz and opens no subscriber.

| arm | gate | xruns / over deadline / over 90% / guard | load p50 / p99 / p99.9 / worst | blocks >= 40% | core 0 / 1 / 2 / 3 busy | namchaind CPU | namchaind PSS | MemAvailable | temp |
|---|---|---|---|---|---|---|---|---|---|
| base | PASS | 0 / 0 / 0 / 0 | 19% / 28% / 38% / 57% | 369 | 10.3% / 10.2% / 0.0% / 21.2% | 32.0% of a core | 30 MB | 729 MB | 69.7..72.5 °C |
| knob | PASS | 0 / 0 / 0 / 0 | 19% / 30% / 46% / 63% | 747 | 15.9% / 10.7% / 0.0% / 22.1% | 35.8% of a core | 30 MB | 728 MB | 70.3..73.0 °C |
| events | PASS | 0 / 0 / 0 / 0 | 20% / 31% / 45% / 59% | 721 | 13.5% / 10.7% / 0.0% / 22.3% | 37.0% of a core | 30 MB | 729 MB | 70.3..73.0 °C |
| base2 | PASS | 0 / 0 / 0 / 0 | 19% / 28% / 40% / 60% | 482 | 10.5% / 10.2% / 0.0% / 21.2% | 32.0% of a core | 30 MB | 728 MB | 69.7..72.5 °C |

- **The knob alone moves the render core**: p99 28% → 30%, p99.9 38% → 46%, and twice the blocks at or
  over 40%. That is the ramps — 100 parameter changes a second, each one ramped on the render thread —
  and it is there with or without a subscriber. A knob turned by hand sends far fewer.
- **The subscriber adds at most a point of p99** (30% → 31%), and nothing to the tail: p99.9, the worst
  block and the count over 40% are all a little *lower* in the events arm than the knob arm. A point of
  p99 between two ten-minute arms is within what base and base2 differ by on p99.9 and the worst block.
- **Events cost the control thread about 1.2% of a core** (namchaind 35.8% → 37.0%): one coalesced
  `rig.params` frame every 50 ms (11,997 in the arm, no `resync`). Core 0's busy figure went the other
  way (15.9% → 13.5%); core 0 also carries rigpa and pedald, so namchaind's own ticks are the figure to
  read.
- base and base2 agree on p99 again (28%): nothing drifted. vip ran about 3 °C warmer than in the first
  run.

## Found on the way

- **A reply larger than the local socket's send buffer closes the connection.** `engine.schema` is
  313 KB on vip (it lists 520 IRs) and a SEQPACKET datagram can be no larger than the socket's send
  buffer, 208 KB by default, so `namchainctl schema` over `/run/namchain/namchaind.sock` gets "the
  daemon closed the connection"; over TCP it works. Older than O1, unnoticed because rigpa and ljoss
  use TCP. The driver uses TCP for that reason.
- **A macro addressed by node id goes the structural way.** The tone stack's `bass` is rampable, but a
  `set_param` naming the macro's node id (rather than its `element`) was answered `structural` and sent
  a whole `rig.patched` per op — 300 recompiles in three seconds in a trial. By `element`, as ljoss and
  rigpa address a block, it ramps. The driver addresses by element.

## How it ran

`run-o1` (from C3's `run-c3`, without rigpa's arms): the heavy rig is built from the playing rig's
chains just under a cost of 0.70, `scripts/soak/soak-monitor.sh` samples `engine.status` every 10 s and
`soak-summary.py` judges each arm, `/proc/stat`, MemAvailable and namchaind's `smaps_rollup` before and
after, and `analyse.py run` makes the table. `o1-stream.py` runs on vip as a transient unit
(`systemd-run`) for the events arm: it finds the first rampable numeric parameter in the playing
document, sweeps it ±5% of its range around where it was at 0.5 Hz, sent at 100 Hz, and puts it back.
Put back by the cleanup: pedald's resume files and the rig they name, the test rig removed.

`--arms` picks and orders the arms (`knob` added for the second run); `analyse.py run2` makes that table.
`run/env.txt`'s `namchain` and `rigpa` lines are the card image's; the `bin` lines are what ran.
