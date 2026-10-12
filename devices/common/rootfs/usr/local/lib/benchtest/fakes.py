"""The benchtests with nothing behind them, for `--fake`.

Every benchtest has a fake with the real one's result shape: pass or fail, the blocks it exercised,
and the check that ties each block to the result. Nothing here talks to pedal-diag, namchaind, the
workstation helper, the audio interface or the Debug Probe, and nothing waits.

Each fake holds a queue of outcomes; a run takes the next one, and an empty queue passes. An
outcome is a dict:

    {"ok": bool}                       pass or fail with the catalog's own wording
    {"ok": false, "component": id, "check": str}
                                       fail on a named check that exercises a named block
    {"status": "not_run"}              could not judge anything (paints nothing)
    {"hum": true}                      Guitar input noise only: the known mains hum
    {"codec_present": false}           Codec only: say the codec is absent, which stops the
                                       noise benchtests in the same run
    "summary": str                     optional, replaces the result's summary

Noise fakes go through catalog.py's real classifiers with made-up analyses, so the pass bars
and the blocks a failure paints are the real ones.
"""

import collections
import threading
import time

from . import catalog


def _analysis(rms, lines=(), seconds=18.0):
    return {"dc_offset": 0.0, "rms_dbfs": rms, "rms_dbfs_a": rms - 1.0, "peak_dbfs": rms + 11.0,
            "lines_low": [{"hz": hz, "dbfs": level} for hz, level in lines],
            "lines_high": [{"hz": 1500.0, "dbfs": rms - 12.0}],
            "seconds": seconds, "sample_rate": 48000}


ENGINE_LINES = ((750.0, -115.0),)


class FakeBench:
    needs_helper = False
    fake = True

    def __init__(self, clock=time.time):
        self._clock = clock
        self._lock = threading.Lock()
        self.queues = {t: collections.deque() for t in catalog.TEST_IDS}
        self.ran = []

    # -- the control the tests and the page use ------------------------------------------------

    def push(self, test_id, outcome):
        catalog.test(test_id)
        with self._lock:
            self.queues[test_id].append(normalise(outcome))

    def set_next(self, test_id, outcome):
        """The page's control: the next run of this benchtest takes this outcome, then passes."""
        catalog.test(test_id)
        with self._lock:
            self.queues[test_id].clear()
            self.queues[test_id].append(normalise(outcome))

    def reset(self, ran=True, queues=True):
        with self._lock:
            if queues:
                for q in self.queues.values():
                    q.clear()
            if ran:
                self.ran = []

    def snapshot(self):
        with self._lock:
            return {"queues": {t: list(q) for t, q in self.queues.items()},
                    "ran": [dict(r) for r in self.ran]}

    # -- the bench ---------------------------------------------------------------------------------

    def codec_present(self, ctx):
        return True

    def run(self, test_id, ctx):
        with self._lock:
            queue = self.queues[test_id]
            outcome = queue.popleft() if queue else {"ok": True}
        result = fake_result(test_id, outcome, ctx.facts)
        result["fake"] = True
        with self._lock:
            self.ran.append({"run": ctx.run_id, "test": test_id, "status": result["status"],
                             "at": self._clock()})
        return result


def normalise(outcome):
    if isinstance(outcome, bool):
        return {"ok": outcome}
    if isinstance(outcome, str):
        return {"ok": outcome == "pass"} if outcome in ("pass", "fail") else {"status": outcome}
    if not isinstance(outcome, dict):
        raise ValueError("an outcome is a dict, true/false, or pass/fail/not_run")
    out = dict(outcome)
    if out.get("status") == "pass":
        out["ok"] = True
    elif out.get("status") == "fail":
        out["ok"] = False
    elif out.get("status") not in (None, "not_run"):
        raise ValueError("status is pass, fail or not_run")
    if out.get("component") is not None and out["component"] not in catalog.COMPONENT_IDS:
        raise ValueError("no block %r" % out["component"])
    if out.get("component") or out.get("check"):
        out["ok"] = False
    out.setdefault("ok", not out.get("hum"))
    return out


def fake_result(test_id, outcome, facts):
    """The result a real benchtest would have given for this outcome."""
    entry = catalog.test(test_id)
    if outcome.get("status") == "not_run":
        return catalog.not_run(test_id, outcome.get("summary") or "Not run (fake).")
    named = bool(outcome.get("component") or outcome.get("check"))
    ok = named or bool(outcome.get("ok", True))
    result = _classified(test_id, entry, ok, outcome, facts or {})
    if named:
        result = _named_failure(test_id, entry, result, outcome)
    if outcome.get("summary"):
        result["summary"] = outcome["summary"]
    return result


def _classified(test_id, entry, ok, outcome, facts):
    kind = entry["kind"]
    if kind == "output_noise":
        return catalog.classify_output(test_id, _analysis(-99.4 if ok else -84.0, ENGINE_LINES))
    if kind == "input_noise":
        if outcome.get("hum"):
            return catalog.classify_input(_analysis(-52.8, ((49.8, -58.3), (100.3, -59.8),
                                                            (750.0, -80.0))))
        return catalog.classify_input(_analysis(-68.4 if ok else -55.0, ((750.0, -80.0),)))
    if kind == "battery":
        reference = facts.get("input_line50_dbfs")
        if reference is None:
            reference = -58.3
        return catalog.classify_battery(_analysis(-65.5, ((49.8, reference - (26.0 if ok else 4.0)),
                                                          (750.0, -75.0))), reference)
    if kind == "codec_only":
        reference = facts.get("input_rms_dbfs")
        if reference is None:
            reference = -68.4
        return catalog.classify_codec_only(_analysis(reference - (3.0 if ok else 9.0)), reference)
    if kind == "probe":
        return catalog.probe_result({"present": ok, "serial": "E6614103E7176F2F" if ok else None,
                                     "port": "/dev/cu.usbmodem1102" if ok else None})
    # Health: the catalog's own wording for every block the benchtest exercises.
    checks = [catalog.check(c, True, entry["exercises"][c], "Passed (fake).")
              for c in entry["components"]]
    facts_out = {}
    if test_id == "codec":
        facts_out["codec_present"] = bool(outcome.get("codec_present", ok))
    if ok:
        return catalog.make_result(test_id, checks, entry.get("pass_summary") or "Passed.",
                                   "fake: no pedal was asked", None, [], facts_out)
    target = entry["components"][0]
    checks[0] = catalog.check(target, False, entry["exercises"][target], "Failed (fake).")
    return catalog.make_result(test_id, checks, "Failed: %s." % entry["exercises"][target],
                               "fake: no pedal was asked", "This is a fake failure.", [], facts_out)


def _named_failure(test_id, entry, result, outcome):
    """Fail the named block on the named check, as a real benchtest would report it."""
    target = outcome.get("component") or entry["components"][0]
    check_text = outcome.get("check") or entry["exercises"].get(target) or "a fake check"
    said = "Failed (fake): %s." % check_text
    checks = [c for c in result["checks"] if c["component"] != target]
    checks.insert(0, catalog.check(target, False, check_text, said))
    failed = catalog.make_result(test_id, checks, "Failed: %s." % check_text,
                                 result.get("evidence"), "This is a fake failure.",
                                 result.get("likely"), result.get("facts"))
    if test_id == "codec" and "codec_present" not in outcome:
        failed["facts"]["codec_present"] = True
    return failed
