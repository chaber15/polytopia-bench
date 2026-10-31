"""Replay the logged results of a real game: how big would each act result be in compact mode?"""
import json, re, sys, glob, os
d = sys.argv[1]
strip = lambda l: re.sub(r" \[#\d+\]", "", l)
head = lambda l: l.split(" ")[0] if l.startswith("U") else l.split(":")[0]
tot_old = tot_new = tot_acts = 0
rows = []
for td in sorted(glob.glob(os.path.join(d, "turn??"))):
    f = os.path.join(td, "calls.jsonl")
    if not os.path.exists(f): continue
    calls = [json.loads(l) for l in open(f, encoding="utf-8")]
    st = json.load(open(os.path.join(td, "claude_stdout.json"), encoding="utf-8")) if os.path.exists(os.path.join(td, "claude_stdout.json")) else {}
    shown = None; old = new = n = 0
    for c in calls:
        r = c["result"] if isinstance(c["result"], str) else str(c["result"])
        if c["tool"] != "act" or "Actions now:" not in r:
            continue
        ch, acts = r.split("\n\nActions now:\n", 1)
        lines = [strip(l) for l in acts.splitlines()]
        if shown is None:
            diff = lines  # be conservative: first act shows everything changed
        else:
            o = set(shown); diff = [l for l in lines if l not in o]
            gone = {head(l) for l in shown} - {head(l) for l in lines}
            if gone: diff.append("No actions left for: " + "; ".join(sorted(gone)))
        shown = lines
        n += 1; old += len(r); new += len(ch) + 20 + len("\n".join(diff))
    if n:
        u = st.get("usage", {})
        rows.append((os.path.basename(td), n, old, new, st.get("num_turns"), u.get("cache_read_input_tokens"), u.get("cache_creation_input_tokens"), u.get("output_tokens"), st.get("total_cost_usd")))
        tot_old += old; tot_new += new; tot_acts += n
for r in rows[::5] + rows[-2:]:
    print("%s acts=%d result_chars old=%d new=%d (%.0f%%) api_calls=%s cache_r=%s cache_w=%s out=%s cost=%s" % (r[0], r[1], r[2], r[3], 100*r[3]/r[2], r[4], r[5], r[6], r[7], r[8]))
print("ALL turns: acts=%d result chars old=%d new=%d -> %.0f%% of old" % (tot_acts, tot_old, tot_new, 100*tot_new/tot_old))
json.dump(rows, open(os.path.join(os.path.dirname(sys.argv[0]), "est_rows.json"), "w"))
