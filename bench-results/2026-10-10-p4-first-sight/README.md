# P4: a first-sight measurement, end to end (2026-10-10)

P4 measures a unit this device's table has no row for, on a core the player is not using, and hands
the result to the operator to merge. The trigger was verified on the board and then the measurement
was run the same way:

1. **The gap was brought, because the pedal's library has none** — eight models from eight library
   directories all costed as measured (`unmeasured: none`), so the verification used
   `namchain/vendor/NeuralAmpModelerCore/example_models/lstm.nam` (an LSTM, 2.3 KB, `architecture:
   LSTM`), copied into the library and built into a one-chain rig.
2. **The engine named it**: loading that rig raised `cost_unknown`, and pedald's `/status` reported
   `needs_measuring: [{"row": "unknown.NAM", "count": 1, "reference": ".../t5-lstm.nam", "chain":
   "one", "node": "amp0"}]`. The row a first-sight rig actually reports is `unknown.NAM` — the engine
   could not name the family — which the measurer did not match until this run found it.
3. **The measurer measured it**: `pedal-measure --seconds 12` refused nothing, found the DI the table
   was measured with (8,182,024 bytes, hash-checked against the table's own `input` block), ran the
   bench on core 2 inside `pedal-bench.slice`, and wrote
   `/var/lib/pedal/cost-fragments/unknown.NAM.json`.
4. **The fragment names the row the engine could not**:

   ```json
   {"unit":"NAM.LSTM.full","core_percent":0.00885,"bar":"p99","quantum":64,"deadline_us":1333.333,
    "sources":{"n":113,"p99_at_n":0.991,"overruns_at_n":0,"p99_at_n_plus_1":1.000,
               "overruns_at_n_plus_1":344,"p99_at_n_plus_2":1.010,"blocks_behind_at_n_plus_1":9}}
   ```

   So an LSTM costs **0.00885 of a core** (113 copies fitted the deadline before the fit point broke),
   and the bench learned the family from the file while the engine could only say `unknown.NAM`.

5. **The pedal put itself back**: the test rig and model were removed, `last.json` reloaded, pedald
   restarted — `last.json last.prev.json`, both services active.

**What is left is the operator's step, deliberately**: `devices/common/cost-merge` folds
`/var/lib/pedal/cost-fragments/<row>.json` into the device's table, `devices/vip/apply` installs it,
and then a rig on that family is admitted at its true cost instead of D8's `unknown`. The tool does not
merge — a device's numbers are the device's, and `devices/<host>/check` hashes the installed table —
which is the boundary P4 was designed around.

Two bugs were found by *running* it rather than reading it: the measurer's row spelling (`unknown.NAM`)
and `systemd-run --property=CPUAffinity=` being refused by this systemd (the bench's own `--cpu N`
does the pinning; the slice is what the tool needs).
