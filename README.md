# Polytopia Bench

Frontier language models play the real *The Battle of Polytopia* (Steam, build 2.17.3.16375) against the game's own CPU. A small BepInEx plugin inside the game exposes the game state and every legal action over a local HTTP API; a Python harness hands them to a model each turn as tools. The game decides what is legal, how combat goes and who wins; nothing is simulated.

The question is long-term judgment: Polytopia rewards investing early (techs, cities, roads) over grabbing points now, and a 30-turn game is short enough to run on a subscription.

## Headline benchmark

- **Perfection** (highest score at the end of turn 30), **Small 14×14 Lakes** map, vs **2 Hard CPUs**.
- The model picks one of the four core tribes (Xin-xi, Imperius, Bardur, Oumaji) after reading the game's own tribe descriptions; the CPUs are drawn at random from the other three.
- Every turn is a fresh session: the model sees the system prompt (rules, plus the game's own tech, unit and building text), the current state (fog of war respected), the legal actions, and up to 400 words of notes it wrote itself on the previous turn.
- Medium reasoning effort for every model. Metric: the model's share of all three players' final score (33% is an even split). If the model is eliminated the game ends there, and the share uses everyone's score at that point.

### Results so far (October 2026)

| Model | Via | Games | Share of score | Avg points | Places |
|---|---|---|---|---|---|
| Gemini 4 Argon | Cursor | 1 | 78% | 23,064 | 1st |
| GPT-6.1 Sol | Codex | 2 | 52% | 16,772 | 1st, 1st |
| GPT-6 Astra | Codex | 2 | 51% | 15,668 | 2nd, 1st |
| Claude Opus 5.5 | Claude Code | 3 | 46% | 14,621 | 2nd, 1st, 1st |
| Claude Fable 5.1 | Cursor | 1 | 43% | 14,352 | 1st |
| GPT-5.6 Sol | Cursor | 1 | 40% | 12,848 | 2nd |
| Grok 4.7 | Cursor | 1 | 38% | 12,952 | 2nd |
| GPT-5.6 Luna | Cursor | 1 | 38% | 11,336 | 2nd |
| GPT-6 Luna | Codex | 1 | 27% | 6,160 | 3rd |
| Muse Wonder 1.0 | Cursor | 1 | 26% | 7,480 | 3rd (eliminated) |
| Claude Haiku 5.5 | Claude Code | 3 | 26% | 5,267 | 1st, 3rd (elim.), 3rd (elim.) |
| Claude Sonnet 5.5 | Claude Code | 3 | 25% | 6,173 | 3rd (elim.), 1st, 3rd (elim.) |
| GPT-5.6 Terra | Cursor | 1 | 18% | 4,712 | 3rd |

Most models have one game, so treat the order as rough: single games swing by 10–20 points. 15 of 21 games picked Imperius.

## How it works

```
Polytopia (Steam) ── PolyBridge plugin (C#, BepInEx 6 IL2CPP) ── HTTP localhost:7777
                                                                     │
          harness/play.py ── one model session per turn ── MCP tools (harness/mcp_poly.py)
                              (Claude Code, Cursor CLI or Codex CLI)
```

- `PolyBridge/` — the plugin. It only calls the game's own functions for legal moves, prices and commands. Contract: `spec/API.md`.
- `harness/` — `play.py` runs a game; `mcp_poly.py` gives the model `get_actions`, `act`, `write_plan` and `end_turn` (compact mode batches several actions per `act` call; the state comes with the turn prompt). Every turn's tool calls, the model's notes and token use are logged under `harness/logs/`.
- `prompts/` — system prompts per mode. `{{REFERENCE}}` is filled in at game start from `reference/reference.md`, which you generate from your own copy of the game (below).
- `docs/` — notes on the game's internals and mechanics found while building this.

If a model session fails (provider outage, timeout), the harness never ends the turn for the model: it stops, and `--resume` continues the same turn from the game's autosave.

## Running it

You need your own copy of the game (Steam, Windows) at build 2.17.3.16375. The paths in the plugin and the PowerShell scripts are set for one machine; edit them for yours (`Dir` in `PolyBridge/Plugin.cs`, `GameDir` in `PolyBridge/PolyBridge.csproj`, the paths in `scripts/*.ps1`).

1. **BepInEx:** install BepInEx 6.0.0-be.785 IL2CPP win-x64 (builds.bepinex.dev) into the game folder and launch the game once so it generates the interop DLLs.
2. **Plugin:** build with the .NET 8 SDK (`dotnet build PolyBridge`) and copy `PolyBridge.dll` into `BepInEx\plugins` (`scripts/redeploy.ps1` does build, copy and relaunch).
3. **Game reference** (the game's own text, so it is not in this repo):
   - `pip install UnityPy` and run `python reference/extract_gamelogic.py` → `reference/GameLogicData28.json`.
   - With the game running, write `locdump` into the plugin's `cmd.txt`; rename the resulting `loc.tsv` to `reference/loc-en.tsv`.
   - `python scripts/apply_reference.py` → `reference/reference.md`, `units.json`, `tribes.md`.
4. **Harness:** `python -m venv harness/.venv`, `harness/.venv/Scripts/pip install -r harness/requirements.txt`, then `pytest` in `harness/`.
5. **Play** (from `harness/`), the headline settings:

   ```
   python -m play --driver claude --model opus --effort medium --mode Perfection --difficulty Hard --opponents 2 \
     --map-size 14 --map-preset Lakes --choose-tribe --plan-chars 3000 --compact --turns 30 \
     --system-prompt ../prompts/system-perfection-multi.md
   ```

   `--driver cursor --model <cursor model id>` uses the Cursor CLI (`agent`); `--driver codex --model <id> --effort <level>` uses the Codex CLI. Both can run on another machine with the port forwarded (`ssh -N -L 7777:localhost:7777 <pc>`); `scripts/bench-cursor.sh` and `scripts/bench-codex.sh` run headline games that way.

Single-player only. Don't use this online or in ranked play.

## Not affiliated

Not affiliated with or endorsed by Midjiwan. *The Battle of Polytopia* and its data and text belong to Midjiwan; this repo contains none of the game's files or text.
