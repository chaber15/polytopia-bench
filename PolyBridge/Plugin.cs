using System;
using System.IO;
using System.Text;
using BepInEx;
using BepInEx.Logging;
using BepInEx.Unity.IL2CPP;
using Polytopia.Data;
using PolytopiaBackendBase.Game;
using UnityEngine;

namespace PolyBridge;

[BepInPlugin("polytopia-bench.polybridge", "PolyBridge", "0.1.0")]
public class Plugin : BasePlugin
{
    internal static ManualLogSource L;

    public override void Load()
    {
        L = Log;
        L.LogInfo("hello from PolyBridge");
        Http.Handler = Api.Handle;
        Http.Start(7777);
        AddComponent<Bridge>();
    }
}

// Polls a command file once per ~0.25 s on the main thread and appends results to out.log.
public class Bridge : MonoBehaviour
{
    // Folder for the file channel (cmd.txt / out.log / loc.tsv): %POLYBRIDGE_DIR%, else %LOCALAPPDATA%\PolyBridge.
    static readonly string Dir = Environment.GetEnvironmentVariable("POLYBRIDGE_DIR") is { Length: > 0 } d ? d
        : Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData), "PolyBridge");
    static string CmdFile => Path.Combine(Dir, "cmd.txt");
    static string OutFile => Path.Combine(Dir, "out.log");

    float next;
    string lastTurnKey = "";

    public Bridge(IntPtr ptr) : base(ptr) { }

    void Update()
    {
        try { Api.Tick(); Http.Pump(); } catch (Exception e) { Plugin.L.LogError("pump: " + e); }
        if (Time.unscaledTime < next) return;
        next = Time.unscaledTime + 0.25f;
        try { WatchTurn(); } catch (Exception e) { Out("turn-watch error: " + e.Message); }
        try { PollCommand(); } catch (Exception e) { Out("command error: " + e); }
    }

    static void Out(string s)
    {
        Plugin.L.LogInfo(s);
        Directory.CreateDirectory(Dir);
        File.AppendAllText(OutFile, $"[{DateTime.Now:HH:mm:ss}] {s}\n");
    }

    static bool InMatch(out GameState gs)
    {
        gs = null;
        // The static accessors throw outside a match (main menu), so treat any failure as "no match".
        try
        {
            if (GameManager.Client == null) return false;
            gs = GameManager.GameState;
            return gs != null && (gs.CurrentState == GameState.State.Started || gs.CurrentState == GameState.State.FinalTurn);
        }
        catch { gs = null; return false; }
    }

    static bool MyTurn(GameState gs) =>
        GameManager.Client.IsPlayerLocal(gs.CurrentPlayer) && GameManager.Client.IsWaitingForCommand;

    void WatchTurn()
    {
        if (!InMatch(out var gs) || !MyTurn(gs)) return;
        var key = $"{gs.CurrentTurn}/{gs.CurrentPlayer}";
        if (key == lastTurnKey) return;
        lastTurnKey = key;
        Out("TURN START\n" + Describe(gs));
    }

    void PollCommand()
    {
        if (!File.Exists(CmdFile)) return;
        var text = File.ReadAllText(CmdFile).Trim();
        File.Delete(CmdFile);
        if (text.Length == 0) return;
        Out("> " + text);
        var a = text.Split(' ', StringSplitOptions.RemoveEmptyEntries);
        switch (a[0])
        {
            case "status": Out(Status()); break;
            case "newgame": NewGame(a.Length > 1 ? int.Parse(a[1]) : 0); break;
            case "state": Out(InMatch(out var gs) ? Describe(gs) : "not in a match"); break;
            case "moves": Moves(uint.Parse(a[1])); break;
            case "move": Move(uint.Parse(a[1]), int.Parse(a[2]), int.Parse(a[3]), a.Length > 4 && a[4] == "force"); break;
            case "diag": Out(Diag()); break;
            case "diplo": Out(Diplo()); break;
            case "players": Out(Players()); break;
            case "locdump": Out(LocDump()); break;
            case "buttons": Out(Buttons(null)); break;
            case "click": Out(Buttons(text.Substring(6))); break;
            case "popup": Out(Popup(a.Length > 1 && a[1] == "ok")); break;
            case "skiprecap": GameManager.Client.SkipRecap(); Out("recap skipped"); break;
            case "clearpopups": PopupManager.RemoveAllPopups(); Out("popups cleared"); break;
            case "endturn": Send(new EndTurnCommand(GameManager.LocalPlayer.Id)); break;
            default: Out("unknown command"); break;
        }
    }

    static string Status()
    {
        GameState gs = null;
        try { gs = GameManager.Client == null ? null : GameManager.GameState; } catch { }
        if (gs == null) return $"instance={(GameManager.Instance != null)} no game state";
        return $"state={gs.CurrentState} turn={gs.CurrentTurn} current={gs.CurrentPlayer} local={GameManager.LocalPlayer?.Id} " +
               $"waiting={GameManager.Client.IsWaitingForCommand}";
    }

    static void NewGame(int difficulty)
    {
        var s = GameManager.PreliminaryGameSettings;
        s.BaseGameMode = GameMode.Perfection;
        s.RulesGameMode = GameMode.Perfection;
        s.Difficulty = (BotDifficulty)difficulty;
        s.OpponentCount = 1;
        s.MapSize = 11;
        s.rules.LoadPreset(GameMode.Perfection);
        Out($"starting Perfection vs 1 CPU, difficulty {s.Difficulty}");
        GameManager.Instance.CreateSinglePlayerGame();
    }

    static string Describe(GameState gs)
    {
        var me = GameManager.LocalPlayer;
        var sb = new StringBuilder();
        sb.AppendLine($"turn {gs.CurrentTurn}  player {me.Id} ({me.tribe})  stars {me.Currency}  score {me.score}  cities {me.cities}");
        var tiles = gs.Map.Tiles;
        for (int i = 0; i < tiles.Length; i++)
        {
            var u = tiles[i].GetUnit(gs, me.Id, false);
            if (u == null || u.owner != me.Id) continue;
            sb.AppendLine($"  unit {u.id} {u.type} at ({u.coordinates.X},{u.coordinates.Y}) hp {u.health / 10f} moved={u.moved} attacked={u.attacked}");
        }
        return sb.ToString().TrimEnd();
    }

    static bool TryFindUnit(GameState gs, uint id, out UnitState unit) => gs.TryGetUnit(id, out unit);

    static void Moves(uint id)
    {
        if (!InMatch(out var gs) || !TryFindUnit(gs, id, out var u)) { Out("no such unit"); return; }
        var opts = u.GetMovementOptions(gs, u.GetMovement(gs));
        var sb = new StringBuilder($"unit {id} can move to:");
        for (int i = 0; i < opts.Count; i++) sb.Append($" ({opts[i].X},{opts[i].Y})");
        Out(sb.ToString());
    }

    static void Move(uint id, int x, int y, bool force)
    {
        if (!InMatch(out var gs) || !TryFindUnit(gs, id, out var u)) { Out("no such unit"); return; }
        Send(new MoveCommand(GameManager.LocalPlayer.Id, u, new WorldCoordinates(x, y)), force);
    }

    static string Diag()
    {
        var gs = GameManager.GameState;
        var c = GameManager.Client;
        return $"actionManager={Try(() => c.ActionManager != null)} processing={Try(() => c.ActionManager.IsProcessing)} " +
               $"triggers={Try(() => gs.pendingCommandTriggers.Count)} queued={Try(() => gs.HasQueuedCommands())} " +
               $"recap={Try(() => c.IsRecap)} spectating={Try(() => c.IsSpectating)} replay={Try(() => c.IsReplay)}";
    }

    // Lists active, interactable UI buttons as "path [label]"; with a target, clicks the first whose path or label contains it.
    static string Buttons(string target)
    {
        var sb = new StringBuilder();
        var all = UnityEngine.Object.FindObjectsOfType(Il2CppInterop.Runtime.Il2CppType.Of<UIButtonBase>());
        sb.AppendLine($"  ({all.Length} UIButtonBase objects found)");
        foreach (var o in all)
        {
            var b = o.Cast<UIButtonBase>();
            if (!b.isActiveAndEnabled) continue;
            var label = Try(() => b.GetComponentInChildren<TMPro.TMP_Text>()?.text);
            var path = b.name;
            for (var t = b.transform.parent; t != null; t = t.parent) path = t.name + "/" + path;
            if (target != null && (path.Contains(target) || label.Contains(target)))
            {
                b.OnButtonClicked();
                return $"clicked {path} [{label}]";
            }
            sb.AppendLine($"  {path} [{label}]");
        }
        return target != null ? "no button matching " + target : "buttons:\n" + sb.ToString().TrimEnd();
    }

    // Describes the top popup; with ok=true presses its main button the same way a click would.
    static string Popup(bool ok)
    {
        if (!PopupManager.PopupShowing) return "no popup";
        var p = PopupManager.GetCurrentPopup();
        var desc = $"popup {p.GetIl2CppType().Name} header=\"{Try(() => p.Header)}\"";
        if (!ok) return desc;
        var bp = p.TryCast<BasicPopup>();
        if (bp == null) return desc + " (not a BasicPopup; can't press)";
        bp.MainButton.OnButtonClicked();
        return desc + " -> pressed main button";
    }

    static string Try(Func<object> f)
    {
        try { return f()?.ToString() ?? "null"; } catch (Exception e) { return "!" + e.GetType().Name; }
    }

    // Debug only (it reveals tribes the player has not met): every player's tribe, and the map settings.
    static string Players()
    {
        if (!InMatch(out var gs)) return "not in a match";
        var sb = new System.Text.StringBuilder();
        for (int i = 0; i < gs.PlayerStates.Count; i++)
        {
            var p = gs.PlayerStates[i];
            if (p.Id == 0 || p.Id == 255) continue;
            sb.Append($"player {p.Id} {p.tribe}{(p.AutoPlay ? " (CPU)" : "")}\n");
        }
        try { sb.Append($"mapPreset {gs.Settings.mapPreset} mapSize {gs.Settings.MapSize} difficulty {gs.Settings.Difficulty}"); } catch (Exception e) { sb.Append("settings: " + e.Message); }
        return sb.ToString();
    }

    // Every localization term with its current-language text, one "term<TAB>text" line each (newlines escaped).
    static string LocDump()
    {
        var terms = I2.Loc.LocalizationManager.GetTermsList(null);
        var path = Path.Combine(Dir, "loc.tsv");
        using var w = new StreamWriter(path, false, new System.Text.UTF8Encoding(false));
        int n = 0;
        for (int i = 0; i < terms.Count; i++)
        {
            string t = terms[i], v;
            try { v = I2.Loc.LocalizationManager.GetTranslation(t, false, 0, true, false, null, null, false); } catch (Exception e) { v = "ERR " + e.Message; }
            if (v == null) continue;
            w.WriteLine(t + "\t" + v.Replace("\r", "").Replace("\n", "\\n").Replace("\t", " "));
            n++;
        }
        return $"wrote {n} of {terms.Count} terms to {path} (language {I2.Loc.LocalizationManager.CurrentLanguage})";
    }

    // Relation with every known tribe, and every diplomacy command with why it is (not) valid.
    static string Diplo()
    {
        if (!InMatch(out var gs)) return "not in a match";
        var me = GameManager.LocalPlayer; var sb = new System.Text.StringBuilder();
        sb.Append("turn " + gs.CurrentTurn + "\n");
        var known = me.knownPlayers;
        for (int i = 0; i < known.Count; i++)
        {
            if (known[i] == me.Id || known[i] == 255 || !gs.TryGetPlayer(known[i], out var op)) continue;
            try
            {
                var r = PlayerDiplomacyExtensions.GetRelation(me, known[i]);
                sb.Append($"{op.tribe} id={op.Id} state={r.State} lastAttack={r.LastAttackTurn} peaceBroken={r.LastPeaceBrokenTurn} killedTurn={op.killedTurn}\n");
                var theirs = PlayerDiplomacyExtensions.GetRelation(op, me.Id);
                sb.Append($"  their view: state={theirs.State}\n");
            }
            catch (Exception e) { sb.Append("  relation error " + e.Message + "\n"); }
            try
            {
                var dc = CommandUtils.GetDiplomacyCommandsForOpponent(gs, me, known[i], true);
                for (int j = 0; j < dc.Count; j++)
                {
                    string err = null; bool ok = false;
                    try { ok = dc[j].IsValid(gs, out err); } catch (Exception e) { err = e.Message; }
                    sb.Append($"  {dc[j].GetCommandType()} valid={ok} {err}\n");
                }
            }
            catch (Exception e) { sb.Append("  commands error " + e.Message + "\n"); }
        }
        return sb.ToString();
    }

    static void Send(CommandBase cmd, bool force = false)
    {
        var gs = GameManager.GameState;
        if (!cmd.IsValid(gs, out var err)) { Out("invalid: " + err); return; }
        if (!ClientActionManager.CanReceiveCommand(cmd, gs))
        {
            Out("client not ready for command (" + Diag() + ")");
            if (!force) return;
        }
        GameManager.Client.SendCommand(cmd);
        Out("sent " + cmd.GetType().Name);
    }
}
