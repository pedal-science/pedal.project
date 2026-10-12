"""pedal-benchtest's command line.

    pedal-benchtest [--fake] [--bind ADDR] [--port N] [--state-dir DIR] [--run-dir DIR]
                    [--idle-seconds N] [--diag PATH]

`pedal.benchtest.service` runs it as root with the defaults; `scripts/benchtest` depends on these
exact flags. `--port 0` binds a free port, and the URL file and stdout carry the real one.
`--fake` swaps every benchtest for its fake (fakes.py) and touches nothing on the pedal; without
an explicit --state-dir or --run-dir it keeps them in a temporary directory, so a fake session on
a workstation never needs /var/lib or /run.
"""

import argparse
import os
import signal
import sys
import tempfile

from . import VERSION

STATE_DIR = "/var/lib/pedal/benchtest"
RUN_DIR = "/run/pedal-benchtest"
PORT = 47820
IDLE_S = 300
INTERFACE = "etc/pedal/pedal-interface.json"


def parse(argv):
    p = argparse.ArgumentParser(prog="pedal-benchtest", description=__doc__.splitlines()[0])
    p.add_argument("--fake", action="store_true", help="fake benchtests; nothing on the pedal is touched")
    p.add_argument("--bind", default="0.0.0.0", help="address to listen on (default 0.0.0.0)")
    p.add_argument("--port", type=int, default=PORT, help="port (default %d; 0 picks a free one)" % PORT)
    p.add_argument("--state-dir", help="where history.json lives (default %s)" % STATE_DIR)
    p.add_argument("--run-dir", help="where the url file goes (default %s)" % RUN_DIR)
    p.add_argument("--idle-seconds", type=float, default=IDLE_S,
                   help="exit after this long with no browser (default %d)" % IDLE_S)
    p.add_argument("--diag", default="/usr/local/sbin/pedal-diag", help="the pedal-diag to run")
    p.add_argument("--version", action="version", version="pedal-benchtest " + VERSION)
    return p.parse_args(argv)


def interface_path():
    """The installed interface model, or the checkout's when run from one: the same relative place."""
    here = os.path.dirname(os.path.abspath(__file__))       # .../usr/local/lib/benchtest
    root = os.path.abspath(os.path.join(here, "..", "..", "..", ".."))
    return os.path.join(root, INTERFACE)


def main(argv=None):
    args = parse(sys.argv[1:] if argv is None else argv)
    from .server import App, serve

    scratch = None
    if args.fake and (args.state_dir is None or args.run_dir is None):
        scratch = tempfile.mkdtemp(prefix="pedal-benchtest-")
    state_dir = args.state_dir or (os.path.join(scratch, "state") if args.fake else STATE_DIR)
    run_dir = args.run_dir or (os.path.join(scratch, "run") if args.fake else RUN_DIR)
    os.makedirs(state_dir, mode=0o755, exist_ok=True)

    if args.fake:
        from .fakes import FakeBench
        bench = FakeBench()
    else:
        from .real import RealBench, load_interface
        bench = RealBench(diag=args.diag, interface=load_interface(interface_path()))

    app = App(bench, state_dir, idle_seconds=args.idle_seconds)
    if hasattr(bench, "log"):
        bench.log = app.log
    for signum in (signal.SIGTERM, signal.SIGINT):
        signal.signal(signum, lambda *_: app.request_stop("signal"))
    return serve(app, args.bind, args.port, run_dir)


if __name__ == "__main__":
    sys.exit(main())
