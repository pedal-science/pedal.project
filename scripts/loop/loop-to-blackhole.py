import sounddevice as sd, soundfile as sf, numpy as np, sys

file_path = sys.argv[1]

data, sr = sf.read(file_path)
#, dtype="float32")
sd.play(data, sr, device="BlackHole 2ch", blocking=True)
# To truly loop without the tiny gap afplay/sox introduce:
while True:
    sd.play(data, sr, device="BlackHole 2ch")
    sd.wait()

