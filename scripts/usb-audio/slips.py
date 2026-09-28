#!/usr/bin/env python3
# Walk the loopback (in3) against out1 bit for bit, and locate each place the delay changes.
#   slips.py DIR   (a namchaind recording: `namchainctl record start NAME`, then `record stop`;
#                   set MAXLAG0 higher when capture and playback didn't start together)
import sys
import numpy as np

d = sys.argv[1]
rate = 48000
cap = np.memmap(f"{d}/capture.wav", dtype="<i4", mode="r", offset=44).reshape(-1, 8)
pb = np.memmap(f"{d}/playback.wav", dtype="<i4", mode="r", offset=44).reshape(-1, 6)
n = min(len(cap), len(pb))
lb = np.ascontiguousarray(cap[:n, 2])
out = np.ascontiguousarray(pb[:n, 0])
inp = np.ascontiguousarray(cap[:n, 0])

RUN = 512       # frames of exact, non-silent match that establish a lag
SEARCH = 64     # how far either way a slip may move the lag
LOOK = rate     # how far past a mismatch to look for the new lag

def locked_at(lag, s):
    """Does lag match exactly over RUN frames at s, on audio that is not silence?"""
    if s - lag < 0 or s + RUN > n:
        return False
    a = lb[s : s + RUN]
    b = out[s - lag : s - lag + RUN]
    return np.count_nonzero(b) > RUN // 2 and np.array_equal(a, b)

def find_lock(s0, around):
    """Earliest s >= s0 and lag near `around` that lock. Returns (s, lag) or None."""
    best = None
    for lag in range(max(0, around - SEARCH), around + SEARCH + 1):
        lo = s0
        hi = min(n - RUN, s0 + LOOK)
        if hi - lag <= 0:
            continue
        eq = lb[lo : hi + RUN] == out[lo - lag : hi - lag + RUN] if lo - lag >= 0 else None
        if eq is None:
            continue
        # first index where RUN consecutive matches start
        cs = np.concatenate(([0], np.cumsum(eq, dtype=np.int64)))
        idx = np.flatnonzero(cs[RUN:] - cs[:-RUN] == RUN)
        for i in idx[:50]:
            if np.count_nonzero(out[lo + i - lag : lo + i - lag + RUN]) > RUN // 2:
                if best is None or lo + i < best[0]:
                    best = (lo + i, lag)
                break
    return best

# initial lock: search all plausible lags at a loud spot
s = rate * 2
lock = None
while lock is None and s < n - LOOK:
    for lag in range(0, int(__import__("os").environ.get("MAXLAG0", "2048"))):
        if locked_at(lag, s):
            lock = (s, lag)
            break
    s += rate // 4
if lock is None:
    sys.exit("never locked")
s, lag = lock
print(f"locked at {s / rate:.3f} s, lag {lag}")

events = []
CH = rate
while s < n - RUN:
    e = min(n, s + CH)
    a = lb[s:e]
    b = out[s - lag : e - lag]
    ne = np.flatnonzero(a != b)
    if ne.size == 0:
        s = e
        continue
    f = s + int(ne[0])
    nxt = find_lock(f, lag)
    if nxt is None:
        events.append((f, lag, None, None))
        print(f"  {f / rate:9.4f} s  lag {lag} -> lost, no relock within 1 s")
        s = f + LOOK
        # try a wide relock
        for L2 in range(0, 2048):
            if locked_at(L2, s):
                lag = L2
                break
        continue
    s2, lag2 = nxt
    events.append((f, lag, lag2, s2 - f))
    print(f"  {f / rate:9.4f} s  lag {lag} -> {lag2}", flush=True)
    lag = lag2
    s = s2 + RUN

print(f"\n{len(events)} slips in {n / rate:.1f} s; lag at the end {lag}")
ups = sum(1 for _, a, b, _ in events if b is not None and b > a)
print(f"lag up {ups}, down {len(events) - ups}")
print("time (s)   lag before -> after   step   mismatched frames   in1 level there (dBFS)")
FS = 2.0**31
for f, l1, l2, span in events:
    lvl = 20 * np.log10(max(np.abs(inp[max(0, f - 480) : f + 480].astype(np.int64)).max(), 1) / FS)
    if l2 is None:
        print(f"  {f / rate:9.4f}  {l1:4d} -> ?")
    else:
        print(f"  {f / rate:9.4f}  {l1:4d} -> {l2:4d}   {l2 - l1:+4d}   {span:7d}   {lvl:6.1f}")
steps = [l2 - l1 for _, l1, l2, _ in events if l2 is not None]
if steps:
    vals, cnt = np.unique(steps, return_counts=True)
    print("step sizes:", dict(zip(vals.tolist(), cnt.tolist())))
    ts = np.array([f for f, *_ in events]) / rate
    print("intervals between slips (s): median %.2f, min %.2f, max %.2f" % (np.median(np.diff(ts)), np.diff(ts).min(), np.diff(ts).max()))
