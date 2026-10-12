"""The run history, and the lamp rule that reads it.

The rule (plan, "The page"), the same for a block and for a test row:

- Nothing has exercised it: no lamp.
- A run that exercises a block fails if any check in that run naming the block failed, and passes
  only if every one passed. A test row's run is simply that test's result.
- One lamp, the latest run's colour — unless the latest run and the run before it that also
  exercised it disagree. Then two: the previous colour muted on the left, the new colour bright on
  the right. Two fails in a row are one red lamp, not a pair.

The history is `<state-dir>/history.json`, so a later session still shows a change. "Forget
previous results" empties it. Runs that judged nothing (every benchtest not run) are not kept.
"""

import json
import os
import time

FORMAT = 1
#: Runs kept. The rule reads two per block; the rest is there for a person reading the file.
MAX_RUNS = 200


def lamp(verdicts):
    """The lamps for one block or test, from its verdicts oldest first (True = passed).

    {"current": "pass" | "fail" | None, "previous": "pass" | "fail" | None}; `previous` is set only
    when the last two disagree, which is the only time two lamps are drawn.
    """
    if not verdicts:
        return {"current": None, "previous": None}
    current = "pass" if verdicts[-1] else "fail"
    if len(verdicts) >= 2 and bool(verdicts[-2]) != bool(verdicts[-1]):
        return {"current": current, "previous": "pass" if verdicts[-2] else "fail"}
    return {"current": current, "previous": None}


def empty():
    return {"format": FORMAT, "runs": [], "last_results": {}, "facts": {}}


class History:
    """history.json, held in memory and written whole (to a temporary file, then renamed)."""

    def __init__(self, path, clock=time.time, log=None):
        self.path = path
        self._clock = clock
        self._log = log or (lambda message: None)
        self.data = self._load()

    # -- storage -----------------------------------------------------------------------------

    def _load(self):
        try:
            with open(self.path) as f:
                data = json.load(f)
        except FileNotFoundError:
            return empty()
        except (OSError, ValueError) as exc:
            broken = "%s.broken-%d" % (self.path, int(self._clock()))
            self._log("history %s is unreadable (%s); starting again, the old one kept as %s"
                      % (self.path, exc, broken))
            try:
                os.replace(self.path, broken)
            except OSError:
                pass
            return empty()
        if not isinstance(data, dict) or data.get("format") != FORMAT:
            return empty()
        for key, value in empty().items():
            data.setdefault(key, value)
        return data

    def save(self):
        tmp = self.path + ".tmp"
        with open(tmp, "w") as f:
            json.dump(self.data, f, indent=1, sort_keys=True)
            f.write("\n")
        os.replace(tmp, self.path)

    # -- runs ----------------------------------------------------------------------------------

    def begin_run(self, run_id, origin):
        self.data["runs"].append({"id": run_id, "at": self._clock(), "origin": origin,
                                  "tests": {}, "components": {}})

    def _run(self, run_id):
        for run in reversed(self.data["runs"]):
            if run["id"] == run_id:
                return run
        raise KeyError(run_id)

    def record(self, run_id, result):
        """Fold one benchtest's pass or fail into its run. A `not_run` result changes nothing."""
        if result.get("status") not in ("pass", "fail"):
            return
        run = self._run(run_id)
        test_id = result["test"]
        run["tests"][test_id] = result["status"] == "pass"
        for c in result.get("checks") or []:
            slot = run["components"].setdefault(c["component"], {"ok": True, "checks": []})
            slot["ok"] = slot["ok"] and bool(c["ok"])
            slot["checks"].append({"test": test_id, "ok": bool(c["ok"]),
                                   "check": c.get("check"), "said": c.get("said")})
        self.data["last_results"][test_id] = result
        if result.get("facts"):
            self.data["facts"][test_id] = result["facts"]
        self._trim()
        self.save()

    def end_run(self, run_id):
        """Drop the run if it judged nothing, so an all-not-run click leaves no trace."""
        try:
            run = self._run(run_id)
        except KeyError:
            return
        if not run["tests"]:
            self.data["runs"].remove(run)
        self.save()

    def forget(self):
        self.data = empty()
        self.save()

    def _trim(self):
        if len(self.data["runs"]) > MAX_RUNS:
            del self.data["runs"][:len(self.data["runs"]) - MAX_RUNS]

    # -- reading -----------------------------------------------------------------------------

    def lamps(self, component_ids, test_ids):
        runs = self.data["runs"]
        return {
            "components": {c: lamp([r["components"][c]["ok"] for r in runs if c in r["components"]])
                           for c in component_ids},
            "tests": {t: lamp([r["tests"][t] for r in runs if t in r["tests"]]) for t in test_ids},
        }

    def failures(self, component_ids):
        """For each block, the failed checks of the latest run that exercised it: which benchtest
        failed and the check that tied it to the block."""
        out = {}
        for c in component_ids:
            for run in reversed(self.data["runs"]):
                if c in run["components"]:
                    out[c] = [x for x in run["components"][c]["checks"] if not x["ok"]]
                    break
        return out

    def last_results(self):
        return dict(self.data["last_results"])

    def test_facts(self, test_id):
        return dict(self.data["facts"].get(test_id) or {})

    def bench_facts(self):
        """What later benchtests compare against: the guitar input's hum and level on mains."""
        noise = self.test_facts("noise_input")
        return {"hum": bool(noise.get("hum")),
                "input_rms_dbfs": noise.get("rms_dbfs"),
                "input_line50_dbfs": noise.get("line50_dbfs")}
