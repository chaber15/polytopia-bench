using System;
using System.Collections.Generic;
using Polytopia.Data;
using PolytopiaBackendBase.Game;

namespace PolyBridge;

using D = Dictionary<string, object>;

public static partial class Api
{
    // What the local player could see the opponents do, from the command stack since `from` (best effort).
    static List<string> OpponentEvents(GameState gs, int from)
    {
        var ev = new List<string>();
        try
        {
            byte pid = GameManager.LocalPlayer.Id;
            var stack = gs.CommandStack;
            for (int i = Math.Max(0, from); i < stack.Count; i++)
            {
                var c = stack[i];
                if (c.PlayerId == pid) continue;
                string tribe = gs.TryGetPlayer(c.PlayerId, out var op) ? Name(op.tribe) : "Opponent";
                WorldCoordinates at; string what;
                var mv = c.TryCast<MoveCommand>(); var at1 = c.TryCast<AttackCommand>(); var tr = c.TryCast<TrainCommand>();
                var cp = c.TryCast<CaptureCommand>(); var bd = c.TryCast<BuildCommand>();
                if (mv != null) { at = mv.To; what = "moved to"; }
                else if (at1 != null) { at = at1.Target; what = "attacked"; }
                else if (tr != null) { at = tr.Coordinates; what = "trained " + Name(tr.Type) + " at"; }
                else if (cp != null) { at = cp.Coordinates; what = "captured"; }
                else if (bd != null) { at = bd.Coordinates; what = "built " + Name(bd.Type) + " at"; }
                else continue;
                var tile = gs.Map.GetTile(at);
                if (tile == null || !tile.GetExplored(pid)) continue;
                string who = tribe;
                if (mv != null) { var u = tile.GetUnit(gs, pid, false); if (u == null) continue; who += " " + Name(u.type); }
                ev.Add($"{who} {what} [{at.X},{at.Y}]");
            }
        }
        catch (Exception e) { Plugin.L.LogWarning("events: " + e.Message); }
        return ev;
    }

    static Reply EndTurn(Request r)
    {
        if (!Ready(out var gs)) return Reply.Err("not ready (phase " + Phase() + ")", 409);
        var cmd = new EndTurnCommand(GameManager.LocalPlayer.Id);
        if (!cmd.IsValid(gs, out var err)) return Reply.Err("invalid: " + err);
        if (!ClientActionManager.CanReceiveCommand(cmd, gs)) return Reply.Err("client not ready for command", 409);
        uint startTurn = gs.CurrentTurn;
        byte ender = gs.CurrentPlayer;
        int stackFrom = gs.CommandStack.Count + 1;      // skip our own EndTurn
        events.Clear();
        GameManager.Client.SendCommand(cmd);
        int frames = 0;
        return new Reply
        {
            Poll = () =>
            {
                frames++;
                var g = Gs();
                if (g == null) return null;
                try { if (GameManager.Client.IsRecap) GameManager.Client.SkipRecap(); } catch { }
                if (frames < 3) return null;
                bool over = Over(g);
                if (!over && !(Ready(out g) && g.CurrentTurn > startTurn))
                {
                    // Pass & Play: the next seat (a person, or another model's session) may take a while; answer once
                    // the turn has passed on.
                    if (Seats.Count == 0 || frames < 30 || g == null || g.CurrentPlayer == ender) return null;
                    return PJson.Write(new D { ["ok"] = true, ["phase"] = "busy", ["turn"] = (int)g.CurrentTurn });
                }
                var d = new D { ["ok"] = true, ["phase"] = over ? "game_over" : "my_turn", ["turn"] = (int)g.CurrentTurn, ["stateId"] = StateId(g) };
                var ev = OpponentEvents(g, stackFrom);
                ev.AddRange(DrainEvents());
                if (ev.Count > 0) d["events"] = ev;
                return PJson.Write(d);
            }
        };
    }

    static Reply Result()
    {
        var gs = Gs();
        if (!Over(gs)) return Reply.Err("game not over (phase " + Phase() + ")", 409);
        var d = new D { ["ok"] = true };
        if (gs.TryGetWinner(out var w)) d["winner"] = (int)w.Id;
        var scores = new List<D>();
        for (int i = 0; i < gs.PlayerStates.Count; i++)
        {
            var p = gs.PlayerStates[i];
            if (p.Id == 0 || p.Id == 255) continue;
            long sc = p.score;
            try { sc = (long)p.GetScore(gs).TotalScoreIncludingBonus; } catch { }
            scores.Add(new D { ["id"] = (int)p.Id, ["tribe"] = Name(p.tribe), ["score"] = sc });
        }
        d["scores"] = scores;
        d["turn"] = (int)gs.CurrentTurn;
        return Reply.Ok(d);
    }
}
