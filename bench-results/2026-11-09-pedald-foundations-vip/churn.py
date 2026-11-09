#!/usr/bin/env python3
"""churn.py HOST TOKEN_FILE OUT_DIR [SECONDS]: O2's churn gate (docs/pedal-service.md, "Threads").

From the Mac, against pedald on the Core host, for SECONDS: fresh connections, keep-alive, sockets
abandoned mid-request and silent ones, event streams opened and dropped without a goodbye, and more
connections than the cap allows. All the while a listener on /events must hear every rig step, in order.
pedald's thread count and memory are sampled over ssh; the pass is threads back where they started once
the connection timeouts have run out. Run it under scripts/host-lock.
"""
import http.client
import json
import random
import socket
import struct
import subprocess
import sys
import threading
import time

host, token_file, out = sys.argv[1], sys.argv[2], sys.argv[3]
seconds = float(sys.argv[4]) if len(sys.argv) > 4 else 600.0
PORT = 47820
# Once: asking the Mac for a .local name takes about a second each time, which would pace the churn.
ADDRESS = socket.gethostbyname(host)
SETTLE = 45.0   # past the 30 s between requests, the 5 s first byte and the 30 s TCP user timeout
TOKEN = open(token_file).read().strip()
AUTH = {"Authorization": "Bearer " + TOKEN}
AUTH_LINE = f"Authorization: Bearer {TOKEN}\r\n"
stop = threading.Event()
counts = {}
lock = threading.Lock()


def count(name):
    with lock:
        counts[name] = counts.get(name, 0) + 1


def worker(name, period, body):
    def run():
        while not stop.is_set():
            try:
                body()
                count(name)
            except OSError:
                count(name + "_error")
            stop.wait(period * random.uniform(0.5, 1.5))
    thread = threading.Thread(target=run, name=name, daemon=True)
    thread.start()
    return thread


def fresh():
    conn = http.client.HTTPConnection(ADDRESS, PORT, timeout=10)
    conn.request("GET", "/status", headers=AUTH)
    conn.getresponse().read()
    conn.close()


kept = {"conn": None}


def keepalive():
    if kept["conn"] is None:
        kept["conn"] = http.client.HTTPConnection(ADDRESS, PORT, timeout=10)
    try:
        kept["conn"].request("GET", "/pedal", headers=AUTH)
        kept["conn"].getresponse().read()
    except (OSError, http.client.HTTPException):
        kept["conn"] = None
        raise OSError("the kept connection went")


def abandoned_mid_request():
    sock = socket.create_connection((ADDRESS, PORT), timeout=5)
    sock.sendall(b"GET /sta")
    sock.close()


def abandoned_mid_body():
    sock = socket.create_connection((ADDRESS, PORT), timeout=5)
    sock.sendall(f"PUT /pedal HTTP/1.1\r\nHost: x\r\n{AUTH_LINE}Content-Length: 500\r\n\r\nxx".encode())
    sock.close()


silent_sockets = []


def silent():
    """A socket that says nothing: the first-byte deadline is what ends it."""
    silent_sockets.append(socket.create_connection((ADDRESS, PORT), timeout=5))
    if len(silent_sockets) > 4:
        silent_sockets.pop(0).close()


def dropped_stream():
    """An event stream that goes without a goodbye: a reset, as a Wi-Fi drop's successor would see."""
    sock = socket.create_connection((ADDRESS, PORT), timeout=5)
    sock.sendall(f"GET /events HTTP/1.1\r\nHost: x\r\n{AUTH_LINE}\r\n".encode())
    sock.recv(4096)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_LINGER, struct.pack("ii", 1, 0))
    sock.close()


def over_the_cap():
    """More connections at once than the server takes, held for a second."""
    socks = [socket.create_connection((ADDRESS, PORT), timeout=5) for _ in range(24)]
    time.sleep(1)
    for sock in socks:
        sock.close()


actions, gaps = [], []


def listener():
    """Stays connected throughout, and comes back with Last-Event-ID if it is ever dropped."""
    last = None
    seen = 0
    while not stop.is_set():
        try:
            sock = socket.create_connection((ADDRESS, PORT), timeout=5)
            extra = f"Last-Event-ID: {last}\r\n" if last else ""
            sock.sendall(f"GET /events HTTP/1.1\r\nHost: x\r\n{AUTH_LINE}{extra}\r\n".encode())
            sock.settimeout(1.0)
            buffer = b""
            while not stop.is_set():
                try:
                    chunk = sock.recv(65536)
                except socket.timeout:
                    continue
                if not chunk:
                    break
                buffer += chunk
                while b"\n\n" in buffer:
                    block, _, buffer = buffer.partition(b"\n\n")
                    fields = dict(l.split(": ", 1) for l in block.decode().split("\n") if ": " in l)
                    if "id" not in fields:
                        continue
                    last = fields["id"]
                    if fields.get("event") == "action":
                        data = json.loads(fields["data"])
                        actions.append({"id": last, "rig": data["result"].get("rig"), "ok": data["result"]["ok"],
                                        "how": data["result"].get("how"), "client": data["cause"].get("client"),
                                        "at": time.time()})
                    if fields.get("event") == "resync":
                        gaps.append(last)
            sock.close()
            count("listener_reconnect")
        except OSError:
            count("listener_error")
            stop.wait(1)
        seen += 1


posted = []


def press():
    conn = http.client.HTTPConnection(ADDRESS, PORT, timeout=15)
    conn.request("POST", "/event", body=json.dumps({"kind": 1}), headers=dict(AUTH, **{"Pedal-Client": "churn"}))
    reply = conn.getresponse()
    data = json.loads(reply.read())
    conn.close()
    posted.append({"status": reply.status, "result": data.get("result"), "at": time.time()})


def sample(samples, label=""):
    script = ("pid=$(systemctl show -p MainPID --value pedald); "
              "grep -E '^(Threads|VmRSS):' /proc/$pid/status; ls /proc/$pid/fd | wc -l; "
              "awk '{print $14+$15}' /proc/$pid/stat")
    text = subprocess.run(["ssh", "-o", "BatchMode=yes", host, "sudo", "sh"], input=script,
                          capture_output=True, text=True, timeout=20).stdout.split()
    # /proc/<pid>/status lists VmRSS before Threads.
    if len(text) != 7 or text[0] != "VmRSS:" or text[3] != "Threads:" or int(text[4]) < 1:
        sys.exit(f"pedald's numbers can't be read: {text}")
    row = {"t": round(time.time(), 1), "label": label, "threads": int(text[4]), "rss_kb": int(text[1]),
           "fds": int(text[5]), "ticks": int(text[6])}
    try:
        conn = http.client.HTTPConnection(ADDRESS, PORT, timeout=10)
        conn.request("GET", "/status", headers=AUTH)
        status = json.loads(conn.getresponse().read())
        conn.close()
        row["http"] = status["http"]
        row["xruns"] = status["engine"]["xruns"]
        row["guard_trips"] = status["engine"]["guard_trips"]
        row["rig"] = status["engine"]["rig_name"]
    except (OSError, ValueError, KeyError) as exc:
        row["status_error"] = repr(exc)
    samples.append(row)
    print(json.dumps(row), flush=True)


samples = []
started = time.time()
sample(samples, "before")
threading.Thread(target=listener, daemon=True).start()
time.sleep(1)
workers = [worker("fresh", 0.05, fresh), worker("keepalive", 0.05, keepalive),
           worker("abandoned_mid_request", 0.2, abandoned_mid_request),
           worker("abandoned_mid_body", 0.5, abandoned_mid_body),
           worker("silent", 3.0, silent), worker("dropped_stream", 2.0, dropped_stream),
           worker("over_the_cap", 60.0, over_the_cap), worker("press", 20.0, press)]
while time.time() - started < seconds:
    time.sleep(30)
    sample(samples, "churn")
stop.set()
for thread in workers:
    thread.join(20)
for sock in silent_sockets:
    sock.close()
if kept["conn"] is not None:
    kept["conn"].close()
time.sleep(SETTLE)
sample(samples, "after")
presses_churning = len(posted)   # what the listener was there to hear; a press to put the rig back isn't
churning = [row for row in samples if row["label"] == "churn"]

# The rig it started on, whichever way the steps ended.
for _ in range(4):
    if samples[-1].get("rig") == samples[0].get("rig"):
        break
    press()
    time.sleep(2)
    sample(samples, "put back")

before, after = samples[0], next(row for row in samples if row["label"] == "after")
ok_posts = [p for p in posted if p["status"] == 200 and p["result"] and p["result"]["ok"]]
summary = {
    "seconds": seconds, "counts": counts,
    "threads": [before["threads"], max(s["threads"] for s in samples), after["threads"]],
    "rss_kb": [before["rss_kb"], max(s["rss_kb"] for s in samples), after["rss_kb"]],
    "fds": [before["fds"], max(s["fds"] for s in samples), after["fds"]],
    "cpu_share_of_a_core_while_churning": round((churning[-1]["ticks"] - before["ticks"]) / 100.0 / (churning[-1]["t"] - before["t"]), 3),
    "refused_at_cap": after.get("http", {}).get("refused"),
    "presses": presses_churning, "presses_ok": len(ok_posts[:presses_churning]),
    "actions_heard": len(actions), "actions_by_how": {h: sum(a["how"] == h for a in actions) for h in set(a["how"] for a in actions)},
    "resyncs_heard_by_listener": len(gaps),
    "xruns": [before.get("xruns"), after.get("xruns")], "guard_trips": [before.get("guard_trips"), after.get("guard_trips")],
    "pass": after["threads"] == before["threads"] and len(actions) == presses_churning and not gaps
            and after.get("http", {}).get("refused", 0) > before.get("http", {}).get("refused", 0),
}
json.dump(samples, open(out + "/samples.json", "w"), indent=1)
json.dump(summary, open(out + "/summary.json", "w"), indent=1)
json.dump({"posted": posted, "actions": actions}, open(out + "/presses.json", "w"), indent=1)
print(json.dumps(summary, indent=1))
