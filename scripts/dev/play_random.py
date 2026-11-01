"""Dev tool: plays random legal actions through the bridge to exercise every action kind. Usage: play_random.py [turns]"""
import json, random, sys, urllib.request
B = "http://localhost:7777"
def call(path, body=None):
    req = urllib.request.Request(B + path, data=None if body is None else json.dumps(body).encode(), method="GET" if body is None else "POST")
    return json.loads(urllib.request.urlopen(req, timeout=300).read())
seen = {}
turns = int(sys.argv[1]) if len(sys.argv) > 1 else 5
for _ in range(turns):
    for _ in range(40):
        a = call("/actions")
        if not a["ok"]: print("actions err", a); sys.exit(1)
        acts = [x for x in a["actions"] if x["k"] != "endTurn"]
        if not acts: break
        pri = [x for x in acts if x["k"] in ("capture", "attack", "unit", "ability")] or acts
        x = random.choice(pri)
        body = {"stateId": a["stateId"], "id": x["id"]}
        if x["k"] == "move": body["to"] = random.choice(x["to"])
        r = call("/act", body)
        key = x["k"] + (":" + x.get("cmd", "") if x["k"] in ("unit", "ability") else "")
        if key not in seen:
            seen[key] = 1; print("NEW", key, json.dumps(x)[:150], "->", json.dumps(r)[:600])
        if not r["ok"]: print("ERR", x, r)
        if r.get("phase") == "game_over": break
    r = call("/end_turn", {})
    print("end_turn", json.dumps(r)[:300])
    if r.get("phase") == "game_over": break
print("kinds seen:", sorted(seen))
