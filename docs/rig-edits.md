# Rig edits: a proposed design change

**Proposed** by you on 2026-09-28. It isn't a decision yet. Claude's comments on it follow the
proposal, then your answers to them. Claude's replies to those (2026-10-01) are at the end; they
bring in the step 8 soak on vip and propose what to build next.

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

## Claude's replies, 2026-10-01

These reply to your answers, with what the step 8 soak on vip found (`plan.md`, "Next session
starts with", item 3). Each is labelled with the answer it replies to. None of it is built.

### What the vip soak adds

The replayed session failed step 8's gate on vip by two blocks, at 93% and 92% of the deadline.
Both were structural edits to Ambient Wash, in the second of the session's three loops:
- 17 s into the loop, a second amp added after the first;
- 27 s in, the first amp removed.

The same two edits peaked at 47% and 71% in the first loop, and at 72% and 46% in the third.

- Every knob in the session was already a ramp: 510 patches, all smooth. What's left per loop is
  six structural edits:
  - a model pick (3 s);
  - the amp added (17 s) and the first one removed (27 s);
  - a switch to Crunch Lead (19.6 min), and an amp added to it (19.8 min);
  - the switch back to Ambient Wash as the loop starts again.
- ljoss has no other way to send any of them. So "ljoss sends fewer rebuilds" comes down to your
  question in C5: why does each one cost a rebuild?
- Ambient Wash with one amp runs at p50 8%, and with the second amp at about 14%. During the fade
  namchain runs both whole plans, so adding the amp briefly runs three amps, two cab IRs and two
  delays.

### Replies

**C2 and C13, on heavy rigs.** Partly. There are two problems, and your wording describes the
second.
1. During a structural edit, namchain runs two whole copies of the chain, not only the part that
   changed. Adding one amp to a one-amp rig runs three amps for the fade. That's C5 below, and
   fixing it is what this soak needs.
2. Some changes do need a lot running at once: switching between two heavy rigs, or swapping one
   heavy model for another. namchain has to check before it starts whether the change fits in the
   deadline. If it doesn't, the transition runs differently: a shorter fade, a staggered start, a
   brief dip, or a refusal with a reason. That's admission control (namchain's
   `docs/transitions.md`, "What is next", item 1).
- "In parallel" here means inside one audio block, on one core: the two plans run one after the
  other within 1.33 ms. Rendering the incoming plan on a second core would make it truly parallel;
  vip's core 2 is isolated beside the render thread's core 3, and P7 moved the codec's DMA
  interrupt off it to core 0, so core 2 is free for that. It costs a hand-over between cores
  every block, and this soak doesn't need it.

**C4, bypass as a ramp.** It works, and namchain is closer to it than this doc said.
- A bypassed node already keeps running, so its state stays warm, and its output is replaced by
  its input (`docs/transitions.md`, "Bypass"). Only the switch is structural: the flag is part of
  the graph, so flipping it compiles a new plan and fades the whole chain across.
- In your version the plan keeps a wet/dry mix per block, and a bypass ramps it. There's no
  compile, no second plan and nothing reloaded, and ljoss streams it like a knob.
- Four things to settle on the way, none of which stops it:
  - **A bypassed block still costs its CPU.** namchain keeps it running so that un-bypassing
    doesn't start from stale state: a NAM model's history, or a delay's old echoes. The
    alternative stops it while bypassed. On un-bypass it would run at mix 0 on the live input for a
    short warm-up (a model's receptive field, tens of ms), then ramp in. That saves the CPU, but
    un-bypass takes longer.
  - **Trails.** Fading a delay's output cuts its echoes off. Pedals call the other behaviour
    "trails": fade the input instead, and let the echoes ring out. It's a choice per block type,
    and namchain has a placeholder for it (`tail_hold`).
  - **One fade per block, not per node.** An amp is two nodes. namchain should fade the block as a
    unit, from the block's input to its output, grouping its nodes by `element`. That's the same
    unit as C9's versions.
  - **Latency.** The dry and wet signals have to line up. Every node namchain has today is
    zero-latency, so they do. A future node with latency (a look-ahead limiter, a linear-phase EQ)
    needs its dry path delayed to match.

**C5, point 1: why structural edits cost a rebuild.** They don't have to. Your linked-list
intuition holds for the graph, which is cheap to edit. The cost is in what namchain does with the
edited graph, and most of it can be avoided.
- Today, once anything in a chain's graph changes, namchain compiles a new plan for the whole
  chain, and **every node in it is created again** (`src/daemon/daemon.cpp`, where it compares the
  chains):
  - every NAM model and IR is read from its file again and reset to silence;
  - every delay starts empty;
  - then both plans run for the 5 ms fade.
- So an edit to one block pays for all of them:
  - the CPU of the fade, which is this soak's failure;
  - the amps nobody touched restart from NAM's silence prewarm, which E1 found sounds wrong for
    170–340 ms;
  - the echoes in flight vanish at every structural edit. Ambient Wash's delay (345 ms, 79% mix)
    should make that audible.
- It was built that way because swapping whole, immutable plans is simple and safe. The render
  thread never shares a node with the control thread, and a failed compile can't leave a chain
  half changed.

**Proposal: carry unchanged nodes across.** When namchain builds the new plan, a node whose id,
type and settings haven't changed moves into it as the same object, state and all, instead of being
created again. Only changed nodes are loaded and warmed, and the transition covers only what changed:

| Edit | What runs during the fade (today: both whole plans) |
|---|---|
| Add a block | the chain, plus the new block fading in from its input, as un-bypass would |
| Remove a block | the chain, with the block fading out to its input as bypass would; then it's dropped |
| Pick a model or IR, or change a setting that can't ramp (a cut's slope) | the old and new block side by side; nothing else doubles |
| Move a block | the stretch between its old and new places, rebuilt and crossfaded; blocks outside it carry over |
| Switch rig | both whole plans, since nothing carries over; admission control keeps that safe |

- For this soak: adding the second amp would run two amps, one cab and one delay, which is the rig
  it's becoming. Removing it would be the same. The peak would be about the heavier rig's own load
  (p50 14%) rather than the two rigs' loads added together.
- What needs care:
  - A node belongs to one plan at a time. The old plan stops running in the block where the new
    one starts, and it mustn't free what it handed over.
  - A carried-over node can't be prewarmed on the control thread, because the render thread is
    still using it. Only new nodes are prewarmed, each on its own.
  - The fade moves from the chain's output to wherever the change is. In a series chain that's the
    stretch from the first changed node to the last. Each of ljoss's parallel sections has one way
    in and one way out, so the same works per lane or section. Where namchain can't find such a
    stretch, it falls back to today's whole-chain fade.
- A whole document and a patch would then cost the same, because namchain works out what changed
  by node id either way. ljoss can keep sending whole documents for structural edits (C5), and undo
  and redo stay inside ljoss. How an edit is sent becomes a question of traffic only, which we
  agree isn't the problem.

**C5, point 2: the tree-to-graph conversion.** These are the assumptions behind it, as I
understand them, and whether each still holds:
1. **namchain stays a generic engine (D4).** It runs graphs of nodes and knows nothing of ljoss's
   blocks, lanes and sections. That still holds. Two layers above nodes exist already: macros (an
   amp's tone stack, a cab, a feedback delay), and `element`, which says which nodes make one block.
2. **A graph can say anything ljoss's tree can.** True: series blocks and parallel lanes are a
   narrow kind of graph. Nothing ljoss shows needs more, though a feedback loop or a side-chain
   would.
3. **One place converts.** ljoss's `DocumentEncoder` is the only code that knows how a tree becomes
   a graph: an amp's two nodes, a lane at 0 dB having no gain node, a section's split and mix.
   Sending edits as graph ops would need that knowledge twice, once for a whole rig and once per
   kind of edit.
4. **Edits travel as whole documents.** That was the cheap choice when nothing cared what an edit
   cost. It's the assumption the rebuild cost hangs on, and with nodes carried across, the cost no
   longer depends on it.

The options:
- **(a) Keep the conversion in ljoss.** ljoss sends whole graphs for structural edits, and namchain
  compares them by node id and carries nodes across. This is the least change, and the conversion
  stays in one place. namchain sees which nodes changed, not that you moved the delay before the
  amp; because ids survive a move, that's enough.
- **(b) ljoss sends graph ops per edit.** `rig.patch` already has `add_node`, `remove_node`,
  `connect` and `rewire`. Messages get smaller, but the conversion is needed twice (point 3).
- **(c) namchain takes the tree.** Blocks, lanes and sections become protocol objects, and edits
  become tree ops ("insert this block in lane 2 at position 3"). The engine would know what the
  user meant, and its patch vocabulary would match ljoss's. But namchain would then own one app's
  editing model, against D4, and every other client (the pedal service, the tests, a future app)
  would have to speak ljoss's tree.

I'd take (a) now, and revisit it only if traffic, or namchain needing to know what the user meant,
becomes the limit. That's your call.

**C10, unknown keys.** namchain refuses unknown parameters on purpose. Before it did, a rig could
say `"gainz": 3` and be published happily, which in a UI is a knob that does nothing (`lint_params`
in `src/graph/plan.cpp`, and `docs/ljoss-comparison.md` §3.5). Both aims fit if a document has a
place namchain never reads:
- a `meta` object on the document, each chain and each node;
- kept as written, and returned by `rig.get`;
- every other key still checked.

Versions would go there. Ignoring every unknown key also works, but then a mistyped parameter is
silent. Either way it's a protocol change in namchain, so it waits for the protocol revisit you
mentioned.

### What I'd build, in order

1. **namchain: carry unchanged nodes across a structural edit,** with the fade local to what
   changed (C5, point 1).
   - Tested offline first, with the glitch detector judging each edit. That needs structural ops
     in its timeline (`docs/transitions.md`, "What is next", item 3).
   - Then the same replay on vip. ljoss, the protocol and the recorded session stay as they are.
   - Done when the replay passes step 8's gate, with the second amp's add and remove peaking near
     the two-amp rig's own load.
2. **namchain: bypass as a ramp per block** (C4), built on step 1. ljoss then streams a bypass as a
   patch.
3. **namchain: admission control** for what still runs two whole plans: rig switches, and D10.
4. **ljoss: history and undo** (C13 step 2). Steps 1–3 don't affect it.

## Your decisions, 2026-10-01

1. **Build step 1:** namchain carries unchanged nodes across a structural edit, and fades only what
   changed.
2. **The conversion stays in ljoss (a).** ljoss sends whole graphs for structural edits, and
   namchain works out what changed by node id.
3. **Unknown keys go in `meta`.** The document, each chain and each node can carry a `meta` object
   that namchain keeps as written, returns from `rig.get` and never reads. Every other key is still
   checked. Built: namchain `2b5584e` (protocol feature `meta`). A change to `meta` alone is not
   an edit to the graph, so it keeps the generation. Versions will go there.

## Step 1 built, 2026-10-01

namchain `974060c`: a structural edit compares the two graphs node by node, keeps the instances
(and state) of nodes that didn't change, and fades only the inputs whose driver changed. It falls
back to the whole-chain crossfade when the input or output node changes, or nothing with state
would be kept. namchain's `docs/transitions.md`, "Local transitions", has the rules.

- **Offline** (`namchain-transition`, Mac, q64): adding the second amp to Ambient Wash ran at a
  mean 52 µs during the fade against 83 µs for the crossfade, with the two-amp rig steady at 54 µs;
  removing it, 52 against 82. All edits pass the detector's rules 1–3. A local edit also keeps
  the 620 ms feedback delay's echoes, which the crossfade dropped.
- **On vip,** the same replay soak as before: **PASS**, worst block 84% (was 94%), none over 90%.
  12 of the 18 structural edits were local; the other 6 were rig switches. The details are in
  `plan.md`, vip soak item 3.
- **Done-when met** (measured steady on vip, 2026-10-01): the second amp's add and remove peaked
  at 70–84%, and the two-amp rig alone peaks at 63–98% per 10 s interval (median 79%). The same
  measurement found that **the two-amp rig fails the gate by itself** at q64 on vip (7 blocks over
  90% in 10 minutes, no edits). That is a load problem, not an edit problem; `plan.md`, vip soak
  item 3, has the numbers and the open choice.


## Step 2 built, 2026-10-01

namchain `2e1a63a` (protocol feature `bypass_ramp`): a bypass is no longer a structural edit. The
render thread crossfades the node between its output and its dry input, equal-power, over the fade
length (5 ms), and a toggle mid-fade turns around from where it is. A patch or `rig.set` that only
bypasses blocks keeps the generation and reports transitions of kind `ramps` with a `bypasses`
count. Only nodes with one input and one output take the ramp; a bypass beside a structural edit
still fades as part of that edit. namchain's `docs/transitions.md`, "Bypass", has the rules.

- **ljoss needs no patch op.** It sends a bypass as the whole document, and namchain's
  node-by-node comparison already turns that into a ramp, so a patch op would save bytes, not work.
  ljoss `d57933d` says so in `EngineEdits.swift`, and its `CheckStreaming` tool expects no rebuild
  from an engine with `bypass_ramp`: against `2e1a63a`, 804 ramps over a 201-step drag and a
  bypass, 0 rebuilds.
- **Debt:** a macro block (several nodes) fades node by node, each over its own fade, not as one
  unit. All of them start in the same block, so nodes in series fade together, close to one fade
  but not identical to it; fading by element is the remedy if that is ever heard.
