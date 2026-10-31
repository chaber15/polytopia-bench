import json
import types

import play


class Log:
    def __init__(self):
        self.lines = []

    def error(self, turn, msg):
        self.lines.append(msg)


def _args():
    return types.SimpleNamespace(claude="claude", model="opus", effort="medium", pick_context="test game.")


def _fake_run(answer):
    def run(cmd, **kw):
        assert "--tools" in cmd and "Xinxi (Xin-xi)" in cmd[2] or "Xinxi" in cmd[2]
        return types.SimpleNamespace(stdout=json.dumps({"result": answer, "usage": {}, "total_cost_usd": 0.01}), returncode=0)
    return run


def test_pick_reads_the_first_line(monkeypatch, tmp_path):
    monkeypatch.setattr(play, "PLAYER_DIR", tmp_path)
    monkeypatch.setattr(play.subprocess, "run", _fake_run("Xin-xi\nMountains and metal suit a score game."))
    log = Log()
    assert play.pick_tribe(_args(), log) == "Xinxi"
    assert "model chose" in log.lines[0]


def test_pick_falls_back_to_a_random_core_tribe(monkeypatch, tmp_path):
    monkeypatch.setattr(play, "PLAYER_DIR", tmp_path)
    monkeypatch.setattr(play.subprocess, "run", _fake_run("I would rather not choose."))
    log = Log()
    assert play.pick_tribe(_args(), log) in play.CORE_TRIBES
    assert "random fallback" in log.lines[0]
