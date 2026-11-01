# Polytopia Bench

Frontier language models play the real *The Battle of Polytopia* (Steam, build 2.17.3.16375) against the game's own CPU. A small BepInEx plugin inside the game exposes the game state and every legal action over a local HTTP API; a Python harness hands them to a model each turn as tools. The game decides what is legal, how combat goes and who wins; nothing is simulated.

The question is long-term judgment: Polytopia rewards investing early (techs, cities, roads) over grabbing points now, and a 30-turn game is short enough to run on a subscription.

## Headline benchmark

- **Perfection** (highest score at the end of turn 30), **Small 14×14 Lakes** map, vs **2 Hard CPUs**.
- The model picks one of the four core tribes (Xin-xi, Imperius, Bardur, Oumaji) after reading the game's own tribe descriptions; the CPUs are drawn at random from the other three.
- Every turn is a fresh session: the model sees the system prompt (rules, plus the game's own tech, unit and building text), the current state (fog of war respected), the legal actions, and up to 400 words of notes it wrote itself on the previous turn.
- Medium reasoning effort for every model. Metric: the model's share of all three players' final score (33% is an even split). If the model is eliminated the game ends there, and the share uses everyone's score at that point.
- **Sample standard:** three completed games per model. Rank by the arithmetic mean of each game's score share; average points is also computed per game. Eliminations count as completed games. Results with fewer than three completed games are provisional.

### Results so far (October 2026)

| Model | Via | Games | Share of score | Avg points | Places |
|---|---|---|---|---|---|
| Gemini 4 Argon | Cursor / OpenRouter | 3 | 74% | 25,605 | 1st, 1st, 1st |
| GPT-6 Astra | Codex | 3 | 51% | 14,920 | 2nd, 1st, 1st |
| Claude Opus 5.5 | Claude Code | 3 | 46% | 14,621 | 2nd, 1st, 1st |
| Claude Fable 5.1 | Cursor | 1 | 43% | 14,352 | 1st |
| GPT-6.1 Sol | Codex | 3 | 39% | 11,891 | 1st, 1st, 3rd (elim.) |
| Grok 4.7 | Cursor | 3 | 38% | 12,515 | 2nd, 2nd, 1st |
| GPT-6.1 Terra | Codex | 3 | 32% | 9,296 | 3rd (elim.), 1st, 2nd |
| GPT-6 Luna | Codex | 3 | 30% | 7,501 | 3rd, 1st, 2nd |
| Claude Haiku 5.5 | Claude Code | 3 | 26% | 5,267 | 1st, 3rd (elim.), 3rd (elim.) |
| Claude Sonnet 5.5 | Claude Code | 3 | 25% | 6,173 | 3rd (elim.), 1st, 3rd (elim.) |
| Muse Wonder 1.0 | Cursor / OpenRouter | 3 | 20% | 5,725 | 3rd (elim.), 3rd (elim.), 2nd |

Models with fewer than three games have provisional rankings; even three-game averages can vary with the map draw. The current leaderboard excludes the older GPT-5.6 generation; its raw game logs are retained.

## How it works

```
Polytopia (Steam) ── PolyBridge plugin (C#, BepInEx 6 IL2CPP) ── HTTP localhost:7777
                                                                     │
          harness/play.py ── one model session per turn ── MCP tools (harness/mcp_poly.py)
                              (Claude Code, Cursor CLI, Codex CLI, Antigravity or OpenRouter)
```

- `PolyBridge/` — the plugin. It only calls the game's own functions for legal moves, prices and commands. Contract: `spec/API.md`.
- `harness/` — `play.py` runs a game; `mcp_poly.py` gives the model `get_actions`, `act`, `write_plan` and `end_turn` (compact mode batches several actions per `act` call; the state comes with the turn prompt). Every turn's tool calls, the model's notes and token use are logged under `harness/logs/`.
- `prompts/` — system prompts per mode. `{{REFERENCE}}` is filled in at game start from `reference/reference.md`, which you generate from your own copy of the game ([setup guide](docs/SETUP.md#3-generate-the-game-reference)).
- `docs/` — the [setup guide](docs/SETUP.md) and notes from building the plugin.
- `scripts/` — benchmark runners and Windows helpers; `scripts/dev/` holds one-off development checks.

If a model session fails (provider outage, timeout), the harness never ends the turn for the model: it stops, and `--resume` continues the same turn from the game's autosave.

## Running it

You need your own copy of the game (Steam, Windows, build 2.17.3.16375). **[docs/SETUP.md](docs/SETUP.md)** covers everything step by step:

1. Install BepInEx 6 (IL2CPP) and build the plugin with the .NET 8 SDK.
2. Generate the game reference from your copy of the game (the game's text isn't in this repo).
3. Set up the Python harness and connect a model: Claude Code, Cursor CLI, Codex CLI, Antigravity or OpenRouter.
4. Play a headline game, from the PC or from a second machine over an SSH tunnel:

   ```
   python -m play --driver claude --model opus --effort medium --mode Perfection --difficulty Hard --opponents 2 \
     --map-size 14 --map-preset Lakes --choose-tribe --plan-chars 3000 --compact --turns 30 \
     --system-prompt ../prompts/system-perfection-multi.md
   ```

**Pass & Play against the model:** start the harness with `--seat <player number>` and `--system-prompt ../prompts/system-passplay.md`, then set up a local Pass & Play game with the model in that seat; it plays only its own turns, any tribe, any number of players. See [SETUP.md §9](docs/SETUP.md#9-pass--play-against-a-model).

Offline only: single-player and local Pass & Play. Don't use this online or in ranked play.

## Not affiliated

Not affiliated with or endorsed by Midjiwan. *The Battle of Polytopia* and its data and text belong to Midjiwan; this repo contains none of the game's files or text.

## License

The code in this repo is [MIT licensed](LICENSE). The license covers this repo only, not the game or anything generated from it.
