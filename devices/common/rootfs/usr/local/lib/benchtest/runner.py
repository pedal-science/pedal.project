"""One run at a time: the order, the setup instructions, the codec gate and the helper gate.

A run is what one Test button press or one click on a block asks for. Its benchtests run in the
catalog's order, whatever order they were ticked in. Before each one:

- a noise benchtest is not started when the codec is absent (the codec checks come first);
- a benchtest that needs the workstation helper is not started when no helper has polled in the
  last minute, and says so plainly;
- if the bench is not set up the way it needs (the lead, the codec's input, the Pi's power), the
  run pauses with plain instructions until the page says "done" or "skip". The setup is
  remembered for the session, so an instruction is shown only when the setup changes.

The benchtests themselves are the bench's (real.py or fakes.py): `bench.run(test_id, ctx)`
returns a result in catalog.py's shape.
"""

import itertools
import threading
import time
import traceback

from . import catalog


class NotRun(Exception):
    """A benchtest that could not judge anything; its message is the page's sentence."""

    def __init__(self, summary, evidence=None):
        super().__init__(summary)
        self.summary = summary
        self.evidence = evidence


class Busy(Exception):
    """A run is already going."""


class RunContext:
    """What a benchtest may use while it runs: the run, the helper, the history's facts."""

    def __init__(self, runner, run_id, test_id, shared):
        self.runner = runner
        self.run_id = run_id
        self.test_id = test_id
        self.test = catalog.test(test_id)
        self.shared = shared
        self.cancelled = runner._cancel
        self.helper = runner.helper
        self.facts = runner.history.bench_facts()
        self.log = runner.log

    def sleep(self, seconds):
        """Wait, unless the run is stopped: False when it was."""
        return not self.cancelled.wait(seconds)

    def require_helper(self):
        if not self.helper.present():
            raise NotRun(catalog.HELPER_MISSING)

    def helper_job(self, kind, params, timeout, job_id=None):
        """Give the helper a job and wait for its result; NotRun if it fails or never answers."""
        from .helper import HelperGone
        job_id = self.helper.submit(kind, params, job_id=job_id)
        try:
            reply = self.helper.wait(job_id, timeout, self.cancelled)
        except HelperGone as exc:
            raise NotRun("Not run: the computer running scripts/benchtest did not finish the job "
                         "(%s)." % exc)
        if not reply.get("ok"):
            raise NotRun("Not run: the computer running scripts/benchtest could not do it.",
                         str(reply.get("error") or "no reason given"))
        return reply.get("result") or {}


class Runner:
    def __init__(self, bench, history, helper, lock, log=None, clock=time.time):
        self.bench = bench
        self.history = history
        self.helper = helper
        self.lock = lock
        self.log = log or (lambda message: None)
        self._clock = clock
        self._counter = itertools.count(1)
        self._thread = None
        self._cancel = threading.Event()
        self._decided = threading.Event()
        self._decision = None
        self.run = None
        self.setup = {}

    # -- control -----------------------------------------------------------------------------

    def start(self, test_ids, origin):
        """Start a run of these benchtests (in catalog order) and return its snapshot."""
        order = catalog.ordered(test_ids)
        if not order:
            raise ValueError("no benchtests to run")
        with self.lock:
            if self.active():
                raise Busy()
            run_id = "%s-%d" % (time.strftime("%Y%m%d-%H%M%S", time.localtime(self._clock())),
                                next(self._counter))
            self._cancel = threading.Event()
            self._decided.clear()
            self.run = {"id": run_id, "origin": origin, "status": "running",
                        "started_at": self._clock(), "finished_at": None, "waiting": None,
                        "tests": [{"test": t, "status": "queued", "result": None} for t in order]}
            self.history.begin_run(run_id, origin)
            self._thread = threading.Thread(target=self._go, args=(run_id,),
                                            name="benchtest-run", daemon=True)
            self._thread.start()
            return self.snapshot()

    def decide(self, run_id, skip):
        """The page's answer to a setup instruction: done (False) or skip this benchtest (True)."""
        with self.lock:
            if not self.run or self.run["id"] != run_id or self.run["status"] != "waiting_setup":
                return False
            self._decision = "skip" if skip else "done"
            self._decided.set()
            return True

    def cancel(self):
        """Stop after the benchtest that is running; the ones after it are not started."""
        self._cancel.set()

    def active(self):
        return self._thread is not None and self._thread.is_alive()

    def executing(self):
        """Whether a benchtest is running right now: that, and only that, defers the idle exit."""
        with self.lock:
            return bool(self.run and self.active()
                        and any(t["status"] == "running" for t in self.run["tests"]))

    def join(self, timeout):
        if self._thread is not None:
            self._thread.join(timeout)

    def snapshot(self):
        with self.lock:
            if self.run is None:
                return None
            run = dict(self.run)
            run["tests"] = [dict(t) for t in self.run["tests"]]
            return run

    # -- the run -------------------------------------------------------------------------------

    def _go(self, run_id):
        shared = {}
        try:
            for index, slot in enumerate(list(self.run["tests"])):
                test_id = slot["test"]
                if self._cancel.is_set():
                    self._set(index, "stopped")
                    continue
                result = self._one(run_id, index, test_id, shared)
                if result is None:
                    continue
                result["at"] = self._clock()
                result["run"] = run_id
                with self.lock:
                    self.run["tests"][index]["result"] = result
                    self.run["tests"][index]["status"] = result["status"]
                    try:
                        self.history.record(run_id, result)
                    except OSError as exc:
                        self.log("history not written: %s" % exc)
        finally:
            with self.lock:
                self.run["status"] = "stopped" if self._cancel.is_set() else "done"
                self.run["waiting"] = None
                self.run["finished_at"] = self._clock()
                try:
                    self.history.end_run(run_id)
                except OSError as exc:
                    self.log("history not written: %s" % exc)

    def _one(self, run_id, index, test_id, shared):
        """Gate, set up and run one benchtest. None when it was skipped or stopped."""
        entry = catalog.test(test_id)
        ctx = RunContext(self, run_id, test_id, shared)
        if catalog.is_noise(test_id) and self._codec_absent(ctx, index):
            return catalog.not_run(test_id, catalog.CODEC_FIRST)
        if entry["helper"] and self.bench.needs_helper and not self.helper.present():
            return catalog.not_run(test_id, catalog.HELPER_MISSING)
        steps = catalog.setup_steps(self.setup, entry["setup"])
        if steps:
            decision = self._ask(index, test_id, steps)
            if decision == "skip":
                self._set(index, "skipped")
                return None
            if decision != "done":
                self._set(index, "stopped")
                return None
        if entry["setup"]:
            self.setup.update(entry["setup"])
        self._set(index, "running")
        try:
            return self.bench.run(test_id, ctx)
        except NotRun as exc:
            return catalog.not_run(test_id, exc.summary, exc.evidence)
        except Exception as exc:                      # a benchtest's bug is a sentence, not a crash
            self.log("benchtest %s raised: %s" % (test_id, traceback.format_exc()))
            return catalog.not_run(test_id, "Not run: this benchtest could not run (%s)." % exc)

    def _codec_absent(self, ctx, index):
        with self.lock:
            earlier = [t["result"] for t in self.run["tests"][:index]
                       if t["test"] == "codec" and t["result"]]
        if earlier and earlier[0]["status"] in ("pass", "fail"):
            return earlier[0]["facts"].get("codec_present") is False
        try:
            return self.bench.codec_present(ctx) is False
        except Exception as exc:
            self.log("could not tell whether the codec is present: %s" % exc)
            return False

    def _ask(self, index, test_id, steps):
        """Pause for the page: 'done', 'skip', or None when the run was stopped meanwhile."""
        with self.lock:
            self._decided.clear()
            self._decision = None
            self.run["status"] = "waiting_setup"
            self.run["waiting"] = {"test": test_id, "name": catalog.test(test_id)["name"],
                                   "steps": steps}
            self.run["tests"][index]["status"] = "waiting_setup"
        while not self._decided.wait(0.2):
            if self._cancel.is_set():
                break
        with self.lock:
            self.run["status"] = "running"
            self.run["waiting"] = None
            return None if self._cancel.is_set() else self._decision

    def _set(self, index, status):
        with self.lock:
            self.run["tests"][index]["status"] = status
