import json

from mcp_poly import PolyTools, action_key


def test_ids_stay_fixed_and_batch_runs(bridge, tmp_path):
    bridge.newgame()
    t = PolyTools(bridge, tmp_path, compact=True)
    full = t.get_actions()
    first = {action_key(a): a["id"] for a in bridge.actions()["actions"]}
    assert t.sid == first  # first list keeps the bridge's ids (matches the turn prompt)
    mv = next(a for a in bridge.actions()["actions"] if a["k"] == "move")
    out = t.act_steps([{"id": mv["id"], "to": mv["to"][0]}])
    assert "Actions changed:" in out and "ERROR" not in out
    assert len(out) < len(full) + 400
    # ids of untouched actions are unchanged after the act
    for a in bridge.actions()["actions"]:
        k = action_key(a)
        if k in first:
            assert t.sid[k] == first[k]


def test_batch_stops_at_bad_step(bridge, tmp_path):
    bridge.newgame()
    t = PolyTools(bridge, tmp_path, compact=True)
    t.get_actions()
    mv = next(a for a in bridge.actions()["actions"] if a["k"] == "move")
    out = t.act_steps([{"id": mv["id"], "to": mv["to"][0]}, {"id": 999}, {"id": mv["id"], "to": mv["to"][0]}])
    assert "#999: unknown" in out and out.count(" move:") == 1


def test_first_step_error_is_an_error(bridge, tmp_path):
    bridge.newgame()
    t = PolyTools(bridge, tmp_path, compact=True)
    out = t.act_steps([{"id": 999}])
    assert out.startswith("ERROR") and "Current actions" in out
    assert json.loads((tmp_path / "calls.jsonl").read_text(encoding="utf-8").splitlines()[-1])["error"]


def test_compact_prompt_rewrites_act_line(tmp_path):
    from play import SYSTEM_PROMPT, system_prompt_file
    (tmp_path / "ref.md").write_text("# Tech tree (tier: tech → what it unlocks)\n- Riding (T1)\n", encoding="utf-8")
    dst = system_prompt_file(SYSTEM_PROMPT, tmp_path / "s.md", compact=True, reference=tmp_path / "ref.md")
    text = dst.read_text(encoding="utf-8")
    assert "`act(steps)`" in text and "`act(id, to?)`" not in text
    assert "- Riding (T1)\n\n# Score" in text and "{{REFERENCE}}" not in text
