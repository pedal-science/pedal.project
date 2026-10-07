# E2 item 1, the listening half

Each model has three files, 48 kHz mono 24-bit:

| file | what it is |
|---|---|
| `<model>-full.wav` | the Full submodel (8 channels), running all along |
| `<model>-lite.wav` | the Lite submodel (3 channels), running all along |
| `<model>-handover.wav` | the two alternating, with a 5 ms equal-power crossfade at each switch |

Play `-full` then `-lite`: that is the whole question. If you can hear the difference, tier 2's
"a Lite copy takes over at once" plays the wrong sound until the Full catches up. Then play
`-handover`: the crossfade itself is click-free (the glitch detector says so on 102 of 104 of
these), so what you are listening for is the *change of tone*, not a tick.

| model | null (below signal) | why it is in this set |
|---|---|---|
| `Ampeg SVT VR _ 8x10 _ Beta52A + DI` | −9.2 dB | the worst in the library |
| `Ampeg SVT - MD 421` | −20.2 dB | tripped continuity on one switch in 56 |
| `Ampeg SVT - SM75` | −25.4 dB | tripped the HF rule and a dropout on one switch each |
| `Ampeg VT-40 - Vol 4, Bass 6, Mid 5, Treble 8, M160` | −23.2 dB | a typical NAM Ampeg |
| `AMPEG_CH 2 NEUTRAL G5` | −23.9 dB | E1's model, so comparable with E1 |
| `APP-SD1-Boost-I` | −39.2 dB | the best in the library |

The first four are 16 s from 40 s in, with a switch every second, so they include the switch the
detector flagged. The last two are 16 s from 20 s in, a switch every two seconds. The DI's last
second is silence, so the very last switch tests nothing.

## Where the files are, and how to make them again

The WAVs are 40 MB, so they are not committed. They were written to
`build/e2/audition/24bit/` (float originals beside them in `build/e2/audition/`), and
`make-auditions.sh` regenerates them: it needs `colima`/`docker` with the image build's container,
the built `namchain-warm-bench`, and the library. `make-sweep.sh` is the 52-model sweep the table in
[../2026-10-06-e2-tiers.md](../2026-10-06-e2-tiers.md) comes from; both take the model list from
`build/e2/vip-models.txt`, which is the shipping library's 52 paths.

The two commands, for the record:

    namchain-warm-bench slim --input guitar-di.wav --switch-every 5 <52 models>        # the table
    namchain-warm-bench slim --input guitar-di.wav --switch-every 2 \
        --audition DIR --audition-start 20 --audition-seconds 16 <the six models>     # the listening

`--ir <cab.wav>` moves every relative null by 1-2 dB and is not used for either: 35 of the 52
models already carry their own cab, and the question is the models.

## The thud, and the fixed set

The six `-handover` files were made with an **equal-power** fade, and that is what a fade wants only
when the two signals are uncorrelated. Two submodels of one rig are correlated at 0.97-1.00, and the
power of `g1*a + g2*b` is `g1^2 + g2^2 + 2*rho*g1*g2` -- so equal power adds 2*rho*g1*g2 at the
midpoint, +2.6 to +3.0 dB measured on every one of 104 model-directions, in the low end because
that is where two amp models put their energy. Heard: "a quiet, short thud at each switch from full
to lite". `../../namchain/bench-results/e2-fade-thump.txt` has the measurement.

`build/e2/audition-fixed/24bit/` is the same six models with `--fade-shape compensated`: both
weights divided by `sqrt(1 + 2*rho*g1*g2)`, rho clamped to [0, 1], which is constant amplitude where
the two are alike and equal power where they are not. All 104 rows come out at 0.00 dB excess and
zero detector findings. The `-full` and `-lite` references are identical in both sets; only the
`-handover` file differs.
