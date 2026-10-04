"""The Core host's end of the Pico link: own the UART, feed the session, reopen when it goes.

This does one thing — move bytes between the port and a `protocol.Session` — and nothing
else. Nothing goes on this wire that is not a protocol frame (docs/uart-protocol.md): the
Pico's USB console is where text belongs.

Why `stty` and not `termios`: the Core host's python3 is `python3-minimal`, which has no
`termios` module (checked on vip, 2026-10-04). `stty -F` does the same job through
coreutils, and `pedald.service` puts the service in `dialout` so it may open the device.
`select` needs no terminal setup, so reading is a plain `os.read`.

The port can go away — the Pico resets, a lead moves, the driver reloads — so every read
and write failure closes the fd and schedules a reopen. The session sees the silence and
drops the session on its own; this class never speaks protocol.
"""
import errno
import os
import select
import subprocess
import time


class Link:
    """A UART that reconnects itself. Attach a session with `attach()` before polling."""

    def __init__(self, device, baud, *, log=None, retry_s=1.0, max_retry_s=10.0):
        self.device = device
        self.baud = baud
        self.session = None
        self.log = log or (lambda _msg: None)
        self.retry_s = retry_s
        self.max_retry_s = max_retry_s
        self.fd = None
        self.retry = retry_s
        self.next_try = 0.0
        self.opened_at = None
        self.inbox = []          # what the session decoded, for the owner to drain

    # ------------------------------------------------------------------ state
    @property
    def open(self):
        return self.fd is not None

    def attach(self, session):
        self.session = session

    # ------------------------------------------------------------------ open/close
    def open_port(self):
        """Open and configure the port. Returns True on success; logs one line either way."""
        try:
            fd = os.open(self.device, os.O_RDWR | os.O_NOCTTY | os.O_NONBLOCK)
        except OSError as exc:
            self._retry(f"cannot open {self.device}: {exc.strerror}")
            return False
        # raw, 8N1, no echo, no flow control. `stty` opens the device a second time, which is
        # what makes this work without termios; the settings live on the tty, not the fd.
        # GNU stty takes -F and BSD/macOS (where the tests run) -f, and -crtscts is GNU's
        # spelling, so the second form is the shorter one.
        attempts = (
            ["stty", "-F", self.device, str(self.baud), "raw", "-echo", "-crtscts"],
            ["stty", "-f", self.device, str(self.baud), "raw", "-echo"],
        )
        failure = None
        for argv in attempts:
            try:
                subprocess.run(argv, check=True, capture_output=True, timeout=5)
                failure = None
                break
            except (OSError, subprocess.SubprocessError) as exc:
                failure = exc
        if failure is not None:
            os.close(fd)
            self._retry(f"cannot configure {self.device}: {failure}")
            return False
        self.fd = fd
        self.retry = self.retry_s
        self.opened_at = time.monotonic()
        self.log(f"{self.device} open at {self.baud} baud")
        return True

    def close(self):
        if self.fd is not None:
            try:
                os.close(self.fd)
            except OSError:
                pass
            self.fd = None
            self.log(f"{self.device} closed")

    def _drop(self, reason):
        if self.fd is not None:
            self.log(f"{self.device}: {reason}")
        self.close()
        self.next_try = time.monotonic() + self.retry
        self.retry = min(self.retry * 2, self.max_retry_s)

    def _retry(self, reason):
        self.log(reason)
        self.next_try = time.monotonic() + self.retry
        self.retry = min(self.retry * 2, self.max_retry_s)

    # ------------------------------------------------------------------ io
    def poll(self, timeout=0.05):
        """Read what is there (waiting at most `timeout`), or try to reopen. Never raises."""
        if self.fd is None:
            if time.monotonic() >= self.next_try:
                self.open_port()
            return
        try:
            ready, _, _ = select.select([self.fd], [], [], timeout)
        except OSError as exc:
            self._drop(f"select: {exc}")
            return
        if not ready:
            return
        try:
            data = os.read(self.fd, 4096)
        except OSError as exc:
            if exc.errno in (errno.EAGAIN, errno.EINTR):
                return
            self._drop(f"read: {exc.strerror}")
            return
        if not data:
            self._drop("end of file")
            return
        if self.session is not None:
            messages = self.session.feed(data)
            if messages:                      # a session that returns nothing is a session too
                self.inbox.extend(messages)

    def take_messages(self):
        """The decoded messages since the last call, for the service to act on."""
        messages, self.inbox = self.inbox, []
        return messages

    def send(self, data):
        """Write one frame. A frame that will not go after a moment is dropped: the session
        times the link out and re-establishes, which beats blocking the control loop."""
        if self.fd is None:
            return
        deadline = time.monotonic() + 0.2
        view = memoryview(data)
        while view:
            try:
                if self.fd is None:
                    return
                written = os.write(self.fd, view)
                view = view[written:]
            except BlockingIOError:
                if time.monotonic() >= deadline:
                    self._drop("write would block")
                    return
                select.select([], [self.fd], [], 0.02)
            except OSError as exc:
                self._drop(f"write: {exc.strerror}")
                return
