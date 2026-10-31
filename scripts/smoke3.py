import json, time, urllib.request
B = "http://localhost:7777"
def call(path, body=None):
    req = urllib.request.Request(B + path, data=None if body is None else json.dumps(body).encode(), method="GET" if body is None else "POST")
    with urllib.request.urlopen(req, timeout=180) as r: return json.loads(r.read())
t = time.time(); print("newgame", call("/newgame", {"mode": "Domination", "difficulty": "Normal", "opponents": 3, "mapSize": 16, "tribe": "Bardur"}), f"{time.time()-t:.1f}s")
s = call("/state"); print("map", s["map"]["w"], s["map"]["h"], "explored", len(s["map"]["tiles"]), "maxTurns", s.get("maxTurns"), "opponents", s.get("opponents"), "bytes", len(json.dumps(s)))
for i in range(3):
    t = time.time(); r = call("/end_turn", {}); print("end_turn", r.get("phase"), r.get("turn"), f"{time.time()-t:.1f}s", r.get("events", [])[:3])
print("quit", call("/quit", {}))
