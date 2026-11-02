# Setup guide

This walks through getting a model to play *The Battle of Polytopia* on your own machine: installing the plugin, connecting a model, running a benchmark game and playing Pass & Play against it.

You need:

- **Windows 10 or 11** with the Steam version of *The Battle of Polytopia*, build **2.17.3.16375**. The plugin calls the game's own code by name, so other builds may not load it.
- **.NET 8 SDK**, to build the plugin.
- **Python 3.12 or newer** (developed on 3.14).
- Access to at least one model: Claude Code, the Cursor CLI, the Codex CLI, Antigravity, or an OpenRouter API key.

There are two ways to set things up:

- **One machine:** the game, the harness and the model's CLI all run on the Windows PC. This is the simplest option.
- **Two machines:** the game runs on the Windows PC, and the harness runs on another computer (macOS or Linux), reaching the game through an SSH tunnel. This is useful when a model's CLI is signed in on a different computer.

Offline only: single-player and local Pass & Play. Don't use this online or in ranked play.

---

## 1. Install BepInEx

1. Download **BepInEx 6.0.0-be.785, IL2CPP, win-x64** from [builds.bepinex.dev](https://builds.bepinex.dev/projects/bepinex_be).
2. Unzip it into the game folder, next to `Polytopia.exe`. The default folder is `C:\Program Files (x86)\Steam\steamapps\common\The Battle of Polytopia`.
3. Launch the game once and wait at the main menu. The first launch takes about a minute while BepInEx generates `BepInEx\interop\`. Then close the game.

## 2. Build and install the plugin

From the repo root in PowerShell:

```powershell
dotnet build PolyBridge -c Release
copy PolyBridge\bin\Release\PolyBridge.dll "C:\Program Files (x86)\Steam\steamapps\common\The Battle of Polytopia\BepInEx\plugins\"
```

If the game is somewhere else, set `POLYTOPIA_DIR` first (or pass `-p:GameDir=<folder>` to `dotnet build`). After the first time, `scripts\redeploy.ps1` builds, copies and relaunches in one step.

Start the game and check that the plugin is up:

```powershell
curl.exe http://localhost:7777/status
```

At the main menu it answers `{"ok":true,"phase":"menu",...}`. If it doesn't answer, look for `PolyBridge` lines in `BepInEx\LogOutput.log`.

**Optional settings** (environment variables):

| Variable | Default | Used by |
|---|---|---|
| `POLYTOPIA_DIR` | `C:\Program Files (x86)\Steam\steamapps\common\The Battle of Polytopia` | plugin build, `scripts\*.ps1`, `reference\extract_gamelogic.py` |
| `POLYBRIDGE_DIR` | `%LOCALAPPDATA%\PolyBridge` | the plugin's file channel (`cmd.txt`, `out.log`, `loc.tsv`) and `scripts\cmd.ps1` |
| `POLY_PLAYER_DIR` | `%USERPROFILE%\polytopia-player` | empty working folder for the model's sessions, so no project instructions leak into them |
| `CLAUDE_EXE` | `%USERPROFILE%\.local\bin\claude.exe`, else `claude` on PATH | `scripts\game.ps1` |

## 3. Generate the game reference

The model's system prompt includes the game's own tech, unit and building text. That text belongs to Midjiwan, so it isn't in this repo; you generate it from your copy of the game. From the repo root:

```powershell
pip install UnityPy
python reference\extract_gamelogic.py             # -> reference\GameLogicData28.json
scripts\cmd.ps1 locdump                           # game running; writes loc.tsv into %LOCALAPPDATA%\PolyBridge
copy $env:LOCALAPPDATA\PolyBridge\loc.tsv reference\loc-en.tsv
python scripts\apply_reference.py                 # -> reference\reference.md, units.json, tribes.md
```

All of these files are gitignored.

## 4. Set up the harness

```powershell
python -m venv harness\.venv
harness\.venv\Scripts\pip install -r harness\requirements.txt
cd harness
.venv\Scripts\python -m pytest
```

The tests use a fake bridge, so they pass without the game running. On macOS or Linux, use `harness/.venv/bin/...` instead.

## 5. Connect a model

Each turn, `harness/play.py` starts a fresh model session and gives it the game's tools (`get_actions`, `act`, `write_plan`, `end_turn`) over MCP. Choose how the model is reached with `--driver`:

| Driver | What you need | Example `--model` |
|---|---|---|
| `claude` (default) | [Claude Code](https://docs.anthropic.com/en/docs/claude-code) installed and signed in (`claude` on PATH, or `--claude <path>`) | `opus`, `sonnet` |
| `cursor` | Cursor CLI (`agent`) signed in (`--cursor <command>` to override) | a Cursor model id |
| `codex` | Codex CLI signed in (`--codex <command>` to override) | a Codex model id |
| `antigravity` | An Antigravity ACP server and its login. If you use T3 Code, sign in to Antigravity there and run `scripts/agy-home.sh` once; otherwise pass `--agy <path to agy_acp_server.par>` and set `POLY_AGY_HOME` to a folder holding `antigravity-acp/acp_token.json` | a Gemini model id |
| `openrouter` | An API key in `OPENROUTER_API_KEY`, or in a file named by `OPENROUTER_API_KEY_FILE`. No agent CLI: the game's tools are the only tools | e.g. `google/gemini-4-argon` |

`--effort` sets reasoning effort (`low`, `medium`, `high`) where the driver supports it.

**OpenRouter tips:** set a credit limit on the key itself. `scripts/bench-openrouter.sh` reads the key from `~/.polytopia-openrouter-key` if the environment variable isn't set; keep that file private (`chmod 600`). Running out of credit stops the game with the turn left open, so you can add credit and continue with `--resume`.

## 6. Play a game

From `harness/`, with the game at the main menu, this runs one headline benchmark game (Perfection, 30 turns, Small 14×14 Lakes map, 2 Hard CPUs, the model picks its tribe):

```
python -m play --driver claude --model opus --effort medium --mode Perfection --difficulty Hard --opponents 2 \
  --map-size 14 --map-preset Lakes --choose-tribe --plan-chars 3000 --compact --turns 30 \
  --system-prompt ../prompts/system-perfection-multi.md
```

The harness starts the game itself; you don't need to touch it. To run several headline games in a row:

- Windows, Claude Code: `scripts\bench.ps1` (see the usage line at the top of the script).
- Any machine with bash: `scripts/bench-codex.sh`, `bench-cursor.sh`, `bench-antigravity.sh` or `bench-openrouter.sh`, e.g. `scripts/bench-openrouter.sh google/gemini-4-argon medium my-run 3`. Output goes to `logs/<prefix>-<n>.out`.

**Logs.** Every game writes `harness/logs/<time>-<driver>-<model>.jsonl` (states, tool calls, the model's notes, token use) plus a `-turns/` folder with each turn's raw session. Open `harness/viewer.html` in a browser and choose a `.jsonl` file to replay the game turn by turn.

**If something fails mid-game** (provider outage, timeout, dropped connection), the harness never ends the turn for the model. It stops, and the game stays on that turn. Run the same command again with `--resume` (and `--plan-file harness/logs/<game>-turns/turnNN/plan.txt` to give the model its last notes); it continues from the game's autosave.

Other prompts in `prompts/` cover Domination, Might, a single CPU opponent and a "competitive" framing; `python -m play --help` lists every option.

## 7. Running the harness from a second machine

The game must stay on the Windows PC, but the harness and the model CLI can run elsewhere.

1. **Enable SSH on the PC:** Settings → System → Optional features → add **OpenSSH Server**, then start the `sshd` service and set it to start automatically. Add your second machine's public key to `C:\Users\<you>\.ssh\authorized_keys` (for an administrator account, `C:\ProgramData\ssh\administrators_authorized_keys`).
2. **Forward the plugin's port** from the second machine:
   ```
   ssh -N -o ServerAliveInterval=15 -L 7777:localhost:7777 <you>@<pc-address>
   ```
   Then `curl http://localhost:7777/status` on the second machine should answer. If the tunnel drops mid-game, the harness stops and the game waits; reconnect and use `--resume`. A small reconnect loop helps on long runs:
   ```
   while true; do ssh -N -o ExitOnForwardFailure=yes -o ServerAliveInterval=15 -L 7777:localhost:7777 <you>@<pc-address>; sleep 5; done
   ```
3. **Keep the second machine awake.** On macOS, the `bench-*.sh` scripts run `caffeinate` for you, but closing a laptop lid still sleeps it.
4. **Keep the PC's desktop session signed in.** The game only runs properly in a signed-in desktop session (next section).

## 8. Launching the game and taking screenshots over SSH

A program started from an SSH session runs without a desktop, and the game won't render. Instead, create two scheduled tasks on the PC that run in your signed-in desktop session. In PowerShell on the PC (as your own user, not elevated):

```powershell
$game = "C:\Program Files (x86)\Steam\steamapps\common\The Battle of Polytopia"
$p = New-ScheduledTaskPrincipal -UserId $env:USERNAME -LogonType Interactive -RunLevel Limited
Register-ScheduledTask PolyLaunch -Principal $p -Action (New-ScheduledTaskAction -Execute "$game\Polytopia.exe" -WorkingDirectory $game)
Register-ScheduledTask PolyShot -Principal $p -Action (New-ScheduledTaskAction -Execute powershell.exe `
  -Argument "-WindowStyle Hidden -ExecutionPolicy Bypass -File $PWD\scripts\shot.ps1")   # run from the repo root
```

- Start the game: `Start-ScheduledTask PolyLaunch`. Restart it: `Stop-Process -Name Polytopia; Start-ScheduledTask PolyLaunch`.
- Screenshot: `Start-ScheduledTask PolyShot`, wait a few seconds, then read `shot.png` in the repo root.

**Black screen?** If nobody is connected to the PC's desktop, for example after a Remote Desktop session is closed rather than signed out, Windows stops drawing it: the game window and screenshots go black, though the plugin keeps answering. To watch a game, sign in at the PC itself or stay connected over Remote Desktop, then restart the game inside that session. Connecting or disconnecting Remote Desktop while a game is running can freeze the game; if that happens, restart the game and continue with `--resume`. To record a game, use any screen recorder (e.g. the Xbox Game Bar, Win+Alt+R) in that session, or replay the log in `harness/viewer.html` afterwards.

**Leaving a game running overnight.** `scripts\watch-game.ps1` keeps one game going until it ends and can record it. It runs `play.py` again on the live game when it stops (provider errors, timeouts), resumes from the autosave with the model's last notes when the game is back at the menu, waits out Claude usage limits, and restarts the game if it stops answering. With `-record` it records the desktop with ffmpeg (put any build with gdigrab under `tools\`) and finishes with a full-length `logs\rec\<name>.mkv` and a sped-up `<name>-fast.mp4`. Its own log is `logs\watch\<name>.log`.

Run it from a scheduled task with an Interactive principal, started through `scripts\hidden.py` so no console window covers the game:

```powershell
$p = "C:\path\to\polytopia-bench"
$a = New-ScheduledTaskAction -Execute "$p\harness\.venv\Scripts\pythonw.exe" -Argument "$p\scripts\hidden.py powershell.exe -ExecutionPolicy Bypass -File $p\run-mygame.ps1"
Register-ScheduledTask PolyWatch -Action $a -Principal (New-ScheduledTaskPrincipal -UserId $env:USERNAME -LogonType Interactive) -Trigger (New-ScheduledTaskTrigger -Once -At "2:30 AM")
```

where `run-mygame.ps1` calls `scripts\watch-game.ps1 -name mygame -record -playArgs "<play.py arguments>"`. For an unattended recording the desktop must stay drawn: instead of staying connected over Remote Desktop, move the session to the PC's own screen before the game starts (as an administrator: a task running `tscon <session id> /dest:console` as SYSTEM). This leaves the desktop signed in on the PC's screen.

## 9. Pass & Play against a model

You can play local Pass & Play games with any number of people and models on one screen.

1. Start one harness per model seat, before or after setting up the game:
   ```
   python -m play --driver claude --model opus --effort high --seat 2 --mode Domination \
     --system-prompt ../prompts/system-passplay.md
   ```
   `--seat` is the model's player number in the Pass & Play setup (1 is the first player). Add `--start-delay <seconds>` to change the pause on its "Next up" screen (default 3).
2. In Polytopia, set up a **Pass & Play** game with a player in that seat (any name and tribe), and start it.
3. Play your own turns as usual. When the model's "Next up" screen appears, step back: after the delay the plugin presses START, skips the recap and plays the turn. People's screens and popups are left alone.

The prompt is filled in with the mode, player count, map size, the model's seat and tribe. The harness waits as long as the people take, and never reloads the save while people are playing. The game must be visible on a real screen or a connected Remote Desktop session for the whole game (see the previous section).

## Troubleshooting

| Problem | What to check |
|---|---|
| `curl localhost:7777/status` doesn't answer | Is the game running? Is `PolyBridge.dll` in `BepInEx\plugins`? Look for errors in `BepInEx\LogOutput.log`. From a second machine, is the tunnel up? |
| Plugin loads but errors on every call | Your game build isn't 2.17.3.16375. |
| `reference/reference.md` missing | Do step 3. |
| The model's session exits immediately | Is its CLI signed in? Try the CLI by hand on the same machine. For OpenRouter, is the key set and in credit? |
| The game is stuck on a popup | `scripts\cmd.ps1 "popup ok"` presses its main button; `scripts\cmd.ps1 buttons` lists the buttons on screen. |
| Black screen or frozen game | See [§8](#8-launching-the-game-and-taking-screenshots-over-ssh). |

For the plugin's HTTP contract, see `spec/API.md`; `docs/02-plugin-notes.md` has notes from building it.
