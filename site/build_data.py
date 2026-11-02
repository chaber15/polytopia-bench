"""Build site/data.js from the headline games' logs (harness/logs, gitignored): results, score per turn, final maps.

Run from the repo root:  python3 site/build_data.py
"""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LOGS = ROOT / "harness" / "logs"

# The 10 released models, each with its three headline games (log names, in the order they were played).
# A game that was resumed after an interruption is listed as its last log, which holds the final result.
MODELS = [
    ("Gemini 4 Argon", "Google", "Cursor / OpenRouter", ["20261030-012621-cursor-gemini-4-argon-medium",
     "20261031-145741-openrouter-google-gemini-4-argon", "20261031-165438-openrouter-google-gemini-4-argon"]),
    ("GPT-6 Astra", "OpenAI", "Codex", ["20261029-203934-codex-gpt-6-astra", "20261030-073958-codex-gpt-6-astra",
     "20261030-235034-codex-gpt-6-astra"]),
    ("Claude Opus 5.5", "Anthropic", "Claude Code", ["20261028-171454-claude-opus", "20261028-173726-claude-opus",
     "20261028-175909-claude-opus"]),
    ("GPT-6.1 Sol", "OpenAI", "Codex", ["20261029-210649-codex-gpt-6.1-sol", "20261030-071016-codex-gpt-6.1-sol",
     "20261030-233520-codex-gpt-6.1-sol"]),
    ("Grok 4.7", "xAI", "Cursor", ["20261028-192809-cursor-grok-4.7-medium", "20261031-093402-cursor-grok-4.7-medium",
     "20261031-112405-cursor-grok-4.7-medium"]),
    ("GPT-6.1 Terra", "OpenAI", "Codex", ["20261030-210150-codex-gpt-6.1-terra", "20261030-211512-codex-gpt-6.1-terra",
     "20261030-213149-codex-gpt-6.1-terra"]),
    ("GPT-6 Luna", "OpenAI", "Codex", ["20261029-224005-codex-gpt-6-luna", "20261101-090620-codex-gpt-6-luna",
     "20261101-091827-codex-gpt-6-luna"]),
    ("Claude Haiku 5.5", "Anthropic", "Claude Code", ["20261028-184137-claude-haiku", "20261028-185154-claude-haiku",
     "20261028-185632-claude-haiku"]),
    ("Claude Sonnet 5.5", "Anthropic", "Claude Code", ["20261028-182121-claude-sonnet", "20261028-182539-claude-sonnet",
     "20261028-183706-claude-sonnet"]),
    ("Muse Wonder 1.0", "Meta", "Cursor / OpenRouter", ["20261030-145258-cursor-muse-wonder-1.0-medium",
     "20261031-232240-openrouter-meta-muse-wonder", "20261031-233600-openrouter-meta-muse-wonder"]),
]
# Earlier logs of resumed games: their turns come first in the score-per-turn series.
RESUMED_FROM = {
    "20261030-012621-cursor-gemini-4-argon-medium": ["20261029-172258-cursor-gemini-4-argon-medium",
                                                     "20261029-230554-cursor-gemini-4-argon-medium"],
    "20261031-165438-openrouter-google-gemini-4-argon": ["20261031-163658-openrouter-google-gemini-4-argon"],
    "20261101-090620-codex-gpt-6-luna": ["20261101-011351-codex-gpt-6-luna"],
}
TERRAIN = {"Field": "f", "Forest": "F", "Mountain": "M", "Water": "w", "Ocean": "o"}


def records(name):
    return [json.loads(line) for line in open(LOGS / f"{name}.jsonl", encoding="utf-8")]


def game(name):
    recs = [r for n in RESUMED_FROM.get(name, []) for r in records(n)] + records(name)
    starts = {}
    for r in recs:
        if r.get("t") == "turn_start" and "me" in r["state"]:
            starts[r["state"]["turn"]] = r["state"]  # a resumed turn replaces the earlier copy
    result = next(r["result"] for r in reversed(recs) if r.get("t") == "game_end")
    last = starts[max(starts)]
    me = last["me"]["id"]
    tribes = {s["id"]: s["tribe"] for s in result["scores"]}
    scores = {s["id"]: s["score"] for s in result["scores"]}
    total = sum(scores.values())
    elim = result["turn"] < 30
    place = 3 if elim else 1 + sum(v > scores[me] for k, v in scores.items() if k != me)
    opp_ids = sorted(k for k in scores if k != me)
    # an opponent's score is only known once the model has met that tribe; None before that
    curve = [[t, s["me"]["score"]] + [next((o["score"] for o in s.get("opponents", []) if o["id"] == k), None) for k in opp_ids]
             for t, s in sorted(starts.items())]
    tiles = [[*x["xy"], TERRAIN.get(x["t"], "f"), x.get("own", 0), x.get("imp", ""), 1 if x.get("road") else 0,
              x.get("res", "")] for x in last["map"]["tiles"]]
    cities = [[*c["xy"], c.get("own", 0), c.get("lvl", 1), 1 if c.get("cap") else 0, c.get("name", "")]
              for c in last.get("cities", [])]
    units = [[*u["xy"], u.get("own", 0), u.get("type", "")] for u in last.get("units", [])]
    return {
        "log": name, "me": me, "tribe": tribes[me], "tribes": tribes, "scores": scores,
        "score": scores[me], "share": scores[me] / total, "place": place, "elim": elim, "endTurn": result["turn"],
        "cities": sum(1 for c in last.get("cities", []) if c.get("own") == me),
        "cpusOut": sum(1 for o in last["opponents"] if o.get("out")),
        "opponentOrder": opp_ids, "curve": curve,
        "map": {"w": last["map"]["w"], "h": last["map"]["h"], "turn": last["turn"], "tiles": tiles,
                "cities": cities, "units": units},
    }


def main():
    models = []
    for name, lab, via, logs in MODELS:
        games = [game(g) for g in logs]
        models.append({"model": name, "lab": lab, "via": via, "games": games,
                       "share": sum(g["share"] for g in games) / len(games),
                       "points": sum(g["score"] for g in games) / len(games)})
    models.sort(key=lambda m: -m["share"])
    out = ROOT / "site" / "data.js"
    out.write_text("// Generated by site/build_data.py from the headline games' logs. Do not edit.\n"
                   "window.BENCH = " + json.dumps({"models": models}, separators=(",", ":")) + ";\n", encoding="utf-8")
    for m in models:
        print(f"{m['model']:20} {m['share']:.1%} {m['points']:8,.0f}  " +
              ", ".join(f"{g['place']}{' elim' if g['elim'] else ''} {g['share']:.0%}" for g in m["games"]))
    print(f"{out} {out.stat().st_size // 1024} KB")


if __name__ == "__main__":
    main()
