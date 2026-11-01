using System;
using System.Collections.Generic;
using Polytopia.Data;
using PolytopiaBackendBase.Common;
using PolytopiaBackendBase.Game;

namespace PolyBridge;

// Game-facing helpers and endpoint dispatch. Everything here runs on the main thread.
public static partial class Api
{
    public static bool Loading;                       // /newgame issued, not yet ready
    // Pass & Play: the seats models play (empty = off, every local seat is ours). Set with POST /seat; /quit clears them.
    public static readonly HashSet<byte> Seats = new();
    public static bool IsSeat(byte id) => Seats.Contains(id);
    static readonly List<string> events = new();      // popup dismissals etc., drained into the next response

    public static List<string> DrainEvents()
    {
        var l = new List<string>(events); events.Clear(); return l;
    }

    // The static accessors throw outside a match (main menu), so treat any failure as "no match".
    public static GameState Gs()
    {
        try { return GameManager.Client == null ? null : GameManager.GameState; } catch { return null; }
    }

    public static bool Over(GameState gs) => gs != null && (gs.CurrentState == GameState.State.FinalTurn || gs.CurrentState == GameState.State.Ended);
    public static bool Playing(GameState gs) => gs != null && gs.CurrentState == GameState.State.Started;

    static bool PopupUp() { try { return PopupManager.PopupShowing; } catch { return false; } }

    static bool Processing()
    {
        try { return GameManager.Client.ActionManager.IsProcessing; } catch { return true; }
    }

    public static bool HasTrigger(GameState gs)
    {
        try { return CommandTriggerUtils.TryGetTriggerCommand(gs, out _); } catch { return false; }
    }

    public static bool Ready(out GameState gs)
    {
        gs = Gs();
        if (!Playing(gs)) return false;
        try
        {
            if (!GameManager.Client.IsPlayerLocal(gs.CurrentPlayer) || GameManager.Client.IsRecap) return false;
            if (Seats.Count > 0 && !IsSeat(gs.CurrentPlayer)) return false;
            if (Processing()) return false;
            if (PopupUp() && !HasTrigger(gs)) return false;
            return true;
        }
        catch { return false; }
    }

    public static string Phase()
    {
        var gs = Gs();
        if (gs == null) return Loading ? "loading" : "menu";
        if (Over(gs)) return "game_over";
        if (Ready(out _)) return "my_turn";
        return Loading && !Playing(gs) ? "loading" : "busy";
    }

    // Per-frame: dismiss dismissable popups (welcome etc.). Popups that carry a choice are left alone.
    static string lastUnknown;
    static IntPtr popupPtr;
    static float popupSince;

    public static void Tick()
    {
        if (Seats.Count > 0 && !SeatTick()) return;
        if (!PopupUp()) return;
        var gs = Gs();
        if (gs == null || Over(gs)) return;
        if (!Playing(gs)) return;
        if (HasTrigger(gs)) return;
        try
        {
            var p = PopupManager.GetCurrentPopup();
            var name = p.GetIl2CppType().Name;
            // The level-up reward popup stays open after the reward command went through; close it.
            if (name == "RewardPopup") { p.Hide(); events.Add("closed popup RewardPopup"); return; }
            // Pressing a popup before its text links are laid out crashes the game (InfoButtonManager coroutine NRE): let it settle first.
            if (p.Pointer != popupPtr) { popupPtr = p.Pointer; popupSince = UnityEngine.Time.unscaledTime; return; }
            if (UnityEngine.Time.unscaledTime - popupSince < 1.5f) return;
            var bp = p.TryCast<BasicPopup>();
            // Older popups (e.g. DiplomacyPopup, a CPU's answer to a peace offer): press their first button.
            // Hide() skips the button's callback and leaves the game processing forever.
            var lp = bp == null ? p.TryCast<BasicPopupLegacy>() : null;
            if (lp != null && lp.Buttons != null && lp.Buttons.Length > 0 && lp.Buttons[0] != null)
            {
                lp.Buttons[0].OnButtonClicked();
                events.Add("dismissed popup " + name); Plugin.L.LogInfo("pressed first button of " + name);
                return;
            }
            if (bp == null)
            {
                if (name != "IconRewardPopup") { p.Hide(); events.Add("closed popup " + name); Plugin.L.LogInfo("closed popup " + name); return; }
                {
                    // "You meet ..." popup: press its button (Hide() would skip the game's own callback).
                    var ip = p.TryCast<UI.Popups.IconRewardPopup>();
                    if (ip != null && ip.RewardButton != null) { ip.RewardButton.OnButtonClicked(); events.Add("dismissed popup " + name); Plugin.L.LogInfo("dismissed popup " + name); return; }
                    var bs = p.GetComponentsInChildren<UIButtonBase>(true);
                    foreach (var b in bs)
                        if (b.isActiveAndEnabled && !b.name.StartsWith("TribeInfoButton")) { b.OnButtonClicked(); events.Add("dismissed popup " + name); Plugin.L.LogInfo("dismissed popup " + name + " via " + b.name); return; }
                    if (lastUnknown != name) { lastUnknown = name; Plugin.L.LogWarning("popup " + name + " has no button to press"); }
                }
                return;
            }
            bp.MainButton.OnButtonClicked();
            events.Add("dismissed popup " + name);
        }
        catch (Exception e) { Plugin.L.LogWarning("popup dismiss: " + e.Message); }
    }

    static float seatCheck, overlaySince = -1;
    public static float StartDelay = 3f;   // seconds the "Next up" screen stays up before the model presses START

    // Pass & Play with model seats. The screen belongs to a model seat from its "Next up" screen on (LocalPlayer
    // switches there; CurrentPlayer only after the recap and the first-turn welcome popup): press START, skip the
    // recap, and let Tick dismiss its popups. Returns false on a human's seat, so their screen is left alone.
    static bool SeatTick()
    {
        var gs = Gs();
        if (gs == null) return true;
        try
        {
            byte local = GameManager.LocalPlayer?.Id ?? 0;
            if (!IsSeat(local) && !IsSeat(gs.CurrentPlayer)) return false;
        }
        catch { return false; }
        if (UnityEngine.Time.unscaledTime - seatCheck < 0.5f) return true;
        seatCheck = UnityEngine.Time.unscaledTime;
        try { if (GameManager.Client.IsRecap) { GameManager.Client.SkipRecap(); events.Add("skipped recap"); } } catch { }
        try
        {
            UIButtonBase start = null;
            var all = UnityEngine.Object.FindObjectsOfType(Il2CppInterop.Runtime.Il2CppType.Of<UIButtonBase>());
            foreach (var o in all)
            {
                var b = o.Cast<UIButtonBase>();
                if (!b.isActiveAndEnabled || b.name != "TextButton") continue;
                var parent = b.transform.parent?.parent;
                if (parent != null && parent.name == "HotSeatOverlay") { start = b; break; }
            }
            // Leave the "Next up" screen up for a moment, so the person who just played can look away first.
            if (start == null) overlaySince = -1;
            else if (overlaySince < 0) overlaySince = UnityEngine.Time.unscaledTime;
            else if (UnityEngine.Time.unscaledTime - overlaySince >= StartDelay)
            {
                overlaySince = -1;
                start.OnButtonClicked();
                events.Add("pressed START"); Plugin.L.LogInfo("pressed hot seat START");
            }
        }
        catch (Exception e) { Plugin.L.LogWarning("seat start: " + e.Message); }
        return true;
    }

    // {"seat": n} adds a model seat ({"seat": 0} clears them all); optional "startDelay" in seconds (default 3).
    static Reply SetSeat(Request r)
    {
        int seat = 0;
        if (r.HasBody && r.Body.TryGetProperty("seat", out var v) && v.ValueKind == System.Text.Json.JsonValueKind.Number) seat = v.GetInt32();
        if (seat < 0 || seat > 254) return Reply.Err("bad seat " + seat, 400);
        if (r.HasBody && r.Body.TryGetProperty("startDelay", out var sd) && sd.ValueKind == System.Text.Json.JsonValueKind.Number)
            StartDelay = (float)Math.Max(0, sd.GetDouble());
        if (seat == 0) Seats.Clear(); else Seats.Add((byte)seat);
        Plugin.L.LogInfo("model seats " + string.Join(",", Seats));
        var list = new List<object>(); foreach (var x in Seats) list.Add((int)x);
        return Reply.Ok(new Dictionary<string, object> { ["ok"] = true, ["seats"] = list, ["startDelay"] = StartDelay });
    }

    public static Reply Handle(Request r)
    {
        switch (r.Method + " " + r.Path)
        {
            case "GET /status": return Status();
            case "POST /newgame": return NewGame(r);
            case "POST /resume": return Resume();
            case "POST /quit": return Quit();
            case "POST /seat": return SetSeat(r);
            case "GET /state": return State(r);
            case "GET /actions": return Actions();
            case "POST /act": return Act(r);
            case "POST /end_turn": return EndTurn(r);
            case "GET /result": return Result();
        }
        return Reply.Err("unknown endpoint " + r.Method + " " + r.Path, 404);
    }

    static Reply Status()
    {
        var d = new Dictionary<string, object> { ["ok"] = true };
        var phase = Phase();
        d["phase"] = phase;
        d["ready"] = phase == "my_turn";
        var gs = Gs();
        if (gs != null)
        {
            d["turn"] = (int)gs.CurrentTurn;
            try { d["current"] = (int)gs.CurrentPlayer; } catch { }
            if (Seats.Count > 0) { var list = new List<object>(); foreach (var x in Seats) list.Add((int)x); d["seats"] = list; }
            try
            {
                int n = 0;
                for (int i = 0; i < gs.PlayerStates.Count; i++) { var id = gs.PlayerStates[i].Id; if (id != 0 && id != 255) n++; }
                d["players"] = n;
            }
            catch { }
            int lim = TurnLimit(gs);
            if (lim > 0) d["maxTurns"] = lim;
        }
        return Reply.Ok(d);
    }

    static int TurnLimit(GameState gs)
    {
        try { return (int)gs.Settings.rules.TurnLimit; } catch { return 0; }
    }

    static Reply NewGame(Request r)
    {
        if (Phase() != "menu") return Reply.Err("newgame only valid in menu (phase " + Phase() + ")", 409);
        string mode = "Perfection", diff = "Easy", tribe = null, preset = null; int opp = 1, size = 11;
        var oppTribes = new List<string>();
        if (r.HasBody)
        {
            var b = r.Body;
            if (b.TryGetProperty("mode", out var m) && m.ValueKind == System.Text.Json.JsonValueKind.String) mode = m.GetString();
            if (b.TryGetProperty("difficulty", out var df) && df.ValueKind == System.Text.Json.JsonValueKind.String) diff = df.GetString();
            if (b.TryGetProperty("opponents", out var o) && o.ValueKind == System.Text.Json.JsonValueKind.Number) opp = o.GetInt32();
            if (b.TryGetProperty("mapSize", out var ms) && ms.ValueKind == System.Text.Json.JsonValueKind.Number) size = ms.GetInt32();
            if (b.TryGetProperty("tribe", out var t) && t.ValueKind == System.Text.Json.JsonValueKind.String) tribe = t.GetString();
            if (b.TryGetProperty("mapPreset", out var mp) && mp.ValueKind == System.Text.Json.JsonValueKind.String) preset = mp.GetString();
            if (b.TryGetProperty("opponentTribes", out var ot) && ot.ValueKind == System.Text.Json.JsonValueKind.Array)
                foreach (var e in ot.EnumerateArray()) if (e.ValueKind == System.Text.Json.JsonValueKind.String) oppTribes.Add(e.GetString());
        }
        if (!Enum.TryParse<GameMode>(mode, true, out var gm)) return Reply.Err("bad mode " + mode, 400);
        if (!Enum.TryParse<BotDifficulty>(diff, true, out var bd)) return Reply.Err("bad difficulty " + diff, 400);
        var s = GameManager.PreliminaryGameSettings;
        s.BaseGameMode = gm;
        s.RulesGameMode = gm;
        s.Difficulty = bd;
        s.OpponentCount = opp;
        s.MapSize = size;
        s.rules.LoadPreset(gm);
        if (preset != null)
        {
            if (!Enum.TryParse<MapPreset>(preset, true, out var mpv)) return Reply.Err("bad mapPreset " + preset, 400);
            s.mapPreset = mpv;
        }
        // CPU tribes: when a list is given, every other tribe is disabled so the game draws the CPUs from it.
        var allowed = new HashSet<TribeType>();
        foreach (var n in oppTribes)
        {
            if (!Enum.TryParse<TribeType>(n, true, out var ttv)) return Reply.Err("bad opponent tribe " + n, 400);
            allowed.Add(ttv);
        }
        foreach (TribeType tt in Enum.GetValues(typeof(TribeType)))
        {
            if (tt == TribeType.None) continue;
            try { if (allowed.Count == 0 || allowed.Contains(tt)) s.EnableTribe(tt); else s.DisableTribe(tt); } catch { }
        }
        if (tribe != null)
        {
            if (!Enum.TryParse<TribeType>(tribe, true, out var tt)) return Reply.Err("bad tribe " + tribe, 400);
            GameManager.SetStartingTribeValues(tt, default(SkinType), TribeType.None, TribeType.None);
        }
        Plugin.L.LogInfo($"newgame {gm} {bd} opp={opp} size={size} tribe={tribe} preset={preset} cpuTribes={string.Join(",", oppTribes)}");
        Loading = true;
        events.Clear();
        GameManager.Instance.CreateSinglePlayerGame();
        int stable = 0;
        return new Reply
        {
            Poll = () =>
            {
                // The welcome popup can show a moment after the game first looks ready: require ~1 s of steady readiness.
                if (!Ready(out var gs)) { stable = 0; return null; }
                if (++stable < 60) return null;
                Loading = false;
                return PJson.Write(new Dictionary<string, object> { ["ok"] = true, ["turn"] = (int)gs.CurrentTurn });
            }
        };
    }

    // The main menu's "resume game": loads the single-player autosave and waits until it is our turn (or over).
    static Reply Resume()
    {
        if (Phase() != "menu") return Reply.Err("resume only valid in menu (phase " + Phase() + ")", 409);
        Plugin.L.LogInfo("resume singleplayer game");
        Loading = true;
        events.Clear();
        GameManager.Instance.ResumeSingleplayerGame();
        int stable = 0;
        return new Reply
        {
            Poll = () =>
            {
                var g = Gs();
                if (g != null && Over(g)) { Loading = false; return PJson.Write(new Dictionary<string, object> { ["ok"] = true, ["phase"] = "game_over", ["turn"] = (int)g.CurrentTurn }); }
                try { if (g != null && GameManager.Client.IsRecap) GameManager.Client.SkipRecap(); } catch { }
                if (!Ready(out var gs)) { stable = 0; return null; }
                if (++stable < 60) return null;
                Loading = false;
                return PJson.Write(new Dictionary<string, object> { ["ok"] = true, ["turn"] = (int)gs.CurrentTurn });
            }
        };
    }

    static Reply Quit()
    {
        Seats.Clear();
        var gs = Gs();
        if (gs == null && !Loading) return Reply.Ok(new Dictionary<string, object> { ["ok"] = true, ["phase"] = "menu" });
        QuitToMenu();
        return new Reply
        {
            Poll = () =>
            {
                if (Gs() != null) return null;
                return PJson.Write(new Dictionary<string, object> { ["ok"] = true, ["phase"] = "menu" });
            }
        };
    }
}
