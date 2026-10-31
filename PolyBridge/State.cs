using System;
using System.Collections.Generic;
using Polytopia.Data;
using PolytopiaBackendBase.Game;

namespace PolyBridge;

using D = Dictionary<string, object>;

// A fog-respecting snapshot of everything /state reports, kept as objects so /act can diff two snapshots.
public class Snap
{
    public int Turn, MaxTurns, W, H;
    public D Me = new();
    public List<D> Opponents = new();
    public SortedDictionary<int, D> Tiles = new();     // by tile index
    public SortedDictionary<int, D> Cities = new();    // by tile index
    public SortedDictionary<uint, D> Units = new();    // by unit id
    public List<int[]> Villages = new(), Ruins = new();
}

public static partial class Api
{
    static int stateId;
    static long lastKey = -1;

    // Bumps whenever the game's command counter or turn changes (any state change).
    public static int StateId(GameState gs)
    {
        long key = ((long)gs.CurrentTurn << 32) | gs.CurrentCommand;
        if (key != lastKey) { lastKey = key; stateId++; }
        return stateId;
    }

    public static int[] Xy(WorldCoordinates c) => new[] { (int)c.X, (int)c.Y };

    static string Name(object o) => o?.ToString() ?? "";

    public static Snap Snapshot(GameState gs)
    {
        var me = GameManager.LocalPlayer;
        byte pid = me.Id;
        var s = new Snap { Turn = (int)gs.CurrentTurn, MaxTurns = TurnLimit(gs), W = gs.Map.Width, H = gs.Map.Height };
        var tiles = gs.Map.Tiles;
        // Cities: (tile coords -> own units supported) for the unit counter.
        var homeCount = new Dictionary<long, int>();
        var units = new List<(TileData t, UnitState u)>();
        for (int i = 0; i < tiles.Length; i++)
        {
            var t = tiles[i];
            if (!t.GetExplored(pid)) continue;
            var u = t.GetUnit(gs, pid, false);
            if (u != null) units.Add((t, u));
        }
        foreach (var (t, u) in units)
            if (u.owner == pid) { long k = u.home.X * 1000L + u.home.Y; homeCount[k] = homeCount.GetValueOrDefault(k) + 1; }

        int income = 0;
        for (int i = 0; i < tiles.Length; i++)
        {
            var t = tiles[i];
            if (!t.GetExplored(pid)) continue;
            var xy = Xy(t.coordinates);
            var d = new D { ["xy"] = xy, ["t"] = Name(t.terrain) };
            if (t.owner != 0) d["own"] = (int)t.owner;
            var res = t.GetResource(gs, pid);
            if (res != null && Name(res.type) != "None") d["res"] = Name(res.type);
            if (t.HasRoad) d["road"] = true;
            if (t.effects != null && t.effects.Count > 0)
            {
                var e = new List<string>();
                for (int j = 0; j < t.effects.Count; j++) e.Add(Name(t.effects[j]));
                d["eff"] = e;
            }
            var imp = t.improvement;
            if (imp != null)
            {
                var it = Name(imp.type);
                if (it == "City")
                {
                    if (t.owner == 0) { s.Villages.Add(xy); }
                    else
                    {
                        var c = new D { ["xy"] = xy, ["own"] = (int)t.owner };
                        if (!string.IsNullOrEmpty(imp.name)) c["name"] = imp.name;
                        if (t.capitalOf != 0) c["cap"] = true;
                        c["lvl"] = (int)imp.level;
                        if (t.owner == pid)
                        {
                            c["pop"] = (int)imp.population;
                            c["popMax"] = (int)imp.level + 1;
                            c["units"] = homeCount.GetValueOrDefault(xy[0] * 1000L + xy[1]);
                            income += t.CalculateRawProduction(gs);
                        }
                        s.Cities[i] = c;
                    }
                }
                else if (it == "Ruin" || it == "Ruins") s.Ruins.Add(xy);
                else if (it != "None") d["imp"] = it;
            }
            s.Tiles[i] = d;
        }
        foreach (var (t, u) in units)
        {
            var d = new D { ["id"] = (long)u.id, ["type"] = Name(u.type), ["own"] = (int)u.owner, ["xy"] = Xy(u.coordinates) };
            d["hp"] = u.health / 10f;
            d["hpMax"] = u.GetMaxHealth(gs) / 10f;
            if (u.promotionLevel > 0) d["vet"] = true;
            if (u.owner == pid)
            {
                // kills toward veteran (the unit card's "1/3 to become a veteran"); none for static units
                try { int lim = u.UnitData.getPromotionLimit(GameManager.LocalPlayer, gs); if (u.promotionLevel == 0 && lim > 0) { d["kills"] = (int)u.xp; d["killsVet"] = lim; } } catch { }
                if (u.moved) d["moved"] = true;
                if (u.attacked) d["attacked"] = true;
            }
            if (u.effects != null && u.effects.Count > 0)
            {
                var e = new List<string>();
                for (int j = 0; j < u.effects.Count; j++) e.Add(Name(u.effects[j]));
                d["fx"] = e;
            }
            s.Units[u.id] = d;
        }

        var techs = new List<string>();
        if (me.availableTech != null) for (int i = 0; i < me.availableTech.Count; i++) techs.Add(Name(me.availableTech[i]));
        s.Me = new D { ["id"] = (int)pid, ["tribe"] = Name(me.tribe), ["stars"] = me.Currency, ["income"] = income, ["score"] = (long)me.score, ["techs"] = techs };
        if (me.knownPlayers != null)
            for (int i = 0; i < me.knownPlayers.Count; i++)
            {
                if (gs.TryGetPlayer(me.knownPlayers[i], out var op) && op.Id != pid && op.Id != 255)
                {
                    var od = new D { ["id"] = (int)op.Id, ["tribe"] = Name(op.tribe), ["score"] = (long)op.score };
                    try
                    {
                        if (op.killedTurn > 0) od["out"] = true;
                        else if (PlayerDiplomacyExtensions.HasPeaceWith(me, op.Id)) od["rel"] = "peace";
                        else if (PlayerDiplomacyExtensions.HasCoolDownWith(me, op.Id)) od["rel"] = "cooldown";
                    }
                    catch { }
                    s.Opponents.Add(od);
                }
            }
        return s;
    }

    static D FullState(GameState gs, Snap s)
    {
        var d = new D { ["ok"] = true, ["stateId"] = StateId(gs), ["turn"] = s.Turn };
        if (s.MaxTurns > 0) d["maxTurns"] = s.MaxTurns;
        d["me"] = s.Me;
        if (s.Opponents.Count > 0) d["opponents"] = s.Opponents;
        d["map"] = new D { ["w"] = s.W, ["h"] = s.H, ["tiles"] = s.Tiles.Values };
        d["cities"] = s.Cities.Values;
        if (s.Villages.Count > 0) d["villages"] = s.Villages;
        d["units"] = s.Units.Values;
        if (s.Ruins.Count > 0) d["ruins"] = s.Ruins;
        return d;
    }

    static Reply State(Request r)
    {
        var gs = Gs();
        if (gs == null) return Reply.Err("not in a match", 409);
        return Reply.Ok(FullState(gs, Snapshot(gs)));
    }

    // Everything in `after` that differs from `before`, as full objects (spec: /act changes).
    public static D Diff(Snap before, Snap after)
    {
        var ch = new D();
        if (PJson.Write(before.Me) != PJson.Write(after.Me)) ch["me"] = after.Me;
        var units = new List<D>(); var gone = new List<long>();
        foreach (var kv in after.Units)
            if (!before.Units.TryGetValue(kv.Key, out var old) || PJson.Write(old) != PJson.Write(kv.Value)) units.Add(kv.Value);
        foreach (var kv in before.Units) if (!after.Units.ContainsKey(kv.Key)) gone.Add(kv.Key);
        if (units.Count > 0) ch["units"] = units;
        if (gone.Count > 0) ch["removedUnits"] = gone;
        var tiles = new List<D>();
        foreach (var kv in after.Tiles)
            if (!before.Tiles.TryGetValue(kv.Key, out var old) || PJson.Write(old) != PJson.Write(kv.Value)) tiles.Add(kv.Value);
        if (tiles.Count > 0) ch["tiles"] = tiles;
        var cities = new List<D>();
        foreach (var kv in after.Cities)
            if (!before.Cities.TryGetValue(kv.Key, out var old) || PJson.Write(old) != PJson.Write(kv.Value)) cities.Add(kv.Value);
        if (cities.Count > 0) ch["cities"] = cities;
        var rc = new List<int[]>();
        foreach (var c in before.Cities.Keys) if (!after.Cities.ContainsKey(c)) rc.Add(Xy(before.Tiles.TryGetValue(c, out var td) ? CoordOf(td) : new WorldCoordinates(0, 0)));
        if (rc.Count > 0) ch["removedCities"] = rc;
        if (PJson.Write(before.Villages) != PJson.Write(after.Villages)) ch["villages"] = after.Villages;
        if (PJson.Write(before.Ruins) != PJson.Write(after.Ruins)) ch["ruins"] = after.Ruins;
        if (PJson.Write(before.Opponents) != PJson.Write(after.Opponents)) ch["opponents"] = after.Opponents;
        return ch;
    }

    static WorldCoordinates CoordOf(D tile) { var xy = (int[])tile["xy"]; return new WorldCoordinates(xy[0], xy[1]); }
}
