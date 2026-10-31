import io

from gamelog import GameLog, read_records, summarize


def write_sample(log_dir):
    log = GameLog("testagent", log_dir=log_dir)
    state0 = {"turn": 0, "me": {"id": 1, "score": 50}}
    state1 = {"turn": 1, "me": {"id": 1, "score": 70}}
    log.turn_start(0, state0)
    log.action(0, {"id": 0, "k": "move", "u": 4, "to": [0, 2]}, {"ok": True, "stateId": 2})
    log.action(0, {"id": 2, "k": "research", "tech": "Archery", "cost": 4}, {"ok": True, "stateId": 3})
    log.error(0, "POST /act: stale", action={"id": 1, "k": "move"})
    log.model(0, text="move north", prompt_tokens=100, output_tokens=12, cache_read_tokens=80)
    log.model(1, text="end turn", prompt_tokens=50, output_tokens=3, cache_read_tokens=40)
    log.turn_start(1, state1)
    log.game_end({"ok": True, "winner": 1, "turn": 2,
                  "scores": [{"id": 1, "tribe": "Bardur", "score": 90}, {"id": 2, "tribe": "Imperius", "score": 80}]})
    log.close()
    return log.path


def test_one_jsonl_file_per_game_with_agent_in_name(tmp_path):
    first = GameLog("random", log_dir=tmp_path)
    second = GameLog("random", log_dir=tmp_path)
    assert first.path.name.endswith("-random.jsonl")
    assert first.path != second.path
    first.close()
    second.close()


def test_records_have_type_and_fields(tmp_path):
    path = write_sample(tmp_path)
    recs = read_records(path)
    assert [r["t"] for r in recs] == ["turn_start", "action", "action", "error", "model", "model",
                                      "turn_start", "game_end"]
    assert recs[1]["turn"] == 0 and recs[1]["action"]["k"] == "move"
    assert recs[4]["cache_read_tokens"] == 80


def test_summarize_prints_and_returns_totals(tmp_path):
    path = write_sample(tmp_path)
    out = io.StringIO()
    s = summarize(path, out=out)
    text = out.getvalue()
    assert "turns:     2" in text
    assert "actions:   2 (move 1, research 1)" in text
    assert "errors:    1" in text
    assert "turn 0: POST /act: stale" in text
    assert "winner 1" in text and "1 Bardur=90" in text
    assert "prompt_tokens 150, output_tokens 15, cache_read_tokens 120" in text
    assert s["turns"] == 2 and s["actions"] == 2 and s["errors"] == 1
    assert s["final_score"] == 90 and s["winner"] == 1
    assert s["tokens"] == {"prompt_tokens": 150, "output_tokens": 15, "cache_read_tokens": 120}


def test_summarize_without_game_end_uses_last_state(tmp_path):
    log = GameLog("partial", log_dir=tmp_path)
    log.turn_start(0, {"turn": 0, "me": {"id": 1, "score": 50}})
    log.close()
    out = io.StringIO()
    s = summarize(log.path, out=out)
    assert s["final_score"] == 50 and not s["game_over"]
    assert "no game_end record" in out.getvalue()
