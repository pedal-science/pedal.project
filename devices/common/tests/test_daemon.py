"""The daemon's own decisions: the STATE flags, the bank's verdicts and what /status says
(docs/pedal-service.md)."""
import os
import pathlib
import sys
import tempfile
import time
import types
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "rootfs/usr/local/lib"))

from pedald import daemon, mapping, protocol  # noqa: E402
from pedald.engine import EngineError  # noqa: E402


class Flags(unittest.TestCase):
    def test_audio_ready_needs_a_running_device_and_a_document(self):
        flags = daemon.flags_from({"state": "running", "audible_generation": 1,
                                   "health": "ok"}, engine_down=False)
        self.assertTrue(flags & protocol.STATE_AUDIO_READY)

    def test_a_running_engine_with_no_document_is_not_ready(self):
        flags = daemon.flags_from({"state": "running", "audible_generation": 0,
                                   "health": "ok"}, engine_down=False)
        self.assertFalse(flags & protocol.STATE_AUDIO_READY)

    def test_a_crossfade_does_not_clear_audio_ready(self):
        # audible_generation lags generation through every crossfade; only > 0 counts (R5).
        flags = daemon.flags_from({"state": "running", "generation": 9, "audible_generation": 8,
                                   "health": "ok"}, engine_down=False)
        self.assertTrue(flags & protocol.STATE_AUDIO_READY)

    def test_health_and_mute_map_to_the_engines_own_words(self):
        flags = daemon.flags_from({"state": "lost", "audible_generation": 0, "mute": True,
                                   "health": "warn"}, engine_down=False)
        self.assertEqual(flags & protocol.STATE_HEALTH_MASK, protocol.STATE_HEALTH_WARN)
        self.assertTrue(flags & protocol.STATE_ENGINE_MUTED)
        self.assertFalse(flags & protocol.STATE_AUDIO_READY)

    def test_an_unreachable_engine_is_an_error_not_a_stale_ok(self):
        flags = daemon.flags_from({}, engine_down=True)
        self.assertEqual(flags & protocol.STATE_HEALTH_MASK, protocol.STATE_HEALTH_ERROR)


def fake_service(status=None, engine_down=False, link_open=True, session_up=True, pico=None,
                 rigs=None, verdicts=None):
    """A Service with only what /status reads, so the handler is tested without a board.

    `verdicts` is what the engine has said about the rigs, name -> the five fields; the rigs
    themselves default to the two the bank below holds.
    """
    service = object.__new__(daemon.Service)
    service.cfg = types.SimpleNamespace(uart_device="/dev/ttyAMA0", uart_baud=115200,
                                        http_port=47820)
    service.started = time.monotonic() - 12.5
    service.status = status if status is not None else {
        "state": "running", "health": "ok", "device": "hw:CARD=wm8960,DEV=0",
        "rig_name": "Crunch Lead", "generation": 4, "audible_generation": 4, "xruns": 0,
        "guard_trips": 0, "issues": [],
    }
    service.engine_down = engine_down
    service.mapping = mapping.Mapping(["Crunch Lead", "Ambient Wash"])
    service.mapping.note_rig("Crunch Lead")
    # /status reports the warm decision as well as the engine's warm object, so the fake has the
    # real WarmSet: `report()` is pure state, and a fake of it would be a second thing to keep true.
    service.warm = daemon.WarmSet(None, log=lambda _m: None)
    service.cost = daemon.RigCost(types.SimpleNamespace(), log=lambda _m: None)
    service.cost.note_rigs(rigs if rigs is not None else ["Crunch Lead", "Ambient Wash"],
                           time.monotonic())
    service.cost.verdicts.update(verdicts or {})
    service.mapping.verdicts = service.cost.verdicts
    service.link = types.SimpleNamespace(open=link_open, bytes_in=4096, bytes_out=512,
                                         drops=0, last_rx_at=time.monotonic() - 0.5,
                                         last_tx_at=time.monotonic() - 1.5,
                                         opened_at=time.monotonic() - 30.0)
    service.session = types.SimpleNamespace(session_up=session_up, frames_ok=12, frames_bad=1)
    service.pico = pico or {"fw": "0.1", "major": 1, "minor": 0, "caps": 0}
    service.bypass = False
    return service


class Status(unittest.TestCase):
    def test_status_reports_the_engine_the_link_and_the_bank(self):
        status, body = fake_service().handle_status(None)
        self.assertEqual(status, 200)
        self.assertEqual(body["engine"]["rig_name"], "Crunch Lead")
        self.assertTrue(body["engine"]["reachable"])
        self.assertTrue(body["link"]["session"])
        self.assertEqual(body["link"]["pico"]["fw"], "0.1")
        self.assertEqual(body["bank"]["current"], "Crunch Lead")
        self.assertEqual(body["bank"]["size"], 2)
        self.assertGreater(body["service"]["uptime_s"], 12)
        # The freshness of the link, which is what makes a rate possible: a counter alone cannot
        # say whether anything is arriving now.
        self.assertEqual(body["link"]["bytes_in"], 4096)
        self.assertEqual(body["link"]["drops"], 0)
        self.assertAlmostEqual(body["link"]["last_rx_s_ago"], 0.5, delta=0.5)
        self.assertAlmostEqual(body["link"]["open_s"], 30.0, delta=1.0)

    def test_an_unreachable_engine_is_reported_not_invented(self):
        _, body = fake_service(status={}, engine_down=True).handle_status(None)
        self.assertFalse(body["engine"]["reachable"])
        self.assertEqual(body["engine"]["issues"], [])

    def test_a_down_link_is_visible(self):
        _, body = fake_service(link_open=False, session_up=False).handle_status(None)
        self.assertFalse(body["link"]["open"])
        self.assertFalse(body["link"]["session"])


class EventKinds(unittest.TestCase):
    def test_the_daemon_translates_the_wire_kind_from_the_session(self):
        service = fake_service()
        service.log = lambda _m: None
        service.mapping = mapping.Mapping(["a", "b"])
        service.mapping.note_rig("a")            # a position, as the engine's rig_name gives
        loaded = []
        service.load_rig = loaded.append
        service.state_key = "something"
        service.on_event({"type": protocol.EVENT, "kind": 0x01, "a": 0, "b": 0,
                          "source": 1, "seq": 3})
        self.assertEqual(loaded, ["b"])          # rig_up steps from the first rig to the second

    def test_an_unknown_kind_is_ignored_rather_than_raised(self):
        service = fake_service()
        service.log = lambda _m: None
        service.on_event({"type": protocol.EVENT, "kind": 0x7F, "seq": 1})


#: `FakeEngine(costs=NO_COSTS)` answers every rig.cost with no cost object at all.
NO_COSTS = object()


class PlayableVerdict(unittest.TestCase):
    """The one rule the service reads out of the engine's cost object (P5, D9)."""

    def test_only_over_is_unusable(self):
        self.assertTrue(daemon.playable_verdict(None))                    # not asked yet
        self.assertTrue(daemon.playable_verdict({"verdict": "fits", "cost": 0.4}))
        self.assertTrue(daemon.playable_verdict({"verdict": "trimmed", "cost": 0.67,
                                                 "trimmed": True, "over": False}))
        self.assertFalse(daemon.playable_verdict({"verdict": "over", "cost": 1.02,
                                                  "over": True}))

    def test_the_verdict_is_the_engines_word_not_a_re_derivation(self):
        # A cost over the headroom that the engine calls `trimmed` is playable: it trimmed, and
        # the service does not second-guess the arithmetic (D9, and D6's visible trim).
        self.assertTrue(daemon.playable_verdict({"verdict": "trimmed", "cost": 0.95,
                                                 "headroom": 0.8, "over": False}))

    def test_a_verdict_without_the_word_is_not_a_refusal(self):
        self.assertTrue(daemon.playable_verdict({"cost": 0.9}))


class FakeEngine:
    """The calls the daemon makes of the engine, and what they answer.

    `service.engine` is a real `EngineClient` in these tests, with these methods replaced, so
    the surrounding object is the one that runs (`close()` still closes a socket that was never
    opened, which is what the loop does at shutdown). `costs` is rig name -> reply body; the
    default is a rig that fits, and `NO_COSTS` is an engine that answers with no cost object.

    The warm half is *modelled* rather than stubbed, because the policy is about the difference
    between what the service believes and what the engine holds. `warm_rig` is the one rig held
    warm and `rig_name` the audible one, both without ".json"; `rig_switch` swaps them the way
    the engine's handover does (`sync_warm_switch`); `status()` reports the pair, and
    `engine.status.warm` is the authority the service reconciles against.

    `warm_enabled=False` is a device with no `warm_cpus`: every warm call refuses
    `warm_disabled`, the status carries no `warm` object, and `rig_switch` refuses too — the
    engine's switch is off altogether there, which is the shape the service must keep working
    through.
    """

    def __init__(self, costs=None, status=None, error=None, warm=None, warm_error=None,
                 warm_enabled=True):
        self.costs = costs
        self.status_report = status if status is not None else {"state": "running"}
        self.error = error                  # an EngineError for every rig.cost, if set
        self.warm_enabled = warm_enabled
        self.warm_error = warm_error        # an EngineError for every rig.warm, if set
        self.rig_name = None                # the rig the engine is playing, without ".json"
        self.warm_rig = warm                # the rig it holds warm, without ".json"
        self.warm_doc_name = None           # the warm document's own name, when it differs
        self.asked = []                     # every rig name rig.cost was called with
        self.loaded = []                    # every rig made audible, by either call
        self.load_calls = []                # every rig.load
        self.switched = []                  # every rig.switch
        self.warmed = []                    # every rig.warm
        self.cooled = []                    # every rig.cool (None for the no-argument form)

    def status(self):
        report = dict(self.status_report)
        if self.rig_name is not None:
            report.setdefault("rig_name", self.rig_name)
        if self.warm_enabled:
            report["warm"] = self.warm_json()
        return {"ok": True, "status": report}

    def warm_json(self):
        """`engine.status.warm` as the engine writes it: every document with content, the audible
        one marked, and the warm entry named after the rig it holds."""
        entries = [{"doc": 0, "generation": 1, "audible": True, "state": "audible", "core": 3,
                    "name": self.rig_name}]
        if self.warm_rig is not None:
            entries.append({"doc": 1, "generation": 2, "audible": False, "state": "warm",
                            "core": 1, "name": self.warm_doc_name or self.warm_rig,
                            "rig": f"/rigs/{self.warm_rig}.json"})
        return {"enabled": True, "device_core": 3, "cores": [1, 2], "priority": 70,
                "active_doc": 0, "switches": 0, "set": entries}

    def rig_cost(self, rig):
        self.asked.append(rig)
        if self.error is not None:
            raise self.error
        if self.costs is NO_COSTS:
            return {"cost": {}}
        return (self.costs or {}).get(rig, engine_cost())

    def rig_load(self, rig):
        self.load_calls.append(rig)
        self.loaded.append(rig)
        self.rig_name = _name(rig)
        return {"ok": True, "rig": rig}

    def rig_switch(self, rig, fallback=True):
        self.switched.append(rig)
        if not self.warm_enabled:
            raise EngineError("warm_disabled", "warming is off: no warm_cpus are configured")
        name = _name(rig)
        if self.warm_rig == name:
            # The handover: the two compiled documents swap, so what was audible is warm now and
            # nothing is compiled or freed.
            self.warm_rig, self.rig_name = self.rig_name, name
            return {"ok": True, "switched": "warm", "rig": rig, "doc": 1, "core": 3,
                    "handover_blocks": 3, "fade_ms": 5, "completed": True}
        self.rig_name = name
        self.loaded.append(rig)
        return {"ok": True, "switched": "cold", "rig": rig, "reason": "nothing is warm"}

    def rig_warm(self, rig):
        self.warmed.append(rig)
        if not self.warm_enabled:
            raise EngineError("warm_disabled", "warming is off: no warm_cpus are configured")
        if self.warm_error is not None:
            raise self.warm_error
        name = _name(rig)
        replaced = self.warm_rig
        self.warm_rig = name
        return {"ok": True, "rig": rig, "name": name, "doc": 1, "core": 1, "generation": 2,
                "state": "warming", "replaced": replaced}

    def rig_cool(self, rig=None):
        self.cooled.append(rig)
        if not self.warm_enabled:
            raise EngineError("warm_disabled", "warming is off: no warm_cpus are configured")
        cooled = [] if self.warm_rig is None else [self.warm_rig]
        self.warm_rig = None
        return {"ok": True, "cooled": cooled}


def _name(rig):
    """A rig name without the ".json" the calls carry (the engine's status reports the name)."""
    return rig[:-5] if rig.endswith(".json") else rig


def engine_cost(verdict="fits", cost=0.4, headroom=0.8, **extra):
    """One `rig.cost` reply, as the engine writes it: the cost object inside the body."""
    body = {"verdict": verdict, "cost": cost, "headroom": headroom, "over": verdict == "over",
            "trimmed": verdict == "trimmed"}
    body.update(extra)
    return {"cost": body, "slimmed_models": [], "missing_assets": []}


def cost_service(rigs, costs=None, error=None, status=None, poll_s=daemon.COST_POLL_S, now=None,
                 warm=None, warm_error=None, warm_enabled=True):
    """A Service with a real RigCost and WarmSet, a fake engine and a temporary state root.

    `now` is the clock the service starts on; a test that passes its own passes the same value,
    and then owns every deadline the sweep compares against. `service.engine` and
    `service.cost.engine` are the same fake, as they are the same client in the daemon.
    """
    logs = []
    service = object.__new__(daemon.Service)
    service.log = logs.append
    service.logs = logs
    service.cfg = types.SimpleNamespace(rigs_root="/rigs", state_root=tempfile.mkdtemp())
    service.running = True
    service.engine_down = False
    service.status, service.positions_at, service.state_key = {}, 0.0, None
    service.bank_at = now if now is not None else time.monotonic()
    service.mapping = mapping.Mapping(rigs, log=logs.append)
    service.engine = FakeEngine(costs, status, error, warm=warm, warm_error=warm_error,
                                warm_enabled=warm_enabled)
    service.cost = daemon.RigCost(service.engine, poll_s=poll_s, log=logs.append)
    service.cost.note_rigs(rigs, time.monotonic() if now is None else now)
    service.mapping.verdicts = service.cost.verdicts
    service.warm = daemon.WarmSet(service.engine, log=logs.append)
    service.resume = types.SimpleNamespace(tick=lambda *_a: None)
    return service


class WarmNeighbour(unittest.TestCase):
    """The warm half of P5: the rig the footswitches reach next is the rig the engine holds warm,
    and a press makes the rig audible with `rig.switch` (D4, D9, D10)."""

    def setUp(self):
        self.now = time.monotonic()
        self.service = cost_service(["a", "b", "c"], now=self.now)
        self.engine = self.service.engine
        self.engine.rig_name = "a"
        self.service.mapping.note_rig("a")

    def _poll(self, at=None):
        self.service.poll_engine(self.now if at is None else at)

    def _press(self, kind):
        """A press, as the daemon does it: the mapping decides, then the rig is made audible."""
        action = self.service.mapping.action(kind)
        self.assertIsNotNone(action)
        self.service.load_rig(action["rig"])
        return action["rig"]

    # ------------------------------------------------------------------ the neighbour
    def test_the_rig_one_press_away_is_warmed(self):
        self._poll()
        self.assertEqual(self.engine.warmed, ["b.json"])
        self.assertEqual(self.service.warm.rig, "b")
        self.assertTrue(any("warming b.json" in line for line in self.service.logs))

    def test_the_warm_set_follows_the_press_and_drops_the_old_neighbour(self):
        # Warming displaces: the engine holds one warm rig, so the rig that is no longer one
        # press away leaves by being replaced — its reply names it — and nothing is cooled. A
        # `rig.cool` naming a rig that is no longer warm is refused (`warm_not_ready`), so
        # displacing is the only way to do this in one round trip and with no empty window.
        self._poll()
        self.assertEqual(self.engine.warm_rig, "b")
        self._press("rig_up")                       # a -> b; b was warm, so this is a handover
        self.assertEqual(self.engine.warm_rig, "c")
        self.assertEqual(self.engine.cooled, [])
        self.assertTrue(any("switched to b.json (warm)" in line for line in self.service.logs))

    def test_the_warm_set_is_emptied_when_nothing_is_one_press_away(self):
        service = cost_service(["a", "b"], now=self.now)
        service.engine.rig_name = "a"
        service.mapping.note_rig("a")
        service.poll_engine(self.now)
        self.assertEqual(service.engine.warm_rig, "b")
        # The engine now says b cannot play: the walk from a skips it and lands back on a, which
        # is the rig already playing. Nothing is next, so nothing should be held — and the
        # no-argument `rig.cool` is right whatever the service believes.
        service.cost.verdicts["b"] = {"verdict": "over", "cost": 1.02, "over": True}
        service.poll_engine(self.now + 1.0)
        self.assertEqual(service.engine.cooled, [None])
        self.assertIsNone(service.warm.rig)

    def test_a_warm_the_engine_refuses_is_logged_once_and_asked_again_later(self):
        self.engine.warm_error = EngineError("over_budget", "costs 1.02 of a core")
        self._poll()
        self.assertEqual(self.engine.warmed, ["b.json"])
        self._poll(self.now + 1.0)
        self._poll(self.now + 2.0)
        self.assertEqual(self.engine.warmed, ["b.json"])            # not every tick
        self.assertTrue(any("over_budget" in line for line in self.service.logs))
        self._poll(self.now + daemon.WARM_RETRY_S + 1.0)
        self.assertEqual(self.engine.warmed, ["b.json", "b.json"])  # the backstop asks again

    # ------------------------------------------------------------------ the switch
    def test_a_cold_answer_is_still_a_switch(self):
        # Nothing has been warmed, so the engine answers `cold` and loads the rig itself: the
        # service asked once, for `rig.switch`, and the sound happened. That fallback is the
        # engine's own, which is why the service never chooses between a handover and a load.
        self.service.load_rig("c")
        self.assertEqual(self.engine.switched, ["c.json"])
        self.assertEqual(self.engine.load_calls, [])
        self.assertEqual(self.engine.rig_name, "c")
        self.assertTrue(any("switched to c.json (cold" in line for line in self.service.logs))

    def test_a_press_still_switches_when_warming_is_off(self):
        # A device with no warm cores: `rig.warm` is refused `warm_disabled` — which is a
        # configuration, not a failure — and the engine's `rig.switch` is off with it, so a press
        # is answered by `rig.load`. A press always makes sound (D10).
        service = cost_service(["a", "b"], now=self.now, warm_enabled=False)
        service.engine.rig_name = "a"
        service.mapping.note_rig("a")
        service.poll_engine(self.now)
        self.assertEqual(service.engine.warmed, ["b.json"])         # asked once
        self.assertTrue(service.warm.disabled)
        self.assertTrue(any("warming is off" in line for line in service.logs))
        service.poll_engine(self.now + 1.0)
        service.poll_engine(self.now + daemon.COST_POLL_S + 1.0)
        self.assertEqual(service.engine.warmed, ["b.json"])         # and never asked again
        service.load_rig("b")
        self.assertEqual(service.engine.switched, ["b.json"])       # asked, and refused
        self.assertEqual(service.engine.load_calls, ["b.json"])     # so the load is the switch
        self.assertEqual(service.engine.rig_name, "b")
        self.assertTrue(any("loading b.json" in line for line in service.logs))

    # ------------------------------------------------------------------ what the engine holds
    def test_a_rig_the_engine_already_holds_is_not_compiled_again(self):
        # A bank of two, and the press swaps it: the handover leaves the rig the press left warm,
        # so asking for it — which the walk does, since it is the only other rig — would compile
        # a rig that is already warm. The service says what it knows instead of asking.
        service = cost_service(["a", "b"], now=self.now)
        service.engine.rig_name = "a"
        service.mapping.note_rig("a")
        service.poll_engine(self.now)
        self.assertEqual(service.engine.warmed, ["b.json"])
        action = service.mapping.action("rig_up")
        service.load_rig(action["rig"])
        self.assertEqual(service.engine.warm_rig, "a")              # what the handover left warm
        self.assertEqual(service.engine.warmed, ["b.json"])         # nothing more was asked for

    def test_a_poll_believes_the_engines_own_warm_set(self):
        # A handover the service did not make — ljoss switched the rig, or an operator warmed
        # something — leaves the engine holding what it was playing. The status is the authority
        # for what is warm, so the rig it names is not compiled again by a service that still
        # believes the rig it asked for.
        service = cost_service(["a", "b"], now=self.now)
        service.engine.rig_name = "a"
        service.mapping.note_rig("a")
        service.poll_engine(self.now)
        self.assertEqual(service.engine.warmed, ["b.json"])
        service.engine.rig_name, service.engine.warm_rig = "b", "a"   # the handover, from outside
        service.poll_engine(self.now + daemon.WARM_ADOPT_S + 1.0)
        self.assertEqual(service.mapping.current_name(), "b")       # the position followed it
        self.assertEqual(service.engine.warmed, ["b.json"])         # a is warm: nothing asked

    def test_a_warm_rig_is_identified_by_its_path_not_its_document_name(self):
        # The engine's `name` is the document's own name, and a rig file need not share it: the
        # pedal's `last.json` holds a document called `soak-three-chains`, and ljoss names the
        # documents it writes. The bank knows a rig by its file, so the path is what decides
        # whether the rig the engine holds is the one the walk wants — believing the name would
        # leave the service asking, every grace period, for a rig it already has.
        service = cost_service(["a", "b"], now=self.now)
        service.engine.rig_name = "a"
        service.mapping.note_rig("a")
        service.poll_engine(self.now)
        self.assertEqual(service.engine.warmed, ["b.json"])
        service.engine.warm_doc_name = "B Lead"                     # the document's own name
        service.poll_engine(self.now + daemon.WARM_ADOPT_S + 1.0)
        self.assertEqual(service.warm.rig, "b")
        self.assertEqual(service.engine.warmed, ["b.json"])


class LoadRig(unittest.TestCase):
    """The belt to the mapping's braces: an unusable rig is never activated (P5)."""

    def setUp(self):
        self.service = cost_service(["Big Lead", "Crunch", "Ambient Wash"], costs={
            "Big Lead.json": engine_cost("over", cost=1.02),
            "Crunch.json": engine_cost("trimmed", cost=0.67),
        })
        self.service.cost.verdicts["Big Lead"] = {"verdict": "over", "cost": 1.02,
                                                  "headroom": 0.8, "trimmed": True, "over": True}

    def test_an_unusable_rig_is_not_activated(self):
        self.service.load_rig("Big Lead")
        self.assertEqual(self.service.engine.loaded, [])
        self.assertTrue(any("Big Lead" in line and "over" in line for line in self.service.logs))

    def test_a_usable_rig_is_activated(self):
        self.service.load_rig("Crunch")
        self.assertEqual(self.service.engine.loaded, ["Crunch.json"])

    def test_a_rig_with_no_verdict_is_activated(self):
        # Only the engine refuses a rig; an unasked one goes to it and is refused there if it
        # deserves to be. That is why a missing verdict is not a refusal here.
        self.service.load_rig("Ambient Wash")
        self.assertEqual(self.service.engine.loaded, ["Ambient Wash.json"])


class CostSweep(unittest.TestCase):
    """Costing the bank: what is asked, when, and what is remembered (P5, D9)."""

    def setUp(self):
        self.now = time.monotonic()
        self.service = cost_service(["a", "b", "c"], now=self.now)
        self.engine = self.service.engine

    def _verdicts(self):
        return {name: (None if v is None else v["verdict"])
                for name, v in self.service.cost.verdicts.items()}

    def test_the_bank_is_costed_without_being_asked_to_play(self):
        self.service.cost.tick(self.now)
        self.service.cost.tick(self.now + 1.0)
        self.assertEqual(sorted(self.engine.asked), ["a.json", "b.json", "c.json"])
        self.assertEqual(self._verdicts(), {"a": "fits", "b": "fits", "c": "fits"})
        self.assertEqual(self.engine.status_report, {"state": "running"})   # nothing was loaded

    def test_a_verdict_is_not_asked_for_again_before_it_goes_stale(self):
        self.service.cost.tick(self.now)
        self.service.cost.tick(self.now + 1.0)
        self.assertEqual(len(self.engine.asked), 3)
        for tick in range(3, 30):                   # the 1 Hz status poll is not a cost poll
            self.service.cost.tick(self.now + tick)
        self.assertEqual(len(self.engine.asked), 3)

    def test_a_stale_verdict_is_asked_for_again(self):
        # Two rigs a tick, so the first pass is a, b, then c: at the backstop, a and b (asked at
        # t+0) are stale and c (asked at t+1) is not — a verdict is never older than the backstop
        # by more than the two ticks it takes the sweep to come round.
        self.service.cost.tick(self.now)
        self.service.cost.tick(self.now + 1.0)
        self.service.cost.tick(self.now + daemon.COST_POLL_S + 1.0)
        self.assertEqual(sorted(self.engine.asked), ["a.json", "a.json", "b.json",
                                                     "c.json", "c.json"])

    def test_a_new_rig_in_the_library_is_asked_about_and_the_old_verdicts_are_kept(self):
        self.service.cost.tick(self.now)
        self.service.cost.tick(self.now + 1.0)
        self.engine.asked.clear()
        self.service.cost.note_rigs(["a", "b", "c", "d"], self.now + 2.0)
        self.service.cost.tick(self.now + 2.0)
        # The new rig is the only thing missing a verdict, so it is what the sweep asks for;
        # the three it already knows are not asked again (that is the backstop's job).
        self.assertEqual(self.engine.asked, ["d.json"])
        self.assertEqual(self._verdicts()["c"], "fits")              # and nothing was thrown away
        self.assertEqual(self._verdicts()["a"], "fits")

    def test_a_removed_rig_keeps_no_verdict(self):
        self.service.cost.tick(self.now)
        self.service.cost.tick(self.now + 1.0)
        self.service.cost.note_rigs(["a"], self.now + 2.0)
        self.assertEqual(self.service.cost.status().keys(), {"a"})

    def test_forgetting_everything_is_what_a_bank_change_and_a_startup_do(self):
        self.service.cost.tick(self.now)
        self.service.cost.tick(self.now + 1.0)
        self.engine.asked.clear()
        self.service.cost.forget()
        self.service.cost.tick(self.now + 2.0)
        self.service.cost.tick(self.now + 3.0)
        self.assertEqual(sorted(self.engine.asked), ["a.json", "b.json", "c.json"])

    def test_an_over_verdict_is_stored_and_handed_to_the_mapping(self):
        self.engine.costs = {"b.json": engine_cost("over", cost=1.02, full_cost=1.3)}
        self.service.cost.tick(self.now)
        self.service.cost.tick(self.now + 1.0)
        self.assertFalse(self.service.mapping.is_usable("b"))
        self.assertEqual(self.service.cost.verdict("b")["cost"], 1.02)

    def test_a_refused_rig_keeps_no_verdict_and_is_not_a_failure(self):
        self.service.cost.engine = FakeEngine(error=EngineError("rig_not_found", "no b.json"))
        self.service.cost.tick(self.now)                # does not raise
        self.service.cost.tick(self.now + 1.0)
        self.assertIsNone(self.service.cost.verdict("a"))
        self.assertTrue(self.service.mapping.is_usable("a"))     # unasked, so not refused
        # Asked once, not once a second: a rig the engine will not describe is not retried
        # every tick, or the journal fills with the same line.
        self.assertEqual(self.service.cost.engine.asked.count("a.json"), 1)
        self.assertTrue(any("rig.cost" in line for line in self.service.logs))

    def test_an_engine_that_answers_without_a_cost_keeps_no_verdict(self):
        # No cost object at all is the engine's shape when it has nothing to say about a rig:
        # asked, and there is no verdict to cache — which is not a failure and not a refusal.
        self.engine.costs = NO_COSTS
        self.service.cost.tick(self.now)
        self.service.cost.tick(self.now + 1.0)
        self.assertIsNone(self.service.cost.verdict("a"))
        self.assertTrue(self.service.mapping.is_usable("a"))


class LibraryChange(unittest.TestCase):
    """A rig that appears in the library is noticed and costed (P5). The engine scans; the
    service reads the same listing it read at startup, slowly."""

    def setUp(self):
        self.rigs_root = tempfile.mkdtemp()
        with open(os.path.join(self.rigs_root, "one.json"), "w") as handle:
            handle.write("{}")
        self.now = time.monotonic()
        self.service = cost_service([], now=self.now)
        self.service.cfg.rigs_root = self.rigs_root
        # As after a service that has been up a while: the first poll lists the root.
        self.service.bank_at = self.now - daemon.COST_POLL_S - 1.0
        self.service.cost.tick(self.now)          # nothing to ask: the listing is empty

    def _names(self):
        return [n[:-5] for n in sorted(os.listdir(self.rigs_root)) if n.endswith(".json")]

    def _relist(self, at):
        """What the daemon does at the top of a poll: list the root, hand it over, then sweep."""
        self.service.relist_rigs(at, self._names())
        self.service.cost.tick(at)

    def test_a_rig_added_to_the_library_is_costed(self):
        with open(os.path.join(self.rigs_root, "two.json"), "w") as handle:
            handle.write("{}")
        self._relist(self.now + daemon.COST_POLL_S + 1.0)
        self.assertEqual(self.service.cost.rigs, ["one", "two"])
        self.assertEqual(self.service.engine.asked, ["one.json", "two.json"])
        self.assertTrue(any("library changed" in line for line in self.service.logs))

    def test_a_rig_removed_from_the_library_keeps_no_verdict(self):
        self._relist(self.now + 1.0)
        self.assertEqual(self.service.cost.rigs, ["one"])
        os.unlink(os.path.join(self.rigs_root, "one.json"))
        self._relist(self.now + daemon.COST_POLL_S + 2.0)
        self.assertEqual(self.service.cost.status(), {})

    def test_the_listing_is_not_repeated_before_the_interval(self):
        self._relist(self.now)                    # the first poll lists the root
        self.assertEqual(self.service.cost.rigs, ["one"])
        listed_at = self.service.bank_at
        with open(os.path.join(self.rigs_root, "two.json"), "w") as handle:
            handle.write("{}")
        self._relist(self.now + 1.0)              # too soon: the root is not read again
        self.assertEqual(self.service.cost.rigs, ["one"])
        self.assertEqual(self.service.bank_at, listed_at)


class EngineRecovery(unittest.TestCase):
    """`poll_engine` drops every verdict when the engine comes back: a new process may have
    loaded a different cost table, and a verdict from before it is a guess."""

    def test_an_engine_that_recovers_is_asked_for_the_bank_again(self):
        now = time.monotonic()
        service = cost_service(["a", "b"], now=now)
        service.cost.tick(now)
        self.assertEqual(sorted(service.cost.verdict("a")), ["cost", "headroom", "over",
                                                             "trimmed", "verdict"])

        def unreachable():
            raise EngineError("engine_unreachable", "gone")

        service.engine.status = unreachable
        service.poll_engine(now + 1.0)                  # it goes away
        self.assertTrue(service.engine_down)
        service.engine.status = lambda: {"ok": True, "status": {"state": "running"}}
        # `refresh=False`: the same poll without the tick, so the drop is what is observed — a
        # real poll drops the map and then starts asking again in the same breath.
        service.poll_engine(now + 2.0, refresh=False)
        self.assertIsNone(service.cost.verdict("a"))
        self.assertTrue(any("recovered" in line for line in service.logs))
        service.poll_engine(now + 3.0)                  # the ordinary poll asks the bank again
        service.poll_engine(now + 4.0)
        self.assertEqual(sorted(service.engine.asked), ["a.json", "a.json", "b.json",
                                                       "b.json"])

    def test_an_unreachable_engine_leaves_no_verdict(self):
        # A verdict is the engine's word about a rig, and an engine that is not answering has no
        # word: `/status` says "no verdict" rather than showing a cost from a process that may be
        # gone, and the rig stays selectable (the engine refuses the publish if it must).
        now = time.monotonic()
        service = cost_service(["a"], now=now)
        service.cost.tick(now)
        self.assertIsNotNone(service.cost.verdict("a"))

        def unreachable():
            raise EngineError("engine_unreachable", "gone")

        service.engine.status = unreachable
        service.poll_engine(now + 1.0)
        self.assertTrue(service.engine_down)
        self.assertIsNone(service.cost.verdict("a"))
        self.assertTrue(service.mapping.is_usable("a"))
        self.assertTrue(any("status failed" in line for line in service.logs))


class StatusVerdicts(unittest.TestCase):
    """`/status` carries the bank's verdicts (P5): a panel or ljoss reads them from there."""

    def test_the_verdicts_are_reported_per_rig(self):
        _, body = fake_service(verdicts={
            "Crunch Lead": {"verdict": "trimmed", "cost": 0.67, "headroom": 0.8, "trimmed": True,
                            "over": False},
            "Ambient Wash": {"verdict": "over", "cost": 1.02, "headroom": 0.8, "trimmed": True,
                             "over": True},
        }).handle_status(None)
        verdicts = body["bank"]["verdicts"]
        self.assertEqual(verdicts["Crunch Lead"]["verdict"], "trimmed")
        self.assertTrue(verdicts["Ambient Wash"]["over"])
        self.assertEqual(verdicts["Ambient Wash"]["headroom"], 0.8)
        self.assertEqual(body["bank"]["verdict_max_age_s"], daemon.COST_POLL_S)
        # The engine's per-node array is the diagnostic's business, not this route's: a bank of
        # them is a megabyte on a route a panel polls.
        self.assertNotIn("nodes", verdicts["Crunch Lead"])

    def test_a_rig_the_engine_has_not_answered_for_is_null(self):
        _, body = fake_service(verdicts={"Crunch Lead": {"verdict": "fits", "cost": 0.2,
                                                         "headroom": 0.8, "trimmed": False,
                                                         "over": False}}).handle_status(None)
        self.assertIsNone(body["bank"]["verdicts"]["Ambient Wash"])

    def test_a_rig_removed_from_the_library_is_not_reported(self):
        service = fake_service(rigs=["Crunch Lead"], verdicts={
            "Crunch Lead": {"verdict": "fits", "cost": 0.2, "headroom": 0.8, "trimmed": False,
                            "over": False},
            "Gone": {"verdict": "over", "cost": 9.0, "headroom": 0.8, "trimmed": True,
                     "over": True}})
        _, body = service.handle_status(None)
        self.assertEqual(list(body["bank"]["verdicts"]), ["Crunch Lead"])


class StatusWarm(unittest.TestCase):
    """`/status` carries the engine's own warm object (P5's warm half): it is the authority for
    what is warm, and a summary here would be a second copy of it to keep true."""

    def test_the_engines_warm_object_is_reported_as_it_stands(self):
        warm = {"enabled": True, "device_core": 3, "cores": [1, 2], "priority": 70,
                "active_doc": 0, "switches": 4, "cold_switches": 1,
                "set": [{"doc": 1, "audible": False, "state": "warm", "name": "next",
                         "core": 1, "behind_blocks": 0, "blocks_dropped": 0}]}
        _, body = fake_service(status={"state": "running", "warm": warm}).handle_status(None)
        self.assertEqual(body["engine"]["warm"], warm)

    def test_a_device_with_no_warm_cores_reports_nothing(self):
        # The engine leaves the object out when warming is off, which is how the panel tells
        # "this device cannot warm" from "nothing is warm yet".
        _, body = fake_service().handle_status(None)
        self.assertIsNone(body["engine"]["warm"])


class WarmDecision(unittest.TestCase):
    """What the service decided to do about the warm set, beside what is warm (2026-10-09).

    The engine's object says what *is* warm; this says what the policy wanted and why it is not
    there, which is the difference a player sees between "keep playing, it is coming" and "the rig
    playing is too heavy to keep a neighbour ready".
    """

    def test_a_held_neighbour_is_reported_as_held(self):
        warm = daemon.WarmSet(None, log=lambda _m: None)
        warm.wanted = "Ambient Wash"
        warm.rig = "Ambient Wash"
        self.assertEqual(warm.report()["state"], "held")
        self.assertIsNone(warm.report()["reason"])

    def test_nothing_one_press_away_is_idle(self):
        warm = daemon.WarmSet(None, log=lambda _m: None)
        warm.wanted = None
        self.assertEqual(warm.report(),
                         {"state": "idle", "wanted": None, "held": None, "reason": None})

    def test_a_refusal_carries_its_reason_and_the_retry(self):
        # `over_budget` is the coexistence charge: the engine refused to hold a neighbour because
        # the rig the player is hearing could not afford it (D3, T5's measurement).
        warm = daemon.WarmSet(None, log=lambda _m: None)
        warm.wanted = "Ambient Wash"
        warm.failed = "over_budget"
        warm.failed_rig = "Ambient Wash"
        warm.retry_at = 100.0
        report = warm.report(now=40.0)
        self.assertEqual(report["state"], "refused")
        self.assertEqual(report["reason"], "over_budget")
        self.assertEqual(report["retry_in_s"], 60.0)

    def test_a_device_with_no_warm_cores_says_off(self):
        warm = daemon.WarmSet(None, log=lambda _m: None)
        warm.disabled = True
        warm.failed = "warm_disabled"
        self.assertEqual(warm.report()["state"], "off")

    def test_status_carries_the_decision(self):
        _, body = fake_service().handle_status(None)
        self.assertEqual(body["engine"]["warm_decision"]["state"], "idle")


if __name__ == "__main__":
    unittest.main()
