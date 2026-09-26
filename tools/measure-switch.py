#!/usr/bin/env python3
"""measure-switch.py [--cycles N] [--drop-caches] — plan 1.7: how long a cold rig switch takes on the Core host.

Runs on the host, as root (the socket is 0660 root). Cycles `rig.apply` through four A2 + cab
rigs with different models and IRs, so every switch loads, parses and prewarms a model and
prepares an IR: the cold path D10's 50 ms has to beat. For each switch it records

  reply    the command sent -> namchaind's reply (compiled and published)
  audible  the command sent -> audible_generation reaches the new generation and the crossfade
           has finished, polled every 1 ms

Output latency after that (the device queue and the converters) is the same for every switch
and is measured separately with namchain-latency through the loopback cable.

--drop-caches empties the page cache before every switch, so each model and IR comes off the
disk, as the first switch after a boot would.

Leaves the engine on the rig it started with.
"""
import json, socket, statistics, sys, time

RIGS = [
    ("Ampeg GVT52 - Channel 2/AMPEG_CH 2 NEUTRAL G5",
     "Orange 4x12/York Audio ORNG 412 V30 v1.00/48k (Fractal, Line 6, Two Notes, etc.)/Natural Phase Singles/YA ORNG 412 V30 421v-CNT"),
    ("Boss SD-1 Super Overdrive/APP-SD1-Drive-III", "Mesa_OS_4x12_57_m160"),
    ("NAM Ampeg VT-40/Ampeg VT-40 - Vol 4, Bass 6, Mid 5, Treble 8, M160",
     "Orange 4x12/York Audio ORNG 412 V30 v1.00/44.1k (Kemper, Mooer, Yamaha, etc.)/Minimum Phase Singles/YA ORNG 412 V30 121-1"),
    ("British Stoner Doom Essentials/RIFF TAPE 001_Green Russian + OR120 + PPC412",
     "Orange 4x12/York Audio ORNG 412 V30 v1.00/96k (Strymon, BOSS, etc.)/Natural Phase Singles/YA ORNG 412 V30 421v-CNT"),
]


def doc(model, ir):
    return {"nodes": [{"id": "in", "type": "nc.input"},
                      {"id": "amp", "type": "nc.nam", "model": model},
                      {"id": "cab", "type": "nc.cab.ir", "ir": ir},
                      {"id": "out", "type": "nc.output"}],
            "connections": [{"from": "in", "to": "amp"}, {"from": "amp", "to": "cab"},
                            {"from": "cab", "to": "out"}]}


s = socket.socket(socket.AF_UNIX, socket.SOCK_SEQPACKET)
s.connect("/run/namchain/namchaind.sock")
n = 0


def call(msg):
    global n
    n += 1
    msg["id"] = str(n)
    s.send(json.dumps(msg).encode())
    return json.loads(s.recv(1 << 20))


def main():
    cycles = int(sys.argv[sys.argv.index("--cycles") + 1]) if "--cycles" in sys.argv else 5
    call({"method": "engine.hello", "protocol": 2})
    start = call({"method": "rig.get"})["document"]
    replies, audibles = [], []
    for c in range(cycles):
        for model, ir in RIGS:
            if "--drop-caches" in sys.argv:
                with open("/proc/sys/vm/drop_caches", "w") as f:
                    f.write("3\n")
                time.sleep(0.5)
            t0 = time.monotonic()
            r = call({"method": "rig.apply", "document": doc(model, ir)})
            t1 = time.monotonic()
            if not r.get("ok"):
                sys.exit(f"rig.apply failed: {r}")
            gen = r["generation"]
            while True:
                st = call({"method": "engine.status"})["status"]
                if st["audible_generation"] >= gen and not st["transition_active"]:
                    break
                time.sleep(0.001)
            t2 = time.monotonic()
            replies.append((t1 - t0) * 1000)
            audibles.append((t2 - t0) * 1000)
            print(f"  {model.split('/')[-1][:44]:44s} reply {replies[-1]:7.1f} ms  audible {audibles[-1]:7.1f} ms",
                  flush=True)
            time.sleep(1.0)
    st = call({"method": "engine.status"})["status"]
    call({"method": "rig.apply", "document": start})
    q = lambda xs: f"median {statistics.median(xs):.1f}  max {max(xs):.1f}  min {min(xs):.1f} ms"
    print(f"switches: {len(audibles)}   xruns during run: {st['xruns']}   health: {st['health']}")
    print(f"reply:   {q(replies)}")
    print(f"audible: {q(audibles)}")


main()
