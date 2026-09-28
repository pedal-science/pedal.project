# Rig edits: a proposed design change

**Proposed** by you on 2026-09-28. It isn't a decision yet, and nothing has been built. Claude's
comments on it follow the proposal, and your answers to them are at the end.

**Done:** step 1 of C13, in ljoss `462e678`, on the current protocol.
- A knob whose parameter the engine ramps is streamed as `rig.patch` `set_param`: at most every
  10 ms, one patch in flight, and the last value always sent.
- Everything else is still sent as a whole document after 250 ms.
- Checked against a local `namchaind`: a 2 s drag of three knobs was 804 ramps and no rebuilds.
  ljoss's `docs/ENGINE.md`, "Sending an edit", has the details.

**On piv with ljoss, 2026-09-28.** namchain `503aac9` gives replies their own 16 MiB limit,
ljoss `6ae4563` reads replies that large, and ljoss `ba50ad2` connects by itself. Watched from
the device while you edited "Ambient Wash" and "Crunch Lead" (22:17–22:37, polling
`engine.status` and `rig.get` five times a second):
- Every knob streamed: 178 ramps, no rebuilds. That was the tone stack's bass, mid and treble,
  a gain, the cab's low and high cut, and the delay's time, feedback and mix.
- The five rebuilds were all structural: a NAM model changed, an amp added twice, an amp
  removed, and a switch of rig.
- 0 xruns, and no block past 90% of the deadline. The worst took 66%, against 43% when the watch
  began; `engine.status` doesn't say when.
- At most 13 ramps landed in one ~260 ms poll, about 50 a second.
- The WiFi round trip, Mac to piv, is about 6 ms at the median. Tails of 40–420 ms show on the
  way to the router too, from both ends, so they belong to the network, not to piv. piv's WiFi
  power saving (the kernel's default) made no difference on or off, with pings every 200 ms or
  every second. It is off now anyway, set by hand, and `pedal-wifi.service` in `devices/common`
  keeps it off once the tree is next applied.
- **Debt.** With one patch in flight, a stall like that holds a moving knob, and the value it
  jumps to then ramps over namchain's 5 ms. Not heard yet. If it is, ramp over the time since
  the last value (capped), or let a second patch go before the first is answered.

This section first said ljoss couldn't connect to piv, and that was wrong. Over TCP, which ljoss
uses, both replies were under the old 1 MiB limit. With 1,538 IRs, `engine.assets` is 1,016,823
bytes, 97% of it, and `engine.schema` is 808,492. Only the Unix socket failed, which is how
namchainctl and `sync-library` reach the daemon.

History and undo, the tree-to-graph conversion and versions wait.

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

## Claude's comments, 2026-09-28

These are Claude's arguments, not part of the proposal, for you to accept, change or reject. Each
is numbered so it can be answered on its own.

### The soak failure

**C1. The engine half already exists.** A micro edit maps onto `rig.patch` `set_param`, namchain's
smooth path, and every continuous parameter ljoss maps can take that path (see "Where it starts
from"). So the proposal would remove most of soak 1's 182 transitions, without any change to
namchain.

**C2. The proposal alone wouldn't have got soak 1 through the gate.**
- Some of the edits in the heavy stretch (27.6–29.1 min) were probably model, IR or block changes.
  Those rebuild under any design.
- At q64, a rebuild of a rig above ~45% p99 overruns, whoever sends it.
- Fixing that needs namchain to admit or refuse a rebuild by its cost, or to make rebuilds cheaper
  (namchain's `docs/transitions.md`, "What is next", item 1). D10's rig switches need the same.

**C3. It gains more than traffic.**
- **Sound:** every knob move sent as a whole document reloads the amp model and restarts it from
  NAM's silence prewarm, which E1 found sounds wrong for 170–340 ms. A ramped change leaves the
  model running.
- **Feel:** today a slider drag isn't heard until it pauses for 250 ms. A rate-limited stream is
  heard while the knob turns.

### Points to settle in the proposal

**C4. Choose how to send an edit by what the engine does with the parameter, not by the kind of
control.**
- A bypass toggle, a model or IR pick and a cut slope are each one control, but each one rebuilds
  the chain.
- Stream only the parameters that `engine.schema` marks `rampable`, and send the rest once, on
  release. ljoss doesn't fetch the schema yet.
- Streaming a control that rebuilds at 100 Hz would be far worse than today.

**C5. Keep sending the whole document for structural edits.** A structural edit adds, removes or
moves a block, or changes a model, IR, slope or bypass.
- They're rare, and each costs a rebuild whichever way it's sent.
- Sending the whole document keeps the conversion from ljoss's tree to namchain's graph in one
  place (`DocumentEncoder`). The alternative is turning each tree edit into graph ops.
- The bytes on the wire aren't the problem; the engine's work per message is.

The edit is still one entry in ljoss's history; only how it's sent differs.

**C6. Match the rate limit to the ramp.**
- namchain ramps each change over the node's `ramp_ms` (5 ms by default). A new value picks up from
  wherever a running ramp has got to.
- With a 10 ms limit, a drag becomes 5 ms of movement then 5 ms of holding: a staircase. Either
  make the ramp at least as long as the interval (10–20 ms for streamed parameters), or limit sends
  to one every 20–30 ms.
- *Correction, 2026-09-28:* the second option doesn't remove the staircase. With a 5 ms ramp, a
  longer interval only makes the holds longer. Only a ramp at least as long as the interval makes
  the movement continuous. Step 1 sends at most every 10 ms, as you proposed, and leaves namchain's
  ramps at 5 ms.
- Always send the final value when the finger lifts.
- Send any waiting micro edit before a structural one, so the engine gets them in order.

**C7. A merged history entry keeps the first edit's "from" value.**
- Undo needs the value from before the drag began, so only the entry's "to" value should be
  replaced.
- As written, two drags of the same knob a minute apart also become one undo step. Ending the merge
  when the finger lifts, or after a pause, is the usual alternative. That one is a UX call.

**C8. Undo is itself an edit.** It goes down the same path as any other edit, so undoing a knob move
is a ramp rather than a rebuild. A structural edit has to record enough to reverse it: a removed
block's full state, or a moved block's old position.

**C9. The version belongs on ljoss's block, not on each engine node.**
- An amp is two engine nodes (`nc.nam` and `fx.amp.tonestack`), and a parallel section is two more
  (`nc.split` and `nc.mix`). The nodes from one block share one element id.
- The block is what ljoss edits, and namchain already carries its id unchanged as `element`.
- So one version per element keeps both sides counting the same thing.

### Versions

**C10. namchain has to store and report the versions**, which is the protocol change noted in
"Where it starts from".
- The rig version could go in `engine.status`, which ljoss already polls twice a second, and the
  element versions in `rig.get`.
- The rig version changes on every edit, micro ones included, so one comparison says whether
  anything differs.

**C11. A returned version shows that namchain received an edit, not that the two sides agree.**
- It proves namchain got ljoss's latest edit, in order. It doesn't prove namchain's state equals
  ljoss's.
- `rig.get` already returns namchain's copy of the document to compare against, and sending that
  copy back changes nothing.
- The two checks catch different bugs.

**C12. The biggest benefit isn't only for development.**
- D3 and D4 bring a second writer: the pedal service changing rigs from the footswitches, and later
  MIDI CCs or an expression pedal streaming a parameter (the mapping row in `plan.md`'s debt
  register).
- ljoss's rule when it connects is "my document wins" (`EngineSession.open`). That's what replaced
  the spec rig in soak 1, and at a gig it would silently undo the rig the player chose on the
  pedal.
- Versions let ljoss see that the device changed without it. For that, every writer has to create
  a new version when it changes something, not only ljoss.
- Whether ljoss then follows the device or asks is a Phase 3 decision.

### Direction and order

**C13. The direction is right. The order I'd build it in:**
1. ljoss streams rampable parameters as `rig.patch` messages. This is small, and needs no protocol
   change.
2. History and undo in ljoss.
3. Versions, with namchain's protocol change, once there is a second writer.

Separately, namchain needs a way to handle rebuilds of heavy rigs (C2).

## Your answers, 2026-09-28

Your replies to Claude's comments, as you wrote them. Each is labelled with the comment it answers.

**C2.** "It wouldn't have passed this soak on its own." Yes, I understand. I deliberately attempted
to cause namchain to struggle, to exercise it. I always want to see where things fail, to
understand them. I didn't expect namchain to hold up, necessarily, though I did expect to see some
overruns. I also don't expect to be able to solve for all of the reasons why we might put namchain
under too much pressure all at once, because there are many ways in which it can be, so it'll take
quite a lot of work for us to get to a point where the design and implementation are good enough.

**C4.** "Decide how to send an edit by what the engine does with it, not by the kind of control." I
agree. I do think that a bypass should be sent as a micro edit. In my mind, it can be logically
represented in our rig data as boolean, implemented as - effectively - a ramp of a master 'mix' for
a node from 0 to full or vice versa, and - though it's not exactly the same as a 'mix' parameter
with a numeric value in terms of model representation or how it's represented in the UI - it can be
dealt with similarly by the engine. I'd love to hear your further thoughts on it as I've likely
missed some important reason[s] why that may not / can not work.

**C5.** "Keep sending whole rigs for structural edits":

1. Why do they _need_ to cost a rebuild? Adding an item to a linked list data structure doesn't
   require recreating the entire list. Moving it to another position doesn't, deleting doesn't... I
   know that chains aren't _just_ linked lists, but why can't we treat them similarly? The
   operations that can be performed on rigs are constrained by what a user can do through the
   interface they're using. Switching rigs is, of course, likely to result in more changing than
   doesn't, and needs to be treated as an atomic operation in its own right. It's a level above a
   'macro' Edit (moving a node) - but still it's a single Edit if I stick to my domain language
   here - with quite different semantics from macro and micro.
2. "Sending the whole rig keeps the conversion from ljoss's tree to namchain's graph in one place".
   That sounds right to me, yes. I'd like to revisit that decision about tree -> graph conversion
   and discuss it in detail. I was happy for it to be taken earlier in the project as it let us
   move forwards but I'd like to go back to the basic assumptions and reasoning which brought about
   the decision and re-validate.
3. "The number of bytes sent isn't the problem; the work namchain does per message is" Yes, I
   understood this already. Agreed.

**C7.** "A merged history entry should keep the first "from" value" Agree, good call!

**C8.** "Undo is itself an edit." It is indeed. I've implemented undo & redo a few times and moving
edits between undo and redo stacks is part of the fun.

**C10.** "UUIDs work as opaque tokens, but namchain has nowhere to keep them." As a general
principle, when we're making data structures that have keys and values, unrecognised keys should
simply be ignored, to allow design and testing flexibility. When we revisit the tree -> graph we
will also need to revisit protocol, so we can cover that.

**C11.** "A returned UUID shows that namchain received your last edit, in order. It doesn't show
namchain's state matches yours." Correct. I don't have much logical reasoning to back up my thinking
about how they could help us with state checking, so let's ignore the state checking angle for now.

**C2 and C13, on heavy rigs.** And yes, namchain needing a way to handle 'rebuilds of heavy rigs':
Can we express that as namchain needing a way to handle the issue of having to have lots of
processing-intensive models running in parallel while making a transition? Does that express what
you said in a logical way or is it different entirely / in part?
