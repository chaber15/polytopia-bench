import json, sys
L = [json.loads(l) for l in open(sys.argv[1], encoding="utf-8")]
ts = [r for r in L if r["t"] == "turn_start"]
for r in ts[::5] + [ts[-1]]:
    s = r["state"]; me = s["me"]
    mine = [c for c in s.get("cities", []) if c.get("own") == 1]
    u = [x for x in s.get("units", []) if x.get("own") == 1]
    print(r["turn"], "stars", me["stars"], "inc", me.get("income"), "score", me["score"], "cities", len(mine),
          [c.get("lvl") for c in mine], "units", len(u), "explored", len(s["map"]["tiles"]), "techs", len(me["techs"]))
calls = [r for r in L if r["t"] == "tool_call"]
print("tool_call keys:", list(calls[0].keys()) if calls else None)
ends = [r for r in calls if "end_turn" in json.dumps(r)[:200]]
for p in ends[0:30:10] + ends[-1:]:
    print("PLAN", json.dumps(p)[:500])
