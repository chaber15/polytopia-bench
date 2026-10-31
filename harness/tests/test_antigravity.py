import json
import sys
import types

import play

# A stand-in ACP server: offers one model and three thinking levels, asks permission for a poly tool and a shell
# command, then writes what it was told to stdout's last message and stops.
FAKE_SERVER = r'''
import json, sys
def send(m): print(json.dumps(m), flush=True)
def recv(): return json.loads(sys.stdin.readline())
asked = {}
def ask(i, title, mcp):
    meta = {"mcp": {"server": "poly", "tool": "act"}} if mcp else {}
    send({"jsonrpc": "2.0", "method": "session/update", "params": {"update": {"sessionUpdate": "tool_call", "title": title, "_meta": meta}}})
    send({"jsonrpc": "2.0", "id": i, "method": "session/request_permission", "params": {"toolCall": {"title": title, "_meta": meta},
          "options": [{"optionId": "allow_always", "kind": "allow_always"}, {"optionId": "allow", "kind": "allow_once"},
                      {"optionId": "deny", "kind": "reject_once"}]}})
    asked[title] = recv()["result"]["outcome"]["optionId"]
while True:
    m = recv()
    if m["method"] == "initialize":
        send({"jsonrpc": "2.0", "id": m["id"], "result": {"protocolVersion": 1}})
    elif m["method"] == "session/new":
        send({"jsonrpc": "2.0", "id": m["id"], "result": {"sessionId": "s1", "configOptions": [
            {"id": "model", "currentValue": "gemini-3.8-flash", "options": [{"value": "gemini-3.8-flash"}]},
            {"id": "thinking_level", "currentValue": "high", "options": [{"value": v} for v in ("low", "medium", "high")]}]}})
        servers = m["params"]["mcpServers"]
    elif m["method"] == "session/set_config_option":
        asked["set " + m["params"]["configId"]] = m["params"]["value"]
        send({"jsonrpc": "2.0", "id": m["id"], "result": {}})
    elif m["method"] == "session/prompt":
        ask(90, "poly_act", True); ask(91, "rm -rf /", False)
        send({"jsonrpc": "2.0", "method": "session/update", "params": {"update": {"sessionUpdate": "usage_update", "used": 1234}}})
        asked["servers"] = [s["name"] for s in servers]
        send({"jsonrpc": "2.0", "method": "session/update", "params": {"update": {"sessionUpdate": "agent_message_chunk",
              "content": {"type": "text", "text": json.dumps(asked)}}}})
        send({"jsonrpc": "2.0", "id": m["id"], "result": {"stopReason": "end_turn"}})
'''


def _setup(monkeypatch, tmp_path):
    server = tmp_path / "fake_acp.py"
    server.write_text(FAKE_SERVER)
    launcher = tmp_path / "agy"
    launcher.write_text(f"#!/bin/sh\nexec {sys.executable} {server}\n")
    launcher.chmod(0o755)
    home = tmp_path / "home"
    (home / "antigravity-acp").mkdir(parents=True)
    (home / "antigravity-acp" / "acp_token.json").write_text("{}")
    monkeypatch.setattr(play, "AGY_HOME", home)
    monkeypatch.setattr(play, "PLAYER_DIR", tmp_path / "player")
    return types.SimpleNamespace(agy=str(launcher), model="gemini-3.8-flash", effort="medium")


def test_session_allows_only_poly_tools_and_sets_thinking(monkeypatch, tmp_path):
    args = _setup(monkeypatch, tmp_path)
    mcp = {"command": "python", "args": ["mcp_poly.py"], "env": {"POLY_URL": "x"}}
    data, err = play.agy_session("play", args, mcp, 30, tmp_path / "t.jsonl")
    assert err is None
    told, note = data["result"].split("\n", 1)
    told = json.loads(told)
    assert told["poly_act"] == "allow" and told["rm -rf /"] == "deny"
    assert told["set thinking_level"] == "medium" and "set model" not in told   # model already current
    assert told["servers"] == ["poly"]
    assert "rm -rf /" in note and "denied" in note
    assert data["usage"]["input_tokens"] == 1234 and data["num_turns"] == 2


def test_usage_limit_reply_is_an_error(monkeypatch, tmp_path):
    args = _setup(monkeypatch, tmp_path)
    server = tmp_path / "fake_acp.py"
    server.write_text(FAKE_SERVER.replace("json.dumps(asked)", "'Usage Limit Reached\\n\\nYou have reached your current quota for this period.'"))
    data, err = play.agy_session("play", args, None, 30, tmp_path / "t.jsonl")
    assert err.startswith("antigravity usage limit")


def test_unknown_model_is_an_error(monkeypatch, tmp_path):
    args = _setup(monkeypatch, tmp_path)
    args.model = "gemini-9-ultra"
    data, err = play.agy_session("play", args, None, 30, tmp_path / "t.jsonl")
    assert "not available" in err and "gemini-3.8-flash" in err
