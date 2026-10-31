import json
from pathlib import Path

from render import render_actions, render_changes, render_grid, render_state, turn_prompt

FIX = Path(__file__).resolve().parents[1] / "fixtures"


def load(n):
    return json.loads((FIX / n).read_text())


def test_grid():
    g = render_grid(load("state.json")).splitlines()
    assert g[0] == "   01234"
    assert g[1] == " 0 OO~??"
    assert g[2] == " 1 .Cu??"   # field, capital, rider
    assert g[3] == " 2 vuM??"   # village, warrior, mountain


def test_state_text():
    s = render_state(load("state.json"))
    assert "stars 5 (+2/turn)" in s and "U4 Warrior (1,2) 10/10hp" in s
    assert "City Guro (1,1) lvl1 capital" in s and "Villages: (0,2)" in s
    assert "(2,1) Field Fruit +Farm" in s


def test_actions_text():
    t = render_actions(load("actions.json"), load("state.json"))
    assert "U4 Warrior (1,2): move→(0-1,1)(0,2)(0-2,3) [#0]" in t
    assert "Research: Archery 4⭐ [#2]" in t and "endTurn" not in t


def test_attack_train_build():
    ac = {"actions": [{"id": 1, "k": "attack", "u": 4, "to": [7, 6], "dmg": 5, "ret": 5},
                      {"id": 2, "k": "attack", "u": 4, "to": [7, 7], "dmg": 10, "kill": True},
                      {"id": 4, "k": "train", "city": [1, 1], "unit": "Warrior", "cost": 2},
                      {"id": 5, "k": "build", "at": [1, 2], "imp": "Farm", "cost": 5}]}
    t = render_actions(ac, load("state.json"))
    assert "attack (7,6) dmg5 ret5 [#1]" in t and "dmg10 ret0 KILL [#2]" in t
    assert "City Guro (1,1): train Warrior 2⭐ [#4]" in t and "Build Farm 5⭐: (1,2)[#5]" in t


def test_forced_and_empty():
    ac = {"forced": True, "actions": [{"id": 0, "k": "reward", "city": [1, 1], "reward": "Workshop"}]}
    t = render_actions(ac, load("state.json"))
    assert t.startswith("FORCED") and "REWARD Workshop [#0]" in t
    assert "end_turn" in render_actions({"actions": [{"id": 0, "k": "endTurn"}]}, load("state.json"))


def test_changes():
    t = render_changes(load("act_ok.json"))
    assert "Warrior 4 moved to [0,2]" in t and "U4 Warrior (0,2)" in t and "2 tiles" in t


def test_turn_prompt():
    p = turn_prompt(load("state.json"), load("actions.json"), 0, 30, "", [])
    assert "Turn 0 of 30" in p and "(none yet" in p and "nothing seen" in p
