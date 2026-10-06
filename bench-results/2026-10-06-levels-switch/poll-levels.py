#!/usr/bin/env python3
"""Poll namchaind's engine.levels at a fixed rate and measure the daemon's CPU while doing it.

This is the instrument behind bench-results/2026-10-06-levels-switch.md. It is deliberately a
*client* and not a change to the daemon: what is being measured is what a meter in ljoss does to
the engine, so the client has to be the same shape as that meter -- one TCP connection, one
engine.levels request per tick, nothing else.

What it reports:

  * the CPU the daemon process used during the run, as a share of one core, summed over every
    thread (the render thread is the interesting one, and it is not the only one). Read from
    /proc/<pid>/stat's utime + stime, so it is the kernel's own accounting of the process rather
    than a sampled estimate.
  * the rate actually achieved, which is not the rate asked for. A daemon that cannot answer in
    time, or a client that schedules badly, shows up here rather than being hidden by a sleep loop
    that silently falls behind.
  * the number of windows that came back empty (frames: 0 everywhere). The probes are read and
    reset, so a client polling faster than the engine renders sees empty windows between populated
    ones; ljoss's meter holds its display through them. A run with many empty windows is a run
    whose numbers came from fewer samples than its ticks suggest.

CPU time is in clock ticks (CLK_TCK, 100 on this kernel); the caller converts.

Usage:
  poll-levels.py --seconds 60 [--hz 20] [--pid PID] [--token-file FILE]
                 [--host 127.0.0.1] [--port 47810]
  poll-levels.py --seconds 60 --expect-refusal          # measuring is off: assert and exit
"""

from __future__ import annotations

import argparse
import json
import socket
import struct
import sys
import time


def call(sock: socket.socket, message: dict) -> dict:
    body = json.dumps(message).encode()
    sock.sendall(struct.pack("<I", len(body)) + body)
    header = b""
    while len(header) < 4:
        chunk = sock.recv(4 - len(header))
        if not chunk:
            raise RuntimeError("the daemon closed the connection")
        header += chunk
    length = struct.unpack("<I", header)[0]
    body = b""
    while len(body) < length:
        chunk = sock.recv(length - len(body))
        if not chunk:
            raise RuntimeError("the daemon closed the connection mid-reply")
        body += chunk
    return json.loads(body)


def cpu_ticks(pid: int) -> int:
    """utime + stime for the process, every thread included, in clock ticks."""
    with open(f"/proc/{pid}/stat", "rb") as handle:
        fields = handle.read().rsplit(b")", 1)[1].split()
    # Fields after the comm: state is [0], so utime is [11] and stime is [12].
    return int(fields[11]) + int(fields[12])


def has_signal(levels: dict) -> bool:
    """Whether this window measured anything anywhere, which is what ljoss checks.

    The shapes differ and that matters: a device entry's `frames` is an **array**, one count per
    channel, while a chain's `out` and a node's entry carry a single count. A reader that treated the
    device's array as a number would either raise or, worse, call a silent input busy.
    """
    def frames(entry) -> int:
        if not isinstance(entry, dict):
            return 0
        value = entry.get("frames")
        if isinstance(value, list):
            return sum(int(v or 0) for v in value)
        return int(value or 0)

    if frames(levels.get("input")) or frames(levels.get("output")):
        return True
    for chain in levels.get("chains") or []:
        if frames(chain.get("out")):
            return True
        for node in chain.get("nodes") or []:
            if frames(node):
                return True
    return False


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--seconds", type=float, required=True)
    parser.add_argument("--hz", type=float)
    parser.add_argument("--pid", type=int)
    parser.add_argument("--token-file", default="/etc/namchain/token")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=47810)
    parser.add_argument("--expect-refusal", action="store_true",
                        help="assert that engine.levels is refused, then exit")
    parser.add_argument("--label", default="")
    args = parser.parse_args()

    token = open(args.token_file).read().strip()

    result: dict = {"label": args.label, "hz": args.hz, "seconds": args.seconds}

    sock = socket.create_connection((args.host, args.port), timeout=5)
    sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
    call(sock, {"id": "h", "method": "engine.hello", "protocol": 2, "token": token})

    if args.expect_refusal:
        reply = call(sock, {"id": "l", "method": "engine.levels"})
        result["refused"] = reply.get("ok") is False
        result["error_code"] = (reply.get("error") or {}).get("code")
        result["error_message"] = (reply.get("error") or {}).get("message")
        sock.close()
        print(json.dumps(result))
        return 0

    if args.pid is None or args.hz is None:
        parser.error("--pid and --hz are required unless --expect-refusal is given")

    period = 1.0 / args.hz
    ticks: int = 0
    empty: int = 0
    populated: int = 0
    errors: int = 0
    chains_seen: int = 0
    nodes_seen: int = 0
    nodes_with_frames: int = 0
    reply_bytes: int = 0

    started_cpu = cpu_ticks(args.pid)
    started = time.monotonic()
    deadline = started + args.seconds
    next_tick = started

    while True:
        now = time.monotonic()
        if now >= deadline:
            break
        if now < next_tick:
            time.sleep(next_tick - now)
        next_tick += period

        request_started = time.monotonic()
        try:
            reply = call(sock, {"id": "l", "method": "engine.levels"})
        except Exception as exc:                      # a dropped connection is a result, not a crash
            errors += 1
            result["exception"] = str(exc)
            if errors > 3:
                break
            continue
        ticks += 1
        reply_bytes += len(json.dumps(reply))
        levels = reply.get("levels") or {}
        if has_signal(levels):
            populated += 1
        else:
            empty += 1
        chains = levels.get("chains") or []
        chains_seen = len(chains)
        nodes_seen = sum(len(chain.get("nodes") or []) for chain in chains)
        nodes_with_frames = sum(
            1
            for chain in chains
            for node in (chain.get("nodes") or [])
            if int(node.get("frames") or 0) > 0
        )
        # The last request's duration, so a run that could not keep up says so.
        result["last_call_ms"] = round((time.monotonic() - request_started) * 1000.0, 3)

    finished = time.monotonic()
    finished_cpu = cpu_ticks(args.pid)

    elapsed = finished - started
    result.update({
        "elapsed_s": round(elapsed, 3),
        "cpu_ticks": finished_cpu - started_cpu,
        "ticks": ticks,
        "achieved_hz": round(ticks / elapsed, 3) if elapsed > 0 else 0.0,
        "empty_windows": empty,
        "populated_windows": populated,
        "errors": errors,
        "chains": chains_seen,
        "nodes": nodes_seen,
        "nodes_with_frames": nodes_with_frames,
        "mean_reply_bytes": round(reply_bytes / ticks) if ticks else 0,
    })
    sock.close()
    print(json.dumps(result))
    return 0


if __name__ == "__main__":
    sys.exit(main())
