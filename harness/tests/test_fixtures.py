"""Fixtures are the spec's example answers. Check they are well-formed and that the fake server
reproduces the ones it can (so fixtures and fake cannot drift apart silently)."""
import json
from pathlib import Path

from bridge import apply_changes

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"
ALL = ["status", "newgame", "state", "actions", "act_ok", "act_stale", "end_turn",
       "end_turn_game_over", "result"]


def load(name):
    return json.loads((FIXTURES / f"{name}.json").read_text(encoding="utf-8"))


def test_every_fixture_is_an_ok_answer_or_a_stale_error():
    for name in ALL:
        data = load(name)
        assert "ok" in data, name
        assert data["ok"] is (name != "act_stale"), name


def test_state_fixture_is_consistent():
    state = load("state")
    tiles = {tuple(t["xy"]) for t in state["map"]["tiles"]}
    w, h = state["map"]["w"], state["map"]["h"]
    assert all(0 <= x < w and 0 <= y < h for x, y in tiles)
    for u in state["units"]:
        assert tuple(u["xy"]) in tiles, f"unit {u['id']} stands on an unexplored tile"
    for c in state["cities"]:
        assert tuple(c["xy"]) in tiles
    assert len({u["id"] for u in state["units"]}) == len(state["units"])


def test_actions_fixture_ends_with_end_turn_and_ids_are_sequential():
    acts = load("actions")["actions"]
    assert acts[-1]["k"] == "endTurn"
    assert [a["id"] for a in acts if "id" in a] == list(range(len(acts)))


def test_game_over_and_result_fixtures():
    assert load("end_turn_game_over")["phase"] == "game_over"
    result = load("result")
    assert {s["id"] for s in result["scores"]} == {1, 2}
    assert result["winner"] in (1, 2)


def test_fake_server_reproduces_fixtures(bridge):
    assert bridge.status() == {"ok": True, "phase": "menu", "ready": False}
    assert bridge.newgame() == load("newgame")
    assert bridge.status() == load("status")
    assert bridge.state() == load("state")
    assert bridge.actions() == load("actions")
    assert bridge.act(1, 0, [0, 2]) == load("act_ok")
    assert bridge.end_turn() == load("end_turn")


def test_act_ok_fixture_applies_to_state_fixture():
    merged = apply_changes(load("state"), load("act_ok")["changes"])
    unit4 = next(u for u in merged["units"] if u["id"] == 4)
    assert unit4["xy"] == [0, 2] and unit4["moved"] is True
    assert len(merged["map"]["tiles"]) == len(load("state")["map"]["tiles"]) + 2
