import io

from agents.endturn_agent import play_endturn
from agents.random_agent import play_random
from bridge import Bridge
from gamelog import GameLog, read_records, summarize


def test_random_agent_finishes_30_turn_game(bridge, tmp_path):
    log = GameLog("random", log_dir=tmp_path)
    result = play_random(bridge, log, seed=1, max_actions=20)
    log.close()

    assert result["turn"] == 30 and result["winner"] in (1, 2)
    s = summarize(log.path, out=io.StringIO())
    assert s["turns"] == 30
    assert s["game_over"] and s["errors"] == 0
    assert s["actions"] > 30
    assert s["action_kinds"].get("move", 0) > 0


def test_random_agent_is_seedable(server, bridge, tmp_path):
    def actions_of(seed):
        log = GameLog("random", log_dir=tmp_path)
        play_random(bridge, log, seed=seed, max_actions=5)
        log.close()
        bridge.quit()  # the fake server holds one game; back to the menu for the next run
        return [r["action"] for r in read_records(log.path) if r["t"] == "action"]

    assert actions_of(7) == actions_of(7)


def test_random_agent_respects_action_cap(bridge, tmp_path):
    log = GameLog("random", log_dir=tmp_path)
    play_random(bridge, log, seed=3, max_actions=2)
    log.close()
    per_turn = {}
    for r in read_records(log.path):
        if r["t"] == "action":
            per_turn[r["turn"]] = per_turn.get(r["turn"], 0) + 1
    assert per_turn and max(per_turn.values()) <= 2


def test_endturn_agent_plays_without_actions(bridge, tmp_path):
    log = GameLog("endturn", log_dir=tmp_path)
    result = play_endturn(bridge, log)
    log.close()
    s = summarize(log.path, out=io.StringIO())
    assert result["turn"] == 30
    assert s["turns"] == 30 and s["actions"] == 0 and s["errors"] == 0

