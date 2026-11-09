# O4 on vip: pedald keeps the rig

2026-11-09, on `e04a80f`, with `autosave` off as planned until O5 deploys. So on vip this measures the following and
the classifying, and the writing is tested on the Mac.

## Does a press pay for it?

Pressing through `POST /event` on the pedal itself, about seven a second, each switching rig
(`press-with-knob.py`, `run/press-with-knob.json`):

| | presses | median | p95 | max |
|---|---|---|---|---|
| Alone | 200 | 24.2 ms | 29.1 ms | 112.5 ms |
| Beside an app streaming a knob at about 25 values a second | 200 | 24.2 ms | 29.3 ms | 123.5 ms |
| Before O4 (O3's run) | 44 | 24.4 ms | 88.0 ms | 161.5 ms |

The plan's limit was 20 ms added to the loop, or document parsing moves to a worker. It added nothing measurable, and
parsing is on the follower's thread anyway. 403 knob values landed; 182 were refused because the rig changed under
them, which is what the presses were doing.

## The switch harness

`scripts/measure-switch --presses 30 --storm-rate 10 --storm-seconds 30` (`run/t7-service.txt`): 30 of 30 presses were warm
handovers. In the storm 98 presses were sent and all answered, and there were 98 more warm switches and 0 cold, with
0 xruns, 0 guard trips and 0 blocks over the deadline. It sent 3.27 presses a second against 2.95 in the
[run of 2026-10-09](../2026-10-09-service-switch/t7-service.txt), so a press isn't slower; the harness's own round
trip limits the rate.

## Resume on the real thing

pedald restarted with no record to trust (the first start of this version), found 0 values to treat as a performance on
Bob, and wrote `state/resume.json`. The next restart found the record and said so, with no warning about trust. `Bob.json`
kept its value through the knob test, as it should with autosave off.

## What this doesn't cover

- **Autosave, undo and the restart of both daemons on vip.** They need `autosave` on, which waits for O5. They pass on the
  Mac against a real `namchaind` on the null backend (`devices/common/tests/test_rig_live.py`, 21 cases).
- **A real footswitch on a block or a parameter.** vip has no such map entry yet. Both pass on the Mac through `POST /event`.
- **Audio.** Nothing is connected, so xruns are the only evidence that it kept playing cleanly.
