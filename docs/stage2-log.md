## 2026-10-25 — Stage 2 works on the PC

Steam build **2.17.3.16375** (matches PolyMod 1.2.18 and the bridge map). No PolyMod: plain **BepInEx 6.0.0-be.785 IL2CPP win-x64** (the build PolyMod pins), from builds.bepinex.dev. Interop generated on first launch (~1 min).

Plugin `PolyBridge` (source in `plugin/PolyBridge/`, built on the PC with .NET 8 SDK, target net6.0, references BepInEx `core/` + `interop/` DLLs directly). It polls `C:\Users\caleb\Workspace\projects\polytopia\bridge\cmd.txt` on the main thread and appends to `bridge\out.log`. Driven over `ssh pc` with `pc-scripts/cmd.ps1 "<command>" <waitSeconds>`.

All three Stage 2 checks pass, plus more:
- "hello from PolyBridge" in `BepInEx\LogOutput.log`.
- Units and stars at turn start: turn 0, Bardur, 5 stars, score 515 (matches wiki), 1 warrior.
- `GetMovementOptions` returned legal tiles; `MoveCommand` via `GameManager.Client.SendCommand` moved the warrior one tile (`moved=True`).
- **Starting a game from code works:** fill `GameManager.PreliminaryGameSettings` (Perfection, Easy, 1 opponent, MapSize 11) → `GameManager.Instance.CreateSinglePlayerGame()`. No clicks.
- `EndTurnCommand` → CPU played → turn 1 began with 7 stars (+2).

Gotchas found:
- Types are in the **global namespace** (`GameLogicAssembly`, `PolytopiaAssembly`); enums `GameMode`/`BotDifficulty` are in `PolytopiaBackendBase.Game`, `TribeType` in `PolytopiaBackendBase.Common`.
- `GameManager.GameState`/`Client` getters **throw** at the main menu; wrap in try/catch.
- The **"Mighty Leader!" welcome popup blocks commands**: `CanReceiveCommand` is false while `ActionManager.IsProcessing` and `Client.IsRecap` are true. `PopupManager.RemoveAllPopups()` hides it but leaves the queue stuck (no HUD). Fix: `PopupManager.GetCurrentPopup().TryCast<BasicPopup>().MainButton.OnButtonClicked()` — then processing=false and moves work.
- Popups use `UIButtonBase_UI2`, not `UnityEngine.UI.Button` or `UIButtonBase`.
- The turn watcher fires before start-of-turn income lands (logged 5 stars, then 7). Gate on `ActionManager.IsProcessing == false` too.
- PowerShell `| Select -First N` kills the upstream script; don't pipe redeploy through it.
- GUI launch from SSH: scheduled task `PolyLaunch` (interactive principal `caleb`); screenshots via task `PolyShot` → `shot.png`.
