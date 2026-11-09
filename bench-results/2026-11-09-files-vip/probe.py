"""On the pedal, under sudo: how long a press takes from the host itself, with no network in the way.

    python3 - <seconds> < probe.py     (check.py pipes it over ssh)

Prints one line per press: seconds since the start, then milliseconds to `POST /event`'s answer. The
answer comes after the loop has run the press, so this is the loop's delay plus one rig switch.
"""
import http.client
import json
import sys
import time

token = open("/etc/namchain/token").read().strip()
stop = time.monotonic() + float(sys.argv[1])
start = time.monotonic()
while time.monotonic() < stop:
    conn = http.client.HTTPConnection("127.0.0.1", 47820, timeout=30)
    began = time.monotonic()
    conn.request("POST", "/event", json.dumps({"kind": 1}), {"Authorization": "Bearer " + token, "Pedal-Client": "probe"})
    conn.getresponse().read()
    print(f"{began - start:.3f} {(time.monotonic() - began) * 1000:.1f}", flush=True)
    conn.close()
    time.sleep(0.1)
