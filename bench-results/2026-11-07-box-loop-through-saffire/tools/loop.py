# Run on piv: play a stimulus out of the Saffire's output 2 and record both inputs, then analyse.
# usage: python3 loop.py <name> [level_dbfs]   -> writes <name>.out.raw, <name>.in.raw, prints JSON
import json, subprocess, sys, time, numpy as np
FS, DEV = 48000, "hw:CARD=USB,DEV=0"
name = sys.argv[1]; lvl = float(sys.argv[2]) if len(sys.argv) > 2 else -20.0
a = 10 ** (lvl / 20)
def sil(s): return np.zeros(int(s * FS))
t = np.arange(int(2.0 * FS)) / FS
tone = a * np.sin(2 * np.pi * 1000 * t); tone[:480] *= np.linspace(0, 1, 480); tone[-480:] *= np.linspace(1, 0, 480)
T, f0, f1 = 4.0, 20.0, 20000.0
ts = np.arange(int(T * FS)) / FS; K = T / np.log(f1 / f0)
sweep = a * np.sin(2 * np.pi * f0 * K * (np.exp(ts / K) - 1)); sweep[:240] *= np.linspace(0, 1, 240); sweep[-240:] *= np.linspace(1, 0, 240)
segs = [("lead", sil(1.0)), ("tone", tone), ("gap", sil(0.5)), ("sweep", sweep), ("quiet", sil(1.5))]
mono = np.concatenate([s for _, s in segs]); starts = {}; p = 0
for n, s in segs: starts[n] = (p, p + len(s)); p += len(s)
out = np.zeros((len(mono), 4)); out[:, 1] = mono            # output 2
def s24(x):
    v = np.clip(np.round(x * 8388607), -8388608, 8388607).astype("<i4")
    return v.view(np.uint8).reshape(-1, 4)[:, :3].tobytes()
open(f"{name}.out.raw", "wb").write(s24(out.reshape(-1)))
dur = len(mono) / FS + 0.5
rec = subprocess.Popen(["arecord", "-q", "-D", DEV, "-f", "S24_3LE", "-r", str(FS), "-c", "2", "-t", "raw",
                        "-d", str(int(np.ceil(dur)) + 1), f"{name}.in.raw"])
time.sleep(0.3)
subprocess.run(["aplay", "-q", "-D", DEV, "-f", "S24_3LE", "-r", str(FS), "-c", "4", "-t", "raw", f"{name}.out.raw"], check=True)
rec.wait()
b = np.frombuffer(open(f"{name}.in.raw", "rb").read(), np.uint8).reshape(-1, 3)
v = (b[:, 0].astype(np.int32) | b[:, 1].astype(np.int32) << 8 | b[:, 2].astype(np.int32) << 16)
v = np.where(v & 0x800000, v - 0x1000000, v) / 8388608.0
x = v[: len(v) // 2 * 2].reshape(-1, 2)
db = lambda r: round(20 * np.log10(max(r, 1e-10)), 1)
res = {"name": name, "stim_dbfs_peak": lvl, "channels": []}
# latency from the sweep, on the louder channel
for c in range(2):
    y = x[:, c]; n = 1 << int(np.ceil(np.log2(len(y) + len(mono))))
    xc = np.fft.irfft(np.fft.rfft(y, n) * np.conj(np.fft.rfft(mono, n)), n)
    lag = int(np.argmax(np.abs(xc[: len(y)]))); al = lambda seg: y[starts[seg][0] + lag: starts[seg][1] + lag]
    ch = {"input": c + 1, "lag_samples": lag, "lag_ms": round(lag / FS * 1000, 2),
          "peak_dbfs": db(np.max(np.abs(y))), "noise_rms_dbfs": db(np.sqrt(np.mean(al("quiet")[int(0.3*FS):] ** 2)))}
    seg = al("tone")[int(0.5 * FS): int(1.5 * FS)]
    if len(seg) == FS:
        w = np.hanning(len(seg)); S = np.abs(np.fft.rfft(seg * w)) ** 2; f = np.fft.rfftfreq(len(seg), 1 / FS)
        fund = S[(f > 990) & (f < 1010)].sum(); band = S[(f > 20) & (f < 20000)].sum()
        harm = [db(np.sqrt(S[(f > k*1000-10) & (f < k*1000+10)].sum() / max(fund, 1e-30))) for k in range(2, 6)]
        ch.update({"tone_rms_dbfs": db(np.sqrt(np.mean(seg ** 2))), "gain_db": round(db(np.sqrt(np.mean(seg ** 2))) - (lvl - 3.01), 1),
                   "thdn_db": db(np.sqrt(max(band - fund, 1e-30) / max(fund, 1e-30))), "harmonics_db_h2_h5": harm})
        sw = al("sweep")
        if len(sw) == len(sweep):
            Y = np.abs(np.fft.rfft(sw)); X = np.abs(np.fft.rfft(sweep)); fr = np.fft.rfftfreq(len(sw), 1 / FS)
            def at(fq):
                m = (fr > fq / 1.06) & (fr < fq * 1.06); return 20 * np.log10(Y[m].mean() / X[m].mean())
            ref = at(1000)
            ch["response_db_rel_1k"] = {str(fq): round(at(fq) - ref, 1) for fq in (40, 100, 250, 3000, 6000, 10000, 15000, 18000)}
    res["channels"].append(ch)
print(json.dumps(res))
