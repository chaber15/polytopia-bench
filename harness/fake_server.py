"""Stdlib fake of the PolyBridge v1 API (spec/API.md) for offline harness tests.

Starts from fixtures/state.json on /newgame. Moves, research, end_turn and game over are
simulated; there are no real rules. Unexplored terrain is Ocean on the east and south edges,
Field elsewhere.

Run: python fake_server.py --port 7777 --max-turns 30
"""
import argparse
import copy
import json
import socket
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

FIXTURES = Path(__file__).resolve().parent / "fixtures"
TECHS = {"Archery": 4, "Riding": 4, "Climbing": 4}
BLOCKED = {"Ocean", "Water", "Mountain"}
OPPONENT_TRIBE = "Imperius"


class ApiError(Exception):
    def __init__(self, status, error, **extra):
        super().__init__(error)
        self.status = status
        self.error = error
        self.extra = extra


def _load(name):
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


class FakeGame:
    def __init__(self, max_turns=30):
        self.max_turns = max_turns
        self.phase = "menu"
        self.s = None  # match state, same shape as /state minus "ok"

    # ---- routing -------------------------------------------------------
    def handle(self, method, path, body, query):
        """Return (http_status, payload). Raises ApiError for error answers."""
        if (method, path) == ("GET", "/status"):
            return 200, self.status()
        if (method, path) == ("POST", "/newgame"):
            return 200, self.newgame()
        if (method, path) == ("GET", "/state"):
            return 200, self.state()
        if (method, path) == ("GET", "/actions"):
            return 200, self.actions()
        if (method, path) == ("POST", "/act"):
            return 200, self.act(body, full=bool(query.get("full")))
        if (method, path) == ("POST", "/end_turn"):
            return 200, self.end_turn()
        if (method, path) == ("GET", "/result"):
            return 200, self.result()
        if (method, path) == ("POST", "/quit"):
            return 200, self.quit()
        raise ApiError(404, "unknown endpoint")

    def _need_match(self):
        if self.phase not in ("my_turn", "game_over"):
            raise ApiError(409, "not in a match")

    # ---- endpoints -----------------------------------------------------
    def status(self):
        if self.phase == "menu":
            return {"ok": True, "phase": "menu", "ready": False}
        return {"ok": True, "phase": self.phase, "ready": self.phase == "my_turn",
                "turn": self.s["turn"], "maxTurns": self.max_turns}

    def newgame(self):
        if self.phase != "menu":
            raise ApiError(409, "newgame only works from the menu")
        self.s = _load("state.json")
        del self.s["ok"]
        self.s["maxTurns"] = self.max_turns
        self.phase = "my_turn"
        return {"ok": True, "turn": 0}

    def state(self):
        self._need_match()
        return {"ok": True, **copy.deepcopy(self.s)}

    def actions(self):
        self._need_match()
        if self.phase != "my_turn":
            raise ApiError(409, "game is over")
        return {"ok": True, "stateId": self.s["stateId"], "forced": False,
                "actions": self._list_actions()}

    def act(self, body, full=False):
        if not isinstance(body.get("stateId"), int) or not isinstance(body.get("id"), int):
            raise ApiError(400, "body needs integer stateId and id")
        self._need_match()
        if self.phase != "my_turn":
            raise ApiError(409, "game is over")
        if body["stateId"] != self.s["stateId"]:
            raise ApiError(200, "stale", stateId=self.s["stateId"])
        action = next((a for a in self._list_actions() if a["id"] == body["id"]), None)
        if action is None:
            raise ApiError(200, "unknown action id")
        if action["k"] == "move":
            return self._move(action, body.get("to"), full)
        if action["k"] == "research":
            return self._research(action, full)
        return self.end_turn()  # endTurn

    def end_turn(self):
        self._need_match()
        if self.phase != "my_turn":
            raise ApiError(409, "game is over")
        self.s["me"]["stars"] += self.s["me"]["income"]
        self.s["turn"] += 1
        for u in self.s["units"]:
            u["moved"] = False
            u["attacked"] = False
        self._bump()
        self._update_score()
        if self.s["turn"] >= self.max_turns:
            self.phase = "game_over"
        return {"ok": True, "phase": self.phase, "turn": self.s["turn"],
                "stateId": self.s["stateId"], "events": []}

    def result(self):
        if self.phase != "game_over":
            raise ApiError(409, "game is not over")
        me = self.s["me"]
        opp = {"id": 2, "tribe": OPPONENT_TRIBE, "score": self._opponent_score()}
        scores = [{"id": me["id"], "tribe": me["tribe"], "score": me["score"]}, opp]
        winner = me["id"] if me["score"] >= opp["score"] else opp["id"]
        return {"ok": True, "winner": winner, "scores": scores, "turn": self.s["turn"]}

    def quit(self):
        self.phase = "menu"
        self.s = None
        return {"ok": True, "phase": "menu"}

    # ---- helpers -------------------------------------------------------
    def _list_actions(self):
        """Ids are positions in this list, so they are only valid for the current stateId."""
        acts = []
        for u in self.s["units"]:
            if u["own"] == 1 and not u["moved"]:
                to = self._move_targets(u)
                if to:
                    acts.append({"k": "move", "u": u["id"], "to": to})
        for tech, cost in TECHS.items():
            if tech not in self.s["me"]["techs"] and self.s["me"]["stars"] >= cost:
                acts.append({"k": "research", "tech": tech, "cost": cost})
        acts.append({"k": "endTurn"})
        for i, a in enumerate(acts):
            a["id"] = i
        return acts

    def _bump(self):
        self.s["stateId"] += 1

    def _update_score(self):
        self.s["me"]["score"] = 20 * self.s["turn"] + 50 * len(self.s["me"]["techs"])

    def _opponent_score(self):
        return 25 * self.s["turn"] + 30

    def _tile(self, xy):
        for t in self.s["map"]["tiles"]:
            if t["xy"] == list(xy):
                return t
        return None

    def _terrain(self, xy):
        tile = self._tile(xy)
        if tile is not None:
            return tile["t"]
        x, y = xy
        return "Ocean" if x == 4 or y == 4 else "Field"

    def _in_bounds(self, xy):
        return 0 <= xy[0] < self.s["map"]["w"] and 0 <= xy[1] < self.s["map"]["h"]

    def _occupied(self, xy):
        return any(u["xy"] == list(xy) for u in self.s["units"])

    def _neighbors(self, xy):
        for dy in (-1, 0, 1):
            for dx in (-1, 0, 1):
                if (dx, dy) != (0, 0):
                    yield [xy[0] + dx, xy[1] + dy]

    def _move_targets(self, unit):
        return [n for n in self._neighbors(unit["xy"])
                if self._in_bounds(n) and self._terrain(n) not in BLOCKED and not self._occupied(n)]

    def _move(self, action, to, full):
        unit = next(u for u in self.s["units"] if u["id"] == action["u"])
        if to not in self._move_targets(unit):
            raise ApiError(200, "illegal target", to=to)
        unit["xy"] = list(to)
        unit["moved"] = True
        revealed = []
        for n in self._neighbors(to):
            if self._in_bounds(n) and self._tile(n) is None:
                tile = {"xy": n, "t": self._terrain(n)}
                self.s["map"]["tiles"].append(tile)
                revealed.append(tile)
        self._bump()
        events = [f"{unit['type']} {unit['id']} moved to [{to[0]},{to[1]}]", f"revealed {len(revealed)} tiles"]
        changes = {"units": [copy.deepcopy(unit)]}
        if revealed:
            changes["tiles"] = revealed
        return self._act_answer(events, changes, full)

    def _research(self, action, full):
        me = self.s["me"]
        me["stars"] -= action["cost"]
        me["techs"].append(action["tech"])
        self._update_score()
        self._bump()
        changes = {"me": {"stars": me["stars"], "techs": list(me["techs"]), "score": me["score"]}}
        return self._act_answer([f"researched {action['tech']}"], changes, full)

    def _act_answer(self, events, changes, full):
        if full:
            return {"ok": True, "stateId": self.s["stateId"], "events": events,
                    **copy.deepcopy(self.s)}
        return {"ok": True, "stateId": self.s["stateId"], "events": events, "changes": changes}


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        self._dispatch("GET")

    def do_POST(self):
        self._dispatch("POST")

    def _dispatch(self, method):
        url = urlparse(self.path)
        body = {}
        if method == "POST":
            length = int(self.headers.get("Content-Length") or 0)
            raw = self.rfile.read(length).strip() if length else b""
            if raw:
                try:
                    body = json.loads(raw)
                except ValueError:
                    return self._send(400, {"ok": False, "error": "malformed JSON"})
            if not isinstance(body, dict):
                return self._send(400, {"ok": False, "error": "body must be a JSON object"})
        query = parse_qs(url.query)
        try:
            with self.server.lock:
                status, payload = self.server.game.handle(method, url.path, body, query)
        except ApiError as e:
            status, payload = e.status, {"ok": False, "error": e.error, **e.extra}
        self._send(status, payload)

    def _send(self, status, payload):
        raw = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def log_message(self, format, *args):  # keep test output quiet
        pass


class FakeServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, address, game, family):
        self.address_family = family  # set before TCPServer creates the socket
        super().__init__(address, Handler)
        self.game = game
        self.lock = threading.Lock()

    def server_bind(self):
        if self.address_family == socket.AF_INET6:
            # dual-stack, so "localhost" works over ::1 and 127.0.0.1 alike (as HttpListener does)
            self.socket.setsockopt(socket.IPPROTO_IPV6, socket.IPV6_V6ONLY, 0)
        super().server_bind()


def make_server(port=7777, max_turns=30):
    game = FakeGame(max_turns=max_turns)
    try:
        return FakeServer(("::", port), game, socket.AF_INET6)
    except OSError:  # no IPv6 on this machine
        return FakeServer(("127.0.0.1", port), game, socket.AF_INET)


def main(argv=None):
    p = argparse.ArgumentParser(description="Fake PolyBridge API for offline harness runs.")
    p.add_argument("--port", type=int, default=7777)
    p.add_argument("--max-turns", type=int, default=30)
    args = p.parse_args(argv)
    srv = make_server(args.port, args.max_turns)
    print(f"fake PolyBridge on http://localhost:{args.port}/ (max turns {args.max_turns})", flush=True)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        srv.server_close()


if __name__ == "__main__":
    main()
