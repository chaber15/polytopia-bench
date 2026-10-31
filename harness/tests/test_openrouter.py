import json
import sys
import threading
import types
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

import openrouter
import play


class FakeOpenRouter(ThreadingHTTPServer):
    """Scripted chat completions: get_actions, then end_turn. Records every request body."""

    def __init__(self, replies):
        self.replies, self.seen = list(replies), []
        super().__init__(("127.0.0.1", 0), self.Handler)

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def do_POST(self):
            body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            self.server.seen.append(body)
            status, reply = self.server.replies.pop(0)
            out = json.dumps(reply).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(out)))
            self.end_headers()
            self.wfile.write(out)


def call(name, args, i):
    return {"id": f"c{i}", "type": "function", "function": {"name": name, "arguments": json.dumps(args)}}


def reply(msg, cost=0.01):
    return 200, {"choices": [{"message": {"role": "assistant", **msg}}],
                 "usage": {"prompt_tokens": 1000, "completion_tokens": 200, "cost": cost,
                           "prompt_tokens_details": {"cached_tokens": 600}}}


@pytest.fixture
def api(monkeypatch):
    servers = []

    def start(replies):
        srv = FakeOpenRouter(replies)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        servers.append(srv)
        monkeypatch.setattr(openrouter, "URL", f"http://127.0.0.1:{srv.server_port}/chat/completions")
        monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
        return srv
    yield start
    for s in servers:
        s.shutdown()


def _mcp(server, tmp_path):
    return {"command": sys.executable, "args": [str(play.HERE / "mcp_poly.py")],
            "env": {"POLY_URL": f"http://localhost:{server.server_port}", "POLY_WORKDIR": str(tmp_path / "turn"),
                    "POLY_COMPACT": "1", "PYTHONPATH": str(play.HERE)}}


ARGS = types.SimpleNamespace(model="google/gemini-4-argon", effort="medium")


def test_plays_a_turn_through_the_game_tools(api, server, bridge, tmp_path):
    bridge.newgame(mode="Perfection", difficulty="Easy", tribe="Bardur", opponents=1, mapSize=11)
    srv = api([reply({"content": None, "reasoning_details": [{"type": "reasoning.encrypted", "data": "sig"}],
                      "tool_calls": [call("get_actions", {}, 1)]}),
               reply({"content": "Ending.", "tool_calls": [call("end_turn", {"plan": "expand east"}, 2)]})])
    data, err = openrouter.session("RULES", "TURN", ARGS, _mcp(server, tmp_path), 60, tmp_path / "t.jsonl")
    assert err is None
    first, second = srv.seen
    assert first["messages"][0] == {"role": "system", "content": "RULES"}
    assert first["reasoning"] == {"effort": "medium"} and first["model"] == "google/gemini-4-argon"
    assert {t["function"]["name"] for t in first["tools"]} == {"get_actions", "act", "write_plan", "end_turn"}
    # the model's reasoning goes back unchanged, and it saw the real tool result
    assert second["messages"][2]["reasoning_details"] == [{"type": "reasoning.encrypted", "data": "sig"}]
    assert second["messages"][3]["role"] == "tool" and "Research" in second["messages"][3]["content"]
    assert (tmp_path / "turn" / "plan.txt").read_text() == "expand east"
    assert (tmp_path / "turn" / "end_turn.json").exists()
    assert data["num_turns"] == 2 and data["total_cost_usd"] == pytest.approx(0.02)
    assert data["usage"]["cache_read_input_tokens"] == 1200 and data["usage"]["input_tokens"] == 800


def test_out_of_credits_is_an_error_and_keeps_what_was_spent(api, server, bridge, tmp_path):
    bridge.newgame(mode="Perfection", difficulty="Easy", tribe="Bardur", opponents=1, mapSize=11)
    api([reply({"content": None, "tool_calls": [call("get_actions", {}, 1)]}, cost=0.05),
         (402, {"error": {"code": 402, "message": "Insufficient credits"}})])
    data, err = openrouter.session("RULES", "TURN", ARGS, _mcp(server, tmp_path), 60, tmp_path / "t.jsonl")
    assert "out of credits" in err
    assert data["total_cost_usd"] == pytest.approx(0.05)
    assert not (tmp_path / "turn" / "end_turn.json").exists()   # the turn stays open for --resume


def test_pick_has_no_tools(api, monkeypatch, tmp_path):
    srv = api([reply({"content": "Oumaji\nOpen plains."})])
    monkeypatch.setattr(play, "PLAYER_DIR", tmp_path)

    class Log:
        def error(self, turn, msg):
            pass
    args = types.SimpleNamespace(driver="openrouter", model="google/gemini-4-argon", effort="medium",
                                 pick_context="test game.", claude="claude")
    assert play.pick_tribe(args, Log()) == "Oumaji"
    assert "tools" not in srv.seen[0]
