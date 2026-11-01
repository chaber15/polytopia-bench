"""Let a model play a game: one fresh headless session per turn, tools via mcp_poly.py.

Drivers: `claude` (Claude Code, `claude -p`), `cursor` (Cursor's CLI, `agent -p`, any model on the Cursor account),
`codex` (`codex exec`), `antigravity` (Antigravity's ACP server, Gemini models) and `openrouter` (OpenRouter's API
directly, no agent CLI around the model).
Run from harness/:  python -m play --model sonnet --turns 30 --difficulty Easy
                    python -m play --driver cursor --model grok-4.7-medium ...
"""
import argparse
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

from bridge import DEFAULT_URL, Bridge, BridgeError
from gamelog import GameLog, summarize
from render import turn_prompt

HERE = Path(__file__).resolve().parent
SYSTEM_PROMPT = HERE.parent / "prompts" / "system.md"
# empty folder for the player session, outside any git repo: no CLAUDE.md, project files or git status get loaded,
# and Cursor reads .cursor/mcp.json from the git root, so inside this repo it would never see the game's tools
PLAYER_DIR = Path(os.environ.get("POLY_PLAYER_DIR") or Path.home() / "polytopia-player")


COMPACT_ACT = ("- `act(steps)`: do one or more actions in order, e.g. `steps=[{\"id\":3,\"to\":[6,6]},{\"id\":7}]`. "
               "Ids stay fixed for the whole turn (new actions get new ids). `to` only for `move`, chosen from its "
               "destinations. Decide your turn first, then send it in as few `act` calls as you can (each call re-reads everything); "
               "split only where you need to see a result before choosing the next step. A batch stops early at an error or a surprise "
               "(new enemy in view, a unit of yours dies, a forced choice). Result: what each step did, then only the "
               "action lines that changed (`get_actions()` re-prints the full list).")


REFERENCE = HERE.parent / "reference" / "reference.md"   # written by scripts/apply_reference.py from your copy of the game


def system_prompt_file(src, dst, compact=False, reference=REFERENCE):
    """The system prompt as the model sees it: {{REFERENCE}} replaced by the game reference, and in compact
    mode the `act` bullet rewritten."""
    text = Path(src).read_text(encoding="utf-8")
    if "{{REFERENCE}}" in text:
        if not Path(reference).exists():
            raise SystemExit(f"{reference} is missing: generate it from your game with scripts/apply_reference.py (see README)")
        text = text.replace("{{REFERENCE}}", Path(reference).read_text(encoding="utf-8").rstrip("\n"))
    lines = text.splitlines()
    if compact:
        lines = [COMPACT_ACT if l.startswith("- `act(id, to?)`") else l for l in lines]
    Path(dst).write_text("\n".join(lines) + "\n", encoding="utf-8")
    return dst


def fill_game(path, args, state, status):
    """Pass & Play prompt: describe this game ({{GAME}}) from what the bridge reports, once our first turn is up."""
    text = Path(path).read_text(encoding="utf-8")
    if "{{GAME}}" not in text:
        return
    m = state.get("map") or {}
    turns = state.get("maxTurns") or status.get("maxTurns")
    if args.mode.lower() == "perfection":
        goal = (f"{turns} turns. Goal: the highest final score at the end of turn {turns} (finishing first is the win)."
                if turns else "Goal: the highest score.")
    else:
        goal = ("no turn limit. Goal: win by eliminating every other player (capture or destroy all their cities); "
                "score does not decide the winner.")
    game = (f"{args.mode} mode, {status.get('players', '?')} players, a {m.get('w', '?')}x{m.get('h', '?')} map, {goal} "
            f"You are player {args.seat} ({state['me'].get('tribe')}).")
    Path(path).write_text(text.replace("{{GAME}}", game), encoding="utf-8")


CORE_TRIBES = ["Xinxi", "Imperius", "Bardur", "Oumaji"]
TRIBES_SHEET = HERE.parent / "reference" / "tribes.md"   # written by reference/gen_reference.py


def pick_tribe(args, log):
    """One short session before the game: the model reads the core tribes' descriptions (as the game's tribe
    picker shows them) and picks one. Falls back to a random core tribe if the answer names none."""
    import random
    sheet = TRIBES_SHEET.read_text(encoding="utf-8")
    sysp = ("You are about to play The Battle of Polytopia through tools: " + args.pick_context +
            " Choose the tribe you will play. Answer with the tribe's name on the first line "
            "(one of: " + ", ".join(CORE_TRIBES) + "), then at most two sentences on why.")
    question = "The four tribes you can choose from:\n" + sheet
    if getattr(args, "driver", "claude") == "cursor":
        cfg = PLAYER_DIR / ".cursor"   # no tools for the pick: no MCP server, no file reads
        cfg.mkdir(parents=True, exist_ok=True)
        (cfg / "mcp.json").write_text('{"mcpServers": {}}', encoding="utf-8")
        (cfg / "cli.json").write_text(json.dumps(CURSOR_PERMISSIONS), encoding="utf-8")
        cmd = [args.cursor, "-p", sysp + " Answer from the text below only; don't use any tools.\n\n" + question,
               "--model", args.model, "--trust", "--workspace", str(PLAYER_DIR), "--output-format", "json"]
    elif getattr(args, "driver", "claude") == "codex":
        cmd = codex_cmd(sysp + " Answer from the text below only; don't use any tools.\n\n" + question, args)
    else:
        cmd = [args.claude, "-p", question, "--model", args.model, "--effort", args.effort,
               "--system-prompt", sysp, "--tools", "", "--strict-mcp-config", "--output-format", "json",
               "--no-session-persistence", "--disable-slash-commands"]
    PLAYER_DIR.mkdir(parents=True, exist_ok=True)
    text, data = "", {}
    try:
        if getattr(args, "driver", "claude") == "antigravity":   # no MCP server: nothing to call
            data, err = agy_session(sysp + " Answer from the text below only; don't use any tools.\n\n" + question, args,
                                    None, 300, PLAYER_DIR / "agy_pick.jsonl")
            if err:
                raise ValueError(err)
        elif getattr(args, "driver", "claude") == "openrouter":   # no tools for the pick
            import openrouter
            data, err = openrouter.session(sysp, question, args, None, 300, PLAYER_DIR / "openrouter_pick.jsonl")
            if err:
                raise ValueError(err)
        else:
            p = subprocess.run(cmd, cwd=PLAYER_DIR, stdin=subprocess.DEVNULL, capture_output=True, text=True, encoding="utf-8",
                               env={**os.environ, "CLAUDE_CODE_DISABLE_CLAUDE_MDS": "1"}, timeout=300)
            data = codex_result(p.stdout) if getattr(args, "driver", "claude") == "codex" else normalize(json.loads(p.stdout))
        text = data.get("result", "") or ""
    except (subprocess.TimeoutExpired, ValueError) as e:
        text = f"(pick failed: {e})"
    first = text.strip().splitlines()[0] if text.strip() else ""
    names = {t.lower(): t for t in CORE_TRIBES} | {"xin-xi": "Xinxi"}
    tribe = next((names[w] for w in sorted(names, key=len, reverse=True) if w in first.lower()), None)
    picked = tribe is not None
    tribe = tribe or random.choice(CORE_TRIBES)
    u = data.get("usage", {})
    log.error(-1, f"tribe pick: {tribe} ({'model chose' if picked else 'random fallback'}): {text[:400]}")
    print(f"tribe pick: {tribe} ({'model chose' if picked else 'random fallback'}); cost ${data.get('total_cost_usd', 0):.3f}, "
          f"in {u.get('input_tokens', 0)} cache_r {u.get('cache_read_input_tokens', 0)} out {u.get('output_tokens', 0)}", flush=True)
    return tribe


def write_mcp_config(path, turn_dir, url, max_calls, max_errors, compact=False, plan_chars=1500):
    cfg = {"mcpServers": {"poly": {
        "command": sys.executable, "args": [str(HERE / "mcp_poly.py")],
        "env": {"POLY_URL": url, "POLY_WORKDIR": str(turn_dir),
                "POLY_MAX_CALLS": str(max_calls), "POLY_MAX_ERRORS": str(max_errors),
                "POLY_COMPACT": "1" if compact else "0", "POLY_PLAN_CHARS": str(plan_chars),
                "PYTHONPATH": str(HERE), "PYTHONIOENCODING": "utf-8"}}}}
    Path(path).write_text(json.dumps(cfg, indent=1), encoding="utf-8")


def run_claude(prompt, args, turn_dir, timeout):
    """One headless session. Returns (parsed final JSON or None, error string or None)."""
    mcp = turn_dir / "mcp.json"; system_prompt = getattr(args, "system_prompt", None) or SYSTEM_PROMPT
    cmd = [args.claude, "-p", prompt, "--model", args.model, "--effort", args.effort,
           "--system-prompt-file", str(system_prompt), "--mcp-config", str(mcp), "--strict-mcp-config",
           "--tools", "", "--allowedTools", "mcp__poly__*", "--output-format", "json",
           "--no-session-persistence", "--disable-slash-commands"]
    PLAYER_DIR.mkdir(parents=True, exist_ok=True)
    try:
        p = subprocess.run(cmd, cwd=PLAYER_DIR, stdin=subprocess.DEVNULL, capture_output=True,
                           env={**os.environ, "CLAUDE_CODE_DISABLE_CLAUDE_MDS": "1"}, text=True, encoding="utf-8", timeout=timeout)
    except subprocess.TimeoutExpired:
        return None, f"claude timed out after {timeout}s"
    (turn_dir / "claude_stdout.json").write_text(p.stdout or "", encoding="utf-8")
    if p.stderr:
        (turn_dir / "claude_stderr.txt").write_text(p.stderr, encoding="utf-8")
    try:
        data = json.loads(p.stdout)
    except ValueError:
        return None, f"claude exit {p.returncode}, stdout not JSON: {(p.stdout or p.stderr)[:300]}"
    if p.returncode != 0 or data.get("is_error"):
        return data, f"claude exit {p.returncode}: {str(data.get('result'))[:300]}"
    return data, None


def normalize(data):
    """Cursor's JSON result -> the Claude Code shape the logger reads (usage keys, cost). Claude output passes through."""
    u = data.get("usage") or {}
    if "inputTokens" in u:
        data = {**data, "usage": {"input_tokens": u.get("inputTokens", 0), "output_tokens": u.get("outputTokens", 0),
                                  "cache_read_input_tokens": u.get("cacheReadTokens", 0),
                                  "cache_creation_input_tokens": u.get("cacheWriteTokens", 0)},
                "total_cost_usd": data.get("total_cost_usd", 0)}
    return data


CURSOR_PERMISSIONS = {"permissions": {"allow": ["Mcp(poly:*)"], "deny": ["Shell(*)", "Write(**)", "Read(**)", "WebFetch(*)"]}}
# Cursor's agent has its own file/web tools; each extra call re-sends its ~45k-token context, so say up front there is nothing to look up.
CURSOR_NOTE = ("Your only tools are the game's (`act`, `get_actions`, `end_turn`, ...), already listed: don't inspect tool "
               "definitions, read files or search; everything you need is in this prompt and the tool results.")


def cursor_result(stdout):
    """The final `result` event of a stream-json (or plain json) Cursor run."""
    for line in reversed(stdout.strip().splitlines()):
        if line.startswith("{") and json.loads(line).get("type") == "result":
            return json.loads(line)
    raise ValueError("no result event")


def toml(v):
    """A Python value as an inline TOML value, for `codex -c key=value`."""
    if isinstance(v, dict):
        return "{" + ", ".join(f"{k} = {toml(x)}" for k, x in v.items()) + "}"
    if isinstance(v, list):
        return "[" + ", ".join(toml(x) for x in v) + "]"
    return json.dumps(v) if isinstance(v, str) else str(v).lower() if isinstance(v, bool) else str(v)


def codex_cmd(prompt, args, mcp=None):
    """`codex exec` for one session: read-only sandbox, no user config or rules, nothing saved; `mcp` is the poly server
    entry (as write_mcp_config writes it). The model id is Codex's (e.g. gpt-5.6-sol); --effort sets reasoning effort."""
    cmd = [args.codex, "exec", "--json", "--ephemeral", "--skip-git-repo-check", "--ignore-user-config", "--ignore-rules",
           "-s", "read-only", "-C", str(PLAYER_DIR), "-m", args.model,
           "-c", f"model_reasoning_effort={toml(args.effort)}", "-c", 'approval_policy="never"']
    if mcp:
        server = {**mcp, "tool_timeout_sec": 900, "startup_timeout_sec": 60,   # end_turn waits for the CPUs' turns
                  "default_tools_approval_mode": "approve"}           # the game tools run without asking
        cmd += ["-c", f"mcp_servers.poly={toml(server)}"]
    return cmd + [prompt]


def codex_result(stdout):
    """Codex's JSONL events -> the Claude Code result shape: last agent message, usage summed over its turns."""
    text, inp, cached, written, out = "", 0, 0, 0, 0
    for line in stdout.splitlines():
        if not line.startswith("{"):
            continue
        e = json.loads(line)
        item = e.get("item") or {}
        if e.get("type") == "item.completed" and item.get("type") == "agent_message":
            text = item.get("text", "")
        if e.get("type") == "turn.completed":
            u = e.get("usage") or {}
            inp += u.get("input_tokens", 0); cached += u.get("cached_input_tokens", 0); out += u.get("output_tokens", 0)
            written += u.get("cache_write_input_tokens", 0)
        if e.get("type") in ("error", "turn.failed"):
            return {"result": json.dumps(e)[:300], "is_error": True}
    if not (text or inp):
        raise ValueError("no Codex result")
    return {"result": text, "total_cost_usd": 0, "usage": {"input_tokens": inp - cached - written, "output_tokens": out,
            "cache_read_input_tokens": cached, "cache_creation_input_tokens": written}}


def run_codex(prompt, args, turn_dir, timeout):
    """One headless Codex session (`codex exec`, signed in with ChatGPT). Like Cursor, the rules go first in the prompt."""
    system_prompt = Path(getattr(args, "system_prompt", None) or SYSTEM_PROMPT).read_text(encoding="utf-8")
    mcp = json.loads((turn_dir / "mcp.json").read_text(encoding="utf-8"))["mcpServers"]["poly"]
    PLAYER_DIR.mkdir(parents=True, exist_ok=True)
    cmd = codex_cmd(system_prompt + "\n" + CURSOR_NOTE + "\n\n---\n\n" + prompt, args, mcp)
    try:
        p = subprocess.run(cmd, cwd=PLAYER_DIR, stdin=subprocess.DEVNULL, capture_output=True, text=True,
                           encoding="utf-8", timeout=timeout)
    except subprocess.TimeoutExpired:
        return None, f"codex timed out after {timeout}s"
    (turn_dir / "codex_events.jsonl").write_text(p.stdout or "", encoding="utf-8")
    if p.stderr:
        (turn_dir / "claude_stderr.txt").write_text(p.stderr, encoding="utf-8")
    try:
        data = codex_result(p.stdout or "")
    except ValueError:
        return None, f"codex exit {p.returncode}, no result: {(p.stdout or p.stderr)[-300:]}"
    if p.returncode != 0 or data.get("is_error"):
        return data, f"codex exit {p.returncode}: {str(data.get('result'))[:300]}"
    return data, None


def run_cursor(prompt, args, turn_dir, timeout):
    """One headless Cursor session (`agent -p`). Cursor has no system-prompt flag, so the rules go first in the prompt.
    Its workspace config allows only the game's MCP tools and denies shell commands and file writes."""
    system_prompt = Path(getattr(args, "system_prompt", None) or SYSTEM_PROMPT).read_text(encoding="utf-8")
    cfg_dir = PLAYER_DIR / ".cursor"
    cfg_dir.mkdir(parents=True, exist_ok=True)
    (cfg_dir / "mcp.json").write_text((turn_dir / "mcp.json").read_text(encoding="utf-8"), encoding="utf-8")
    (cfg_dir / "cli.json").write_text(json.dumps(CURSOR_PERMISSIONS), encoding="utf-8")
    cmd = [args.cursor, "-p", system_prompt + "\n" + CURSOR_NOTE + "\n\n---\n\n" + prompt, "--model", args.model,
           "--approve-mcps", "--trust", "--workspace", str(PLAYER_DIR), "--output-format", "stream-json"]
    try:
        p = subprocess.run(cmd, cwd=PLAYER_DIR, stdin=subprocess.DEVNULL, capture_output=True, text=True,
                           encoding="utf-8", timeout=timeout)
    except subprocess.TimeoutExpired:
        return None, f"cursor timed out after {timeout}s"
    (turn_dir / "cursor_stream.jsonl").write_text(p.stdout or "", encoding="utf-8")   # every event, built-in tool calls too
    if p.stderr:
        (turn_dir / "claude_stderr.txt").write_text(p.stderr, encoding="utf-8")
    try:
        data = normalize(cursor_result(p.stdout))
    except (ValueError, IndexError):
        return None, f"cursor exit {p.returncode}, stdout not JSON: {(p.stdout or p.stderr)[-300:]}"
    if p.returncode != 0 or data.get("is_error"):
        return data, f"cursor exit {p.returncode}: {str(data.get('result'))[:300]}"
    return data, None


# Antigravity has no one-shot CLI; it speaks ACP (Agent Client Protocol: JSON-RPC over stdio). Its server binary comes
# with T3 Code. GEMINI_HOME holds the login (antigravity-acp/acp_token.json); scripts/agy-home.sh copies T3's into it.
AGY_HOME = Path(os.environ.get("POLY_AGY_HOME") or Path.home() / ".polytopia-agy")


AGY_LIMIT = re.compile(r"usage limit reached|reached your current quota", re.I)


def agy_exe(args):
    if getattr(args, "agy", None):
        return args.agy
    found = sorted(Path.home().glob(".t3/tools/antigravity-acp/*/versions/*/agy_acp_server.par"), key=lambda p: p.stat().st_mtime)
    if not found:
        raise SystemExit("Antigravity ACP server not found: pass --agy <path to agy_acp_server.par>")
    return str(found[-1])


def agy_session(prompt, args, mcp, timeout, transcript):
    """One Antigravity session: start the ACP server, open a session with the poly MCP server (`mcp`, or none),
    set model and thinking level (--effort), send one prompt, read until it stops. Only poly tools are allowed;
    Antigravity's own tools (shell, edits, browser) are denied when it asks; file reads don't ask and are only logged. Returns (Claude-shaped result, error)."""
    import queue
    import threading
    if not (AGY_HOME / "antigravity-acp" / "acp_token.json").exists():
        raise SystemExit(f"no Antigravity login in {AGY_HOME}: run scripts/agy-home.sh")
    PLAYER_DIR.mkdir(parents=True, exist_ok=True)
    p = subprocess.Popen([agy_exe(args)], cwd=PLAYER_DIR, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                         stderr=open(Path(transcript).with_suffix(".stderr.txt"), "w", encoding="utf-8"), text=True,
                         encoding="utf-8", env={**os.environ, "GEMINI_HOME": str(AGY_HOME), "AGY_ACP_FORCE_FILE_STORAGE": "1"})
    lines = queue.Queue()
    threading.Thread(target=lambda: [lines.put(l) for l in p.stdout] + [lines.put(None)], daemon=True).start()
    deadline = time.time() + timeout
    text, used, calls, denied, builtin = [], 0, 0, [], []
    with open(transcript, "w", encoding="utf-8") as tr:
        def send(msg):
            tr.write(">> " + json.dumps(msg) + "\n")
            p.stdin.write(json.dumps(msg) + "\n"); p.stdin.flush()

        def call(rid, method, params):
            nonlocal used, calls
            send({"jsonrpc": "2.0", "id": rid, "method": method, "params": params})
            while True:
                try:
                    line = lines.get(timeout=max(1, deadline - time.time()))
                except queue.Empty:
                    raise TimeoutError(f"antigravity timed out after {timeout}s")
                if line is None:
                    raise ConnectionError(f"antigravity server exited ({p.poll()})")
                tr.write(line); tr.flush()
                m = json.loads(line)
                if m.get("method") == "session/request_permission":
                    tc = m["params"]["toolCall"]
                    ok = ((tc.get("_meta") or {}).get("mcp") or {}).get("server") == "poly"
                    if not ok:
                        denied.append(tc.get("title", "?"))
                    kinds = ("allow_once",) if ok else ("reject_once", "reject_always")
                    opt = next(o["optionId"] for o in m["params"]["options"] if o["kind"] in kinds)
                    send({"jsonrpc": "2.0", "id": m["id"], "result": {"outcome": {"outcome": "selected", "optionId": opt}}})
                elif "method" in m and "id" in m:   # fs/terminal requests: this client offers neither
                    send({"jsonrpc": "2.0", "id": m["id"], "error": {"code": -32601, "message": "not supported"}})
                elif m.get("method") == "session/update":
                    u = m["params"]["update"]
                    kind = u.get("sessionUpdate")
                    if kind == "agent_message_chunk" and (u.get("content") or {}).get("type") == "text":
                        text.append(u["content"]["text"])
                    elif kind == "usage_update":
                        used = u.get("used", used)
                    elif kind == "tool_call":
                        calls += 1
                        if ((u.get("_meta") or {}).get("mcp") or {}).get("server") != "poly":
                            builtin.append(u.get("title", "?"))
                elif m.get("id") == rid:
                    if "error" in m:
                        raise RuntimeError(f"{method}: {json.dumps(m['error'])[:300]}")
                    return m["result"]

        started = time.time()
        try:
            call(1, "initialize", {"protocolVersion": 1, "clientCapabilities": {"fs": {"readTextFile": False, "writeTextFile": False},
                                                                                "terminal": False}})
            servers = [] if mcp is None else [{"name": "poly", "command": mcp["command"], "args": mcp["args"],
                                               "env": [{"name": k, "value": v} for k, v in mcp["env"].items()]}]
            sess = call(2, "session/new", {"cwd": str(PLAYER_DIR), "mcpServers": servers})
            sid = sess["sessionId"]
            opts = {o["id"]: o for o in sess.get("configOptions", [])}
            for rid, (cid, value) in enumerate([("model", args.model), ("thinking_level", args.effort)], start=3):
                o = opts.get(cid)
                if o is None or value not in [x["value"] for x in o["options"]]:
                    raise RuntimeError(f"Antigravity {cid} {value!r} not available; options: "
                                       f"{[x['value'] for x in (o or {}).get('options', [])]}")
                if o["currentValue"] != value:
                    call(rid, "session/set_config_option", {"sessionId": sid, "configId": cid, "value": value})
            res = call(5, "session/prompt", {"sessionId": sid, "prompt": [{"type": "text", "text": prompt}]})
            err = None if res.get("stopReason") == "end_turn" else f"antigravity stopped: {res.get('stopReason')}"
            if AGY_LIMIT.search("".join(text)):   # Antigravity reports an exhausted quota as an ordinary reply
                err = "antigravity usage limit: " + "".join(text)[:200]
        except (TimeoutError, ConnectionError, RuntimeError, ValueError) as e:
            err = str(e)
        finally:
            p.kill()
    # Antigravity's own tools: reads run without asking (it reads the poly tool schemas it saved), the rest are denied
    if builtin:
        text.append(f"\n[Antigravity built-in tools: {'; '.join(builtin)}" + (f" (denied: {'; '.join(denied)})" if denied else "") + "]")
    # ACP reports only the context size; it goes in input_tokens (no cost or output count from Antigravity)
    data = {"result": "".join(text), "total_cost_usd": 0, "num_turns": calls, "duration_ms": int((time.time() - started) * 1000),
            "usage": {"input_tokens": used, "output_tokens": 0, "cache_read_input_tokens": 0, "cache_creation_input_tokens": 0}}
    return data, err


def run_antigravity(prompt, args, turn_dir, timeout):
    """One Antigravity session (Gemini models, signed in with Google). Like Cursor, the rules go first in the prompt."""
    system_prompt = Path(getattr(args, "system_prompt", None) or SYSTEM_PROMPT).read_text(encoding="utf-8")
    mcp = json.loads((turn_dir / "mcp.json").read_text(encoding="utf-8"))["mcpServers"]["poly"]
    return agy_session(system_prompt + "\n" + CURSOR_NOTE + "\n\n---\n\n" + prompt, args, mcp, timeout,
                       turn_dir / "agy_acp.jsonl")


def run_openrouter(prompt, args, turn_dir, timeout):
    """One session straight against OpenRouter's API: the rules as the system message, nothing else around the model."""
    import openrouter
    system_prompt = Path(getattr(args, "system_prompt", None) or SYSTEM_PROMPT).read_text(encoding="utf-8")
    mcp = json.loads((turn_dir / "mcp.json").read_text(encoding="utf-8"))["mcpServers"]["poly"]
    return openrouter.session(system_prompt, prompt, args, mcp, timeout, turn_dir / "openrouter.jsonl")


def log_session(log, turn, data, turn_dir):
    u = (data or {}).get("usage", {})
    log.model(turn, text=(data or {}).get("result", "") or "",
              prompt_tokens=u.get("input_tokens", 0), output_tokens=u.get("output_tokens", 0),
              cache_read_tokens=u.get("cache_read_input_tokens", 0),
              cache_creation_tokens=u.get("cache_creation_input_tokens", 0),
              cost_usd=(data or {}).get("total_cost_usd", 0), num_turns=(data or {}).get("num_turns", 0),
              duration_ms=(data or {}).get("duration_ms", 0))
    calls = turn_dir / "calls.jsonl"
    if calls.exists():
        for line in calls.read_text(encoding="utf-8").splitlines():
            c = json.loads(line)
            log.tool_call(turn, c["tool"], c["args"], c["result"], c["error"])
            if c["tool"] == "act" and not c["error"]:
                log.action(turn, {"k": c["args"].get("k", "?"), **c["args"]}, c["result"])


def play(args, bridge=None, log=None):
    bridge = bridge or Bridge(args.url)
    log = log or GameLog(f"{getattr(args, 'driver', 'claude')}-{args.model.replace('/', '-')}")   # OpenRouter ids have a /
    out_dir = Path(args.out) if args.out else HERE / "logs" / (log.path.stem + "-turns")
    started = time.time()
    plan = ""
    out_dir.mkdir(parents=True, exist_ok=True)
    compact = getattr(args, "compact", False)
    args.system_prompt = system_prompt_file(args.system_prompt or SYSTEM_PROMPT,
                                            out_dir / ("system-compact.md" if compact else "system.md"), compact)
    events = []
    if getattr(args, "plan_file", None):
        plan = Path(args.plan_file).read_text(encoding="utf-8")
    seat = getattr(args, "seat", 0)
    if seat:
        # Pass & Play: the humans started the game; play only our seat and wait as long as they take
        bridge.seat(seat, getattr(args, "start_delay", None))
        print(f"pass & play: playing seat {seat}", flush=True)
    if seat and bridge.status()["phase"] == "menu":
        print("waiting for the Pass & Play game to start in Polytopia", flush=True)
        while bridge.status()["phase"] in ("menu", "loading"):
            time.sleep(3)
    if bridge.status()["phase"] == "menu" and getattr(args, "resume", False):
        print("resume:", json.dumps(bridge.resume()), flush=True)
    elif bridge.status()["phase"] == "menu":
        opts = dict(mode=args.mode, difficulty=args.difficulty, tribe=args.tribe, opponents=args.opponents, mapSize=args.map_size)
        if getattr(args, "choose_tribe", False):
            opts["tribe"] = pick_tribe(args, log)
            opts["opponentTribes"] = [t for t in CORE_TRIBES if t != opts["tribe"]]   # the CPUs are drawn from these
        if getattr(args, "opponent_tribes", None):
            opts["opponentTribes"] = args.opponent_tribes.split(",")
        if getattr(args, "map_preset", None):
            opts["mapPreset"] = args.map_preset
        bridge.newgame(**opts)
        print("newgame:", json.dumps(opts), flush=True)
    print(f"log: {log.path}", flush=True)
    played = 0
    while played < args.turns:
        status, state, actions = (bridge.turn_view(stuck_s=6 * 3600, recoveries=0) if seat else bridge.turn_view())
        if status["phase"] == "game_over":
            break
        if getattr(args, "until_turn", 0) and status.get("turn", 0) >= args.until_turn:
            print(f"reached turn {status.get('turn')} (--until-turn)", flush=True)
            break
        if time.time() - started > args.max_minutes * 60:
            log.error(status.get("turn", -1), "wall-clock limit reached")
            print("wall-clock limit reached", flush=True)
            break
        if state is None:
            log.error(status.get("turn", -1), f"game not on our turn (phase {status['phase']})")
            print(f"stopping: game not on our turn (phase {status['phase']})", flush=True)
            break
        turn = state["turn"]
        if seat:
            fill_game(args.system_prompt, args, state, status)
        log.turn_start(turn, state)
        prompt = turn_prompt(state, actions, turn, state.get("maxTurns", args.turns), plan, events)
        log.prompt(turn, prompt)
        data, err = None, None
        for attempt in range(2):  # a turn is retried at most once
            turn_dir = out_dir / f"turn{turn:02d}{'' if attempt == 0 else 'b'}"
            turn_dir.mkdir(parents=True, exist_ok=True)
            write_mcp_config(turn_dir / "mcp.json", turn_dir, args.url, args.max_calls, args.max_errors,
                             getattr(args, "compact", False), getattr(args, "plan_chars", 1500))
            if attempt:  # state may have changed in the failed attempt
                _, state, actions = bridge.turn_view(recoveries=0) if seat else bridge.turn_view()
                if state is None:
                    break
                prompt = turn_prompt(state, actions, turn, state.get("maxTurns", args.turns), plan, events)
            data, err = {"cursor": run_cursor, "codex": run_codex, "antigravity": run_antigravity,
                         "openrouter": run_openrouter}.get(getattr(args, "driver", "claude"), run_claude)(
                prompt, args, turn_dir, args.turn_timeout)
            log_session(log, turn, data, turn_dir)
            if err:
                log.error(turn, err)
                print(f"turn {turn}: {err}", flush=True)
            if (turn_dir / "end_turn.json").exists():
                break
            if not err:
                break  # session finished cleanly without end_turn: force below
        ended = turn_dir / "end_turn.json"
        if err and not ended.exists():
            # The session failed (outage, provider error, timeout): never end the turn for the model, or it loses the
            # turn and the CPUs get a free one. Stop here instead; the game stays on this turn and --resume continues it.
            log.error(turn, "session failed twice; stopping without ending the turn (resume with --resume)")
            print(f"stopped at turn {turn}: session failed twice, turn left open for --resume", flush=True)
            break
        if ended.exists():
            res = json.loads(ended.read_text(encoding="utf-8"))
        else:
            log.error(turn, "model did not call end_turn; ending it from play.py")
            try:
                if bridge.wait_ready()["phase"] != "my_turn":  # the session's end_turn may still be finishing
                    raise BridgeError("game not on our turn after waiting")
                for opt in bridge.resolve_forced():
                    log.error(turn, f"harness picked forced choice for the model: {opt}")
                res = bridge.end_turn()
            except BridgeError as e:
                log.error(turn, f"end_turn failed: {e}")
                break
        events = res.get("events", [])
        planf = turn_dir / "plan.txt"
        if planf.exists():
            plan = planf.read_text(encoding="utf-8")
        played += 1
        u = (data or {}).get("usage", {})
        print(f"turn {turn} done: cost ${(data or {}).get('total_cost_usd', 0):.3f}, "
              f"in {u.get('input_tokens', 0)} cache_r {u.get('cache_read_input_tokens', 0)} "
              f"cache_w {u.get('cache_creation_input_tokens', 0)} out {u.get('output_tokens', 0)}", flush=True)
    if bridge.status()["phase"] == "game_over":
        result = bridge.result()
        log.game_end(result)
        print("result:", json.dumps(result), flush=True)
    log.close()
    summarize(log.path)
    return log.path


def main(argv=None):
    p = argparse.ArgumentParser(description="Claude plays Polytopia via claude -p, one session per turn.")
    p.add_argument("--model", default="sonnet")
    p.add_argument("--turns", type=int, default=30, help="stop after this many turns played")
    p.add_argument("--difficulty", default="Easy")
    p.add_argument("--mode", default="Perfection", help="Perfection or Domination")
    p.add_argument("--system-prompt", help="system prompt file (default prompts/system.md)")
    p.add_argument("--opponents", type=int, default=1)
    p.add_argument("--map-size", type=int, default=11, help="map width: 11 Tiny, 14 Small, 16 Normal, 18 Large")
    p.add_argument("--tribe", default="Bardur", help="regular tribe; the rules sheet covers the standard tech tree")
    p.add_argument("--effort", default="medium")
    p.add_argument("--url", default=DEFAULT_URL)
    p.add_argument("--claude", default="claude")
    p.add_argument("--driver", default="claude", choices=["claude", "cursor", "codex", "antigravity", "openrouter"],
                   help="claude: Claude Code (claude -p); cursor: Cursor's CLI (agent -p), --model is a Cursor model id; "
                        "codex: OpenAI's Codex CLI (codex exec), --model is a Codex model id and --effort its reasoning effort; "
                        "antigravity: Antigravity's ACP server, --model e.g. gemini-3.8-flash and --effort its thinking level; "
                        "openrouter: OpenRouter's API directly (OPENROUTER_API_KEY), --model e.g. google/gemini-4-argon, "
                        "--effort its reasoning effort")
    p.add_argument("--cursor", default="agent", help="Cursor CLI command")
    p.add_argument("--codex", default="codex", help="Codex CLI command")
    p.add_argument("--agy", help="Antigravity ACP server (default: the newest one T3 Code installed)")
    p.add_argument("--max-calls", type=int, default=40)
    p.add_argument("--max-errors", type=int, default=3)
    p.add_argument("--turn-timeout", type=int, default=600, help="seconds per claude session")
    p.add_argument("--max-minutes", type=int, default=150, help="overall wall-clock limit")
    p.add_argument("--out", help="folder for per-turn files (default harness/logs/<log>-turns)")
    p.add_argument("--map-preset", help="Dryland, Lakes, Continents, Archipelago, WaterWorld or Pangea")
    p.add_argument("--opponent-tribes", help="comma list the CPU tribes are drawn from, e.g. Imperius,Oumaji")
    p.add_argument("--choose-tribe", action="store_true",
                   help="the model picks one of the four core tribes before the game; the CPUs are drawn from the other three")
    p.add_argument("--pick-context", default="Perfection mode, 30 turns, a Small 14x14 Lakes map, you vs 2 Hard CPU tribes; "
                   "the goal is the highest score at the end of turn 30.", help="game description shown when picking a tribe")
    p.add_argument("--plan-chars", type=int, default=1500, help="longest plan/notes carried to the next turn")
    p.add_argument("--seat", type=int, default=0,
                   help="Pass & Play: join the game already started in Polytopia and play only this seat (player number)")
    p.add_argument("--start-delay", type=float,
                   help="Pass & Play: seconds the model's \"Next up\" screen stays up before it presses START (default 3)")
    p.add_argument("--resume", action="store_true", help="from the menu, continue the single-player autosave")
    p.add_argument("--plan-file", help="plan text to show on the first turn (e.g. the last plan before a resume)")
    p.add_argument("--until-turn", type=int, default=0, help="stop once the game reaches this turn number")
    p.add_argument("--compact", action="store_true",
                   help="batched act with turn-stable ids and diff-only results (fewer, smaller tool calls)")
    p.add_argument("--quit-at-end", action="store_true", help="POST /quit when finished")
    args = p.parse_args(argv)
    path = play(args)
    if args.quit_at_end:
        Bridge(args.url).quit()
    return path


if __name__ == "__main__":
    main()
