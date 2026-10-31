"""Compact mode against the live game: full list, a 2-step batch, then a bad id."""
import sys, tempfile
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "harness"))
from bridge import Bridge
from mcp_poly import PolyTools
b = Bridge("http://localhost:7777")
t = PolyTools(b, tempfile.mkdtemp(), compact=True)
full = t.get_actions(); print("FULL LIST:\n" + full + "\n")
acts = b.actions()["actions"]
mv = next(a for a in acts if a["k"] == "move")
res = next((a for a in acts if a["k"] == "research"), None)
steps = [{"id": mv["id"], "to": mv["to"][0]}] + ([{"id": res["id"]}] if res else [])
print("BATCH", steps); out = t.act_steps(steps); print(out + "\n")
print("BAD ID:", t.act_steps([{"id": 999}])[:300])
print("\nchars: full list %d, batch result %d" % (len(full), len(out)))
