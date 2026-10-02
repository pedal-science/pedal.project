#!/bin/sh
# run.sh <graph> <input> <seconds> [extra soak args]: one offline run on core 2, SCHED_FIFO 80
g=$1; i=$2; s=$3; shift 3
cd /tmp/tail
sudo -n systemd-run --quiet --scope --slice=pedal-bench.slice chrt -f 80 taskset -c 2 /opt/namchain/current/bin/namchain-soak --graph "$g.json" --seconds "$s" --json "$@" "$i.wav" > "out-$g-$i.json"
python3 - "out-$g-$i.json" "$g" "$i" "$*" <<'PY'
import json,sys
d=json.load(open(sys.argv[1]));b=d['block_ns'];D=d['deadline_ns']
print(f"{sys.argv[2]:10s} {sys.argv[3]:8s} {sys.argv[4]:14s} p50 {100*b['p50']/D:5.1f}%  p99 {100*b['p99']/D:5.1f}%  max {100*b['max']/D:6.1f}%  overruns {d['deadline_overruns']}")
PY
