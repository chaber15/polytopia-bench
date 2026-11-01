# PolyBridge HTTP API v1 (contract)

The plugin (C#, inside the game) and the harness (Python) both build to this file. Change it only by agreement through Opus; note changes at the bottom.

- Base URL: `http://localhost:7777/`. Must be `localhost`: requests to `127.0.0.1` get HTTP 400 (HttpListener host check).
- Every POST must send a body (`{}` is fine); a bodyless POST gets HTTP 411.
- All bodies are JSON, UTF-8. All responses are HTTP 200 with `"ok": true|false` except: 409 when the game is not ready for the request, 400 for malformed bodies.
- Every game call runs on Unity's main thread (the HTTP thread enqueues work and waits). Long calls (`/newgame`, `/act`, `/end_turn`) block until the game is `ready` again or a timeout (default 120 s, `?timeout=` overrides) and then answer.
- Coordinates are `[x, y]` arrays. Names are the game's enum names as strings (`"Warrior"`, `"Riding"`, `"Bardur"`).
- **Fog:** the plugin never reveals anything the local player can't see (unexplored tiles are omitted; hidden units omitted; opponents' stars/techs omitted).

## Token-economy rules (both sides)

The model's context is the scarce resource. Be compact without dropping information the model needs:

- Omit fields that are null/false/empty/default rather than sending them. Document defaults here.
- Short stable keys are fine, but no cryptic codes; the harness renders text for the model anyway.
- `stateId` lets the harness send only what changed: `/act` returns a `changes` block (units/tiles/me fields that changed), not the whole state, unless `?full=1`.
- Static facts (unit stats, tech tree, costs formulas) are **not** in `/state`; the harness sends them once per game in the rules sheet.

## `ready`

True when: in a match, it is the local player's turn, `Client.IsWaitingForCommand`, `ActionManager.IsProcessing == false`, no popup open. Popups are auto-dismissed by pressing their main button (`PopupManager.GetCurrentPopup().TryCast<BasicPopup>().MainButton.OnButtonClicked()`); each dismissal is recorded in `events`. Popups that need a choice (city level-up rewards) are not auto-dismissed; they appear as forced actions.

## Endpoints

### `GET /status`
```json
{"ok":true,"phase":"my_turn","ready":true,"turn":3,"maxTurns":30}
```
`phase`: `menu` | `loading` | `my_turn` | `busy` (animations, CPU turn) | `game_over`. `turn`/`maxTurns` omitted outside a match (`maxTurns` omitted if no turn limit). In a match also `current` (player to move) and `players` (count); `seats` while model seats are set.

### `POST /newgame`
Body (all optional, defaults shown):
```json
{"mode":"Perfection","difficulty":"Easy","opponents":1,"mapSize":11,"tribe":null}
```
Only valid in `menu`. Returns when `ready` on turn 0 (welcome popup already dismissed): `{"ok":true,"turn":0}`.

### `GET /state`
```json
{"ok":true,"stateId":17,"turn":3,"maxTurns":30,
 "me":{"id":1,"tribe":"Bardur","stars":9,"income":4,"score":1240,"techs":["Hunting","Riding"]},
 "opponents":[{"id":2,"tribe":"Imperius","score":1100}],
 "map":{"w":11,"h":11,
   "tiles":[{"xy":[3,4],"t":"Field","own":1,"res":"Fruit","imp":"Farm","road":true,"eff":["Flooded"]}]},
 "cities":[{"xy":[5,5],"name":"Guro","own":1,"cap":true,"lvl":2,"pop":1,"popMax":3,"units":2}],
 "villages":[[8,2]],
 "units":[{"id":4,"type":"Warrior","own":1,"xy":[5,6],"hp":10,"hpMax":10,"vet":false,"moved":false,"attacked":false,"fx":["Boosted"]}],
 "ruins":[[1,9]]}
```
- `map.tiles`: explored tiles only. Omitted keys mean: `own` 0 (nobody), no `res`, no `imp`, `road` false, `eff` empty. `t` = terrain (`Field`, `Forest`, `Mountain`, `Water`, `Ocean`, …).
- `cities`: every city the player can see (own and enemy); `units`/`pop`/`popMax` only for own cities. `units` = own units whose home is the city. `pop` is the game's running population total (level L+1 is reached at (L+1)(L+2)/2 - 1, checked on 319/328 city-turns); `popMax` = level+1, which is really the city's unit limit. No `unitsMax`/`walls` (not reliably readable).
- `units`: every visible unit (own and enemy). `hp` in hearts (internal health / 10, may be .5). `moved`/`attacked` only for own units.
- `opponents`: only players the local player has met; `score` only if the game exposes it to the player.
- `income`: stars at the start of next turn (sum of city production), if obtainable; else omitted.

### `GET /actions`
```json
{"ok":true,"stateId":17,"forced":false,
 "actions":[
  {"id":0,"k":"move","u":4,"to":[[5,7],[6,6],[6,7]]},
  {"id":1,"k":"attack","u":4,"to":[7,6],"dmg":5,"ret":5,"kill":false},
  {"id":2,"k":"capture","u":4,"at":[5,6]},
  {"id":3,"k":"unit","u":4,"cmd":"Recover"},
  {"id":4,"k":"train","city":[5,5],"unit":"Warrior","cost":2},
  {"id":5,"k":"build","at":[4,5],"imp":"Farm","cost":5},
  {"id":6,"k":"research","tech":"Archery","cost":6},
  {"id":7,"k":"reward","city":[5,5],"reward":"Workshop"},
  {"id":8,"k":"endTurn"}]}
```
- **Moves are grouped**: one action per unit with a `to` list; act with `{"id":0,"to":[6,6]}`. All other kinds are one action per id.
- `attack` includes the game's own `GetBattleResults` preview: `dmg` (hearts dealt), `ret` (hearts taken back; omitted if no retaliation), `kill` (target dies).
- `unit` covers every remaining `GetUnitActions` command by its `CommandType` name (`Recover`, `Promote`, `Disband`, `HealOthers`, `Boost`, `ExamineRuins`, `Upgrade`, …). Improvement abilities (e.g. `Destroy`, `BurnForest`, `ClearForest`, `GrowForest`) appear as `{"k":"ability","at":[x,y],"cmd":"ClearForest","cost":…}`.
- Only actions that pass `IsValid` and the player can afford are listed.
- `forced: true` means a command trigger is pending (e.g. city reward choice); only those actions are listed.
- `endTurn` is always last when legal.

### `POST /act`
```json
{"stateId":17,"id":0,"to":[6,6]}
```
Rejects stale `stateId` (`{"ok":false,"error":"stale","stateId":18}`) and unknown ids. On success, after the game is `ready` again:
```json
{"ok":true,"stateId":18,
 "events":["Warrior 4 moved to [6,6]","revealed 5 tiles"],
 "changes":{"me":{"stars":7},"units":[{...full unit...}],"removedUnits":[9],"tiles":[{...full tile...}],"cities":[{...}]}}
```
`changes` holds full objects (same shape as `/state`) for everything that changed. `?full=1` returns the full state instead of `changes`.

### `POST /end_turn`
Ends the turn, waits through the opponents' turns and popups, returns when `ready` on the next turn or `game_over`:
```json
{"ok":true,"phase":"my_turn","turn":4,"stateId":25,
 "events":["Imperius Rider moved to [7,5]","Imperius captured village [8,2]"]}
```
`events`: what the local player could see happen during the opponents' turns, if obtainable (best effort; may be empty in v1).

### `GET /result`
Only in `game_over`:
```json
{"ok":true,"winner":1,"scores":[{"id":1,"tribe":"Bardur","score":8420},{"id":2,"tribe":"Imperius","score":6110}],"turn":30}
```

### `POST /quit`
Returns to the main menu (`menu` phase) from any match state. Clears the model seats.

### `POST /seat`
Pass & Play. `{"seat":3}` adds a model seat, `{"seat":0}` clears them; optional `"startDelay"` (seconds, default 3). With seats set, `my_turn` means a model seat is to move (a client playing one seat also checks `current`); on a model seat the plugin presses the "Next up" START after `startDelay`, skips the recap and dismisses popups, and leaves people's seats alone. `/end_turn` answers `busy` once the turn has passed to another seat.
```json
{"ok":true,"seats":[3],"startDelay":3}
```

## Change log
- v1, 25 Oct 2026: initial contract (Opus).
- v1.3, 31 Oct 2026: `/seat` (Pass & Play model seats); `/status` gains `current`, `players`, `seats`.
- v1.2, 27 Oct 2026: `/resume`; opponents carry `rel` (peace, cooldown) and `out`; actions `peace` (forced accept/decline) and `diplomacy`; `pop`/`popMax` meaning corrected.
- v1.1, 25 Oct 2026: from Sonnet's plugin report: POSTs need a body; localhost only; cities drop `unitsMax`/`walls`; `Disband`/`Destroy` not listed in `/actions`; harvest is `build` with `imp` = the harvest name (e.g. `Hunting`); `stateId` also advances on opponent commands; `/end_turn` `turn` is the game's `CurrentTurn` (30 at Perfection game over).
