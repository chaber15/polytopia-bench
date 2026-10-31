"""Build the model's game reference from this build's own data (GameLogicData28.json) and English UI text (loc-en.tsv).

Usage: python gen_reference.py <GameLogicData28.json> <loc-en.tsv> [units.json [tribes.md]] > reference.md
units.json (optional output): stats and skill text for units not in the reference, which the harness shows
in the state only when such a unit is visible.
Everything a human can read in the tech tree and unit cards: what each tech unlocks, what each building does,
every unit's stats and skills, veterans, city level rewards, monuments.
"""
import json, re, sys

data = json.load(open(sys.argv[1], encoding="utf-8"))
loc = {}
for line in open(sys.argv[2], encoding="utf-8"):
    k, _, v = line.rstrip("\n").partition("\t")
    loc[k] = v.replace("\\n", " ")

U, T, I = data["unitData"], data["techData"], data["improvementData"]
CAMEL = {}  # enum names as the state/actions print them

def enum(n):
    """lower-case data key -> the game's enum name (as the harness prints it)."""
    special = {"mindbender": "MindBender", "freespirit": "FreeSpirit", "lumberhut": "LumberHut", "foresttemple": "ForestTemple",
               "mountaintemple": "MountainTemple", "watertemple": "WaterTemple", "icetemple": "IceTemple", "customshouse": "CustomsHouse",
               "transportship": "Transportship", "scoutship": "Scoutship", "rammership": "Rammership", "bombership": "Bombership",
               "battlesled": "BattleSled", "icefortress": "IceFortress", "icearcher": "IceArcher", "dragonegg": "DragonEgg",
               "babydragon": "BabyDragon", "firedragon": "FireDragon", "aquafarm": "AquaFarm", "starfishing": "Starfishing",
               "clearforest": "ClearForest", "burnforest": "BurnForest", "growforest": "GrowForest", "harvestfruit": "HarvestFruit",
               "peacetreaty": "PeaceTreaty", "capitalvision": "CapitalVision", "cloak_boat": "CloakBoat",
               "mermaidwarrior": "MermaidWarrior", "mermaidarcher": "MermaidArcher", "mermaidswordsman": "MermaidSwordsman",
               "mermaiddefender": "MermaidDefender", "mermaidcloak": "MermaidCloak", "mermaiddagger": "MermaidDagger"}
    return special.get(n, n[:1].upper() + n[1:])

def name(kind, n):
    disp = loc.get(f"{kind}.names.{n}")
    e = enum(n)
    return e if not disp or disp.replace(" ", "").lower() == n else f"{e} ({disp})"

def hp(v): return f"{v/10:g}"

def skill_text(s):
    return loc.get(f"tooltip.ability.{s}", "")

# ---- techs reachable for a regular tribe (from 'basic'), with tier
tier, order, queue = {"basic": 0}, [], ["basic"]
while queue:
    t = queue.pop(0); order.append(t)
    for c in T[t].get("techUnlocks", []):
        if c not in tier:
            tier[c] = tier[t] + 1; queue.append(c)

EFFECT = {"clearforest": "forest becomes field", "burnforest": "forest becomes field with crop",
          "growforest": "field becomes forest"}
ABILITY_TEXT = {"literacy": "all techs cost 33% less", "peacetreaty": "offer a peace treaty with the `diplomacy` action PeaceTreaty",
                "disband": "remove one of your units for half its cost back", "destroy": "remove a building in your territory"}

def imp_line(n):
    d = I[n]; parts = []
    if d.get("cost"): parts.append(f"{d['cost']}★")
    req = d.get("terrainRequirements", [])
    if req:
        parts.append("on " + "/".join(r.get("terrain") or r.get("resource") or r.get("improvement") or "?" for r in req))
    adj = d.get("adjacencyRequirements")
    if adj: parts.append("next to " + "/".join(a["improvement"] for a in adj))
    rw = (d.get("rewards") or [{}])[0]
    eff = []
    if rw.get("population"): eff.append(f"+{rw['population']} pop")
    if rw.get("score"): eff.append(f"+{rw['score']} score")
    if rw.get("currency"): eff.append(f"+{rw['currency']}★")
    g = (d.get("growthRewards") or [{}])[0]
    if g.get("population") and d.get("adjacencyImprovements"):
        eff.append(f"+{g['population']} pop per adjacent " + "/".join(a["improvement"] for a in d["adjacencyImprovements"]))
    if g.get("score"): eff.append(f"+{g['score']} score every {d.get('growthRate', '?')} turns (max level {d.get('maxLevel')})")
    if n in EFFECT: eff.append(EFFECT[n])
    if n == "market": eff.append("+1★/turn per level from adjacent Windmill/Forge/Sawmill")
    abil = [loc.get(f"building.ability.{a}", "") for a in d.get("improvementAbilities", []) if a not in ("patina", n)]
    abil = [re.sub(r"\{\d\}", name("building", n).split(" (")[0], a) for a in abil if a]
    txt = re.sub(r"\{\d\} ?", "", loc.get(f"building.ability.{n}", "")).strip()
    txt = txt[:1].upper() + txt[1:]
    s = name("building", n) + ": " + ", ".join(parts)
    if eff: s += " → " + ", ".join(eff)
    extra = " ".join(dict.fromkeys(x for x in [txt] + abil if x))
    return s + (f". {extra}" if extra else "")

out = []
out.append("# Tech tree (tier: tech → what it unlocks)")
for t in order:
    if t == "basic": continue
    d = T[t]; bits = []
    if d.get("unitUnlocks"): bits.append("units " + ", ".join(name("unit", u) for u in d["unitUnlocks"]))
    if d.get("improvementUnlocks"): bits.append("build " + ", ".join(name("building", i) for i in d["improvementUnlocks"] if i in I and not I[i].get("hidden")))
    if d.get("abilityUnlocks"):
        bits.append("abilities " + ", ".join(f"{enum(a)} ({ABILITY_TEXT.get(a) or skill_text(a) or a})" for a in d["abilityUnlocks"]))
    if d.get("movementUnlocks"): bits.append("move on " + ", ".join(d["movementUnlocks"]))
    if d.get("techUnlocks"): bits.append("leads to " + ", ".join(name("technology", c) for c in d["techUnlocks"]))
    out.append(f"- {name('technology', t)} (T{tier[t]}): " + "; ".join(bits))

out.append("\n# Buildings, harvests and tile actions (what the game's build menu says)")
seen = set()
for t in order:
    for i in T[t].get("improvementUnlocks", []):
        if i in I and i not in seen and not I[i].get("hidden"):
            seen.add(i); out.append("- " + imp_line(i))

out.append("\n# Units (names as the state prints them; cost ★ or - if not trainable)")
out.append("unit cost hp atk def move range skills")
regular = ["warrior", "rider", "archer", "defender", "swordsman", "knight", "catapult", "mindbender", "cloak", "dagger", "giant",
           "transportship", "scoutship", "rammership", "bombership", "juggernaut"]
def unit_line(n):
    d = U[n]
    cost = "-" if d.get("hidden") else str(d["cost"])
    sk = [a for a in d.get("unitAbilities", []) if a not in ("land",)]
    return " ".join([enum(n), cost, hp(d["health"]), hp(d["attack"]), hp(d["defence"]), str(d["movement"]), str(d["range"]), ",".join(sk) or "-"])
for n in regular: out.append(unit_line(n))
out.append("Boats: a boat's hp is that of the unit it carries. A land unit moved onto your own Port becomes a Transportship carrying it (a Giant becomes a Juggernaut); "
           "upgrade it (unit action `Upgrade`, 5/5/15★) to Scoutship/Rammership/Bombership (only inside your territory). "
           "A Giant (super unit) spawns in a city that reaches level 5+ when you pick the SuperUnit reward. "
           "Cloak: invisible after moving; can enter enemy cities to incite revolts (its Daggers appear there).")
out.append("Other tribes' units are described in the state when you see one.")

IN_RULES = {"land", "dash", "escape", "stiff", "persist", "fortify"}   # explained in the rules section
used = sorted({a for n in regular for a in U[n].get("unitAbilities", [])} - IN_RULES)
out.append("\n# Unit skills")
out.append("; ".join(f"{a}: {skill_text(a)}" for a in used if skill_text(a)))
if len(sys.argv) > 3:
    special = [n for n in U if n not in regular and n not in ("none", "scout") and U[n].get("health")]
    json.dump({"units": {enum(n).lower(): unit_line(n) for n in special},
               "skills": {a: skill_text(a) for n in U for a in U[n].get("unitAbilities", []) if skill_text(a)},
               "explained": sorted(set(used) | IN_RULES)},
              open(sys.argv[3], "w", encoding="utf-8"), ensure_ascii=False, indent=0)

out.append("\n# Veterans, cities, connections")
out.append("- Veterans: a unit with a kill counter (`kills 2/3` in the state) can `Promote` once it reaches the limit (3 kills for most units): +5 max hp and fully healed. Units with `static` never become veterans.")
out.append("- City level rewards (forced choice on level-up): lvl2 Workshop (+1★/turn) or Explorer (reveals nearby land); lvl3 CityWall (much stronger defence for fortify units) or Resources (+5★); "
           "lvl4 PopulationGrowth (+3 pop) or BorderGrowth (bigger territory); lvl5+ Park (+1★/turn, +250 score) or SuperUnit (a Giant spawns in the city).")
out.append("- " + loc["building.ability.road"] + " Roads halve movement cost; a Port also links cities over water. Each connected city adds +1 pop to it and to the capital.")
out.append("- A city produces 1★ per level per turn (plus Workshop/Park); a city with an enemy unit on it (under siege) produces nothing.")
out.append("- Movement: forests and mountains (without roads) end a unit's move; units stop when they move next to an enemy unless they have `sneak`/`creep`.")
mon = {"monument1": "pacifist", "monument2": "genius", "monument3": "network", "monument4": "wealth", "monument5": "killer", "monument6": "metropolis", "monument7": "explorelighthouses"}
out.append("- Monuments (+3 pop, +400 score, one each; unlocked by a feat, then buildable for free): " + "; ".join(
    f"{enum(m)} ({loc.get('building.names.' + m)}): {loc.get('polyplayer.task.' + t + '.description')}" for m, t in mon.items()))
print("\n".join(out))

# ---- tribe picker sheet for the four core tribes (what the game's tribe picker and data say)
if len(sys.argv) > 4:
    TR = data["tribeData"]
    def mods(d):
        bits = []
        for kind, m in (("terrain", d.get("terrainModifier", {})), ("resources", d.get("resourceModifier", {}))):
            for k, v in m.items():
                bits.append(f"no {k}" if v == 0 else f"{'more' if v > 1 else 'less'} {k} (x{v:g})")
        return ", ".join(bits) or "standard"
    lines = []
    for t in ("xinxi", "imperius", "bardur", "oumaji"):
        d = TR[t]; nm = loc.get(f"tribes.{t}", t)
        techs = [x for x in d.get("startingTech", []) if x != "basic"]
        tech_txt = "; ".join(f"{name('technology', x)} (unlocks: " + ", ".join(
            [name('unit', u) for u in T[x].get('unitUnlocks', [])] + [name('building', i) for i in T[x].get('improvementUnlocks', []) if i in I and not I[i].get('hidden')]
            + (["move on " + ", ".join(T[x]["movementUnlocks"])] if T[x].get("movementUnlocks") else [])) + ")" for x in techs)
        desc = loc.get(f"tribes.{t}.info", "").replace("{0}", nm)
        lines.append(f"- {enum(t)} ({nm}): {desc} Starts with tech {tech_txt}; starting unit {name('unit', d['startingUnit'])}; "
                     f"{d.get('startingStars', 5)} starting stars. Home land: {mods(d)}.")
    open(sys.argv[4], "w", encoding="utf-8").write("\n".join(lines) + "\n")
