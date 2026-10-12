#!/usr/bin/env python3
"""benchtest-helper.py — the workstation half of pedal.benchtest, run by scripts/benchtest.

    scripts/benchtest-helper.py --host vip [--device NAME] [--choose-device] [--no-browser]
    scripts/benchtest-helper.py --fake [--device NAME] [--choose-device] [--no-browser]

Not normally run by hand: scripts/benchtest takes the Core host's lock and starts the service,
then hands over to this. It waits until the service writes its URL (/run/pedal-benchtest/url,
read over ssh) and answers an authenticated GET /api/health, opens the URL in the browser, and
then stays in the foreground as the audio helper until the service is gone or Ctrl-C. Ctrl-C
leaves the service running: it stops itself 5 minutes after the page is closed.

--fake starts the app from this checkout instead (devices/common/rootfs/usr/local/sbin/
pedal-benchtest --fake on 127.0.0.1, its state in a temporary directory), with no ssh and no
lock, and stops it on Ctrl-C.

The helper protocol. Every request carries the session's bearer token, and never
`X-Benchtest-Client: browser`, so the helper's waiting does not keep the service awake.

    GET  /api/helper/next?wait=25   -> 200 {"job": {"id", "kind", "params"}} | {"job": null} | 204
    POST /api/helper/result         <- {"id", "ok", "error", "result"}

Jobs (params in "params"; a job's own keys are accepted as params too):

    capture            {seconds, skip_seconds, channel, note}   record the audio interface, analyse
    analyse_recording  {url, channel, skip_seconds}              fetch the engine's WAV, analyse
    probe_usb          {}                                        is a Debug Probe on this computer?

A capture is sox through CoreAudio, 2 channels, 24-bit, 48 kHz — two, never eight: opening the
interface at eight channels raises its own floor by about 12 dB (bench-results/
2026-10-11-first-sound/troubleshooting-log.md). Channel 0 is input 1. The interface is asked for
once and remembered in ~/.config/pedal-benchtest/station.json (--device overrides it,
--choose-device asks again). Recordings and their analyses go to
bench-results/benchtest/<date>/, never /tmp. The analysis is scripts/codec-noise.py --json from
skip_seconds on; its dict is the job's result, with the file and the device added.

Standard library only, on the workstation's python3.
"""
import argparse
import datetime
import http.client
import importlib.machinery
import importlib.util
import json
import os
import re
import shutil
import signal
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
import wave

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CODEC_NOISE = os.path.join(REPO, "scripts", "codec-noise.py")
PEDAL_DIAG = os.path.join(REPO, "devices", "common", "rootfs", "usr", "local", "sbin", "pedal-diag")
APP = os.path.join(REPO, "devices", "common", "rootfs", "usr", "local", "sbin", "pedal-benchtest")
RESULTS = os.path.join(REPO, "bench-results", "benchtest")
CONFIG = os.path.join(os.environ.get("XDG_CONFIG_HOME") or os.path.expanduser("~/.config"),
                      "pedal-benchtest", "station.json")

URL_FILE = "/run/pedal-benchtest/url"
UNIT = "pedal.benchtest"
SSH_OPTS = ["-o", "BatchMode=yes", "-o", "ConnectTimeout=10"]
CLIENT_HEADER = ("X-Benchtest-Client", "helper")
LOOPBACK = {"127.0.0.1", "localhost", "0.0.0.0", "::", "::1"}

RATE, CHANNELS, BITS = 48000, 2, 24
IDLE_MINUTES = 5


class JobError(Exception):
    """A job that could not be done, said plainly enough to show on the page as it is."""


class Unreachable(Exception):
    """The service did not answer the way a live session does."""


def say(message):
    print("benchtest: %s" % message, flush=True)


# --- the session --------------------------------------------------------------------------------

def parse_url(url):
    """(base URL without the fragment, token). The token is the fragment, or its token= field."""
    url = (url or "").strip()
    base, _, fragment = url.partition("#")
    token = fragment
    if "=" in fragment:
        token = urllib.parse.parse_qs(fragment).get("token", [""])[0]
    if not token:
        query = urllib.parse.parse_qs(urllib.parse.urlsplit(base).query)
        token = query.get("token", [""])[0]
    return base, token


def reachable_url(url, host):
    """The service's URL as this computer reaches it: a loopback or wildcard host becomes <host>."""
    parts = urllib.parse.urlsplit(url)
    if host and parts.hostname in LOOPBACK:
        netloc = host + (":%d" % parts.port if parts.port else "")
        return urllib.parse.urlunsplit(parts._replace(netloc=netloc))
    return url


class Session:
    def __init__(self, url, opener=None):
        self.url = url
        self.base, self.token = parse_url(url)
        parts = urllib.parse.urlsplit(self.base)
        self.origin = "%s://%s" % (parts.scheme, parts.netloc)
        self.opener = opener or urllib.request.build_opener()

    def _request(self, method, path, body=None, timeout=10.0):
        url = urllib.parse.urljoin(self.origin + "/", path)
        data = None if body is None else json.dumps(body).encode()
        req = urllib.request.Request(url, data=data, method=method)
        req.add_header("Authorization", "Bearer %s" % self.token)
        req.add_header(*CLIENT_HEADER)
        if data is not None:
            req.add_header("Content-Type", "application/json")
        try:
            with self.opener.open(req, timeout=timeout) as resp:
                return resp.status, resp.read()
        except urllib.error.HTTPError as exc:
            with exc:
                return exc.code, exc.read()
        except (urllib.error.URLError, OSError, http.client.HTTPException) as exc:
            raise Unreachable("%s %s: %s" % (method, path, getattr(exc, "reason", exc)))

    def healthy(self, timeout=5.0):
        try:
            return self._request("GET", "/api/health", timeout=timeout)[0] == 200
        except Unreachable:
            return False

    def health_problem(self, timeout=5.0):
        """None when healthy, else what went wrong, for the waiting message."""
        try:
            status, _ = self._request("GET", "/api/health", timeout=timeout)
        except Unreachable as exc:
            return str(exc)
        return None if status == 200 else "GET /api/health answered %d" % status

    def next_job(self, wait=25):
        status, body = self._request("GET", "/api/helper/next?wait=%d" % wait, timeout=wait + 15)
        if status == 204:
            return None
        if status != 200:
            raise Unreachable("GET /api/helper/next answered %d" % status)
        return parse_job(body)

    def post_result(self, job_id, ok, error=None, result=None, timeout=10.0):
        status, body = self._request("POST", "/api/helper/result",
                                     {"id": job_id, "ok": ok, "error": error, "result": result},
                                     timeout=timeout)
        if status not in (200, 204):
            raise Unreachable("POST /api/helper/result answered %d: %s"
                              % (status, body[:200].decode("utf-8", "replace")))

    def download(self, url, dest, timeout=60.0):
        """GET <url> (relative to the service, or on its origin) into <dest>, with the token."""
        absolute = urllib.parse.urljoin(self.origin + "/", url)
        parts = urllib.parse.urlsplit(absolute)
        if "%s://%s" % (parts.scheme, parts.netloc) != self.origin:
            raise JobError("the recording is at %s, not on the pedal's service; the token is "
                           "not sent anywhere else" % absolute)
        req = urllib.request.Request(absolute)
        req.add_header("Authorization", "Bearer %s" % self.token)
        req.add_header(*CLIENT_HEADER)
        try:
            with self.opener.open(req, timeout=timeout) as resp, open(dest, "wb") as out:
                shutil.copyfileobj(resp, out)
        except urllib.error.HTTPError as exc:
            exc.close()
            raise JobError("fetching the recording answered %d" % exc.code)
        except (urllib.error.URLError, OSError, http.client.HTTPException) as exc:
            raise JobError("could not fetch the recording: %s" % getattr(exc, "reason", exc))


def parse_job(body):
    """A job as {"id", "kind", "params"}, or None when the wait ended with nothing to do."""
    if not body or not body.strip():
        return None
    data = json.loads(body)
    if not isinstance(data, dict):
        raise Unreachable("GET /api/helper/next answered something that is not a job")
    job = data.get("job") if "job" in data else (data if "id" in data else None)
    if not job:
        return None
    kind = job.get("kind") or job.get("type")
    params = job.get("params")
    if params is None:
        params = job.get("args")
    if params is None:
        params = {k: v for k, v in job.items() if k not in ("id", "kind", "type")}
    return {"id": job.get("id"), "kind": kind, "params": params or {}}


# --- the audio interface ------------------------------------------------------------------------

def list_input_devices(run=subprocess.run):
    """CoreAudio's input devices by name, as sox's coreaudio driver names them. [] if unknown."""
    if sys.platform != "darwin":
        return []
    try:
        p = run(["system_profiler", "SPAudioDataType", "-json"], stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL, timeout=30)
        data = json.loads(p.stdout or b"{}")
    except (OSError, ValueError, subprocess.SubprocessError):
        return []
    names = []
    for group in data.get("SPAudioDataType", []):
        for item in group.get("_items", []):
            if item.get("coreaudio_device_input") and item.get("_name"):
                names.append(item["_name"])
    return names


class DeviceChoice:
    """Which CoreAudio device is the audio interface: --device, else remembered, else asked."""

    def __init__(self, override=None, config=CONFIG, lister=list_input_devices, ask=input,
                 interactive=None, show=None):
        self.override = override
        self.config = config
        self.lister = lister
        self.ask = ask
        self.interactive = sys.stdin.isatty() if interactive is None else interactive
        self.show = show or (lambda line: print(line, flush=True))

    def remembered(self):
        try:
            with open(self.config) as f:
                return json.load(f).get("device") or None
        except (OSError, ValueError):
            return None

    def remember(self, name):
        os.makedirs(os.path.dirname(self.config), exist_ok=True)
        data = {}
        try:
            with open(self.config) as f:
                data = json.load(f)
        except (OSError, ValueError):
            pass
        data["device"] = name
        tmp = self.config + ".tmp"
        with open(tmp, "w") as f:
            json.dump(data, f, indent=2)
            f.write("\n")
        os.replace(tmp, self.config)

    def forget(self):
        try:
            os.unlink(self.config)
        except OSError:
            pass

    def choose(self):
        """Ask in the terminal which input device is the interface, and remember the answer."""
        names = self.lister()
        if not names:
            raise JobError("this computer lists no audio input devices; plug in the audio "
                           "interface, or name it with scripts/benchtest --device NAME")
        if not self.interactive:
            raise JobError("no audio interface chosen yet, and no terminal to ask in; run "
                           "scripts/benchtest --device NAME (one of: %s)" % ", ".join(names))
        self.show("\a\nWhich of these is the audio interface the pedal's output goes into?")
        for i, name in enumerate(names, 1):
            self.show("  %d. %s" % (i, name))
        while True:
            answer = self.ask("Number (1-%d): " % len(names)).strip()
            if answer.isdigit() and 1 <= int(answer) <= len(names):
                name = names[int(answer) - 1]
                self.remember(name)
                self.show("benchtest: remembered %r in %s (--choose-device asks again)"
                          % (name, self.config))
                return name
            self.show("  Type one of the numbers above.")

    def get(self):
        if self.override:
            return self.override
        name = self.remembered()
        if name:
            present = self.lister()
            if present and name not in present:
                raise JobError("the audio interface %r is not plugged in (this computer has: "
                               "%s); plug it in, or run scripts/benchtest --choose-device"
                               % (name, ", ".join(present)))
            return name
        return self.choose()


def record_with_sox(device, path, seconds, run=subprocess.run, which=shutil.which):
    """Record <seconds> of the interface's first two inputs, 24-bit at 48 kHz, into <path>."""
    if which("sox") is None:
        raise JobError("sox is not installed on this computer; install it with `brew install sox` "
                       "and run scripts/benchtest again")
    if sys.platform != "darwin":
        raise JobError("recording the audio interface needs macOS's CoreAudio; this computer is %s"
                       % sys.platform)
    # The same command as the 2026-10-11 troubleshooting log, so its numbers stay comparable.
    argv = ["sox", "-q", "-t", "coreaudio", device, "-r", str(RATE), "-c", str(CHANNELS),
            "-b", str(BITS), path, "trim", "0", "%g" % seconds]
    try:
        p = run(argv, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=seconds + 30)
    except subprocess.TimeoutExpired:
        raise JobError("sox did not finish recording from %r within %d s" % (device, seconds + 30))
    if p.returncode != 0:
        detail = (p.stderr or b"").decode("utf-8", "replace").strip().splitlines()
        raise JobError("sox could not record from %r: %s"
                       % (device, detail[-1] if detail else "exit %d" % p.returncode))
    try:
        with wave.open(path, "rb") as w:
            frames, channels = w.getnframes(), w.getnchannels()
    except (OSError, wave.Error, EOFError) as exc:
        raise JobError("sox wrote no usable recording: %s" % exc)
    if channels != CHANNELS or frames < 0.9 * seconds * RATE:
        raise JobError("the recording is %d channel(s), %.1f s; wanted %d channels, %g s"
                       % (channels, frames / RATE, CHANNELS, seconds))


def analyse_with_codec_noise(path, channel=0, skip_seconds=2.0, run=subprocess.run):
    """scripts/codec-noise.py --json on <path>, as a dict."""
    argv = [sys.executable, CODEC_NOISE, path, "--json", "--channel", str(int(channel)),
            "--skip", "%g" % float(skip_seconds)]
    p = run(argv, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=300)
    if p.returncode != 0:
        detail = (p.stderr or b"").decode("utf-8", "replace").strip().splitlines()
        raise JobError("codec-noise.py could not analyse %s: %s"
                       % (os.path.basename(path), detail[-1] if detail else "exit %d" % p.returncode))
    return json.loads(p.stdout)


# --- the Debug Probe ----------------------------------------------------------------------------

def load_pedal_diag(path=PEDAL_DIAG):
    loader = importlib.machinery.SourceFileLoader("pedal_diag_for_benchtest", path)
    spec = importlib.util.spec_from_loader(loader.name, loader)
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


def probe_usb_local(diag=None):
    """Is a Raspberry Pi Debug Probe on this computer's USB? pedal-diag's own local view decides."""
    diag = diag or load_pedal_diag()
    side = diag.local_machine_aids()
    probes = [d for d in side.get("usb") or [] if (d.get("vid"), d.get("pid")) == diag.DEBUG_PROBE]
    if not probes:
        return {"present": False, "serial": None, "port": None, "machine": side.get("hostname")}
    ports = diag.serial_ports_for(side, probes[0])
    return {"present": True, "serial": probes[0].get("serial") or None,
            "port": ports[0]["device"] if ports else None, "machine": side.get("hostname")}


# --- the jobs -----------------------------------------------------------------------------------

def slug(text, limit=40):
    s = re.sub(r"[^a-z0-9]+", "-", (text or "").lower()).strip("-")
    return s[:limit].rstrip("-")


def number(params, key, default):
    value = params.get(key)
    if value is None:
        return float(default)
    try:
        return float(value)
    except (TypeError, ValueError):
        raise JobError("the job's %s is %r, not a number" % (key, value))


def relative_to_repo(path):
    path = os.path.abspath(path)
    return os.path.relpath(path, REPO) if path.startswith(REPO + os.sep) else path


class Jobs:
    """What the helper does for each kind of job. Every outside effect is injectable."""

    def __init__(self, device=None, record=record_with_sox, analyse=analyse_with_codec_noise,
                 probe_usb=probe_usb_local, results=RESULTS, now=datetime.datetime.now,
                 out=say):
        self.device = device or DeviceChoice()
        self.record = record
        self.analyse = analyse
        self.probe_usb = probe_usb
        self.results = results
        self.now = now
        self.say = out

    def _path(self, what):
        now = self.now()
        directory = os.path.join(self.results, now.strftime("%Y-%m-%d"))
        os.makedirs(directory, exist_ok=True)
        base = now.strftime("%H%M%S") + ("-" + what if what else "")
        path = os.path.join(directory, base + ".wav")
        n = 2
        while os.path.exists(path):
            path = os.path.join(directory, "%s-%d.wav" % (base, n))
            n += 1
        return path

    def _keep(self, path, job, result):
        """The analysis beside the recording, so the evidence explains itself later."""
        with open(os.path.splitext(path)[0] + ".json", "w") as f:
            json.dump({"job": job, "result": result}, f, indent=2, allow_nan=False)
            f.write("\n")

    def run(self, job, session):
        kind = job.get("kind")
        handler = {"capture": self.capture, "analyse_recording": self.analyse_recording,
                   "probe_usb": self.probe}.get(kind)
        if handler is None:
            raise JobError("this helper does not know the job %r; update this checkout "
                           "(scripts/benchtest-helper.py)" % kind)
        return handler(job, job.get("params") or {}, session)

    def capture(self, job, params, session):
        seconds = number(params, "seconds", 20)
        skip = number(params, "skip_seconds", 2)
        channel = int(number(params, "channel", 0))
        note = params.get("note") or ""
        if not 0 < seconds <= 600 or not 0 <= skip < seconds:
            raise JobError("a capture of %g s that skips %g s cannot be measured" % (seconds, skip))
        device = self.device.get()
        path = self._path("capture" + ("-" + slug(note) if slug(note) else ""))
        self.say("recording %g s from %r%s ..." % (seconds, device, " (%s)" % note if note else ""))
        self.record(device, path, seconds)
        result = dict(self.analyse(path, channel, skip))
        result.update({"file": relative_to_repo(path), "device": device})
        self._keep(path, job, result)
        self.say("wrote %s: %s dBFS unweighted" % (relative_to_repo(path), result.get("rms_dbfs")))
        return result

    def analyse_recording(self, job, params, session):
        url = params.get("url")
        if not url:
            raise JobError("the job names no recording to fetch")
        name = slug(os.path.splitext(os.path.basename(urllib.parse.urlsplit(url).path))[0])
        path = self._path("core" + ("-" + name if name else ""))
        self.say("fetching the engine's recording ...")
        session.download(url, path)
        result = dict(self.analyse(path, int(number(params, "channel", 0)),
                                   number(params, "skip_seconds", 2)))
        result["file"] = relative_to_repo(path)
        self._keep(path, job, result)
        self.say("wrote %s: %s dBFS unweighted" % (relative_to_repo(path), result.get("rms_dbfs")))
        return result

    def probe(self, job, params, session):
        result = self.probe_usb()
        self.say("Debug Probe on this computer: %s" % ("yes" if result.get("present") else "no"))
        return result


def do_job(job, jobs, session, out=say):
    """Do one job and post its result; a failure is a result too, never an exception."""
    try:
        result, ok, error = jobs.run(job, session), True, None
    except JobError as exc:
        result, ok, error = None, False, str(exc)
    except KeyboardInterrupt:
        try:
            session.post_result(job.get("id"), False, "the helper on the workstation was "
                                "stopped (Ctrl-C) during this job", None, timeout=3)
        except Unreachable:
            pass
        raise
    except Exception as exc:                            # a bug here must not end the session
        result, ok, error = None, False, "the helper failed: %s: %s" % (type(exc).__name__, exc)
    if error:
        out("job %s failed: %s" % (job.get("kind"), error))
    try:
        session.post_result(job.get("id"), ok, error, result)
    except Unreachable as exc:
        out("could not post the result of %s: %s" % (job.get("kind"), exc))


def serve(session, jobs, wait=25, gone_after=3, sleep=time.sleep, alive=lambda: True, out=say,
          clock=time.monotonic):
    """Do jobs until the service has gone. Returns when it has; Ctrl-C raises."""
    failures = 0
    while True:
        if not alive():
            return "exited"
        try:
            asked = clock()
            job = session.next_job(wait)
            failures = 0
            if job is None and clock() - asked < 1:
                sleep(1)                                # a service that does not hold the wait
        except (Unreachable, ValueError):
            if session.healthy():
                failures = 0
                sleep(2)
                continue
            failures += 1
            if failures >= gone_after:
                return "gone"
            sleep(2)
            continue
        if job is not None:
            do_job(job, jobs, session, out)


def wait_for_service(read_url, timeout=60.0, sleep=time.sleep, clock=time.monotonic,
                     opener=None, alive=lambda: None, out=say):
    """Poll until the URL is there and an authenticated health check answers; the Session.

    The URL is read again each time: a file left from an earlier session names an old token, and
    the new process replaces it once it is listening. <alive> returns a reason to stop waiting
    (the service failed, the fake exited) or None.
    """
    deadline = clock() + timeout
    problem, said = "no URL yet", None
    while True:
        stop = alive()
        if stop:
            raise SystemExit("benchtest: %s" % stop)
        url = read_url()
        if url:
            session = Session(url, opener)
            problem = session.health_problem()
            if problem is None:
                return session
        else:
            problem = "no URL yet"
        if problem != said:
            out("waiting for the service (%s)" % problem)
            said = problem
        if clock() >= deadline:
            raise SystemExit("benchtest: the service did not answer within %d s (%s)"
                             % (timeout, problem))
        sleep(1)


# --- the two ways in ----------------------------------------------------------------------------

def remote_reader(host, run=subprocess.run):
    """read_url and alive for the Core host, over ssh: one round trip for both."""
    state = {"active": None}

    def read_url():
        cmd = "sudo -n cat %s 2>/dev/null; echo; systemctl is-active %s" % (URL_FILE, UNIT)
        try:
            p = run(["ssh"] + SSH_OPTS + [host, cmd], stdout=subprocess.PIPE,
                    stderr=subprocess.DEVNULL, timeout=20)
        except subprocess.TimeoutExpired:
            return None
        lines = [l.strip() for l in p.stdout.decode("utf-8", "replace").splitlines() if l.strip()]
        state["active"] = lines[-1] if lines else None
        url = lines[0] if len(lines) > 1 else None
        return reachable_url(url, host) if url else None

    def alive():
        if state["active"] in ("failed", "inactive"):
            return ("%s on %s is %s; its log: ssh %s journalctl -u %s -n 30"
                    % (UNIT, host, state["active"], host, UNIT))
        return None

    return read_url, alive


def open_browser(url, run=subprocess.run):
    opener = "open" if sys.platform == "darwin" else "xdg-open"
    try:
        run([opener, url], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=20)
        return True
    except (OSError, subprocess.SubprocessError):
        return False


def start_fake(app=None):
    """The app from this checkout, on loopback, in a scratch directory. (process, scratch, run dir)."""
    app = app or APP
    if not os.path.exists(app):
        raise SystemExit("benchtest: there is no %s in this checkout" % relative_to_repo(app))
    scratch = tempfile.mkdtemp(prefix="pedal-benchtest-fake-")
    state, run_dir = os.path.join(scratch, "state"), os.path.join(scratch, "run")
    os.makedirs(state)
    os.makedirs(run_dir)
    proc = subprocess.Popen([sys.executable, app, "--fake", "--bind", "127.0.0.1", "--port", "0",
                             "--state-dir", state, "--run-dir", run_dir])
    return proc, scratch, run_dir


def stop_fake(proc, scratch):
    if proc.poll() is None:
        proc.terminate()
        try:
            proc.wait(5)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait()
    shutil.rmtree(scratch, ignore_errors=True)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    where = ap.add_mutually_exclusive_group(required=True)
    where.add_argument("--host", help="the Core host whose service scripts/benchtest started")
    where.add_argument("--fake", action="store_true", help="run the app locally with its fakes")
    ap.add_argument("--device", help="the CoreAudio input device that is the audio interface")
    ap.add_argument("--choose-device", action="store_true",
                    help="ask again which device is the audio interface")
    ap.add_argument("--no-browser", action="store_true", help="print the URL, open nothing")
    ap.add_argument("--timeout", type=float, default=60, help="seconds to wait for the service")
    args = ap.parse_args(argv)

    def interrupted(signum, frame):
        raise KeyboardInterrupt
    signal.signal(signal.SIGTERM, interrupted)
    signal.signal(signal.SIGHUP, interrupted)

    device = DeviceChoice(override=args.device)
    if args.choose_device:
        device.forget()
    proc = scratch = None
    try:
        if args.fake:
            proc, scratch, run_dir = start_fake()
            url_file = os.path.join(run_dir, "url")

            def read_url():
                try:
                    with open(url_file) as f:
                        return f.read().strip() or None
                except OSError:
                    return None

            def alive():
                return None if proc.poll() is None else "the fake app exited (%d)" % proc.returncode
            session = wait_for_service(read_url, args.timeout, alive=alive)
        else:
            read_url, alive = remote_reader(args.host)
            session = wait_for_service(read_url, args.timeout, alive=alive)
            if not args.device and not device.remembered() and device.interactive:
                try:
                    device.choose()
                except JobError as exc:
                    say("%s (the noise tests will ask again)" % exc)
        if args.no_browser or not open_browser(session.url):
            say("open this in the browser: %s" % session.url)
        else:
            say("opened %s in the browser" % session.url)
        say("helping with the recordings; Ctrl-C to stop helping")
        serve(session, Jobs(device=device),
              alive=(lambda: proc.poll() is None) if proc else (lambda: True))
        if proc is not None:
            say("the fake app has stopped")
        else:
            say("%s on %s has stopped (Stop on the page, or %d minutes with no page open)"
                % (UNIT, args.host, IDLE_MINUTES))
        return 0
    except KeyboardInterrupt:
        print(flush=True)
        if proc is not None:
            say("stopping the fake app")
        else:
            say("left %s running on %s: it stops itself %d minutes after the page is closed, "
                "or at once from Stop on the page" % (UNIT, args.host, IDLE_MINUTES))
        return 0
    finally:
        if proc is not None:
            stop_fake(proc, scratch)


if __name__ == "__main__":
    sys.exit(main())
