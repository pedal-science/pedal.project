#!/bin/sh
# Play SECS of a namchaind recording's output to the SSL with aplay, record every input with arecord
# (namchaind stopped), and capture the USB traffic with usbmon for wire.py. Run as root on the
# Core host: BUS=<usbmon bus> SECS=60 SRC=<recording>/playback.wav sh wire-test.sh. Leaves the
# files in /dev/shm/wire-test for wire.py; delete them after.
set -e
D=/dev/shm/wire-test
BUS=${BUS:-2}
SECS=${SECS:-60}
SRC=${SRC:-/var/lib/namchain/recordings/pops-empty-rig-2/playback.wav}
rm -rf $D; mkdir -p $D
python3 - "$SRC" "$D/playback.wav" "$SECS" <<'PY'
import struct, sys
import numpy as np
src = np.memmap(sys.argv[1], dtype="<i4", mode="r", offset=44).reshape(-1, 6)
start = int(np.flatnonzero(np.abs(src[:, 0]) > 2**24)[0]) - 48000
x = np.ascontiguousarray(src[start:start + 48000 * int(sys.argv[3])])
hdr = open(sys.argv[1], "rb").read(44)
hdr = hdr[:4] + struct.pack("<I", 36 + x.nbytes) + hdr[8:40] + struct.pack("<I", x.nbytes)
with open(sys.argv[2], "wb") as f:
    f.write(hdr); f.write(x.tobytes())
PY
modprobe usbmon
systemctl stop namchaind
sleep 1
tcpdump -q -i usbmon$BUS -s 0 -B 262144 -w $D/usb.pcap 2> $D/tcpdump.err &
TP=$!
sleep 1
chrt -f 80 arecord -q -D hw:CARD=II,DEV=0 -c 8 -f S32_LE -r 48000 --period-size=64 --buffer-size=48000 -d $((SECS + 3)) $D/capture.wav &
sleep 0.3
chrt -f 80 aplay -q -D hw:CARD=II,DEV=0 --period-size=64 --buffer-size=384 $D/playback.wav
wait %2 2>/dev/null || true
sleep 3
kill -INT $TP; wait $TP 2>/dev/null || true
systemctl start namchaind
cat $D/tcpdump.err
ls -l $D
