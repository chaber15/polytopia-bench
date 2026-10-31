import json, sys, collections
L = [json.loads(l) for l in open(sys.argv[1], encoding="utf-8")]
S = [r for r in L if r.get("t") == "turn_start"]
for r in S[::10] + S[-1:]:
    s = r["state"]; me = s["me"]["id"]
    own = collections.Counter(c.get("own") for c in s.get("cities", []))
    print(r["turn"], "opps:", [(o["tribe"], o.get("score")) for o in s.get("opponents", [])], "cities by owner:", dict(own))
txt = [r for r in L if r.get("t") == "tool_call" and ("peace" in json.dumps(r).lower() or "treaty" in json.dumps(r).lower())]
print("peace mentions:", len(txt))
for r in txt[:4]: print(r["turn"], r["tool"], json.dumps(r["args"])[:200])
