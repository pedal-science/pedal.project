#!/usr/bin/env python3
# Rebuild the SSL's audio streams from a usbmon pcap and find where samples go missing.
#   wire.py DIR   (DIR holds usb.pcap, playback.wav as aplay played it, capture.wav as arecord saved it)
import struct, sys
import numpy as np

d = sys.argv[1]
rate = 48000

def wav(path, ch):
    return np.memmap(path, dtype="<i4", mode="r", offset=44).reshape(-1, ch)

# --- pcap (LINKTYPE_USB_LINUX_MMAPPED): 64-byte usbmon header, iso descriptors, data ---
buf = open(f"{d}/usb.pcap", "rb").read()
magic, _, _, _, _, snap, linktype = struct.unpack_from("<IHHiIII", buf, 0)
assert magic == 0xA1B2C3D4 and linktype == 220, (hex(magic), linktype)
pos = 24
out_chunks, in_chunks = [], []
out_frames, in_frames = [], []
urbs = {"out": 0, "in": 0}
bad = 0
badlist = []
while pos + 16 <= len(buf):
    _, _, incl, orig = struct.unpack_from("<IIII", buf, pos)
    pos += 16
    rec = buf[pos : pos + incl]
    pos += incl
    ev, xfer, ep, dev = struct.unpack_from("<cBBB", rec, 8)
    if xfer != 0:  # isochronous only
        continue
    status, length, len_cap = struct.unpack_from("<iII", rec, 28)
    err_count, numdesc = struct.unpack_from("<ii", rec, 40)
    start_frame = struct.unpack_from("<i", rec, 52)[0]
    ndesc = struct.unpack_from("<I", rec, 60)[0]
    descs = [struct.unpack_from("<iII", rec, 64 + 16 * i) for i in range(ndesc)]
    data = rec[64 + 16 * ndesc :]
    if ep == 0x01 and ev == b"S":
        urbs["out"] += 1
        for st, off, ln in descs:
            out_chunks.append(data[off : off + ln])
        out_frames.append(start_frame)
    elif ep == 0x81 and ev == b"C":
        urbs["in"] += 1
        for st, off, ln in descs:
            if st != 0:
                bad += 1
                badlist.append((sum(len(c) for c in in_chunks) // 32, st, ln, start_frame))
            in_chunks.append(data[off : off + ln])
        in_frames.append(start_frame)
print(f"URBs: out {urbs['out']}, in {urbs['in']}; IN packets with bad status: {bad}")
import collections
print("bad IN packets by (status, length):", dict(collections.Counter((st, ln) for _, st, ln, _ in badlist)))
if badlist:
    fr = [p for p, *_ in badlist]
    print(f"bad IN packets at wire-in frames {fr[0]}..{fr[-1]} ({fr[0] / rate:.3f}..{fr[-1] / rate:.3f} s into the capture); "
          f"USB frames {badlist[0][3]}..{badlist[-1][3]}")
wire_out = np.frombuffer(b"".join(out_chunks), dtype="<i4")
wire_in = np.frombuffer(b"".join(in_chunks), dtype="<i4")
assert wire_out.size % 6 == 0 and wire_in.size % 8 == 0, (wire_out.size, wire_in.size)
wire_out = wire_out.reshape(-1, 6)
wire_in = wire_in.reshape(-1, 8)
print(f"wire out {len(wire_out)} frames ({len(wire_out) / rate:.1f} s), wire in {len(wire_in)} frames")

played = wav(f"{d}/playback.wav", 6)
saved = wav(f"{d}/capture.wav", 8)

RUN, SEARCH = 512, 64

def slips(ref, obs, name, maxlag0=96000):
    """obs[t] == ref[t - lag] with lag stepping. Negative lags allowed via offsets."""
    ref = np.ascontiguousarray(ref)
    obs = np.ascontiguousarray(obs)
    n_ref, n_obs = len(ref), len(obs)

    def ok(lag, s):
        if s - lag < 0 or s - lag + RUN > n_ref or s + RUN > n_obs:
            return False
        b = ref[s - lag : s - lag + RUN]
        return np.count_nonzero(b) > RUN // 2 and np.array_equal(obs[s : s + RUN], b)

    def relock(f, lag):
        best = None
        for L in range(lag - SEARCH, lag + SEARCH + 1):
            lo, hi = f, min(n_obs - RUN, f + rate, n_ref - RUN + L)
            if lo - L < 0 or hi <= lo:
                continue
            eq = obs[lo : hi + RUN] == ref[lo - L : hi - L + RUN]
            cs = np.concatenate(([0], np.cumsum(eq, dtype=np.int64)))
            idx = np.flatnonzero(cs[RUN:] - cs[:-RUN] == RUN)
            for i in idx[:50]:
                if np.count_nonzero(ref[lo + i - L : lo + i - L + RUN]) > RUN // 2:
                    if best is None or lo + i < best[0]:
                        best = (lo + i, L)
                    break
        return best

    lock = None
    s = rate
    while lock is None and s < n_obs - rate:
        # coarse: find the lag by matching one 512-frame block anywhere in ref
        blk = obs[s : s + RUN]
        if np.count_nonzero(blk) > RUN // 2:
            cand = np.flatnonzero(ref[: n_ref - RUN] == blk[0])
            for c in cand:
                if np.array_equal(ref[c : c + RUN], blk):
                    lock = (s, s - int(c))
                    break
        s += rate // 4
    if lock is None:
        print(f"{name}: never locked")
        return
    s, lag = lock
    lag0 = lag
    ev = []
    end = min(n_obs, n_ref + lag)
    while s < end - RUN:
        e = min(end, s + rate, n_ref + lag)
        if e <= s:
            break
        ne = np.flatnonzero(obs[s:e] != ref[s - lag : e - lag])
        if ne.size == 0:
            s = e
            continue
        f = s + int(ne[0])
        nx = relock(f, lag)
        if nx is None:
            ev.append((f, lag, None))
            break
        ev.append((f, lag, nx[1]))
        s, lag = nx[0] + RUN, nx[1]
    steps = [b - a for _, a, b in ev if b is not None]
    vals, cnt = np.unique(steps, return_counts=True) if steps else ([], [])
    tail = " (lost lock)" if ev and ev[-1][2] is None else ""
    print(f"{name}: locked at lag {lag0}, {len(ev)} slips over {(s - lock[0]) / rate:.1f} s{tail}; "
          f"steps {dict(zip(np.asarray(vals).tolist(), np.asarray(cnt).tolist()))}")
    return ev

def near_bad(ev, label):
    if not ev:
        return
    pos = np.array([p for p, *_ in badlist])
    hits = 0
    for f, a, b in ev:
        if pos.size and np.min(np.abs(pos - f)) < 64:
            hits += 1
    print(f"   {label}: {hits} of {len(ev)} slips within 64 frames of a bad IN packet")

print()
slips(played[:, 0], wire_out[:, 0], "1. file aplay played -> host's OUT packets (kernel, playback side)")
e2 = slips(wire_out[:, 0], wire_in[:, 2], "2. OUT packets -> loopback in IN packets (inside the SSL)")
near_bad(e2, "loopback on the wire")
slips(wire_in[:, 2], saved[:, 2], "3. IN packets -> what arecord saved (kernel, capture side)")
slips(played[:, 0], saved[:, 2], "   end to end, as before")
