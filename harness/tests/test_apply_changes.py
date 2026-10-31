import copy
import json
from pathlib import Path

from bridge import apply_changes

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"


def state():
    return json.loads((FIXTURES / "state.json").read_text(encoding="utf-8"))


def test_unit_replaced_by_id_and_new_unit_appended():
    s = state()
    new_unit = {"id": 9, "type": "Warrior", "own": 2, "xy": [3, 3], "hp": 10, "hpMax": 10}
    moved = {**s["units"][0], "xy": [0, 2]}
    merged = apply_changes(s, {"units": [moved, new_unit]})
    assert [u["id"] for u in merged["units"]] == [4, 5, 9]
    assert merged["units"][0]["xy"] == [0, 2]
    assert merged["units"][2] == new_unit


def test_removed_units_are_dropped():
    merged = apply_changes(state(), {"removedUnits": [5]})
    assert [u["id"] for u in merged["units"]] == [4]


def test_tiles_replaced_by_xy_and_appended():
    s = state()
    changed = {"xy": [0, 1], "t": "Forest", "own": 1}
    merged = apply_changes(s, {"tiles": [changed, {"xy": [0, 3], "t": "Field"}]})
    tiles = merged["map"]["tiles"]
    assert len(tiles) == len(s["map"]["tiles"]) + 1
    assert next(t for t in tiles if t["xy"] == [0, 1]) == changed
    assert tiles[-1] == {"xy": [0, 3], "t": "Field"}


def test_cities_replaced_by_xy():
    s = state()
    city = {**s["cities"][0], "lvl": 2, "pop": 2}
    merged = apply_changes(s, {"cities": [city]})
    assert merged["cities"] == [city]


def test_me_is_merged_field_by_field():
    merged = apply_changes(state(), {"me": {"stars": 7}})
    assert merged["me"]["stars"] == 7
    assert merged["me"]["techs"] == ["Hunting"] and merged["me"]["id"] == 1


def test_other_keys_are_replaced_wholesale():
    merged = apply_changes(state(), {"villages": [[1, 1]]})
    assert merged["villages"] == [[1, 1]]


def test_input_is_not_modified_and_stateid_is_left_alone():
    s = state()
    before = copy.deepcopy(s)
    merged = apply_changes(s, {"me": {"stars": 1}, "removedUnits": [4], "tiles": [{"xy": [0, 0], "t": "Field"}]})
    assert s == before
    assert merged is not s
    assert merged["stateId"] == s["stateId"]


def test_empty_changes_return_an_equal_copy():
    s = state()
    assert apply_changes(s, {}) == s
