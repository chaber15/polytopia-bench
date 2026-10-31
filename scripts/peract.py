import json, glob, os, sys
for d in sys.argv[1:]:
    acts = calls = 0; cost = 0.0
    for td in sorted(glob.glob(os.path.join(d, "turn*"))):
        f = os.path.join(td, "calls.jsonl")
        if os.path.exists(f):
            for l in open(f, encoding="utf-8"):
                c = json.loads(l); calls += 1
                if c["tool"] == "act" and not c["error"]:
                    acts += len(c["args"].get("steps", [])) or 1
        s = os.path.join(td, "claude_stdout.json")
        if os.path.exists(s):
            try: cost += json.load(open(s, encoding="utf-8")).get("total_cost_usd", 0)
            except Exception: pass
    print("%s: actions=%d tool_calls=%d cost=$%.2f  $/action=%.4f  actions/call=%.1f" % (os.path.basename(d), acts, calls, cost, cost / max(acts, 1), acts / max(calls, 1)))
