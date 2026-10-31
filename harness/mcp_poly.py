"""Stdio MCP server for one turn of play: tools get_actions, act, end_turn, write_plan.

Started by `claude -p` (see mcp.json). Config comes from environment variables:
  POLY_URL        bridge base URL (default http://localhost:7777)
  POLY_WORKDIR    folder for this turn's files: calls.jsonl (every tool call), plan.txt, end_turn.json
  POLY_MAX_CALLS  tool calls before end_turn is forced (default 40)
  POLY_MAX_ERRORS consecutive errors before end_turn is forced (default 3)
  POLY_PLAN_CHARS longest plan/notes kept for the next turn (default 1500)
  POLY_COMPACT    1 = compact mode: action ids stay fixed for the whole turn, `act` takes a list of steps,
                  and results show only the action lines that changed (fewer round trips, smaller results)
"""
import json
import os
import time
from pathlib import Path

from bridge import Bridge, BridgeError
from render import render_actions, render_changes

# fields that change without the action itself changing; everything else identifies it
_VOLATILE = {"id", "cost", "dmg", "ret", "kill"}


def action_key(a):
    """Identity of an action across refreshes: a unit's move is one action whatever its destinations."""
    if a["k"] == "move":
        return ("move", a["u"])
    return tuple(sorted((k, json.dumps(v)) for k, v in a.items() if k not in _VOLATILE))


class PolyTools:
    def __init__(self, bridge, workdir, max_calls=40, max_errors=3, compact=False, plan_chars=1500):
        self.bridge = bridge
        self.plan_chars = plan_chars
        self.compact = compact
        self.sid = {}       # compact mode: action key -> id shown to the model, fixed for the turn
        self.shown = None   # compact mode: rendered lines the model has seen, for diffs
        self.dir = Path(workdir)
        self.dir.mkdir(parents=True, exist_ok=True)
        self.max_calls, self.max_errors = max_calls, max_errors
        self.calls = self.errors = 0
        self.ended = False
        self.state = self.acts = None

    # --- plumbing -------------------------------------------------------
    def _log(self, tool, args, result, error=False):
        rec = {"ts": time.time(), "tool": tool, "args": args, "error": error, "result": result}
        with (self.dir / "calls.jsonl").open("a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")

    def _refresh(self):
        self.state = self.bridge.state()
        self.acts = self.bridge.actions()
        if self.compact:
            # first list of the turn keeps the bridge's ids, so the turn prompt's ids stay valid
            first = not self.sid
            for a in self.acts["actions"]:
                k = action_key(a)
                if k not in self.sid:
                    self.sid[k] = a["id"] if first else max(self.sid.values(), default=-1) + 1

    def _shown_actions(self):
        """The action list with ids the model uses (stable ones in compact mode)."""
        if not self.compact:
            return self.acts
        return {**self.acts, "actions": [{**a, "id": self.sid[action_key(a)]} for a in self.acts["actions"]]}

    def _render(self):
        return render_actions(self._shown_actions(), self.state)

    def _diff(self):
        """Compact mode: action lines that are new or changed since the model last saw the list."""
        now = self._render().splitlines()
        if self.shown is None:
            self.shown = now
            return "\n".join(now)
        old = set(self.shown)
        head = lambda l: l.split(" ")[0] if l.startswith("U") else l.split(":")[0]
        changed = [l for l in now if l not in old]
        gone = sorted({head(l) for l in self.shown} - {head(l) for l in now})
        self.shown = now
        out = changed or ["(no other changes)"]
        if gone:
            out.append("No actions left for: " + "; ".join(gone))
        if not any(l.startswith("FORCED") for l in now) and any(l.startswith("FORCED") for l in old):
            out.append("(forced choice resolved)")
        return "\n".join(out) if now else "(no actions left; call end_turn)"
    def _guarded(self, tool, args, fn):
        """Run fn() with call counting, error counting and forced end_turn."""
        if self.ended:
            msg = "The turn is already over. Stop now; do not call any more tools."
            self._log(tool, args, msg, True)
            return msg
        self.calls += 1
        if self.calls > self.max_calls and tool != "end_turn":
            return self._force("tool-call limit reached", tool, args)
        try:
            out = fn()
            self.errors = 0
            self._log(tool, args, out)
            return out
        except BridgeError as e:
            self.errors += 1
            msg = f"ERROR: {e}"
            if e.stale or "unknown" in str(e).lower():
                try:
                    self._refresh()
                    self.shown = None
                    msg += "\nCurrent actions:\n" + self._render()
                except BridgeError:
                    pass
            self._log(tool, args, msg, True)
            if self.errors >= self.max_errors and tool != "end_turn":
                return self._force(f"{self.errors} errors in a row", tool, args, prefix=msg)
            return msg

    def _force(self, why, tool, args, prefix=""):
        self._log(tool, args, f"forced end_turn: {why}", True)
        out = self._do_end_turn(force=True)
        return (prefix + "\n" if prefix else "") + f"Forced end of turn ({why}). " + out

    # --- tools ----------------------------------------------------------
    def get_actions(self):
        def run():
            self._refresh()
            text = self._render()
            self.shown = text.splitlines()
            return text
        return self._guarded("get_actions", {}, run)

    def act(self, id, to=None):
        args = {"id": id, "to": to}

        def run():
            if self.acts is None:
                self._refresh()
            a = next((x for x in self.acts["actions"] if x["id"] == id), None)
            if a is None:
                raise BridgeError(f"unknown action id {id}")
            args["k"] = a["k"]
            if a["k"] == "move":
                if to is None or [int(to[0]), int(to[1])] not in a["to"]:
                    raise BridgeError(f"move #{id} needs `to` from its destination list")
            elif a["k"] == "endTurn":
                raise BridgeError("use the end_turn tool")
            res = self.bridge.act(self.acts["stateId"], id, [int(to[0]), int(to[1])] if to is not None else None)
            text = render_changes(res, self.state["me"]["id"])
            self._refresh()
            return (text or "done") + "\n\nActions now:\n" + render_actions(self.acts, self.state)
        return self._guarded("act", args, run)

    def act_steps(self, steps):
        """Compact mode: do several actions in order. Stops at the first error, or when something the model
        could not have planned for happens (a new enemy comes into view, one of its units dies, a forced choice)."""
        args = {"steps": steps}

        def run():
            if self.acts is None:
                self._refresh()
                self.shown = self._render().splitlines()
            me = self.state["me"]["id"]
            out, done = [], 0
            for n, step in enumerate(steps):
                sid, to = step.get("id"), step.get("to")
                a = next((x for x in self.acts["actions"] if self.sid.get(action_key(x)) == sid), None)
                if a is None:
                    out.append(f"#{sid}: unknown action id or no longer available")
                    break
                if a["k"] == "move" and (to is None or [int(to[0]), int(to[1])] not in a["to"]):
                    out.append(f"#{sid}: move needs `to` from its destination list")
                    break
                if a["k"] == "endTurn":
                    out.append("use the end_turn tool")
                    break
                seen = {u["id"] for u in self.state.get("units", []) if u.get("own") != me}
                mine = {u["id"] for u in self.state.get("units", []) if u.get("own") == me}
                before = self.state["me"]
                res = self.bridge.act(self.acts["stateId"], a["id"], [int(to[0]), int(to[1])] if to is not None else None)
                if "me" in res.get("changes", {}):  # keep only the fields that actually changed
                    me_ch = {k: v for k, v in res["changes"]["me"].items() if before.get(k) != v}
                    res = {**res, "changes": {**res["changes"], "me": me_ch}}
                    if not me_ch:
                        del res["changes"]["me"]
                done += 1
                out.append(f"#{sid} {a['k']}: " + (render_changes(res, me).replace("\n", "; ") or "done"))
                self._refresh()
                ch = res.get("changes", {})
                new_enemy = [u for u in ch.get("units", []) if u.get("own") != me and u["id"] not in seen]
                lost = mine & set(ch.get("removedUnits", []))
                why = ("new enemy in view" if new_enemy else "one of your units died" if lost
                       else "forced choice pending" if self.acts.get("forced") else None)
                if why and n < len(steps) - 1:
                    out.append(f"Stopped after step {n + 1} of {len(steps)} ({why}); the rest were not run.")
                    break
            if done == 0 and out:
                raise BridgeError(out[-1])
            return "\n".join(out) + "\n\nActions changed:\n" + self._diff()
        return self._guarded("act", args, run)

    def write_plan(self, text):
        def run():
            (self.dir / "plan.txt").write_text(str(text)[:self.plan_chars], encoding="utf-8")
            return "plan saved"
        return self._guarded("write_plan", {"text": text}, run)

    def _do_end_turn(self, force=False):
        if force:
            self.resolved = self.bridge.resolve_forced()
        elif self.bridge.actions().get("forced"):
            raise BridgeError("A forced choice (city reward or peace offer) is pending: pick one of its "
                              "options first, then call end_turn.")
        turn = self.bridge.status().get("turn")
        try:
            res = self.bridge.end_turn()
        except BridgeError:
            # The end-turn command went through if the game is now busy (CPU turns), over, or on a later turn;
            # play.py waits for our next turn before starting the next session.
            st = self.bridge.status()
            if not (st["phase"] in ("busy", "game_over") or st.get("turn", turn) != turn):
                raise
            res = {"ok": True, "phase": st["phase"], "turn": st.get("turn"), "events": [],
                   "note": "end_turn reply timed out while the CPUs were moving"}
        (self.dir / "end_turn.json").write_text(json.dumps(res), encoding="utf-8")
        self.ended = True
        return "Turn ended. Stop now; do not call any more tools."

    def end_turn(self, plan=None):
        def run():
            if plan:
                (self.dir / "plan.txt").write_text(str(plan)[:self.plan_chars], encoding="utf-8")
            return self._do_end_turn()
        return self._guarded("end_turn", {"plan": plan} if plan else {}, run)


def build_server(tools):
    from mcp.server.fastmcp import FastMCP
    mcp = FastMCP("poly")

    @mcp.tool()
    def get_actions() -> str:
        """Current legal actions, grouped by unit/city, with action ids."""
        return tools.get_actions()

    if tools.compact:
        @mcp.tool()
        def act(steps: list[dict]) -> str:
            """Do actions in order: steps=[{"id":3,"to":[x,y]},{"id":7}]. Ids stay fixed all turn. `to` only for moves."""
            return tools.act_steps(steps)
    else:
        @mcp.tool()
        def act(id: int, to: list[int] | None = None) -> str:
            """Perform action #id from the latest action list. For move actions pass to=[x,y] from its destinations."""
            return tools.act(id, to)

    @mcp.tool()
    def write_plan(text: str) -> str:
        """Save your plan/notes for next turn (length limit in the rules); shown to you at the start of next turn."""
        return tools.write_plan(text)

    @mcp.tool()
    def end_turn(plan: str = "") -> str:
        """End your turn (always your last call). plan = your plan/notes for next turn (length limit in the rules)."""
        return tools.end_turn(plan)

    return mcp


def main():
    env = os.environ
    tools = PolyTools(Bridge(env.get("POLY_URL", "http://localhost:7777")), env.get("POLY_WORKDIR", "turn"),
                      int(env.get("POLY_MAX_CALLS", 40)), int(env.get("POLY_MAX_ERRORS", 3)),
                      env.get("POLY_COMPACT") == "1", int(env.get("POLY_PLAN_CHARS", 1500)))
    build_server(tools).run()


if __name__ == "__main__":
    main()
