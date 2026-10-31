using System;
using System.Collections.Generic;
using Polytopia.Data;
using PolytopiaBackendBase.Game;

namespace PolyBridge;

using D = Dictionary<string, object>;

public static partial class Api
{
    class Rec
    {
        public D Json;
        public string Kind;                       // move | other
        public CommandBase Cmd;                   // for non-move
        public UnitState Unit;                    // for move
        public List<WorldCoordinates> To;         // for move
        public string Desc;
    }

    static List<Rec> recs = new();
    static int recsFor = -1;
    static bool recsForced;

    static string Cmd(CommandBase c) => Name(c.GetCommandType());

    static bool Valid(CommandBase c, GameState gs) { try { return c.IsValid(gs, out _); } catch { return false; } }

    static void Add(D d, string desc, CommandBase cmd)
    {
        d["id"] = recs.Count;
        recs.Add(new Rec { Json = d, Kind = "other", Cmd = cmd, Desc = desc });
    }

    static int UnitCost(GameState gs, UnitData.Type t) { return gs.GameLogicData.TryGetData(t, out UnitData ud) ? ud.cost : 0; }
    static int ImpCost(GameState gs, ImprovementData.Type t) { return gs.GameLogicData.TryGetData(t, out ImprovementData id) ? id.cost : 0; }

    public static void BuildRecs(GameState gs)
    {
        recs = new List<Rec>();
        recsFor = StateId(gs);
        recsForced = false;
        var me = GameManager.LocalPlayer; byte pid = me.Id;

        // Forced: a pending command trigger (e.g. city level-up reward) is the only thing that may happen.
        CommandBase trig = null;
        bool has = false;
        try { has = CommandTriggerUtils.TryGetTriggerCommand(gs, out trig); } catch { }
        if (has && trig != null)
        {
            recsForced = true;
            var cr = trig.TryCast<CityRewardCommand>();
            if (cr != null)
            {
                var tile = gs.Map.GetTile(cr.Coordinates);
                var rewards = tile?.improvement?.rewards;
                var seen = new HashSet<string>();
                if (rewards != null)
                    for (int i = 0; i < rewards.Count; i++)
                    {
                        var rc = new CityRewardCommand(pid, rewards[i], cr.Coordinates);
                        if (!Valid(rc, gs) || !seen.Add(Name(rewards[i]))) continue;
                        Add(new D { ["k"] = "reward", ["city"] = Xy(cr.Coordinates), ["reward"] = Name(rewards[i]) }, "chose reward " + Name(rewards[i]), rc);
                    }
                if (recs.Count == 0) Add(new D { ["k"] = "reward", ["city"] = Xy(cr.Coordinates), ["reward"] = Name(cr.Reward) }, "chose reward " + Name(cr.Reward), trig);
            }
            var pr = trig.TryCast<PeaceRequestResponseCommand>();
            if (pr != null)
            {
                // A CPU offers peace: the model answers yes or no (the trigger alone would only ever accept).
                string who = gs.TryGetPlayer(pr.OpponentId, out var po) ? Name(po.tribe) : "opponent";
                foreach (var yes in new[] { true, false })
                {
                    var pc = new PeaceRequestResponseCommand(pid, pr.OpponentId, yes);
                    if (Valid(pc, gs)) Add(new D { ["k"] = "peace", ["with"] = who, ["accept"] = yes }, (yes ? "accepted" : "declined") + " peace with " + who, pc);
                }
            }
            if (recs.Count == 0) Add(new D { ["k"] = "trigger", ["cmd"] = Cmd(trig) }, "trigger " + Cmd(trig), trig);
            return;
        }

        var tiles = gs.Map.Tiles;
        // Units: moves, attacks, other unit actions
        for (int i = 0; i < tiles.Length; i++)
        {
            var t = tiles[i];
            if (!t.GetExplored(pid)) continue;
            var u = t.GetUnit(gs, pid, false);
            if (u == null || u.owner != pid) continue;

            if (u.CanMove())
            {
                var opts = u.GetMovementOptions(gs, u.GetMovement(gs));
                var to = new List<WorldCoordinates>();
                for (int j = 0; j < opts.Count; j++)
                    if (Valid(new MoveCommand(pid, u, opts[j]), gs)) to.Add(opts[j]);
                if (to.Count > 0)
                {
                    var xs = new List<int[]>(); foreach (var c in to) xs.Add(Xy(c));
                    var d = new D { ["id"] = recs.Count, ["k"] = "move", ["u"] = (long)u.id, ["to"] = xs };
                    recs.Add(new Rec { Json = d, Kind = "move", Unit = u, To = to });
                }
            }
            if (u.CanAttack())
            {
                var tg = u.GetAttackOptions(gs, u.GetRange(gs));
                for (int j = 0; j < tg.Count; j++)
                {
                    var ac = new AttackCommand(pid, u, tg[j]);
                    if (!Valid(ac, gs)) continue;
                    var d = new D { ["k"] = "attack", ["u"] = (long)u.id, ["to"] = Xy(tg[j]) };
                    var dt = gs.Map.GetTile(tg[j]);
                    var def = dt?.GetUnit(gs, pid, false);
                    if (def != null)
                    {
                        try
                        {
                            var br = BattleHelpers.GetBattleResults(gs, u, def, true, true);
                            d["dmg"] = br.attackDamage / 10f;
                            if (br.retaliationDamage > 0) d["ret"] = br.retaliationDamage / 10f;
                            if (br.attackDamage >= def.health) d["kill"] = true;
                        }
                        catch (Exception e) { Plugin.L.LogWarning("battle preview: " + e.Message); }
                    }
                    Add(d, $"{Name(u.type)} {u.id} attacked {Name(def?.type)} at [{tg[j].X},{tg[j].Y}]", ac);
                }
            }
            var acts = CommandUtils.GetUnitActions(gs, me, t, false);
            for (int j = 0; j < acts.Count; j++)
            {
                var c = acts[j];
                if (!Valid(c, gs)) continue;
                var ct = Cmd(c);
                if (ct == "Disband" || ct == "Destroy") continue;   // always legal and never useful: omitted for token economy
                var xy = Xy(t.coordinates);
                if (ct == "Capture")
                    Add(new D { ["k"] = "capture", ["u"] = (long)u.id, ["at"] = xy }, $"{Name(u.type)} {u.id} captured [{xy[0]},{xy[1]}]", c);
                else
                {
                    var d = new D { ["k"] = "unit", ["u"] = (long)u.id, ["cmd"] = ct };
                    var up = c.TryCast<UpgradeCommand>();
                    if (up != null) d["to"] = Name(up.Type);
                    Add(d, $"{Name(u.type)} {u.id} {ct}", c);
                }
            }
        }

        // Research
        try
        {
            var techs = gs.GameLogicData.GetUnlockableTech(me, gs);
            for (int i = 0; i < techs.Count; i++)
            {
                var td = techs[i];
                var rc = new ResearchCommand(pid, td.type);
                if (!Valid(rc, gs)) continue;
                Add(new D { ["k"] = "research", ["tech"] = Name(td.type), ["cost"] = gs.GameLogicData.GetTechPrice(td, me, gs) }, "researched " + Name(td.type), rc);
            }
        }
        catch (Exception e) { Plugin.L.LogWarning("research list: " + e.Message); }

        // Diplomacy with each known tribe: BreakPeace, PeaceTreaty (offer peace), embassies, ...
        try
        {
            var known = me.knownPlayers;
            if (known != null)
                for (int i = 0; i < known.Count; i++)
                {
                    if (known[i] == pid || known[i] == 255 || !gs.TryGetPlayer(known[i], out var op)) continue;
                    var dc = CommandUtils.GetDiplomacyCommandsForOpponent(gs, me, known[i], false);
                    for (int j = 0; j < dc.Count; j++)
                    {
                        if (!Valid(dc[j], gs)) continue;
                        Add(new D { ["k"] = "diplomacy", ["cmd"] = Cmd(dc[j]), ["with"] = Name(op.tribe) }, Cmd(dc[j]) + " with " + Name(op.tribe), dc[j]);
                    }
                }
        }
        catch (Exception e) { Plugin.L.LogWarning("diplomacy list: " + e.Message); }

        // City tiles: train. Own-territory tiles: build + improvement abilities.
        for (int i = 0; i < tiles.Length; i++)
        {
            var t = tiles[i];
            if (t.owner != pid) continue;
            var xy = Xy(t.coordinates);
            bool city = t.improvement != null && Name(t.improvement.type) == "City";
            if (city)
            {
                var tr = CommandUtils.GetTrainableUnits(gs, me, t, false);
                for (int j = 0; j < tr.Count; j++)
                {
                    if (!Valid(tr[j], gs)) continue;
                    Add(new D { ["k"] = "train", ["city"] = xy, ["unit"] = Name(tr[j].Type), ["cost"] = UnitCost(gs, tr[j].Type) }, $"trained {Name(tr[j].Type)} in [{xy[0]},{xy[1]}]", tr[j]);
                }
            }
            var bl = CommandUtils.GetBuildableImprovements(gs, me, t, false);
            for (int j = 0; j < bl.Count; j++)
            {
                var c = bl[j];
                if (!Valid(c, gs)) continue;
                var bc = c.TryCast<BuildCommand>();
                if (bc != null) Add(new D { ["k"] = "build", ["at"] = xy, ["imp"] = Name(bc.Type), ["cost"] = ImpCost(gs, bc.Type) }, $"built {Name(bc.Type)} at [{xy[0]},{xy[1]}]", c);
                else Add(new D { ["k"] = "ability", ["at"] = xy, ["cmd"] = Cmd(c) }, $"{Cmd(c)} at [{xy[0]},{xy[1]}]", c);
            }
            if (t.improvement != null)
            {
                var ab = CommandUtils.GetImprovementAbilities(gs, me, t, false);
                for (int j = 0; j < ab.Count; j++)
                {
                    var c = ab[j];
                    if (!Valid(c, gs)) continue;
                    var ct = Cmd(c);
                    if (ct == "Destroy" || ct == "Disband") continue;
                    Add(new D { ["k"] = "ability", ["at"] = xy, ["cmd"] = ct }, $"{ct} at [{xy[0]},{xy[1]}]", c);
                }
            }
        }

        var et = new EndTurnCommand(pid);
        if (Valid(et, gs)) Add(new D { ["k"] = "endTurn" }, "ended turn", et);
    }

    static void EnsureRecs(GameState gs)
    {
        if (recsFor != StateId(gs)) BuildRecs(gs);
    }

    static Reply Actions()
    {
        var gs = Gs();
        if (!Ready(out gs)) return Reply.Err("not ready (phase " + Phase() + ")", 409);
        BuildRecs(gs);
        var list = new List<D>(); foreach (var r in recs) list.Add(r.Json);
        var d = new D { ["ok"] = true, ["stateId"] = StateId(gs) };
        if (recsForced) d["forced"] = true;
        d["actions"] = list;
        return Reply.Ok(d);
    }

    static Reply Act(Request r)
    {
        if (!Ready(out var gs)) return Reply.Err("not ready (phase " + Phase() + ")", 409);
        if (!r.HasBody || !r.Body.TryGetProperty("id", out var idE) || !idE.TryGetInt32(out var id)) return Reply.Err("missing id", 400);
        int sid = StateId(gs);
        if (r.Body.TryGetProperty("stateId", out var sE) && sE.TryGetInt32(out var given) && given != sid)
            return Reply.Err("stale", 200, new D { ["stateId"] = sid });
        EnsureRecs(gs);
        if (id < 0 || id >= recs.Count) return Reply.Err("unknown id " + id);
        var rec = recs[id];
        CommandBase cmd; string desc = rec.Desc;
        if (rec.Kind == "move")
        {
            if (!r.Body.TryGetProperty("to", out var toE) || toE.ValueKind != System.Text.Json.JsonValueKind.Array || toE.GetArrayLength() != 2)
                return Reply.Err("move needs \"to\":[x,y]");
            int x = toE[0].GetInt32(), y = toE[1].GetInt32();
            int di = rec.To.FindIndex(c => c.X == x && c.Y == y);
            if (di < 0) return Reply.Err($"[{x},{y}] is not a legal destination");
            var dest = rec.To[di];
            cmd = new MoveCommand(GameManager.LocalPlayer.Id, rec.Unit, dest);
            desc = $"{Name(rec.Unit.type)} {rec.Unit.id} moved to [{x},{y}]";
        }
        else cmd = rec.Cmd;

        if (!cmd.IsValid(gs, out var err)) return Reply.Err("invalid: " + err);
        if (!ClientActionManager.CanReceiveCommand(cmd, gs)) return Reply.Err("client not ready for command", 409);
        bool full = r.Query.ContainsKey("full") && r.Query["full"] != "0";
        var before = Snapshot(gs);
        int startCommand = gs.CurrentCommand;
        GameManager.Client.SendCommand(cmd);
        int frames = 0;
        return new Reply
        {
            Poll = () =>
            {
                frames++;
                var g = Gs();
                if (g == null) return null;
                if (frames < 3) return null;
                if (!Over(g) && !Ready(out g)) return null;
                if (g.CurrentCommand == startCommand && !Over(g)) return null;   // command not applied yet
                var ev = new List<string> { desc };
                ev.AddRange(DrainEvents());
                var after = Snapshot(g);
                if (after.Tiles.Count > before.Tiles.Count) ev.Add($"revealed {after.Tiles.Count - before.Tiles.Count} tiles");
                var d = new D { ["ok"] = true, ["stateId"] = StateId(g) };
                if (Over(g)) d["phase"] = "game_over";
                d["events"] = ev;
                if (full) { var f = FullState(g, after); f.Remove("ok"); foreach (var kv in f) d[kv.Key] = kv.Value; }
                else d["changes"] = Diff(before, after);
                return PJson.Write(d);
            }
        };
    }
}
