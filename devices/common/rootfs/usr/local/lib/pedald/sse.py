"""pedald's event stream: `GET /events` (docs/pedal-service.md, "The pedal's identity and its event
stream").

One ring of finished frames, and each connection's thread keeps its own place in it. A publisher only
ever appends, so nothing a client does can hold up the loop, and a client that falls behind costs its
own thread and no memory: when the ring has moved past its place, it is told to start again.
"""
import collections
import json
import secrets
import threading
import time

RING = 512
KEEPALIVE_S = 15.0
#: How often a quiet stream looks at whether its peer has gone.
POLL_S = 1.0


def frame(event_id, kind, data):
    return f"id: {event_id}\nevent: {kind}\ndata: {json.dumps(data, separators=(', ', ': '))}\n\n".encode("utf-8")


class EventHub:
    """The ring. `publish` may be called from any thread."""

    def __init__(self, ring=RING, run=None):
        self.run = run or secrets.token_hex(4)
        self._ring = collections.deque(maxlen=ring)
        self._seq = 0
        self._closed = False
        self._changed = threading.Condition()

    def publish(self, kind, data):
        with self._changed:
            self._seq += 1
            self._ring.append((self._seq, frame(f"{self.run}-{self._seq}", kind, data)))
            self._changed.notify_all()
            return self._seq

    def current(self):
        with self._changed:
            return self._seq

    def close(self):
        with self._changed:
            self._closed = True
            self._changed.notify_all()

    def event_id(self, seq):
        return f"{self.run}-{seq}"

    def position(self, last_event_id):
        """The place a `Last-Event-ID` names, or None if this run's ring can't continue from it."""
        run, separator, seq = (last_event_id or "").rpartition("-")
        if not separator or run != self.run or not seq.isascii() or not seq.isdigit():
            return None
        seq = int(seq)
        with self._changed:
            if seq > self._seq or self._behind(seq):
                return None
        return seq

    def _behind(self, cursor):
        return bool(self._ring) and cursor < self._ring[0][0] - 1

    def after(self, cursor, wait):
        """(frames after `cursor`, the new cursor, whether the ring has moved past it, closed)."""
        with self._changed:
            if self._seq <= cursor and not self._closed and wait > 0:
                self._changed.wait(wait)
            if self._behind(cursor):
                return [], self._seq, True, self._closed
            frames = [data for seq, data in self._ring if seq > cursor]
            return frames, self._seq, False, self._closed


def stream(hub, last_event_id, hello, *, keepalive_s=KEEPALIVE_S, poll_s=POLL_S):
    """What a `Stream` runs: `run(out)`, until the peer goes or the hub closes.

    `hello` is called on this thread for what the client should hold now, so it reads state the loop
    has already published rather than asking anything. The place in the ring is taken first, so a
    change made while the snapshot is read is sent after it, never lost.
    """

    def begin(resync):
        cursor = hub.current()
        data = b""
        if resync:
            data += frame(hub.event_id(cursor), "resync", {})
        return cursor, data + frame(hub.event_id(cursor), "hello", hello())

    def run(out):
        cursor = hub.position(last_event_id) if last_event_id else None
        first = b""
        if cursor is None:
            cursor, first = begin(bool(last_event_id))
            out.write(first)
        written_at = time.monotonic()
        while True:
            left = keepalive_s - (time.monotonic() - written_at)
            frames, seq, missed, closed = hub.after(cursor, min(poll_s, max(left, 0)))
            if closed or out.closed():
                return
            if missed:
                cursor, data = begin(True)
                out.write(data)
                written_at = time.monotonic()
            elif frames:
                cursor = seq
                out.write(b"".join(frames))
                written_at = time.monotonic()
            elif time.monotonic() - written_at >= keepalive_s:
                out.write(b": ka\n\n")
                written_at = time.monotonic()

    return run
