"""The Core host's end of the Pico link: own the UART, feed the session, reopen when it goes.

This does one thing — move bytes between the port and a `protocol.Session` — and nothing
else. Nothing goes on this wire that is not a protocol frame (docs/uart-protocol.md): the
Pico's USB console is where text belongs.

Why `termios` and not `stty`: `stty` was the way in while the Core host's python3 was
`python3-minimal` (no `termios`). The image installs the full `python3` now, so the service
sets the line itself — see `_configure`. `select` does the waiting, so reading is a plain
`os.read` on a non-blocking fd.

The port can go away — the Pico resets, a lead moves, the driver reloads — so every read
and write failure closes the fd and schedules a reopen. The session sees the silence and
drops the session on its own; this class never speaks protocol.
"""
import errno
import os
import select
import termios
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
        # Counters and timestamps, for /status and for pedal-diag: a rate is a diagnosis where a
        # total is only a fact ("frames ok 27,523" says nothing; "24 a second" says the link is
        # alive). Everything here is monotonic-clock, and bytes are counted as they cross.
        self.bytes_in = 0
        self.bytes_out = 0
        self.drops = 0
        self.last_rx_at = None
        self.last_tx_at = None

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
        # Raw 8N1, no echo, no flow control — set on our own fd, below.
        try:
            self._configure(fd)
        except (OSError, termios.error) as exc:
            os.close(fd)
            self._retry(f"cannot configure {self.device}: {exc}")
            return False
        self.fd = fd
        self.retry = self.retry_s
        self.opened_at = time.monotonic()
        self.log(f"{self.device} open at {self.baud} baud")
        return True

    def _configure(self, fd):
        """The line discipline this link needs, set through `termios` on our own fd.

        `stty` did this until 2026-10-04, because the Core host's python3 was
        `python3-minimal` and had no `termios`. The image installs the full `python3` now
        (devices/vip/packages), so the service sets the line itself: no fork per open, no
        second opener of the device, and no GNU/BSD spelling to fork on for the tests' sake.
        What this asks for is what `stty raw -echo -crtscts` gave: no canonical mode, no echo,
        no signals or flow control, 8 bits, one stop bit, no parity, receiver enabled.
        """
        iflag, oflag, cflag, lflag, _ispeed, _ospeed, cc = termios.tcgetattr(fd)
        iflag &= ~(termios.IGNBRK | termios.BRKINT | termios.PARMRK | termios.ISTRIP
                   | termios.INLCR | termios.IGNCR | termios.ICRNL | termios.IXON
                   | termios.IXOFF | termios.IXANY)
        oflag &= ~termios.OPOST
        lflag &= ~(termios.ECHO | termios.ECHONL | termios.ICANON | termios.ISIG
                   | termios.IEXTEN)
        # CRTSCTS is Linux's name; Darwin splits it. Either way it is off.
        flow = (getattr(termios, "CRTSCTS", 0) | getattr(termios, "CCTS_OFLOW", 0)
                | getattr(termios, "CRTS_IFLOW", 0))
        cflag &= ~(termios.CSIZE | termios.PARENB | termios.CSTOPB | flow)
        cflag |= termios.CS8 | termios.CREAD | termios.CLOCAL
        speed = getattr(termios, f"B{self.baud}", None)
        if speed is None:
            raise ValueError(f"unsupported baud rate {self.baud}")
        # VMIN/VTIME stay as they were: the fd is non-blocking and `select` does the waiting.
        termios.tcsetattr(fd, termios.TCSANOW, [iflag, oflag, cflag, lflag, speed, speed, cc])

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
            self.drops += 1
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
        self.bytes_in += len(data)
        self.last_rx_at = time.monotonic()
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
                self.bytes_out += written
                self.last_tx_at = time.monotonic()
            except BlockingIOError:
                if time.monotonic() >= deadline:
                    self._drop("write would block")
                    return
                select.select([], [self.fd], [], 0.02)
            except OSError as exc:
                self._drop(f"write: {exc.strerror}")
                return
