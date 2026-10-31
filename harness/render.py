"""Compact text rendering of /state, /actions and /act results for the model."""
import json
import re
from pathlib import Path

TERRAIN = {"Field": ".", "Forest": "F", "Mountain": "M", "Water": "~", "Ocean": "O"}


_REF = Path(__file__).resolve().parent.parent / "reference" / "units.json"
try:
    OTHER_UNITS = json.loads(_REF.read_text(encoding="utf-8"))   # written by reference/gen_reference.py
except (OSError, ValueError):
    OTHER_UNITS = {"units": {}, "skills": {}, "explained": []}


def other_unit_types(units):
    """Stats (same columns as the rules' unit table) for visible unit types the rules don't list, plus their unexplained skills."""
    lines, skills = [], set()
    for t in sorted({u["type"] for u in units}):
        line = OTHER_UNITS["units"].get(re.sub(r"[^a-z0-9]", "", t.lower()))
        if line:
            lines.append(line)
            skills |= set(line.rsplit(" ", 1)[-1].split(",")) - set(OTHER_UNITS["explained"]) - {"-"}
    if not lines:
        return ""
    s = "Unit types not in the rules (unit cost hp atk def move range skills): " + "; ".join(lines)
    known = [f"{k}: {OTHER_UNITS['skills'][k]}" for k in sorted(skills) if k in OTHER_UNITS["skills"]]
    return s + (". Skills: " + " ".join(known) if known else "")


def _xy(p):
    return f"({p[0]},{p[1]})"


def _moves(points):
    """Destinations sorted by row, runs of x merged: (0-1,9)(0-1,10)(1,13) = x 0 to 1 at y 9, ..."""
    rows = {}
    for x, y in points:
        rows.setdefault(y, []).append(x)
    out = []
    for y in sorted(rows):
        xs = sorted(rows[y]); start = prev = xs[0]
        for x in xs[1:] + [None]:
            if x is not None and x == prev + 1:
                prev = x; continue
            out.append(f"({start},{y})" if start == prev else f"({start}-{prev},{y})")
            if x is not None:
                start = prev = x
    return "".join(out)


def _hp(h):
    return str(int(h)) if float(h).is_integer() else str(h)


def _tile_index(state):
    return {tuple(t["xy"]): t for t in state["map"].get("tiles", [])}


def render_grid(state):
    w, h = state["map"]["w"], state["map"]["h"]
    tiles = _tile_index(state)
    me = state["me"]["id"]
    over = {}
    for v in state.get("villages", []):
        over[tuple(v)] = "v"
    for r in state.get("ruins", []):
        over[tuple(r)] = "r"
    for c in state.get("cities", []):
        over[tuple(c["xy"])] = "C" if c.get("own") == me else "X"
    for u in state.get("units", []):
        over[tuple(u["xy"])] = "u" if u.get("own") == me else "e"
    rows = ["   " + "".join(str(x % 10) for x in range(w))]
    for y in range(h):
        line = []
        for x in range(w):
            if (x, y) in over:
                line.append(over[(x, y)])
            elif (x, y) in tiles:
                t = tiles[(x, y)]["t"]
                line.append(TERRAIN.get(t, t[0].lower()))
            else:
                line.append("?")
        rows.append(f"{y:>2} " + "".join(line))
    return "\n".join(rows)


def unit_line(u, me, terrain=None):
    mine = u.get("own") == me
    flags = ["vet"] if u.get("vet") else []
    if mine:
        flags += [f for f in ("moved", "attacked") if u.get(f)]
    flags += [str(e) for e in u.get("fx", [])]
    if mine and "killsVet" in u:
        flags.append(f"kills {u.get('kills', 0)}/{u['killsVet']}")
    s = f"{'U' if mine else 'E'}{u['id']} {u['type']} {_xy(u['xy'])} {_hp(u['hp'])}/{_hp(u['hpMax'])}hp"
    if terrain and terrain != "Field":
        s += f" on {terrain}"
    if flags:
        s += " [" + ",".join(flags) + "]"
    return s


def render_state(state, offered=frozenset()):
    """`offered`: tiles that have a build action (their resource shows up there, so it is not repeated here)."""
    me = state["me"]
    me_id = me["id"]
    tiles = _tile_index(state)
    out = []
    def rival(o):
        s = f"{o['tribe']} {o['score']}" if "score" in o else o["tribe"]
        rel = {"peace": "at peace", "cooldown": "peace treaty recently broken"}.get(o.get("rel"), o.get("rel"))
        return s + (" (eliminated)" if o.get("out") else f" ({rel})" if rel else "")
    opp = ", ".join(rival(o) for o in state.get("opponents", []))
    inc = f" (+{me['income']}/turn)" if "income" in me else ""
    out.append(f"Turn {state['turn']}/{state.get('maxTurns', '?')} | {me['tribe']} | stars {me['stars']}{inc} | "
               f"score {me.get('score', '?')}" + (f" | rivals: {opp}" if opp else ""))
    out.append("Techs: " + (", ".join(me.get("techs", [])) or "none"))
    out.append(render_grid(state))
    cities = state.get("cities", [])
    mine = [c for c in cities if c.get("own") == me_id]
    on_tile = {tuple(u["xy"]): u for u in state.get("units", [])}
    for c in mine:
        lvl = c["lvl"]
        # the game's population is a running total: level L+1 is reached at (L+1)(L+2)/2 - 1
        pop = f" pop {c['pop']} (lvl{lvl + 1} at {(lvl + 1) * (lvl + 2) // 2 - 1})" if "pop" in c else ""
        line = (f"City {c['name']} {_xy(c['xy'])} lvl{lvl}" + (" capital" if c.get("cap") else "")
                + pop + f" units {c.get('units', 0)}/{lvl + 1}")
        u = on_tile.get(tuple(c["xy"]))
        if u:
            line += f", tile occupied by {'U' if u.get('own') == me_id else 'E'}{u['id']}"
        out.append(line)
    for c in cities:
        if c.get("own") != me_id:
            out.append(f"Enemy city {c.get('name', '?')} {_xy(c['xy'])} lvl{c.get('lvl', '?')}")
    own_units = [u for u in state.get("units", []) if u.get("own") == me_id]
    en_units = [u for u in state.get("units", []) if u.get("own") != me_id]
    if own_units:
        out.append("My units: " + "; ".join(unit_line(u, me_id, tiles.get(tuple(u["xy"]), {}).get("t")) for u in own_units))
    if en_units:
        out.append("Visible enemies: " + "; ".join(unit_line(u, me_id, tiles.get(tuple(u["xy"]), {}).get("t")) for u in en_units))
    other = other_unit_types(state.get("units", []))
    if other:
        out.append(other)
    if state.get("villages"):
        out.append("Villages: " + " ".join(_xy(v) for v in state["villages"]))
    if state.get("ruins"):
        out.append("Ruins: " + " ".join(_xy(v) for v in state["ruins"]))
    centres = [tuple(c["xy"]) for c in mine]
    feats = []
    for t in state["map"].get("tiles", []):
        near = t.get("own") == me_id or any(max(abs(t["xy"][0] - cx), abs(t["xy"][1] - cy)) <= 2 for cx, cy in centres)
        if near and (t.get("res") or t.get("imp")) and not (t.get("res") and not t.get("imp") and tuple(t["xy"]) in offered):
            s = f"{_xy(t['xy'])} {t['t']}"
            if t.get("res"):
                s += f" {t['res']}"
            if t.get("imp"):
                s += f" +{t['imp']}"
            feats.append(s)
    if feats:
        out.append("Resources/buildings near my cities: " + "; ".join(feats))
    return "\n".join(out)


def render_actions(actions, state):
    """Group the action list by unit/city. `actions` is the /actions answer (or its list)."""
    forced = isinstance(actions, dict) and actions.get("forced")
    acts = actions["actions"] if isinstance(actions, dict) else actions
    me = state["me"]["id"]
    tiles = _tile_index(state)
    units = {u["id"]: u for u in state.get("units", [])}
    cities = {tuple(c["xy"]): c for c in state.get("cities", [])}
    by_unit, by_city, misc = {}, {}, []
    for a in acts:
        k = a["k"]
        if k == "endTurn":
            continue
        if "u" in a:
            by_unit.setdefault(a["u"], []).append(a)
        elif "city" in a and k in ("train", "reward"):
            by_city.setdefault(tuple(a["city"]), []).append(a)
        else:
            misc.append(a)
    lines = ["FORCED CHOICE PENDING: pick one option below before any other action; end_turn is refused until you do."] if forced else []
    for uid, group in by_unit.items():
        u = units.get(uid)
        head = f"U{uid} {u['type']} {_xy(u['xy'])}" if u else f"U{uid}"   # hp and status are in the state's unit list
        parts = []
        for a in group:
            k = a["k"]
            if k == "move":
                parts.append("move→" + _moves(a["to"]) + f" [#{a['id']}]")
            elif k == "attack":
                s = f"attack {_xy(a['to'])} dmg{_hp(a.get('dmg', '?'))} ret{_hp(a['ret']) if a.get('ret') else '0'}"
                parts.append(s + (" KILL" if a.get("kill") else "") + f" [#{a['id']}]")
            elif k == "capture":
                parts.append("capture" + (f" {_xy(a['at'])}" if "at" in a else "") + f" [#{a['id']}]")
            else:
                parts.append(f"{a.get('cmd', k)} [#{a['id']}]")
        lines.append(f"{head}: " + "; ".join(parts))
    for xy, group in by_city.items():
        name = cities.get(xy, {}).get("name", "")
        parts = [f"train {a['unit']} {a['cost']}⭐ [#{a['id']}]" if a["k"] == "train"
                 else f"REWARD {a['reward']} [#{a['id']}]" for a in group]
        lines.append(f"City {name} {_xy(xy)}: " + "; ".join(parts))
    # one line per building/ability type, so a change only reprints that type's line
    groups = {}
    for a in misc:
        if a["k"] == "build":
            groups.setdefault(("Build", a["imp"], a.get("cost")), []).append(a)
        elif a["k"] == "ability":
            groups.setdefault(("Ability", a["cmd"], a.get("cost")), []).append(a)
    for (kind, what, cost), group in groups.items():
        price = f" {cost}⭐" if cost is not None else ""
        lines.append(f"{kind} {what}{price}: " + " ".join(f"{_xy(a['at'])}[#{a['id']}]" for a in group))
    res = [a for a in misc if a["k"] == "research"]
    if res:
        lines.append("Research: " + "; ".join(f"{a['tech']} {a['cost']}⭐ [#{a['id']}]" for a in res))
    peace = [a for a in misc if a["k"] == "peace"]
    if peace:
        lines.append(f"Peace offer from {peace[0]['with']}: " + "; ".join(
            f"{'ACCEPT' if a['accept'] else 'DECLINE'} [#{a['id']}]" for a in peace))
    dip = [a for a in misc if a["k"] == "diplomacy"]
    if dip:
        lines.append("Diplomacy: " + "; ".join(f"{a['cmd']} with {a['with']} [#{a['id']}]" for a in dip))
    for a in misc:
        if a["k"] not in ("build", "ability", "research", "peace", "diplomacy"):
            lines.append(f"{a['k']} " + " ".join(f"{k}={v}" for k, v in a.items() if k not in ("id", "k")) + f" [#{a['id']}]")
    return "\n".join(lines) if lines else "(no actions left; call end_turn)"


def render_changes(res, me_id=1):
    """Short summary of an /act answer."""
    out = list(res.get("events", []))
    ch = res.get("changes", {})
    if "me" in ch:
        out.append("me: " + ", ".join(f"{k} {','.join(v) if isinstance(v, list) else v}" for k, v in ch["me"].items()))
    for u in ch.get("units", []):
        out.append(unit_line(u, me_id))
    if ch.get("removedUnits"):
        out.append("removed units: " + ",".join(map(str, ch["removedUnits"])))
    if ch.get("cities"):
        out.append("cities: " + "; ".join(f"{c.get('name', '')} {_xy(c['xy'])} lvl{c.get('lvl', '?')}" for c in ch["cities"]))
    if ch.get("tiles"):
        out.append(f"{len(ch['tiles'])} tiles changed/revealed")
    return "\n".join(out)


def render_events(events, limit=25):
    if not events:
        return "nothing seen"
    s = "\n".join("- " + e for e in events[:limit])
    return s + (f"\n- ... {len(events) - limit} more" if len(events) > limit else "")


def _build_tiles(actions):
    acts = actions["actions"] if isinstance(actions, dict) else actions
    return frozenset(tuple(a["at"]) for a in acts if a.get("k") == "build" and "at" in a)


def turn_prompt(state, actions, turn, max_turns, plan, events):
    left = (max_turns - turn) if max_turns else "?"
    return (f"# Turn {turn} of {max_turns} ({left} turns left after this one)\n\n"
            f"## Your last plan\n{plan or '(none yet: first turn)'}\n\n"
            f"## Since your last turn\n{render_events(events)}\n\n"
            f"## State\n{render_state(state, _build_tiles(actions))}\n\n"
            f"## Legal actions\n{render_actions(actions, state)}\n\n"
            "Play your turn with `act`, then finish with `end_turn(plan)`.")
