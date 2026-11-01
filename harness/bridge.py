"""Client for the PolyBridge HTTP API (spec/API.md). Standard library + requests."""
import copy
import time

import requests

DEFAULT_URL = "http://localhost:7777"


class BridgeError(Exception):
    """The game answered ok:false or an HTTP error. `data` is the parsed body, if any."""

    def __init__(self, message, status=None, data=None):
        super().__init__(message)
        self.status = status
        self.data = data or {}

    @property
    def stale(self):
        return self.data.get("error") == "stale"


class Bridge:
    my_seat = 0   # Pass & Play: the seat this client plays (see seat())

    def __init__(self, base_url=DEFAULT_URL, timeout=10, long_timeout=150, session=None):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout            # status, state, actions, result
        self.long_timeout = long_timeout  # newgame, act, end_turn, quit wait for the game
        self.session = session or requests.Session()

    def _call(self, method, path, body=None, timeout=None, params=None):
        try:
            r = self.session.request(method, self.base_url + path, json=body, params=params,
                                     timeout=timeout or self.timeout)
        except requests.RequestException as e:
            raise BridgeError(f"{method} {path}: {e}") from e
        try:
            data = r.json()
        except ValueError:
            raise BridgeError(f"{method} {path}: HTTP {r.status_code}, body is not JSON", status=r.status_code)
        if r.status_code >= 400 or not data.get("ok"):
            raise BridgeError(f"{method} {path}: {data.get('error', 'failed')}", status=r.status_code, data=data)
        return data

    def status(self):
        return self._call("GET", "/status")

    def newgame(self, **opts):
        """opts: mode, difficulty, opponents, mapSize, tribe (see spec). Empty = server defaults."""
        return self._call("POST", "/newgame", body=opts, timeout=self.long_timeout)

    def state(self):
        return self._call("GET", "/state")

    def actions(self):
        return self._call("GET", "/actions")

    def act(self, state_id, id, to=None, full=False):
        body = {"stateId": state_id, "id": id}
        if to is not None:
            body["to"] = to
        return self._call("POST", "/act", body=body, timeout=self.long_timeout,
                          params={"full": 1} if full else None)

    def end_turn(self, wait=300):
        """Ends the turn and waits up to `wait` s for the CPUs (3 Hard CPUs late in a game can take minutes)."""
        return self._call("POST", "/end_turn", body={}, timeout=wait + 30, params={"timeout": wait})

    def resume(self, wait=300):
        """Load the single-player autosave from the menu and wait until it is our turn (or the game is over)."""
        return self._call("POST", "/resume", body={}, timeout=wait + 30, params={"timeout": wait})

    def wait_ready(self, max_s=1800, poll=3):
        """Wait while the game is busy (CPU turns, animations). Returns the last /status.
        "my_turn" must hold on two polls a second apart: right after the CPUs move the game can look ready for a
        moment and then go busy again (a popup or animation)."""
        end = time.time() + max_s
        while True:
            st = self.status()
            if self.my_seat and st["phase"] == "my_turn" and st.get("current") != self.my_seat:
                st = {**st, "phase": "busy"}   # another model's seat
            if st["phase"] == "my_turn":
                time.sleep(1)
                again = self.status()
                if self.my_seat and again.get("current") != self.my_seat:
                    again = {**again, "phase": "busy"}
                if again["phase"] == "my_turn" or time.time() > end:
                    return again
                st = again
            if st["phase"] not in ("busy", "loading", "my_turn") or time.time() > end:
                return st
            time.sleep(poll)

    def seat(self, seat, start_delay=None):
        """Pass & Play: this client plays `seat` (a player number). The bridge reports my_turn on any model seat, so
        wait_ready also checks that the current player is ours (another model may play another seat)."""
        self.my_seat = seat
        body = {"seat": seat} if start_delay is None else {"seat": seat, "startDelay": start_delay}
        return self._call("POST", "/seat", body=body)

    def recover(self):
        """The game sometimes hangs 'busy' in a CPU turn (seen after resuming a swapped-in save); reloading the
        autosave from the menu clears it."""
        self.quit()
        time.sleep(3)
        return self.resume()

    def turn_view(self, tries=10, stuck_s=420, recoveries=2):
        """(status, state, actions) once it is our turn, retrying if the game goes busy between the calls and
        reloading the autosave if it stays busy for `stuck_s`. state/actions are None when the game is not on our
        turn (e.g. game over)."""
        for _ in range(tries):
            st = self.wait_ready(max_s=stuck_s)
            if st["phase"] == "busy" and recoveries > 0:
                recoveries -= 1
                self.recover()
                continue
            if st["phase"] != "my_turn":
                return st, None, None
            try:
                return st, self.state(), self.actions()
            except BridgeError as e:
                if "not ready" not in str(e):
                    raise
                time.sleep(2)
        raise BridgeError("game kept going busy while reading the turn")

    def result(self):
        return self._call("GET", "/result")

    def quit(self):
        return self._call("POST", "/quit", body={}, timeout=self.long_timeout)


    def resolve_forced(self, max_steps=5):
        """Pick the first option of any pending forced choice (city reward), so a turn can end.
        Only for when the harness must end the turn itself; returns the actions picked."""
        picked = []
        for _ in range(max_steps):
            a = self.actions()
            if not a.get("forced"):
                break
            opt = next((x for x in a["actions"] if x["k"] != "endTurn"), None)
            if opt is None:
                break
            self.act(a["stateId"], opt["id"])
            picked.append(opt)
        return picked


def apply_changes(state, changes):
    """Return a new full state dict with an /act `changes` block merged in. The input is not modified.

    - me: merged field by field.
    - units (by id), tiles (by xy, inside map), cities (by xy), opponents (by id): replaced or appended.
    - removedUnits: unit ids dropped.
    - any other key: replaced wholesale (the block holds full objects).
    stateId is not touched; the caller takes it from the act response.
    """
    out = copy.deepcopy(state)
    for key, value in changes.items():
        if key == "me":
            out["me"] = {**out.get("me", {}), **value}
        elif key == "units":
            out["units"] = _merge_by(out.get("units", []), value, lambda o: o["id"])
        elif key == "removedUnits":
            gone = set(value)
            out["units"] = [u for u in out.get("units", []) if u["id"] not in gone]
        elif key == "tiles":
            out.setdefault("map", {})
            out["map"]["tiles"] = _merge_by(out["map"].get("tiles", []), value, lambda o: tuple(o["xy"]))
        elif key == "cities":
            out["cities"] = _merge_by(out.get("cities", []), value, lambda o: tuple(o["xy"]))
        elif key == "opponents":
            out["opponents"] = _merge_by(out.get("opponents", []), value, lambda o: o["id"])
        else:
            out[key] = copy.deepcopy(value)
    return out


def _merge_by(current, new_items, key):
    """Replace items with the same key, append new ones; keeps the existing order."""
    index = {key(item): i for i, item in enumerate(current)}
    merged = list(current)
    for item in new_items:
        item = copy.deepcopy(item)
        k = key(item)
        if k in index:
            merged[index[k]] = item
        else:
            index[k] = len(merged)
            merged.append(item)
    return merged
