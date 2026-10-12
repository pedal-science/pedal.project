"""The benchtests that touch the pedal.

Health benchtests run the installed `pedal-diag --json` once per run and read its findings
(catalog.DIAG_ROWS says which finding speaks to which block). The Debug Probe benchtest asks the
workstation helper, because pedal-diag on Core cannot see the computer's USB.

Noise benchtests follow the 2026-10-11 method: the engine keeps running and is muted (its playback
path held open), the capture is 20 s at 48 kHz and the first 2 s are dropped, and the previous mute
is put back afterwards. Output benchtests have the helper record the audio interface (`capture`);
input benchtests have the engine record what the codec hears (`engine.record`) and hand the WAV to
the helper (`analyse_recording`). The FFT stays on the workstation. This module never stops
namchaind, never runs arecord, and never touches the period size.
"""

import contextlib
import json
import os
import subprocess
import time

from pedald.engine import EngineClient, EngineError

from . import catalog
from .runner import NotRun

DIAG = "/usr/local/sbin/pedal-diag"
DIAG_TIMEOUT_S = 120
ENGINE_TOKEN = "/etc/namchain/token"
ENGINE_HOST, ENGINE_PORT = "127.0.0.1", 47810
#: How long the engine is given to settle after a mute before anything is measured: a level read
#: in the same breath as the mute still shows the old output (2026-10-11, operational notes).
MUTE_SETTLE_S = 0.5
#: The helper's own time on top of the capture: sox's start, the transfer, and the pure-Python FFT.
HELPER_MARGIN_S = 240


class RealBench:
    needs_helper = True
    fake = False

    def __init__(self, diag=DIAG, interface=None, token_path=ENGINE_TOKEN,
                 engine_host=ENGINE_HOST, engine_port=ENGINE_PORT, log=None):
        self.diag_path = diag
        self.interface = interface or {}
        self.token_path = token_path
        self.engine_host = engine_host
        self.engine_port = engine_port
        self.log = log or (lambda message: None)

    # -- the bench ---------------------------------------------------------------------------------

    def run(self, test_id, ctx):
        kind = catalog.test(test_id)["kind"]
        if kind == "diag":
            return catalog.evaluate_diag(test_id, self.diag(ctx), self.interface)
        if kind == "probe":
            ctx.require_helper()
            return catalog.probe_result(ctx.helper_job("probe_usb", {}, timeout=60))
        if kind == "output_noise":
            return catalog.classify_output(test_id, self.capture_output(ctx))
        if kind == "input_noise":
            return catalog.classify_input(self.record_input(ctx))
        if kind == "battery":
            reference = ctx.facts.get("input_line50_dbfs")
            if reference is None:
                return catalog.classify_battery({}, None)
            return catalog.classify_battery(self.record_input(ctx), reference)
        if kind == "codec_only":
            return catalog.classify_codec_only(self.record_input(ctx), ctx.facts.get("input_rms_dbfs"))
        raise ValueError("no benchtest of kind %r" % kind)

    def codec_present(self, ctx):
        return catalog.codec_present_from_diag(self.diag(ctx, required=False))

    # -- pedal-diag, once per run ------------------------------------------------------------------

    def diag(self, ctx, required=True):
        """The run's one pedal-diag report. NotRun (or None) if it cannot be had."""
        if "diag" not in ctx.shared:
            ctx.shared["diag"] = self._diag_once()
        report, error = ctx.shared["diag"]
        if report is None and required:
            raise NotRun("Not run: pedal-diag could not be read, so there is nothing to judge.",
                         error)
        return report

    def _diag_once(self):
        try:
            done = subprocess.run([self.diag_path, "--json"], stdout=subprocess.PIPE,
                                  stderr=subprocess.PIPE, timeout=DIAG_TIMEOUT_S, check=False)
        except (OSError, subprocess.TimeoutExpired) as exc:
            return None, "%s --json: %s" % (self.diag_path, exc)
        # pedal-diag exits 1 when anything is a fail; that is a report, not an error.
        try:
            report = json.loads(done.stdout.decode("utf-8", "replace"))
        except ValueError as exc:
            tail = done.stderr.decode("utf-8", "replace").strip().splitlines()[-1:] or [""]
            return None, "%s --json exited %d and printed no report (%s) %s" % (
                self.diag_path, done.returncode, exc, tail[0])
        if not isinstance(report, dict):
            return None, "%s --json printed something other than a report" % self.diag_path
        return report, None

    # -- the engine --------------------------------------------------------------------------------

    def engine(self):
        try:
            with open(self.token_path) as f:
                token = f.read().strip()
        except OSError as exc:
            raise NotRun("Not run: the engine's token could not be read.", str(exc))
        return EngineClient(self.engine_host, self.engine_port, token=token, timeout=5.0)

    @contextlib.contextmanager
    def muted(self, ctx):
        """The engine muted for the measurement, and its previous mute put back whatever happens."""
        client = self.engine()
        try:
            status = client.status()
            previous = bool((status.get("status") or status).get("mute", False))
            client.call("engine.mute", mute=True)
        except EngineError as exc:
            client.close()
            raise NotRun("Not run: the engine is not answering, so it cannot be muted for the "
                         "measurement. \"Sound device and engine\" says why.", str(exc))
        try:
            ctx.sleep(MUTE_SETTLE_S)
            yield client
        finally:
            try:
                client.call("engine.mute", mute=previous)
            except EngineError as exc:
                self.log("the engine's mute could not be put back to %s: %s" % (previous, exc))
            client.close()

    # -- the measurements -------------------------------------------------------------------------

    def capture_output(self, ctx):
        """The helper records the interface while the engine sends silence."""
        ctx.require_helper()
        bars = ctx.test["bars"]
        params = {"seconds": bars["seconds"], "skip_seconds": bars["skip_seconds"], "channel": 0,
                  "note": "%s: %s" % (ctx.test["name"], ctx.test["line"])}
        with self.muted(ctx):
            return ctx.helper_job("capture", params, timeout=bars["seconds"] + HELPER_MARGIN_S)

    def record_input(self, ctx):
        """The engine records what the codec hears; the helper fetches the WAV and analyses it."""
        ctx.require_helper()
        bars = ctx.test["bars"]
        seconds = bars["seconds"]
        name = "benchtest-%s-%s" % (ctx.run_id, ctx.test_id)
        with self.muted(ctx) as client:
            try:
                reply = client.call("engine.record", action="start", name=name, seconds=seconds)
            except EngineError as exc:
                raise NotRun("Not run: the engine would not record.", str(exc))
            record = reply.get("record") or {}
            directory = record.get("path")
            deadline = time.monotonic() + seconds + 15
            while True:
                if not ctx.sleep(1.0):
                    _stop_recording(client)
                    raise NotRun("Not run: the run was stopped during the recording.")
                try:
                    record = client.call("engine.record").get("record") or {}
                except EngineError as exc:
                    raise NotRun("Not run: the engine stopped answering during the recording.",
                                 str(exc))
                if not record.get("active") or record.get("name") != name:
                    break
                if time.monotonic() > deadline:
                    _stop_recording(client)
                    break
        if record.get("error"):
            raise NotRun("Not run: the engine's recording failed.", str(record["error"]))
        wav = os.path.join(directory or record.get("path") or "", "capture.wav")
        if not directory or not os.path.isfile(wav):
            raise NotRun("Not run: the engine's recording is not where it said it would be.", wav)
        job_id = ctx.helper.new_id()
        ctx.helper.attach_recording(job_id, wav)
        params = {"url": "/api/helper/recording/%s" % job_id, "channel": 0,
                  "skip_seconds": bars["skip_seconds"]}
        return ctx.helper_job("analyse_recording", params, timeout=HELPER_MARGIN_S, job_id=job_id)


def _stop_recording(client):
    try:
        client.call("engine.record", action="stop")
    except EngineError:
        pass


def load_interface(path):
    try:
        with open(path) as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}
