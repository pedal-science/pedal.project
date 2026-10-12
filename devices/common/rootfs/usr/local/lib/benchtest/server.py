"""The HTTP side: one page, its API, the session token, the idle timer and shutdown.

The page and its assets need no token; every `/api/` call does, as `Authorization: Bearer
<token>`, compared in constant time. The token is made at start, written into the URL file as
the page's fragment (`#token=`), and never travels as a query string — except to
`/api/shutdown`, which also takes `?token=` because `navigator.sendBeacon` cannot set a header.

Idle means no browser request for `idle_seconds`: an authenticated `/api/` call carrying
`X-Benchtest-Client: browser`, which the page sends on every call. The workstation helper's
calls never count, and a benchtest that is running defers the timer. When it fires the process
exits 0, and with `Restart=no` systemd leaves it stopped.

API (JSON in and out unless said; every route needs the bearer token):

    GET  /api/health                    {"ok", "fake", "version"}
    GET  /api/state                     everything the page draws (see App.state)
    POST /api/run                       {"tests": [id, ...]} or {"component": id} -> 202 {"run"}
    POST /api/run/continue              {"run": id, "skip": bool}: the setup is done, or skip it
    POST /api/run/cancel                stop after the benchtest that is running
    POST /api/history/forget            "Forget previous results"
    POST /api/shutdown                  200, then the process exits 0
    GET  /api/helper/next?wait=25       {"job": null | {...}}
    POST /api/helper/result             {"id", "ok", "error", "result"}
    GET  /api/helper/recording/<id>     the WAV the engine recorded for that job
    GET  /api/fake                      --fake only: {"queues", "ran"}
    POST /api/fake/outcome              --fake only: {"test", ...outcome} appended to its queue
    POST /api/fake/next                 --fake only: {"test", ...outcome} as its only queued outcome
    POST /api/fake/reset                --fake only: {"ran": bool, "queues": bool}
"""

import hmac
import json
import os
import secrets
import shutil
import socket
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlsplit

from . import VERSION, catalog
from .helper import HelperQueue
from .lamps import History
from .runner import Busy, Runner

STATIC = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")
PAGES = {"/": "index.html", "/stopped": "stopped.html"}
TYPES = {".html": "text/html; charset=utf-8", ".css": "text/css; charset=utf-8",
         ".js": "text/javascript; charset=utf-8", ".svg": "image/svg+xml"}
MAX_BODY = 1 << 20
CSP = ("default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; "
       "connect-src 'self'; base-uri 'none'; form-action 'none'; frame-ancestors 'none'")
#: The browser's mark on a request, which is the only kind that keeps the service awake.
BROWSER_HEADER = "X-Benchtest-Client"


class App:
    """The service's state: the bench, the history, the helper's queue, the runner, the timers."""

    def __init__(self, bench, state_dir, idle_seconds=300, log=None, clock=time.monotonic):
        self.bench = bench
        self.fake = bool(getattr(bench, "fake", False))
        self.idle_seconds = float(idle_seconds)
        self.log = log or _stderr_log
        self._clock = clock
        self.lock = threading.RLock()
        self.token = secrets.token_urlsafe(24)
        self.history = History(os.path.join(state_dir, "history.json"), log=self.log)
        self.helper = HelperQueue()
        self.runner = Runner(bench, self.history, self.helper, self.lock, log=self.log)
        self.stopping = threading.Event()
        self.stop_reason = None
        self._last_browser = clock()

    # -- time --------------------------------------------------------------------------------

    def touch(self):
        with self.lock:
            self._last_browser = self._clock()

    def idle_for(self):
        with self.lock:
            return self._clock() - self._last_browser

    def idle_expired(self):
        """True once the page has been away long enough. A running benchtest resets the clock."""
        if self.runner.executing():
            self.touch()
            return False
        return self.idle_for() >= self.idle_seconds

    def request_stop(self, reason):
        with self.lock:
            if self.stop_reason is None:
                self.stop_reason = reason
        self.stopping.set()

    # -- what the page draws ---------------------------------------------------------------------

    def state(self):
        with self.lock:
            facts = self.history.bench_facts()
            tests = []
            for t in catalog.TESTS:
                tests.append({"id": t["id"], "name": t["name"], "line": t["line"],
                              "group": t["group"], "components": t["components"],
                              "default": t["default"], "offered": catalog.offered(t, facts),
                              "auto": t["auto"], "helper": t["helper"],
                              "setup": bool(t["setup"])})
            components = []
            for c in catalog.COMPONENTS:
                entry = dict(c)
                entry["tests"] = [t["id"] for t in catalog.TESTS if c["id"] in t["components"]]
                entry["runs"] = catalog.tests_for_component(c["id"], facts)
                components.append(entry)
            out = {
                "ok": True, "fake": self.fake, "version": VERSION,
                "helper": {"present": self.helper.present() if self.bench.needs_helper else True,
                           "needed": bool(self.bench.needs_helper),
                           "seen_s_ago": self.helper.seen_s_ago()},
                "components": components, "tests": tests,
                "lamps": self.history.lamps(catalog.COMPONENT_IDS, catalog.TEST_IDS),
                "failures": self.history.failures(catalog.COMPONENT_IDS),
                "results": self.history.last_results(),
                "facts": facts,
                "run": self.runner.snapshot(),
                "setup": dict(self.runner.setup),
                "idle_seconds": self.idle_seconds,
            }
            if self.fake:
                out["fake_bench"] = self.bench.snapshot()
            return out

    # -- the routes --------------------------------------------------------------------------------

    def route(self, method, path, query, body):
        """(status, JSON body) for one authenticated API call."""
        if path == "/api/health" and method == "GET":
            return 200, {"ok": True, "fake": self.fake, "version": VERSION}
        if path == "/api/state" and method == "GET":
            return 200, self.state()
        if path == "/api/run" and method == "POST":
            return self._run(body)
        if path == "/api/run/continue" and method == "POST":
            if not self.runner.decide(str(body.get("run")), bool(body.get("skip"))):
                return 409, {"error": "that run is not waiting for its setup"}
            return 200, {"ok": True}
        if path == "/api/run/cancel" and method == "POST":
            self.runner.cancel()
            return 200, {"ok": True, "run": self.runner.snapshot()}
        if path == "/api/history/forget" and method == "POST":
            if self.runner.active():
                return 409, {"error": "a run is going; forget its results when it has finished"}
            with self.lock:
                self.history.forget()
            return 200, {"ok": True}
        if path == "/api/helper/next" and method == "GET":
            try:
                wait = float((query.get("wait") or ["25"])[0])
            except ValueError:
                return 400, {"error": "wait is a number of seconds"}
            return 200, {"job": self.helper.next(wait)}
        if path == "/api/helper/result" and method == "POST":
            job_id = body.get("id")
            if not isinstance(job_id, str):
                return 400, {"error": "id is required"}
            if not self.helper.post(job_id, body.get("ok"), body.get("error"), body.get("result")):
                return 404, {"error": "no job %s is waiting" % job_id}
            return 200, {"ok": True}
        if path.startswith("/api/fake"):
            if not self.fake:
                return 404, {"error": "not found"}
            return self._fake(method, path, body)
        return 404, {"error": "not found"}

    def _run(self, body):
        if "component" in body:
            component_id = body.get("component")
            if component_id not in catalog.COMPONENT_IDS:
                return 400, {"error": "no block %r" % component_id}
            tests = catalog.tests_for_component(component_id, self.history.bench_facts())
            origin = {"kind": "component", "component": component_id}
            if not tests:
                return 400, {"error": "nothing can test %s yet" % catalog.component(component_id)["name"]}
        else:
            tests = body.get("tests")
            if not isinstance(tests, list) or not tests:
                return 400, {"error": "tests is a list of benchtest ids"}
            facts = self.history.bench_facts()
            for t in tests:
                if t not in catalog.TEST_IDS:
                    return 400, {"error": "no benchtest %r" % t}
                if not catalog.offered(catalog.test(t), facts):
                    return 400, {"error": "%s is not offered yet" % catalog.test(t)["name"]}
            origin = {"kind": "tests"}
        try:
            return 202, {"run": self.runner.start(tests, origin)}
        except Busy:
            return 409, {"error": "a run is already going", "run": self.runner.snapshot()}

    def _fake(self, method, path, body):
        if path == "/api/fake" and method == "GET":
            return 200, self.bench.snapshot()
        if path in ("/api/fake/outcome", "/api/fake/next") and method == "POST":
            test_id = body.get("test")
            if test_id not in catalog.TEST_IDS:
                return 400, {"error": "no benchtest %r" % test_id}
            outcome = {k: v for k, v in body.items() if k != "test"}
            try:
                if path.endswith("/next"):
                    self.bench.set_next(test_id, outcome)
                else:
                    self.bench.push(test_id, outcome)
            except ValueError as exc:
                return 400, {"error": str(exc)}
            return 200, self.bench.snapshot()
        if path == "/api/fake/reset" and method == "POST":
            self.bench.reset(ran=body.get("ran", True), queues=body.get("queues", True))
            return 200, self.bench.snapshot()
        return 404, {"error": "not found"}


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    server_version = "pedal-benchtest/" + VERSION
    app = None                                   # set on the subclass made by make_server

    def do_GET(self):
        self._dispatch("GET")

    def do_POST(self):
        self._dispatch("POST")

    def do_HEAD(self):
        self._dispatch("HEAD")

    def log_message(self, fmt, *args):           # the page polls every second: no access log
        pass

    # -- dispatch ----------------------------------------------------------------------------------

    def _dispatch(self, method):
        try:
            parts = urlsplit(self.path)
            path, query = parts.path, parse_qs(parts.query)
            if not path.startswith("/api/"):
                return self._static(method, path)
            app = self.app
            body_bytes = self._body()
            if body_bytes is None:
                return
            if not self._authorised(path, query, body_bytes):
                return self._json(401, {"error": "unauthorized"})
            if (self.headers.get(BROWSER_HEADER, "").strip().lower() == "browser"
                    and not path.startswith("/api/helper/")):
                app.touch()
            if path == "/api/shutdown":
                if method != "POST":
                    return self._json(405, {"error": "method not allowed"})
                return self._shutdown()
            if path.startswith("/api/helper/recording/") and method in ("GET", "HEAD"):
                return self._recording(path.rsplit("/", 1)[-1], method)
            body = {}
            if method == "POST" and body_bytes:
                try:
                    body = json.loads(body_bytes.decode("utf-8"))
                except ValueError:
                    return self._json(400, {"error": "the body is not JSON"})
                if not isinstance(body, dict):
                    return self._json(400, {"error": "the body is a JSON object"})
            status, reply = app.route(method, path, query, body)
            self._json(status, reply, head_only=method == "HEAD")
        except (BrokenPipeError, ConnectionResetError):
            pass
        except Exception as exc:                 # a handler's bug is a 500, not the server's end
            self.app.log("%s %s: %r" % (method, self.path, exc))
            try:
                self._json(500, {"error": "internal error"})
            except OSError:
                pass

    def _body(self):
        if "transfer-encoding" in self.headers:
            self._json(400, {"error": "chunked bodies are not supported"}, close=True)
            return None
        length = self.headers.get("content-length")
        if not length:
            return b""
        if not length.strip().isdigit():
            self._json(400, {"error": "bad Content-Length"}, close=True)
            return None
        n = int(length)
        if n > MAX_BODY:
            self._json(413, {"error": "body too large"}, close=True)
            return None
        return self.rfile.read(n)

    def _authorised(self, path, query, body):
        token = self.app.token
        header = self.headers.get("authorization", "")
        scheme, _, presented = header.partition(" ")
        if scheme.lower() == "bearer" and presented.strip():
            return hmac.compare_digest(presented.strip().encode(), token.encode())
        if path == "/api/shutdown":
            # sendBeacon cannot set a header: the token comes as ?token= or a token=... body.
            presented = (query.get("token") or [""])[0]
            if not presented and body:
                text = body.decode("utf-8", "replace")
                presented = (parse_qs(text).get("token") or [""])[0]
            if presented:
                return hmac.compare_digest(presented.encode(), token.encode())
        return False

    # -- replies -----------------------------------------------------------------------------------

    def _json(self, status, body, head_only=False, close=False):
        payload = json.dumps(body).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("Cache-Control", "no-store")
        if close:
            self.send_header("Connection", "close")
            self.close_connection = True
        self.end_headers()
        if not head_only:
            self.wfile.write(payload)

    def _shutdown(self):
        payload = json.dumps({"ok": True, "stopping": True}).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("Connection", "close")
        self.end_headers()
        self.wfile.write(payload)
        self.wfile.flush()
        self.close_connection = True
        self.app.request_stop("asked to stop")

    def _recording(self, job_id, method):
        path = self.app.helper.recording(job_id)
        if path is None:
            return self._json(404, {"error": "no recording for %s" % job_id})
        size = os.path.getsize(path)
        self.send_response(200)
        self.send_header("Content-Type", "audio/wav")
        self.send_header("Content-Length", str(size))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        if method == "GET":
            with open(path, "rb") as f:
                shutil.copyfileobj(f, self.wfile, 1 << 16)

    def _static(self, method, path):
        if method not in ("GET", "HEAD"):
            return self._json(405, {"error": "method not allowed"})
        name = PAGES.get(path)
        if name is None and path.startswith("/static/"):
            name = path[len("/static/"):]
            if "/" in name or name.startswith(".") or name not in _static_names():
                name = None
        if name is None:
            return self._json(404, {"error": "not found"}, head_only=method == "HEAD")
        with open(os.path.join(STATIC, name), "rb") as f:
            payload = f.read()
        self.send_response(200)
        self.send_header("Content-Type", TYPES.get(os.path.splitext(name)[1], "application/octet-stream"))
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Security-Policy", CSP)
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.end_headers()
        if method == "GET":
            self.wfile.write(payload)


def _static_names():
    return set(n for n in os.listdir(STATIC) if not n.startswith("."))


class Server(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True


def make_server(app, bind, port):
    handler = type("BoundHandler", (Handler,), {"app": app})
    return Server((bind, port), handler)


def page_url(bind, port, token):
    """The address the URL file carries: loopback stays loopback, anything else is the hostname."""
    host = "127.0.0.1" if bind in ("127.0.0.1", "localhost") else socket.gethostname()
    return "http://%s:%d/#token=%s" % (host, port, token)


def serve(app, bind, port, run_dir, out=None):
    """Listen, write the URL file, and serve until shutdown, idle, or a signal. Returns 0."""
    out = out or sys.stdout
    server = make_server(app, bind, port)
    real_port = server.server_address[1]
    url = page_url(bind, real_port, app.token)
    url_file = os.path.join(run_dir, "url")
    os.makedirs(run_dir, mode=0o755, exist_ok=True)
    _remove(url_file)
    fd = os.open(url_file + ".tmp", os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as f:
        f.write(url + "\n")
    os.replace(url_file + ".tmp", url_file)
    thread = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": 0.2},
                              name="benchtest-http", daemon=True)
    thread.start()
    app.log("listening on %s:%d%s" % (bind, real_port, " (fake benchtests)" if app.fake else ""))
    print(url, file=out, flush=True)
    try:
        tick = max(0.05, min(1.0, app.idle_seconds / 10.0))
        while not app.stopping.wait(tick):
            if app.idle_expired():
                app.request_stop("no browser for %.0f s" % app.idle_seconds)
    finally:
        app.log("stopping: %s" % (app.stop_reason or "interrupted"))
        app.runner.cancel()
        app.helper.close()
        # The engine's mute is put back by the benchtest's own `finally`: give it the time.
        app.runner.join(15.0)
        time.sleep(0.2)                          # the shutdown reply's last bytes
        server.shutdown()
        server.server_close()
        _remove(url_file)
    return 0


def _remove(path):
    try:
        os.unlink(path)
    except FileNotFoundError:
        pass


def _stderr_log(message):
    print("pedal-benchtest: %s" % message, file=sys.stderr, flush=True)
