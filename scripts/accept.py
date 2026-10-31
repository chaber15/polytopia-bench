import json, time, urllib.request
def call(base, path, body=None):
    t = time.time()
    req = urllib.request.Request(base + path, data=None if body is None else json.dumps(body).encode(), method="GET" if body is None else "POST")
    with urllib.request.urlopen(req, timeout=180) as r:
        d = json.loads(r.read())
    return d, time.time() - t
for base in ("http://localhost:7777",):
    d, dt = call(base, "/status"); print(f"{base} status {dt*1000:.0f} ms ->", d)
B = "http://localhost:7777"
if call(B, "/status")[0].get("phase") != "menu":
    print("quit", call(B, "/quit", {})[0])
d, dt = call(B, "/newgame", {"difficulty": "Easy"}); print(f"newgame {dt:.1f}s", d)
s, _ = call(B, "/state"); print("state bytes", len(json.dumps(s)), "me", s["me"], "units", s["units"])
a, _ = call(B, "/actions"); print("actions", json.dumps(a)[:700])
mv = next(x for x in a["actions"] if x["k"] == "move")
d, dt = call(B, "/act", {"stateId": a["stateId"], "id": mv["id"], "to": mv["to"][0]}); print(f"act {dt:.1f}s", json.dumps(d)[:400])
d, _ = call(B, "/act", {"stateId": a["stateId"], "id": mv["id"], "to": mv["to"][0]}); print("stale ->", d)
d, dt = call(B, "/end_turn", {}); print(f"end_turn {dt:.1f}s", d)
print("status", call(B, "/status")[0])
