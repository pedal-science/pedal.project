"""Following the engine: its event connection, on a thread, with the frames handed to the loop.

docs/pedal-service.md, "Keeping the rig". The thread owns a connection of its own, named `pedald`, and
it does the parsing, so a large document costs the loop nothing. The loop takes what arrives from
`queue`. On every connection it first gets ("connected", seq) and reads `rig.get` to catch up, which is
also what it does for ("resync", None).
"""

import queue
import threading

from .engine import EngineClient, EngineError

#: How long a read waits before looking at whether the service is stopping.
READ_WAIT_S = 1.0
#: How long to wait before trying the engine again.
RETRY_S = 1.0
#: Frames the loop may fall behind by. Past this they are dropped for a catch-up, so a stalled loop
#: can't cost memory; the engine's own limit on a slow reader works the same way.
MAX_QUEUED = 512


class Follower:
    def __init__(self, host, port, token, wake=None, log=None, client="pedald"):
        self.host, self.port, self.token, self.client = host, port, token, client
        self.wake = wake or (lambda: None)
        self.log = log or (lambda _message: None)
        self.queue = queue.SimpleQueue()
        self._stopping = threading.Event()
        self._thread = None

    def start(self):
        self._stopping.clear()
        self._thread = threading.Thread(target=self._run, name="pedald-follow", daemon=True)
        self._thread.start()

    def stop(self):
        self._stopping.set()
        if self._thread is not None:
            self._thread.join(5)
            self._thread = None

    def threads(self):
        return [self._thread] if self._thread is not None and self._thread.is_alive() else []

    def _put(self, kind, value):
        if self.queue.qsize() >= MAX_QUEUED:
            while True:
                try:
                    self.queue.get_nowait()
                except queue.Empty:
                    break
            self.queue.put(("resync", None))
        self.queue.put((kind, value))
        self.wake()

    def _run(self):
        down = False
        while not self._stopping.is_set():
            engine = EngineClient(self.host, self.port, self.token, timeout=5.0, client=self.client)
            try:
                reply = engine.call("engine.subscribe", events=["rig", "params"], min_interval_ms=50, echo=True)
                if down:
                    self.log("following the engine again")
                down = False
                self._put("connected", reply.get("seq"))
                self._read(engine)
            except EngineError as exc:
                if not down and not self._stopping.is_set():
                    self.log(f"not following the engine: {exc.code}: {exc.message}")
                down = True
            except OSError as exc:
                if not down and not self._stopping.is_set():
                    self.log(f"lost the engine's events: {exc}")
                down = True
            finally:
                engine.close()
            self._stopping.wait(RETRY_S)

    def _read(self, engine):
        while not self._stopping.is_set():
            try:
                frame = engine.read_frame(READ_WAIT_S)
            except TimeoutError:
                continue
            if not isinstance(frame, dict):
                continue
            if frame.get("event") == "resync":
                self._put("resync", None)
            elif "event" in frame:
                self._put("frame", frame)
