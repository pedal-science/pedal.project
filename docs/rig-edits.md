# Rig edits: a proposed design change

**Proposed** by you on 2026-09-28. It isn't a decision yet, and nothing has been built.

It is meant to:
- optimise traffic to namchain
- support undo/redo.

It came out of the first step 8 soak (`plan.md` Phase 1, step 8). In that soak, every ljoss edit
reached `namchaind` as a structural transition.

## The proposal

- Every user-initiated change is recorded as an "Edit".
  - Edits are sent to namchain immediately (see caveat below) - as a single, structured piece of
    data
  - Edits made to individual controls like a gain slider or toggle switch (I'll call these 'micro')
    - Are 'applied' (sent to namchain) as they happen, but with a maximum rate (e.g. no more than
      once every 10ms, but avoid missing the 'last one' if the user pauses/stops editing)
    - Are kept as history by ljoss, but after the first edit any subsequent ones - unless the user
      has edited something other than this particular control in the meantime - replace the saved
      edit, so only the 'final' value is kept in history
    - Edits will form the basis of a future undo/redo mechanism in ljoss
- Every node has a state version identifier, created and maintained by ljoss. Every time an edit is
  'applied' (before being sent to namchain), ljoss updates the node's version identifier. This will
  be used in future (perhaps) to help us check for any sync issues (maybe only in development and
  testing work)
- Every rig has a state version identifier, just as nodes do.
- State version identifiers are generated UUIDs and their values have no meaning - they are only
  useful for 1:1 comparison (they're either different or the same as each other).

## Where it starts from

This describes ljoss at `b8cf180` and namchain at `abe1f34`.

- **ljoss sends every change as the whole document.**
  - `RigEditor.rig`'s `didSet` calls `EngineSession.rigDidChange`. That waits until the rig has
    been unchanged for 250 ms, then sends the flattened document as `rig.apply`, followed by an
    `engine.mute` for each chain.
  - An inspector slider writes to the rig on every step of a drag, so the device doesn't hear a
    drag until it pauses.
  - ljoss has no `rig.patch` request (it defines only the response type), no edit history and no
    version identifiers.
- **namchain already has the path that micro edits need.**
  - A `rig.patch` `set_param` on a parameter that `engine.schema` marks `rampable` takes namchain's
    smooth path: no compile and no crossfade. The node ramps to the new value, and a new value
    that arrives mid-ramp continues from wherever the ramp has got to.
  - The engine writes the value into its document, so a later structural edit keeps it.
  - `docs/schema.md` already says a slider streams a rampable parameter, and a control for any
    other parameter commits on release.
  - Every continuous parameter ljoss maps today is rampable: tone stack, EQ bands, tilt, cut
    frequencies, cab level and cuts, delay time, feedback and mix, and gain. The pickers (model,
    IR, cut slope) and bypass are structural.
- **Each whole-document edit is a structural transition.** `namchaind` replans every chain whose
  graph changed, and a parameter's value is part of the graph. So each edit:
  - compiles a new plan on the control thread, reloading every NAM model from its file and
    resetting it;
  - runs both the old and new plans for the 5 ms fade;
  - starts the new models from NAM's silence prewarm. E1 found this gives the wrong sound for
    170–340 ms.
- **Soak 1** (step 8's first run) had 182 transitions in the hour, and no edit took the smooth path.
  Its overruns came from running two plans of a rig whose load was already p99 39–52% on its own.
- **namchain has nowhere to keep a version identifier.** It reads any key on a document node other
  than `id`, `type`, `element`, `role`, `params`, `strings` and `bypass` as a parameter, and refuses
  a parameter that no node type declares. Versions would need a change to namchain's protocol. The
  protocol belongs to namchain, so under `docs/working-across-repos.md` rule 2 the change is
  specified there first.
