# Plugin notes: first working build

Steam build **2.17.3.16375** (the build PolyMod 1.2.18 targets). No PolyMod: plain **BepInEx 6.0.0-be.785 IL2CPP win-x64** (the build PolyMod pins), from builds.bepinex.dev. Interop DLLs are generated on first launch (~1 min).

The plugin (`PolyBridge/`, built with the .NET 8 SDK, target net6.0, referencing BepInEx `core/` + `interop/` DLLs directly) serves the HTTP API on `localhost:7777`. It also polls a file channel on the main thread, `%LOCALAPPDATA%\PolyBridge\cmd.txt`, and appends replies to `out.log` there; `scripts/cmd.ps1 "<command>" <waitSeconds>` drives it.

What the first build proved:
- "hello from PolyBridge" in `BepInEx\LogOutput.log`.
- Units and stars at turn start: turn 0, Bardur, 5 stars, score 515, 1 warrior.
- `GetMovementOptions` returned legal tiles; `MoveCommand` via `GameManager.Client.SendCommand` moved the warrior one tile.
- **Starting a game from code works:** fill `GameManager.PreliminaryGameSettings` (Perfection, Easy, 1 opponent, MapSize 11) → `GameManager.Instance.CreateSinglePlayerGame()`. No clicks.
- `EndTurnCommand` → CPU played → turn 1 began with 7 stars (+2).

Gotchas:
- Types are in the **global namespace** (`GameLogicAssembly`, `PolytopiaAssembly`); enums `GameMode`/`BotDifficulty` are in `PolytopiaBackendBase.Game`, `TribeType` in `PolytopiaBackendBase.Common`.
- `GameManager.GameState`/`Client` getters **throw** at the main menu; wrap in try/catch.
- The **"Mighty Leader!" welcome popup blocks commands**: `CanReceiveCommand` is false while `ActionManager.IsProcessing` and `Client.IsRecap` are true. `PopupManager.RemoveAllPopups()` hides it but leaves the queue stuck (no HUD). Fix: `PopupManager.GetCurrentPopup().TryCast<BasicPopup>().MainButton.OnButtonClicked()`; then processing is false and moves work.
- Popups use `UIButtonBase_UI2`, not `UnityEngine.UI.Button` or `UIButtonBase`.
- The turn watcher fires before start-of-turn income lands (logged 5 stars, then 7). Gate on `ActionManager.IsProcessing == false` too.
- PowerShell `| Select -First N` kills the upstream script; don't pipe redeploy through it.
- The game only renders in a logged-in, connected Windows session. Launched over SSH it needs a scheduled task with an interactive principal (see `docs/SETUP.md`).
