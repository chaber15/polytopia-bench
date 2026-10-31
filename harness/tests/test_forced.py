from bridge import Bridge, BridgeError


class StubBridge(Bridge):
    def __init__(self, forced_steps):
        self.forced_steps = forced_steps
        self.acted, self.ended = [], False

    def actions(self):
        if self.forced_steps:
            return {"stateId": 5, "forced": True, "actions": [
                {"id": 0, "k": "reward", "reward": "Workshop"}, {"id": 1, "k": "reward", "reward": "Explorer"}]}
        return {"stateId": 6, "actions": [{"id": 0, "k": "endTurn"}]}

    def act(self, state_id, id, to=None, full=False):
        self.acted.append(id)
        self.forced_steps -= 1
        return {"ok": True}

    def status(self):
        return {"phase": "my_turn", "turn": 1}

    def end_turn(self):
        if self.forced_steps:
            raise BridgeError("invalid: Pending command trigger exists")
        self.ended = True
        return {"ok": True, "phase": "my_turn", "turn": 2}


def test_resolve_forced_picks_first_option_until_clear():
    b = StubBridge(forced_steps=2)
    picked = b.resolve_forced()
    assert [p["reward"] for p in picked] == ["Workshop", "Workshop"]
    assert b.forced_steps == 0
    b.end_turn()
    assert b.ended


def test_resolve_forced_noop_when_nothing_pending():
    b = StubBridge(forced_steps=0)
    assert b.resolve_forced() == []
    assert b.acted == []


def test_mcp_end_turn_refuses_then_force_resolves(tmp_path):
    from mcp_poly import PolyTools
    b = StubBridge(forced_steps=1)
    t = PolyTools(b, tmp_path, max_calls=40, max_errors=3)
    out = t.end_turn("plan")
    assert "forced choice" in out.lower() and not b.ended
    out = t._force("test", "end_turn", {})
    assert b.ended and b.acted == [0]


class SlowCpuBridge(StubBridge):
    """end_turn's reply times out while the CPUs are still moving."""
    def __init__(self):
        super().__init__(forced_steps=0)
        self.calls = 0

    def status(self):
        self.calls += 1
        return {"phase": "my_turn", "turn": 52} if self.calls == 1 else {"phase": "busy", "turn": 52}

    def end_turn(self):
        raise BridgeError("POST /end_turn: timeout")


def test_mcp_end_turn_timeout_while_cpus_move_counts_as_ended(tmp_path):
    import json
    from mcp_poly import PolyTools
    t = PolyTools(SlowCpuBridge(), tmp_path)
    out = t.end_turn("keep attacking")
    assert "Turn ended" in out and t.ended
    assert json.loads((tmp_path / "end_turn.json").read_text())["phase"] == "busy"


def test_render_peace_offer_and_diplomacy():
    from render import render_actions, render_state
    state = {"turn": 3, "me": {"id": 1, "tribe": "Bardur", "stars": 5}, "map": {"w": 2, "h": 1, "tiles": []},
             "opponents": [{"id": 2, "tribe": "Imperius", "score": 900, "rel": "peace"},
                           {"id": 3, "tribe": "Vengir", "score": 100, "out": True}]}
    forced = {"forced": True, "actions": [{"id": 0, "k": "peace", "with": "Imperius", "accept": True},
                                          {"id": 1, "k": "peace", "with": "Imperius", "accept": False}]}
    text = render_actions(forced, state)
    assert "Peace offer from Imperius: ACCEPT [#0]; DECLINE [#1]" in text and "FORCED CHOICE" in text
    dip = render_actions({"actions": [{"id": 4, "k": "diplomacy", "cmd": "BreakPeace", "with": "Imperius"}]}, state)
    assert "Diplomacy: BreakPeace with Imperius [#4]" in dip
    head = render_state(state).splitlines()[0]
    assert "Imperius 900 (at peace)" in head and "Vengir 100 (eliminated)" in head


def test_city_line_shows_unit_limit_blocking_unit_and_next_level():
    from render import render_state
    state = {"turn": 5, "me": {"id": 1, "tribe": "Bardur", "stars": 9}, "map": {"w": 2, "h": 1, "tiles": []},
             "cities": [{"xy": [0, 0], "name": "Ckar", "own": 1, "lvl": 6, "pop": 26, "popMax": 7, "units": 5}],
             "units": [{"id": 9, "type": "Knight", "own": 1, "xy": [0, 0], "hp": 10, "hpMax": 10}]}
    line = [l for l in render_state(state).splitlines() if l.startswith("City ")][0]
    assert "pop 26 (lvl7 at 27) units 5/7, tile occupied by U9" in line


def test_unit_line_shows_kills_toward_veteran():
    from render import unit_line
    u = {"id": 7, "type": "Knight", "own": 1, "xy": [2, 3], "hp": 10, "hpMax": 10, "kills": 2, "killsVet": 3}
    assert "kills 2/3" in unit_line(u, 1)
    assert "kills" not in unit_line({**u, "own": 2}, 1)


def test_other_tribe_unit_types_are_described_when_seen(monkeypatch):
    import render
    monkeypatch.setattr(render, "OTHER_UNITS", {"units": {"hexapod": "Hexapod 3 5 3 1 2 1 dash,escape,creep,sneak"},
                                                "skills": {"sneak": "Moves past enemies.", "creep": "No rough terrain penalty."},
                                                "explained": ["dash", "escape", "creep"]})
    state = {"turn": 5, "me": {"id": 1, "tribe": "Bardur", "stars": 9}, "map": {"w": 2, "h": 1, "tiles": []},
             "units": [{"id": 3, "type": "Hexapod", "own": 2, "xy": [1, 0], "hp": 5, "hpMax": 5},
                       {"id": 4, "type": "Warrior", "own": 2, "xy": [0, 0], "hp": 10, "hpMax": 10}]}
    text = render.render_state(state)
    assert "Unit types not in the rules (unit cost hp atk def move range skills): Hexapod 3 5 3 1 2 1" in text
    assert "sneak: Moves past enemies." in text and "creep:" not in text and "Warrior 2" not in text
    state["units"] = state["units"][1:]
    assert "not in the rules" not in render.render_state(state)


def test_turn_view_retries_when_the_game_flickers_busy(monkeypatch):
    import time
    from bridge import Bridge, BridgeError
    monkeypatch.setattr(time, "sleep", lambda s: None)

    class Flicker(Bridge):
        def __init__(self):
            self.statuses = iter(["my_turn", "busy", "busy", "my_turn", "my_turn", "my_turn", "my_turn"])
            self.action_calls = 0

        def status(self):
            return {"phase": next(self.statuses), "turn": 4}

        def state(self):
            return {"turn": 4}

        def actions(self):
            self.action_calls += 1
            if self.action_calls == 1:
                raise BridgeError("GET /actions: not ready (phase busy)")
            return {"actions": []}

    st, state, actions = Flicker().turn_view()
    assert st["phase"] == "my_turn" and state == {"turn": 4} and actions == {"actions": []}


def test_turn_view_reloads_when_stuck_busy(monkeypatch):
    import time
    from bridge import Bridge
    monkeypatch.setattr(time, "sleep", lambda s: None)

    class Stuck(Bridge):
        def __init__(self):
            self.reloaded = False

        def wait_ready(self, max_s=1800, poll=3):
            return {"phase": "my_turn" if self.reloaded else "busy", "turn": 23}

        def recover(self):
            self.reloaded = True

        def state(self):
            return {"turn": 23}

        def actions(self):
            return {"actions": []}

    b = Stuck()
    st, state, _ = b.turn_view()
    assert b.reloaded and st["phase"] == "my_turn" and state == {"turn": 23}
