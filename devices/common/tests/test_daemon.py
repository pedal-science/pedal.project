"""The daemon's own decisions: the STATE flags, and what /status says (docs/pedal-service.md)."""
import pathlib
import sys
import time
import types
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "rootfs/usr/local/lib"))

from pedald import daemon, mapping, protocol  # noqa: E402


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


def fake_service(status=None, engine_down=False, link_open=True, session_up=True, pico=None):
    """A Service with only what /status reads, so the handler is tested without a board."""
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
    service.link = types.SimpleNamespace(open=link_open)
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


if __name__ == "__main__":
    unittest.main()
