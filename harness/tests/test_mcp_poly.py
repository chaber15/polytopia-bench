import asyncio
import json
import sys
from pathlib import Path

from mcp_poly import PolyTools

HARNESS = Path(__file__).resolve().parents[1]


def test_flow(bridge, tmp_path):
    bridge.newgame()
    t = PolyTools(bridge, tmp_path)
    assert "U4 Warrior" in t.get_actions()
    out = t.act(0, [0, 2])
    assert "U4 Warrior (0,2)" in out and "Actions now" in out
    assert "ERROR" in t.act(0, [9, 9]) or "ERROR" in t.act(99)
    assert t.write_plan("go north") == "plan saved"
    assert (tmp_path / "plan.txt").read_text() == "go north"
    assert "Turn ended" in t.end_turn()
    assert json.loads((tmp_path / "end_turn.json").read_text())["turn"] == 1
    assert "already over" in t.act(1, [1, 1])
    tools = [json.loads(l)["tool"] for l in (tmp_path / "calls.jsonl").read_text(encoding="utf-8").splitlines()]
    assert tools[0] == "get_actions" and tools[-1] == "act"


def test_move_needs_valid_destination(bridge, tmp_path):
    bridge.newgame()
    t = PolyTools(bridge, tmp_path)
    assert "ERROR" in t.act(0)
    assert "ERROR" in t.act(0, [5, 5])


def test_error_limit_forces_end(bridge, tmp_path):
    bridge.newgame()
    t = PolyTools(bridge, tmp_path, max_errors=3)
    t.act(99); t.act(98)
    out = t.act(97)
    assert "Forced end of turn" in out and t.ended


def test_call_limit_forces_end(bridge, tmp_path):
    bridge.newgame()
    t = PolyTools(bridge, tmp_path, max_calls=2)
    t.get_actions(); t.get_actions()
    assert "Forced end of turn" in t.get_actions() and t.ended


def test_stdio_server(server, tmp_path):
    """Spawn the real MCP server over stdio and call a tool through the MCP client."""
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client
    from bridge import Bridge
    port = server.server_address[1]
    Bridge(f"http://localhost:{port}").newgame()

    async def run():
        params = StdioServerParameters(command=sys.executable, args=[str(HARNESS / "mcp_poly.py")], cwd=str(HARNESS),
                                       env={"POLY_URL": f"http://localhost:{port}", "POLY_WORKDIR": str(tmp_path)})
        async with stdio_client(params) as (r, w):
            async with ClientSession(r, w) as s:
                await s.initialize()
                names = {x.name for x in (await s.list_tools()).tools}
                res = await s.call_tool("get_actions", {})
                return names, res.content[0].text
    names, text = asyncio.run(run())
    assert names == {"get_actions", "act", "write_plan", "end_turn"}
    assert "U4 Warrior" in text


def test_end_turn_saves_plan(bridge, tmp_path):
    bridge.newgame()
    t = PolyTools(bridge, tmp_path)
    assert "Turn ended" in t.end_turn("hold the line")
    assert (tmp_path / "plan.txt").read_text() == "hold the line"
