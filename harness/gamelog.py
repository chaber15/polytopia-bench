"""JSONL game log: one file per game in harness/logs/<timestamp>-<agent>.jsonl.

Records (one JSON object per line, "t" is the type):
  turn_start  turn, state            (full /state at the start of each turn)
  action      turn, action, result   (action as sent, plus the /act answer)
  model       turn, prompt_tokens, output_tokens, cache_read_tokens, text
  error       turn, message, ...
  game_end    result                 (the /result answer)

Run `python gamelog.py summarize <file>` for a text summary.
"""
import argparse
import json
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path

LOG_DIR = Path(__file__).resolve().parent / "logs"
TOKEN_KEYS = ("prompt_tokens", "output_tokens", "cache_read_tokens")
EXTRA_KEYS = ("cache_creation_tokens", "cost_usd", "duration_ms", "num_turns")


class GameLog:
    def __init__(self, agent, log_dir=None):
        folder = Path(log_dir) if log_dir else LOG_DIR
        folder.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        path = folder / f"{stamp}-{agent}.jsonl"
        n = 2
        while path.exists():  # two games started in the same second
            path = folder / f"{stamp}-{agent}-{n}.jsonl"
            n += 1
        self.path = path
        self._f = path.open("a", encoding="utf-8")

    def write(self, t, **fields):
        self._f.write(json.dumps({"t": t, **fields}, ensure_ascii=False) + "\n")
        self._f.flush()

    def turn_start(self, turn, state):
        self.write("turn_start", turn=turn, state=state)

    def action(self, turn, action, result):
        self.write("action", turn=turn, action=action, result=result)

    def model(self, turn, text="", prompt_tokens=0, output_tokens=0, cache_read_tokens=0, **extra):
        """extra (optional): cache_creation_tokens, cost_usd, num_turns, duration_ms."""
        self.write("model", turn=turn, prompt_tokens=prompt_tokens, output_tokens=output_tokens,
                   cache_read_tokens=cache_read_tokens, text=text, **extra)

    def prompt(self, turn, text):
        self.write("prompt", turn=turn, text=text)

    def tool_call(self, turn, tool, args, result, error=False):
        self.write("tool_call", turn=turn, tool=tool, args=args, result=result, error=error)

    def error(self, turn, message, **extra):
        self.write("error", turn=turn, message=message, **extra)

    def game_end(self, result):
        self.write("game_end", result=result)

    def close(self):
        self._f.close()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()


def read_records(path):
    with Path(path).open(encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def summarize(path, out=None):
    """Print a text summary of a game log and return it as a dict."""
    out = out or sys.stdout
    recs = read_records(path)
    turn_starts = [r for r in recs if r["t"] == "turn_start"]
    actions = [r for r in recs if r["t"] == "action"]
    errors = [r for r in recs if r["t"] == "error"]
    ends = [r for r in recs if r["t"] == "game_end"]
    models = [r for r in recs if r["t"] == "model"]

    last_state = turn_starts[-1]["state"] if turn_starts else {}
    me_id = last_state.get("me", {}).get("id")
    winner, final_score, scores = None, None, []
    if ends:
        result = ends[-1]["result"]
        winner = result.get("winner")
        scores = result.get("scores", [])
        final_score = next((s["score"] for s in scores if s["id"] == me_id), None)
    elif last_state:
        final_score = last_state.get("me", {}).get("score")

    kinds = Counter(r["action"]["k"] for r in actions)
    tokens = {k: sum(r.get(k, 0) for r in models) for k in TOKEN_KEYS}
    summary = {
        "file": str(path),
        "turns": len(turn_starts),
        "actions": len(actions),
        "action_kinds": dict(kinds),
        "errors": len(errors),
        "game_over": bool(ends),
        "winner": winner,
        "final_score": final_score,
        "scores": scores,
        "tokens": tokens,
    }

    lines = [
        f"log:       {Path(path).name}",
        f"turns:     {summary['turns']}" + ("" if summary["game_over"] else " (no game_end record)"),
        f"actions:   {summary['actions']}" + (f" ({', '.join(f'{k} {v}' for k, v in sorted(kinds.items()))})" if kinds else ""),
        f"errors:    {summary['errors']}",
    ]
    for e in errors[:5]:
        lines.append(f"  turn {e['turn']}: {e['message']}")
    lines.append(f"score:     {final_score}" + (f", winner {winner}" if ends else ""))
    if scores:
        lines.append("  " + ", ".join(f"{s['id']} {s.get('tribe', '')}={s['score']}" for s in scores))
    extra = {k: sum(r.get(k, 0) for r in models) for k in EXTRA_KEYS}
    if models and any(extra.values()):
        summary["extra"] = extra
        n = len(models)
        lines.append("           " + ", ".join(f"{k} {round(v, 4)}" for k, v in extra.items()))
        avg = {k: round(v / n) for k, v in {**tokens, **extra}.items() if k != "cost_usd"}
        summary["per_turn"] = {**avg, "cost_usd": round(extra["cost_usd"] / n, 4)}
        lines.append(f"per turn:  " + ", ".join(f"{k} {v}" for k, v in summary["per_turn"].items()))
    lines.append("tokens:    " + ", ".join(f"{k} {v}" for k, v in tokens.items()) + f" ({len(models)} model records)")
    out.write("\n".join(lines) + "\n")
    return summary


def main(argv=None):
    p = argparse.ArgumentParser(description="Summarize a game log.")
    sub = p.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("summarize", help="print turns, actions, errors, score and tokens")
    s.add_argument("path")
    args = p.parse_args(argv)
    if args.cmd == "summarize":
        summarize(args.path)


if __name__ == "__main__":
    main()
