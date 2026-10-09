# T7's offline arm: what the switch bench can and cannot judge (2026-10-09)

`namchain-warm-bench switch` renders a rig on the device thread and a second on a warm thread, swaps
them every `--switch-every` seconds, and judges the result with the engine's own glitch detector
(`namchain::glitch::analyse`) against both rigs rendered offline over the same span. It has been
printing `FAIL` on its own crossfade in both arms with byte-identical output since 2026-10-09, which
is what a fault in the harness looks like rather than a fault in the engine. This is the state after
four fixes to the arm, and the honest reading of what is left.

Engine `df75c18`, vip, inside `pedal-bench.slice` (an ssh session lives in `user.slice`, whose cpuset
is core 0, so the tool cannot pin from there):

```
namchain-warm-bench switch --input /var/tmp/guitar-di.wav --live <A|B> <A|B> \
    --seconds 30 --switch-every 2 --fade-ms 5 --render-cpu 3 --warm-cpu 1 --priority 80
```

`A.nam` and `B.nam` are two amp models from the library's own set.

## The four harness bugs, and what each was

| | what it did | fixed in |
|---|---|---|
| the skipped index | the warm thread jumped its index to `published` when it let go, so the rig the device thread had been rendering arrived at the swap missing the handover block | `c5d0fee` |
| the stale pool block | the pool was not emptied when a fade closed, so the first block of the next fade could mix audio published during the previous one | `222cbb9` |
| the fade's two sides | the device took the newest published block rather than *this* block's, so a late warm thread made the fade span two moments of the input | `d290bea` |
| the oracles' state | the oracle pass drove the same two instances the live threads then rendered, so the live run started from models whose state was the end of the input — the convergence check said so exactly: `render is not the previous chain at frame 27`, a frame no switch had touched | `8c80dcb` |

The protocol fix is the interesting one, because the engine does it and the arm did not: at a
handover the warm thread now **finishes every block the device thread has already rendered** (renders
up to `published`) and only then signals `released`. Both threads are on the same block index at the
swap and both rigs see every input block exactly once. That is why convergence, which was failing
with differences of −3 to −29 dBFS, now reads **−1000 dBFS** — an exact match — on the pair where a
reading means anything.

## The same rig on both sides: the handover is clean

```
rigs:       A -> A (no ir), quantum 64 (deadline 1333 us), 30 s, switch every 2.0 s
handover:   14 switches (0 deferred), last 5 blocks; blocks here are 1333 us
render:     p50 93 us  p99 105 us  p99.9 110 us  max 153 us  over deadline 0
warm:       p50 89 us  p99 103 us  max 141 us  blocks 22500  worst lag 0 blocks
handover:   PASS  convergence -1000.0 dBFS (limit -60), worst dropout 0.00 ms
glitch:     FAIL (for reference)  continuity ref 0.0148 vs edit 0.244, hf excess 34.85 dB
```

The settled output after every one of fourteen switches is the rig that is audible, **bit for bit**
(−1000 dBFS is the detector's exact-match sentinel), with no dropout at the seam, nothing deferred,
no block over the deadline and the warm thread never more than 0 blocks behind. That is the arm's
claim on the handover, and it holds.

## Two rigs: the reading is the comparison, not the handover

```
rigs:       A -> B (no ir), quantum 64 (deadline 1333 us), 30 s, switch every 2.0 s
handover:   14 switches (0 deferred), last 5 blocks; blocks here are 1333 us
            56 fade blocks mixed the newest available outgoing audio instead of this block's
handover:   FAIL  convergence -3.0 dBFS (limit -60), worst dropout 0.25 ms
            the two rigs differ by up to -3.0 dBFS (0.7076), so a convergence reading of that
            order across a switch between different rigs is the comparison, not the handover
```

The convergence reading (−3.0 dBFS, a worst difference of 0.707550) is **the two rigs' own
difference** (0.7076), to four digits. Across a switch between two *different* rigs the detector has
to decide which of them the output should be, and the number it produces is the size of the
difference between them — not a hole, a repeat or a swapped plan. (The engine's own suite says the
same thing from the other side: "a hard switch trips the spectral rule" is a *passing* expectation
there.)

## What is still unproven, and why

* **The arm's fade does not wait for the outgoing block.** 56 of the ~70 fade blocks in a 30 s run
  had to mix the newest available outgoing audio rather than this block's, because the device thread
  needs the warm thread's block *now* and the warm thread publishes it as it renders. The engine does
  not have this gap — its handover has a setup block, and its live switches (`handover_blocks: 3`,
  0 xruns, warm lag 0-1 block) show nothing — but the arm's continuity and high-frequency numbers are
  therefore the harness's timing, not the engine's audio, and they are printed as reference only.
  Closing it means making the device wait for the block it needs, which is a change to the arm's
  timing model and would raise `handover_blocks` by one or two — the engine's own 3 is that cost.
* **So the arm judges the handover (same rig on both sides) and the loads, and does not judge a
  cross-rig switch.** Its continuity/hf rules are for ramped parameter edits: a 5 ms equal-power
  crossfade between two rigs is *meant* to change the spectrum, and between one rig and itself is
  meant to be a +3 dB bump in the middle. Reading a verdict off either would be reading the rules'
  assumptions, not the engine.
* The loads themselves are evidence and are unchanged: the device thread's p99 is 8% of the deadline
  with a warm document rendering beside it, nothing overruns, and the warm thread's worst lag is 0
  blocks.

## What would close it

1. Make the device thread wait (bounded) for the pool block with `seq == b` before mixing, count the
   wait as part of `handover_blocks`, and re-run: the stale count should go to zero and the same-rig
   arm's continuity/hf should become meaningful.
2. Or judge a cross-rig switch by the promise it makes — a bounded, smooth-enough change of timbre —
   rather than by rules written for parameter ramps. That is a question about the detector's
   expectations, and it belongs with `docs/transitions.md`, not with this tool.
