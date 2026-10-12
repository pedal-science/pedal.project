"""The job queue `scripts/benchtest` long-polls from the workstation.

The workstation does what the 1 GB Pi should not: it records the audio interface with sox, runs
the spectrum (`codec-noise.py --json`), and looks at its own USB for the Debug Probe. Core puts a
job here, the helper takes it with `GET /api/helper/next?wait=25`, and answers with
`POST /api/helper/result`. Jobs:

    capture            {"seconds", "skip_seconds", "channel", "note"}: record and analyse
    analyse_recording  {"url", "channel", "skip_seconds"}: fetch an engine recording and analyse it
    probe_usb          {}: is a Raspberry Pi Debug Probe's USB on this computer?

The helper's polling is not browser activity, so none of this touches the idle timer. A helper
counts as present while it is polling or has polled in the last `PRESENT_S` seconds.
"""

import collections
import itertools
import os
import threading
import time

#: How recently a helper must have polled to count as running.
PRESENT_S = 60.0
#: The longest a single long-poll is held.
MAX_WAIT_S = 30.0


class HelperGone(Exception):
    """The helper did not answer in time, or the run was stopped while waiting for it."""


class HelperQueue:
    def __init__(self, clock=time.monotonic):
        self._clock = clock
        self._cond = threading.Condition()
        self._pending = collections.deque()
        self._jobs = {}
        self._recordings = {}
        self._ids = itertools.count(1)
        self._prefix = "%x" % (int(time.time()) & 0xffffff)
        self._last_seen = None
        self._polling = 0
        self._closed = False

    # -- the app's side ------------------------------------------------------------------------

    def new_id(self):
        return "%s-%d" % (self._prefix, next(self._ids))

    def attach_recording(self, job_id, path):
        """Make `path` downloadable as /api/helper/recording/<job_id>."""
        with self._cond:
            self._recordings[job_id] = path

    def recording(self, job_id):
        with self._cond:
            path = self._recordings.get(job_id)
        return path if path and os.path.isfile(path) else None

    def submit(self, kind, params, job_id=None):
        job_id = job_id or self.new_id()
        job = dict(params)
        job["id"] = job_id
        job["kind"] = kind
        with self._cond:
            self._jobs[job_id] = {"job": job, "done": False, "reply": None}
            self._pending.append(job_id)
            self._cond.notify_all()
        return job_id

    def wait(self, job_id, timeout, cancelled=None):
        """The helper's reply, {"ok", "error", "result"}; HelperGone on timeout or cancel."""
        deadline = self._clock() + timeout
        with self._cond:
            while True:
                entry = self._jobs.get(job_id)
                if entry is None:
                    raise HelperGone("the job was withdrawn")
                if entry["done"]:
                    self._jobs.pop(job_id, None)
                    return entry["reply"]
                if cancelled is not None and cancelled.is_set():
                    self._withdraw(job_id)
                    raise HelperGone("the run was stopped")
                left = deadline - self._clock()
                if left <= 0 or self._closed:
                    self._withdraw(job_id)
                    raise HelperGone("the computer did not answer in %.0f s" % timeout)
                self._cond.wait(min(left, 0.25))

    def _withdraw(self, job_id):
        self._jobs.pop(job_id, None)
        try:
            self._pending.remove(job_id)
        except ValueError:
            pass

    def present(self):
        with self._cond:
            if self._polling:
                return True
            return self._last_seen is not None and self._clock() - self._last_seen <= PRESENT_S

    def seen_s_ago(self):
        with self._cond:
            if self._polling:
                return 0.0
            return None if self._last_seen is None else round(self._clock() - self._last_seen, 1)

    def close(self):
        """Release every long-poll: the service is stopping."""
        with self._cond:
            self._closed = True
            self._cond.notify_all()

    # -- the helper's side ---------------------------------------------------------------------

    def next(self, wait):
        """The next job for the helper, or None after `wait` seconds."""
        wait = max(0.0, min(float(wait), MAX_WAIT_S))
        deadline = self._clock() + wait
        with self._cond:
            self._polling += 1
            self._last_seen = self._clock()
            try:
                while True:
                    while self._pending:
                        job_id = self._pending.popleft()
                        if job_id in self._jobs:
                            return dict(self._jobs[job_id]["job"])
                    left = deadline - self._clock()
                    if left <= 0 or self._closed:
                        return None
                    self._cond.wait(min(left, 1.0))
            finally:
                self._polling -= 1
                self._last_seen = self._clock()

    def post(self, job_id, ok, error, result):
        """The helper's answer. False when no job of that id is waiting (late, or never asked)."""
        with self._cond:
            self._last_seen = self._clock()
            entry = self._jobs.get(job_id)
            if entry is None or entry["done"]:
                return False
            entry["done"] = True
            entry["reply"] = {"ok": bool(ok), "error": error, "result": result}
            self._cond.notify_all()
            return True
