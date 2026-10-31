"""Like play.py, but one continuous Claude Code session per game: turn 1 starts it with --session-id,
later turns --resume it, so the model keeps its whole game history (Claude Code auto-compacts if needed).
Prompts, tools and guards are identical to play.py; only memory differs.

Run from harness/:  python -m play_persist --model sonnet --turns 30 --difficulty Hard
"""
import json
import os
import subprocess
import uuid

import play
from gamelog import GameLog


def make_runner():
    session_id = str(uuid.uuid4())
    started = {"v": False}

    def run_claude(prompt, args, turn_dir, timeout):
        mcp = turn_dir / "mcp.json"
        system_prompt = getattr(args, "system_prompt", None) or play.SYSTEM_PROMPT
        session = ["--resume", session_id] if started["v"] else ["--session-id", session_id]
        cmd = [args.claude, "-p", prompt, "--model", args.model, "--effort", args.effort,
               "--system-prompt-file", str(system_prompt), "--mcp-config", str(mcp), "--strict-mcp-config",
               "--tools", "", "--allowedTools", "mcp__poly__*", "--output-format", "json",
               "--disable-slash-commands", *session]
        play.PLAYER_DIR.mkdir(parents=True, exist_ok=True)
        try:
            p = subprocess.run(cmd, cwd=play.PLAYER_DIR, stdin=subprocess.DEVNULL, capture_output=True,
                               env={**os.environ, "CLAUDE_CODE_DISABLE_CLAUDE_MDS": "1"}, text=True,
                               encoding="utf-8", timeout=timeout)
        except subprocess.TimeoutExpired:
            started["v"] = True  # the session may exist even though this turn timed out
            return None, f"claude timed out after {timeout}s"
        (turn_dir / "claude_stdout.json").write_text(p.stdout or "", encoding="utf-8")
        if p.stderr:
            (turn_dir / "claude_stderr.txt").write_text(p.stderr, encoding="utf-8")
        try:
            data = json.loads(p.stdout)
        except ValueError:
            return None, f"claude exit {p.returncode}, stdout not JSON: {(p.stdout or p.stderr)[:300]}"
        started["v"] = True
        if p.returncode != 0 or data.get("is_error"):
            return data, f"claude exit {p.returncode}: {str(data.get('result'))[:300]}"
        return data, None

    return run_claude, session_id


def main(argv=None):
    run, session_id = make_runner()
    play.run_claude = run  # play.play() looks this up at call time
    orig_play = play.play

    def play_with_log(args, bridge=None, log=None):
        log = log or GameLog(f"claude-{args.model}-persist")
        print(f"session: {session_id}", flush=True)
        return orig_play(args, bridge=bridge, log=log)

    play.play = play_with_log
    return play.main(argv)


if __name__ == "__main__":
    main()
