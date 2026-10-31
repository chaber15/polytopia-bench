import json
from pathlib import Path

import pytest

from bridge import Bridge, BridgeError

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"


def load(name):
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def test_status_menu_then_match(bridge):
    assert bridge.status()["phase"] == "menu"
    assert bridge.newgame() == {"ok": True, "turn": 0}
    status = bridge.status()
    assert status["phase"] == "my_turn" and status["ready"] is True
    assert status["turn"] == 0 and status["maxTurns"] == 30


def test_newgame_outside_menu_is_409_with_error_text(bridge):
    bridge.newgame()
    with pytest.raises(BridgeError) as e:
        bridge.newgame()
    assert e.value.status == 409
    assert "newgame only works from the menu" in str(e.value)


def test_state_and_actions_match_fixtures(bridge):
    bridge.newgame()
    assert bridge.state() == load("state.json")
    assert bridge.actions() == load("actions.json")


def test_act_ok_returns_changes(bridge):
    bridge.newgame()
    assert bridge.act(1, 0, [0, 2]) == load("act_ok.json")


def test_act_stale_raises_with_flag_and_current_state_id(bridge):
    bridge.newgame()
    bridge.act(1, 0, [0, 2])
    with pytest.raises(BridgeError) as e:
        bridge.act(1, 1, [3, 1])
    assert e.value.stale
    assert e.value.data == load("act_stale.json")


def test_act_unknown_id_is_ok_false(bridge):
    bridge.newgame()
    with pytest.raises(BridgeError) as e:
        bridge.act(1, 99)
    assert not e.value.stale
    assert "unknown action id" in str(e.value)


def test_malformed_body_is_400(bridge):
    bridge.newgame()
    with pytest.raises(BridgeError) as e:
        bridge._call("POST", "/act", body={"id": 0})
    assert e.value.status == 400


def test_end_turn_matches_fixture(bridge):
    bridge.newgame()
    bridge.act(1, 0, [0, 2])
    assert bridge.end_turn() == load("end_turn.json")


def test_result_before_game_over_is_409(bridge):
    bridge.newgame()
    with pytest.raises(BridgeError) as e:
        bridge.result()
    assert e.value.status == 409


def test_full_game_reaches_game_over_and_result(bridge):
    bridge.newgame()
    for _ in range(29):
        assert bridge.end_turn()["phase"] == "my_turn"
    over = bridge.end_turn()
    assert over["phase"] == "game_over" and over["turn"] == 30
    result = bridge.result()
    assert result["winner"] in (1, 2) and len(result["scores"]) == 2
    with pytest.raises(BridgeError):
        bridge.end_turn()


def test_quit_returns_to_menu(bridge):
    bridge.newgame()
    assert bridge.quit()["phase"] == "menu"
    assert bridge.status()["phase"] == "menu"
    bridge.newgame()  # and a new game can start


def test_connection_error_is_bridge_error():
    with pytest.raises(BridgeError) as e:
        Bridge("http://localhost:1", timeout=2).status()
    assert "GET /status" in str(e.value)
