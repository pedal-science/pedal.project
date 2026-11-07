# Minimal namchaind TCP client: nc.py <method> [json-args-file|-]  -> prints the reply JSON.
import json, socket, struct, subprocess, sys
def call(s, req):
    b = json.dumps(req).encode(); s.sendall(struct.pack("<I", len(b)) + b)
    n = struct.unpack("<I", s.recv(4, socket.MSG_WAITALL))[0]
    return json.loads(s.recv(n, socket.MSG_WAITALL))
tok = subprocess.run(["security","find-generic-password","-s","namchain.control","-a","token","-w"],
                     capture_output=True, text=True, check=True).stdout.strip()
s = socket.create_connection(("vip", 47810), 5)
h = call(s, {"id":"h","method":"engine.hello","protocol":2,"token":tok}); assert h.get("ok"), h
req = {"id":"1","method":sys.argv[1]}
if len(sys.argv) > 2: req.update(json.load(sys.stdin if sys.argv[2]=="-" else open(sys.argv[2])))
print(json.dumps(call(s, req)))
