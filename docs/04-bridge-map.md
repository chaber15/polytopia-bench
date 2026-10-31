# Bridge map: live game internals for a BepInEx plugin

Names and signatures from Mac 2.17.3 **16376** (`/tmp/poly-cs`, `extracted/il2cpp/metadata.json`). The Steam / PolyMod build is **16375**. Use **class / method / field names**, not addresses. Addresses here are only for this Mac binary.

Assemblies the plugin will actually touch:

- `PolytopiaAssembly` — `GameManager`, `ClientBase`, `ClientActionManager`, `GameEvents`, UI reactions
- `GameLogicAssembly` — `GameState`, commands, `AI`, `BattleHelpers`, `CommandUtils`, `PathFinder`
- `Polytopia.Data` — `GameLogicData`, `TechData`, `UnitData`, `ImprovementData`
- `PolytopiaBackendBase.Game` — `BotDifficulty`

Do **not** call `ActionManager.ExecuteCommand` from the plugin. The UI submits through `ClientBase.SendCommand` so reactions, animations, save, and multiplayer stay consistent.

---

## 1. Finding the live game

**Read closely** (C# dump + symbolized skims of getters and UI submit).

### Singleton

`GameManager` (`MonoBehaviour`, `PolytopiaAssembly`):

| Name | Kind | Notes |
|---|---|---|
| `GameManager.Instance` | static property | Live manager |
| `GameManager.Client` | static `ClientBase` | Session object |
| `GameManager.GameState` | static `GameState` | Public accessor used everywhere in UI |
| `GameManager.LocalPlayer` | static `PlayerState` | Forwards to `Client.GetCurrentLocalPlayer()` |
| `GameManager.mockedGameState` | static field | Debug override; ignore in a real match |
| `GameManager.debugAutoPlayLocalPlayer` | static `bool` | If true, the built-in AI plays the local human |

`GameManager.LocalPlayer` **Read closely**: `get_Client()` then `ClientBase.GetCurrentLocalPlayer()`.

`ClientBase.GameState` **Read closely**: `ldr x0, [x0, #0x38]` → field `currentGameState`.

### Session object (`ClientBase`)

| Field / property | Type | Role |
|---|---|---|
| `currentGameState` | `GameState` (private, +0x38) | Live state |
| `GameState` | property | Returns `currentGameState` |
| `ActionManager` | `ClientActionManager` | Reactions / execute |
| `clientType` | `ClientBase.ClientType` | `Local=0`, `Remote=1`, `PassAndPlay=2`, `Replay=3` |
| `IsWaitingForCommand` | `bool` | Safe to list moves / send |
| `HasLocalAI` | `bool` | CPU is playing this client |
| `IsPlayerLocal(byte playerId)` | method | Local vs opponent |
| `GetCurrentLocalPlayer()` | `PlayerState` | Local human (or current hotseat seat) |
| `IsSpectating` / `IsReplay` / `IsRecap` | `bool` | Skip hooks in these modes |

### Whose turn, and is it the local human?

| Question | Where |
|---|---|
| Whose turn | `GameState.CurrentPlayer` (`byte` player id). Also `CurrentPlayerIndex`. |
| Match phase | `GameState.CurrentState`: `Unknown=0`, `Lobby=1`, `Started=2`, `FinalTurn=3`, `Ended=4` |
| Local human | `GameManager.LocalPlayer.Id` |
| Is it local? | `GameManager.IsPlayerLocal(GameState.CurrentPlayer)` **or** `Client.IsPlayerLocal(...)` |
| CPU taking the turn | `PlayerState.AutoPlay` on the current player, and/or `Client.HasLocalAI` |
| Wait for UI idle | `Client.IsWaitingForCommand == true` and `Client.ActionManager.IsProcessing == false` |

Plugin turn gate (inferred from how the AI coroutine and InteractionBar gate themselves):

1. `GameState != null` and `CurrentState` is `Started` or `FinalTurn`
2. `IsPlayerLocal(CurrentPlayer)`
3. `IsWaitingForCommand`
4. Drain `pendingCommandTriggers` first (section 3)

---

## 2. State layout

**Skimmed** (C# field lists). Types and names are exact. “LLM needs” is a recommendation, not a game flag.

### `GameState`

| Field / property | Type | LLM? |
|---|---|---|
| `Version` | `int` | no |
| `Seed` | `int` | optional |
| `CurrentTurn` | `uint` | yes |
| `CurrentPlayerIndex` | `byte` | yes |
| `CurrentPlayer` | `byte` (property) | yes |
| `CurrentState` | `GameState.State` | yes |
| `Settings` | `GameSettings` | difficulty, game type |
| `Map` | `MapData` | yes |
| `PlayerStates` | `List<PlayerState>` | yes |
| `CurrentCommand` | `ushort` | no |
| `CommandStack` | `List<CommandBase>` | no |
| `ActionStack` | `List<ActionBase>` | no |
| `pendingCommandTriggers` | `List<CommandTrigger>` | yes — blocks other commands |
| `GameLogicData` | property | tables |
| `mockedGameLogicData` | field | debug only |

Helpers: `TryGetPlayer(byte, out PlayerState)`, `TryGetUnit(uint, out UnitState)`, `EndPlayerTurn(bool newTurn=false)`, `HasQueuedCommands()`, `GetCommand(CommandType)` (factory).

### `PlayerState`

| Field / property | Type | LLM? |
|---|---|---|
| `Id` | `byte` | yes |
| `UserName` | `string` | optional |
| `AutoPlay` | `bool` | yes (CPU vs human) |
| `startTile` | `WorldCoordinates` | optional |
| `tribe` / `tribeMix` | `TribeType` | yes |
| `handicap` | `int` | CPU difficulty (see §6) |
| `availableTech` | `List<TechData.Type>` | yes |
| `unlockedTechCache` | `List<TechData>` | yes |
| `Currency` | `int` (property; field `currency`) | **stars** |
| `score` | `uint` | yes |
| `cities` | `int` | yes |
| `aiState` | `AIState` | **do not export**; `GetMove` mutates this |
| `knownPlayers` | `List<byte>` | diplomacy fog |
| `relations` | `Dictionary<byte, DiplomacyRelation>` | later MP |
| `kills` / `casualities` / `wipeOuts` | `uint` | optional |

Constants: `NO_PLAYER_ID = 0`, `NATURE_PLAYER_ID = 255`.

Cities as objects are **not** a list on the player. Count is `cities`; actual cities are tiles whose `improvement` is a city (see `ImprovementState` + `TileData.capitalOf` / `rulingCityCoordinates`).

### `MapData`

| | Type |
|---|---|
| `Width` / `Height` | `ushort` |
| `Tiles` | `TileData[]` |
| `Continents` | `WorldContinent[]` |

### `TileData` — fog lives here

| Field | Type | LLM? |
|---|---|---|
| `coordinates` | `WorldCoordinates` (`X`,`Y`) | yes |
| `terrain` | `TerrainData.Type` | yes |
| `owner` | `byte` | yes |
| `capitalOf` | `byte` | yes if city |
| `explorers` | `List<byte>` | **fog**: player ids who have seen the tile |
| `improvement` | `ImprovementState` | yes if explored |
| `resource` | `ResourceState` | yes if explored |
| `unit` | `UnitState` (property) | use `GetUnit`, not the raw field |
| `hasRoad` / `HasRoad` | `bool` | yes |
| `hasRoute` | `bool` | optional |
| `effects` | `List<EffectType>` | flood/swamp/etc. |
| `rulingCityCoordinates` | `WorldCoordinates` | city territory |

Fog / visibility methods **Skimmed** (signatures; bodies not re-read this pass):

```
bool GetExplored(byte playerId)
void SetExplored(byte playerId, bool explored)
UnitState GetUnit(GameState gameState, byte playerId, bool includeHidden = false)
ResourceState GetResource(GameState gameState, byte playerId)
```

Export rule for the local player `p`:

1. If `!tile.GetExplored(p)` → emit “unexplored” (coords only). Do not leak `terrain` / `resource` / `unit` / `improvement` from the raw fields.
2. If explored → `terrain`, `owner`, `GetResource(state, p)`, `improvement` (city level/pop if present), `GetUnit(state, p, includeHidden: false)`.
3. Hidden units: `UnitState.IsInvisible(GameState, byte playerId)` / `IsInvisible(PlayerState viewer)`. `includeHidden: false` is the player-visible path.

`ResourceState` has one field: `ResourceData.Type type`.

### `ImprovementState` (city level / population)

| Field | Type | LLM? |
|---|---|---|
| `type` | `ImprovementData.Type` | yes |
| `level` | `ushort` | **city level** |
| `population` | `short` | **city pop** |
| `xp` | `short` | optional |
| `production` | `ushort` | income |
| `rewards` | `List<CityReward>` | after level-up |
| `name` | `string` | optional |
| `founder` | `byte` | optional |

`owner` on `ImprovementState` is `[Obsolete]` — use `TileData.owner`.

### `UnitState`

| Field | Type | LLM? |
|---|---|---|
| `id` | `uint` | yes |
| `owner` | `byte` | yes |
| `type` | `UnitData.Type` | yes |
| `coordinates` | `WorldCoordinates` | yes |
| `health` | `ushort` | yes (internal ×10; 10 = 1 heart) |
| `promotionLevel` | `ushort` | **veteran** (HP bump; not an attack flag) |
| `xp` | `ushort` | yes |
| `moved` | `bool` | yes |
| `attacked` | `bool` | yes |
| `effects` | `List<UnitEffect>` | Frozen/Poisoned/Boosted/Invisible/… |
| `passengerUnit` | `UnitState` | boats |
| `UnitData` | `UnitData` | table row |
| `home` | `WorldCoordinates` | optional |

Helpers: `CanMove()`, `CanAttack()`, `HasEffect(UnitEffect)`, `GetMaxHealth(this UnitState, GameState)` on `UnitDataExtensions`.

Veteran: `promotionLevel > 0`. Combat `GetAttack` does **not** add +50 for veteran (that was Boosted). See `01-game-mechanics.md`.

---

## 3. Legal moves — call the game, do not reimplement

**Skimmed** (signatures from C# dump). `CommandUtils.AddCommand` runs `command.IsValid`. Prefer `includeUnavailable: false`.

### Movement

```
List<WorldCoordinates> PathFinder.GetMoveOptions(this GameState gameState, WorldCoordinates start, int maxCost, UnitState unit)
List<WorldCoordinates> UnitDataExtensions.GetMovementOptions(this UnitState unit, GameState gameState, int range)
bool UnitDataExtensions.CanMoveTo(this UnitState unitState, GameState gameState, WorldCoordinates coordinates)
int UnitDataExtensions.GetMovement(this UnitState unitState, GameState gameState)
```

Use `GetMovement` for `maxCost` / `range`. Then wrap each coord as `new MoveCommand(playerId, unit, coord)` and keep those that `IsValid`.

### Attacks

```
List<WorldCoordinates> UnitDataExtensions.GetAttackOptions(this UnitState unit, GameState state, int range, bool ignoreDiplomacyRelation = false)
List<WorldCoordinates> UnitDataExtensions.GetAttackOptionsAtPosition(GameState gameState, byte playerId, WorldCoordinates position, int range, bool includeHiddenTiles = false, UnitState customUnitState = null, bool ignoreDiplomacyRelation = false)
int UnitDataExtensions.GetRange(this UnitState unitState, GameState gameState)
bool UnitDataExtensions.CanAttackAnything(this UnitState unitState, int range, GameState gameState)
```

Wrap: `new AttackCommand(playerId, unit, target)`.

### Unit / tile actions (capture, recover, promote, boost, …)

```
List<CommandBase> CommandUtils.GetUnitActions(GameState gameState, PlayerState player, TileData tile, bool includeUnavailable = false)
List<CommandBase> CommandUtils.GetImprovementAbilities(GameState gameState, PlayerState player, TileData tile, bool includeUnavailable = false)
List<CommandBase> CommandUtils.GetDiplomacyCommandsForOpponent(GameState gameState, PlayerState player, byte opponentId, bool includeUnavailable = false)
```

`GetUnitActions` already returns constructed `CommandBase` instances (capture, recover, heal, hide, …).

### Train / build

```
List<TrainCommand> CommandUtils.GetTrainableUnits(GameState gameState, PlayerState player, TileData tile, bool includeUnavailable = false)
List<CommandBase> CommandUtils.GetBuildableImprovements(GameState gameState, PlayerState player, TileData tile, bool includeUnavailable = false)
bool GameLogicData.CanBuild(GameState gameState, TileData tile, PlayerState playerState, ImprovementData improvement)
List<UnitData> GameLogicData.GetUnlockedUnits(PlayerState player, GameState state, bool shouldIncludeHidden)
bool GameLogicData.IsUnlockable(UnitData.Type type, PlayerState player, GameState gameState)
bool GameLogicData.IsUnlockable(ImprovementData.Type type, PlayerState player, GameState gameState)
```

`GameLogicData` is `gameState.GameLogicData`.

### Tech

```
List<TechData> GameLogicData.GetUnlockableTech(PlayerState player, GameState gameState)
bool GameLogicData.IsUnlockable(TechData.Type type, PlayerState player)
int GameLogicData.GetTechPrice(TechData techData, PlayerState playerState, GameState state)
```

Price **Read closely** (`GetTechPrice`): `4 + tier × PlayerState.cities`, then Literacy (`PlayerAbility` 2) × ≈2/3 and ceil. `GameState` argument unused. See `01-game-mechanics.md`.

### `CommandValidation`

```
bool CommandValidation.CanAfford(this PlayerState playerState, int cost)
bool CommandValidation.CanAfford(this PlayerState playerState, UnitData unitData)
bool CommandValidation.CanAfford(this PlayerState playerState, ImprovementData improvementData)
bool CommandValidation.CanAfford(this PlayerState player, GameState gameState, TechData techData)
bool CommandValidation.CanTrainUnit(this PlayerState player, GameState state, UnitData.Type unitType)
bool CommandValidation.HasUnit(GameState state, WorldCoordinates coordinates)
bool CommandValidation.HasCity(GameState state, WorldCoordinates coordinates)
bool CommandValidation.CanCitySupportUnit(GameState state, WorldCoordinates coordinates)
bool CommandValidation.HasUnitTerrain(GameState state, WorldCoordinates coordinates, UnitData unit)
```

### Always-on validation

```
bool CommandBase.IsValid(GameState state)
bool CommandBase.IsValid(GameState state, out string validationError)
bool CommandBase.PassesBasicValidation(GameState state, out string validationError)
bool ClientActionManager.CanReceiveCommand(CommandBase command, GameState gameState)  // static
```

The UI calls `CanReceiveCommand` **before** `SendCommand`. Mirror that.

### Forced moves (city reward, etc.)

If `GameState.pendingCommandTriggers` is non-empty, almost every other command fails with `VALIDATION_ERROR_COMMAND_TRIGGER_EXISTS`.

```
bool CommandTriggerUtils.TryGetTriggerCommand(GameState gameState, out CommandBase command)
bool GameState.TryGetPendingCommandTrigger(byte playerId, out CommandTrigger trigger)
bool ClientActionManager.IsWaitingForCommandTrigger(byte playerId)
```

The built-in AI does exactly this before `GetMove`. The plugin should too: if `TryGetTriggerCommand` succeeds, that is the only legal command (or a small set of `CityRewardCommand` choices).

Suggested enumeration per local turn:

1. Trigger command if any
2. For each explored own unit: `GetMovementOptions`, `GetAttackOptions`, `GetUnitActions`
3. For each explored own city tile: `GetTrainableUnits`, `GetBuildableImprovements`, `GetImprovementAbilities`
4. `GetUnlockableTech` + `GetTechPrice` / `CanAfford`
5. Diplomacy via `GetDiplomacyCommandsForOpponent`
6. Always offer `EndTurnCommand` (after `IsValid`)

---

## 4. Sending a move

### Command constructors

Every command also has a parameterless ctor for deserialize. Plugin should use the parameterized ones. Base: `CommandBase.PlayerId`.

| Class | Constructor | `CommandType` |
|---|---|---|
| `MoveCommand` | `(byte playerId, UnitState unit, WorldCoordinates target)` | `Move = 6` |
| `AttackCommand` | `(byte playerId, UnitState unit, WorldCoordinates target)` | `Attack = 2` |
| `ResearchCommand` | `(byte playerId, TechData.Type type)` | `Research = 8` |
| `TrainCommand` | `(byte playerId, UnitData.Type type, WorldCoordinates coordinates)` | `Train = 5` |
| `BuildCommand` | `(byte playerId, ImprovementData.Type type, WorldCoordinates coordinates)` | `Build = 1` |
| `EndTurnCommand` | `(byte playerId)` | `EndTurn = 15` |
| `CaptureCommand` | `(byte playerId, uint unitId, WorldCoordinates coordinates)` | `Capture = 7` |
| `PromoteCommand` | `(byte playerId, WorldCoordinates coordinates)` | `Promote = 13` |
| `RecoverCommand` | `(byte playerId, WorldCoordinates coordinates)` | `Recover = 3` |
| `HealOthersCommand` | `(byte playerId, WorldCoordinates coordinates)` | `HealOthers = 4` |
| `StayCommand` | `(byte playerId, WorldCoordinates coordinates)` | `Stay = 21` |
| `BoostCommand` | `(byte playerId, WorldCoordinates coordinates)` | `Boost = 25` |
| `DisbandCommand` | `(byte playerId, WorldCoordinates coordinates)` | `Disband = 10` |
| `DestroyCommand` | `(byte playerId, WorldCoordinates coordinates)` | `Destroy = 9` |
| `ExamineRuinsCommand` | `(byte playerId, WorldCoordinates coordinates)` | `ExamineRuins = 14` |
| `UpgradeCommand` | `(byte playerId, UnitData.Type type, WorldCoordinates coordinates)` | `Upgrade = 16` |
| `CityRewardCommand` | `(byte playerId, CityReward reward, WorldCoordinates coordinates)` | `CityReward = 11` |
| `HideCommand` | `(byte playerId, WorldCoordinates coordinates)` | `Hide = 33` |
| `DisembarkCommand` | `(byte playerId, WorldCoordinates coordinates)` | `Disembark = 36` |
| `DecomposeCommand` | `(byte playerId, WorldCoordinates coordinates)` | `Decompose = 26` |
| `ExplodeCommand` | `(byte playerId, WorldCoordinates coordinates)` | `Explode = 24` |
| `FloodCommand` | `(byte playerId, WorldCoordinates coordinates)` | `Flood = 37` |
| `FreezeAreaCommand` | `(byte playerId, WorldCoordinates coordinates)` | `FreezeArea = 17` |
| `BreakIceCommand` | `(byte playerId, WorldCoordinates coordinates)` | `BreakIce = 18` |
| `SwarmCommand` | `(byte playerId, WorldCoordinates coordinates)` | `Swarm = 38` |
| `ClearTileEffectCommand` | `(byte playerId, WorldCoordinates coordinates, TileData.EffectType effect)` | `ClearTileEffect = 39` |
| `PeaceTreatyCommand` | `(byte playerId, byte opponentId, WorldCoordinates coordinates)` | `PeaceTreaty = 27` |
| `PeaceRequestResponseCommand` | `(byte playerId, byte opponentId, bool accepted)` | `PeaceRequestResponse = 28` |
| `BreakPeaceCommand` | `(byte playerId, byte opponentId, WorldCoordinates coordinates)` | `BreakPeace = 29` |
| `EstablishEmbassyCommand` | `(byte playerId, byte opponentId, WorldCoordinates coordinates)` | `EstablishEmbassy = 30` |
| `DestroyEmbassyCommand` | `(byte playerId, byte opponentId, WorldCoordinates coordinates)` | `DestroyEmbassy = 32` |
| `ResignCommand` | `(byte playerId, byte resignedPlayerId, byte kickerPlayerId, bool wasKicked)` | `Resign = 35` |
| `StartMatchCommand` | `(byte playerId)` | `StartMatch = 20` |
| `EndMatchCommand` | `(byte playerId)` | `EndMatch = 22` |

`CommandType` also lists `Harvest = 23` and `SelectTribe = 19`. **No** `HarvestCommand` / `SelectTribeCommand` types in the C# dump or `metadata.json`. Treat as unused / leftover unless a later dump finds them.

Factory: `GameState.GetCommand(CommandType type)` then fill fields — worse than the ctors above.

### UI submit path — **Read closely** (symbolized skim)

`InteractionBar.<ClickedAbility>g__ExecuteCommand|0` and `PlayerInfoPopup.<DiplomacyButton_OnClicked>g__ExecuteCommand|35_0`:

1. `GameManager.GameState`
2. `ClientActionManager.CanReceiveCommand(command, gameState)` — abort + popup if false
3. `InputEvents.SelectionCleared()`
4. `GameManager.Client.SendCommand(command)`

The built-in AI coroutine uses the same last two checks (`CanReceiveCommand` then `SendCommand`).

`ClientBase.SendCommand(CommandBase command)` **Skimmed**: branches on `clientType`. Local / pass-and-play ends in `ClientBase.ReceiveCommand(CommandBase)` (then `ActionManager.ExecuteCommand` + reaction queue). `Remote` goes `SendCommandRemote` → `SendCommandToServer`.

**Plugin path (same as UI):**

```
GameManager.Client.SendCommand(command)
```

after `CanReceiveCommand`. Do not call `ActionManager.ExecuteCommand` directly: that skips `ClientActionManager.reactionQueue` (animations, `StartTurnReaction` / `EndTurnReaction`, save, server).

Also do not set `GameManager.debugSkipNextSend`.

---

## 5. Turn hooks

**Read closely** (C# events + symbolized calls from reactions).

### Preferred: subscribe, do not patch the reaction bodies

`GameEvents` (`static`, `PolytopiaAssembly`):

| Event | Delegate | Fired from |
|---|---|---|
| `OnTurnStarted` | `void OnTurnStartedEvent()` | `StartTurnReaction.Execute` → `GameEvents.TurnStarted()` |
| `OnTurnEnded` | `void OnTurnEndedEvent()` | `EndTurnReaction.Execute` → `GameEvents.TurnEnded()` |
| `OnStateUpdated` | `void` | after commands |
| `OnCommandExecuted` | `void` | after a command |
| `OnFinishedProcessing` | `void` | reaction queue drained |
| `OnMatchStart` / `OnMatchEnd` | match lifetime | |
| `OnWaitingForServer` | `void(bool)` | online |

`StartTurnReaction.Execute` also calls `DoStartTurnNotification()` when the viewing player is local and not spectating, then `GameEvents.TurnStarted()`.

Harmony postfix on `GameEvents.TurnStarted` / `TurnEnded`, **or** a C# `+=` on `OnTurnStarted` / `OnTurnEnded`, is the hook. Then wait until `Client.IsWaitingForCommand` before exporting JSON (animations may still be running when the event fires).

`ClientInteraction.OnTurnStarted` is a UI subscriber (selection reset), not the source of truth.

### Alternative Harmony targets

| Method | Why |
|---|---|
| `StartTurnReaction.Execute(Action onComplete)` | local-turn presentation |
| `StartTurnReaction.DoStartTurnNotification()` | banner / SFX; local only |
| `EndTurnReaction.Execute(Action onComplete)` | fires `TurnEnded` |
| `GameManager.TryCreateAndExecuteAICommands()` | CPU turn; postfix if you need to know the bot is about to move |

---

## 6. Built-in AI as a helper

**Read closely** (signatures + AI coroutine skim). `GetMove` body was not re-disassembled this pass; mutation risk is from `AnalyzeSituationIfNeeded` / `PlayerState.aiState`.

```
static CommandBase AI.GetMove(GameState gameState, PlayerState player, CommandType specificCommand = CommandType.None)
static CommandBase AI.EndCommand(GameState gameState, PlayerState player)
static void AI.AnalyzeSituationIfNeeded(GameState gameState, PlayerState player)
static void AI.AnalyzeSituation(GameState gameState, PlayerState player)
static float AI.StupidFactor(GameState gameState, PlayerState player, int rngCounter1 = 0, int rngCounter2 = 0)
int PlayerState.GetStupidity()
```

How the game calls it (`GameManager+<TryCreateAndExecuteAICommandsCoroutine>d__128.MoveNext`):

1. `GameState.TryGetPlayer(CurrentPlayer, out player)`
2. Skip unless `player.AutoPlay` (field +0x34) and (`HasLocalAI` or not the local human), plus `GameManager.debugAutoPlayLocalPlayer` for the human
3. If `CommandTriggerUtils.TryGetTriggerCommand` → use that
4. Else `AI.GetMove(gameState, player, CommandType.None)`
5. `CanReceiveCommand` then `Client.SendCommand`

Difficulty is **not** an argument to `GetMove`. It is:

| Name | Where |
|---|---|
| `GameSettings.Difficulty` | `BotDifficulty`: `Easy=0`, `Normal=1`, `Hard=2`, `Crazy=3`, `Frozen=4` |
| `GameSettings.HandicapFromDifficulty(BotDifficulty)` | maps to `PlayerState.handicap` |
| `PlayerState.GetStupidity()` | **Read closely**: if `AutoPlay`, `max(0, 2 - handicap)`; else **0** |
| `AI.StupidFactor` | uses that stupidity to randomly pick worse moves |

So on a **human** `PlayerState` (`AutoPlay == false`), `GetMove` still runs but at full strength (stupidity 0), unless you temporarily set `AutoPlay` / `handicap`.

**Risks if used as a hint for the LLM side:**

- `AnalyzeSituationIfNeeded` writes `PlayerState.aiState` (missions, hitlist). That is live state, not a copy.
- `GetMove` may call into scoring that reads the real `GameState`. Treat it as possibly mutating `player.aiState` even if it does not execute a command.
- Safer: clone is not available in-process; either accept the `aiState` dirt, or skip this helper until you have verified `AnalyzeSituation` on a copy.

`AI.isEnabled` (static bool) can disable the CPU entirely — do not flip it if you still want the built-in opponent.

---

## 7. Combat preview

**Read closely** (prior `GetBattleResults` disassembly) + **Skimmed** (C# signature this pass).

```
static BattleResults BattleHelpers.GetBattleResults(
    GameState gameState,
    UnitState attackingUnit,
    UnitState defendingUnit,
    bool accountForPeace = true,
    bool simpleData = false)

struct BattleResults {
    int attackDamage;            // internal ×10 (50 = 5 hearts)
    int retaliationDamage;
    bool shouldMoveToDefeatedEnemyTile;
    bool shouldResetPacifistTask;
}
```

Static; returns a struct. The read of `0x018A6258` computed damage and packed it; it did not store `UnitState.health`. `simpleData: true` skips post-kill pathfinding. `accountForPeace: true` is the UI default.

For a hypothetical: pass the live attacker/defender objects (or copies if you ever see a write). Hearts on screen = `Round(damage) / 10` via `BattleHelpers.Round`.

Also: `BattleHelpers.CanDefenderRetaliate` (private). Formula in `01-game-mechanics.md`. Retaliation uses **pre-damage** defender HP (no health store in this function; warrior vs warrior stays 5 back). Walls **do** increase retaliation because they sit in `defenceForce`.

UI already shows this: `ClientInteraction` has `damageIndicator` and `retaliationDamageIndicator`.

---

## 8. Starting a game from code

**Read closely** (`GameSetupScreen.OnStartGameClickedAndFaded` → `GameManager.CreateSinglePlayerGame` → `LocalClient` + `ClientBase.CreateSession(GameSettings, Guid)` → `LoadLevel`). There is no enum value named Creative; the UI’s custom/creative slot is `GameMode.Custom` / `Sandbox`.

### Settings object

`GameManager.PreliminaryGameSettings` get/set **is** the instance field `GameManager.settings` (+0x20). The setup screen writes it; `CreateSinglePlayerGame` reads the same object.

`GameSettings` (`GameLogicAssembly`):

| Name | Type | Role |
|---|---|---|
| `BaseGameMode` / `RulesGameMode` | `GameMode` | `None=0`, `Perfection=1`, `Domination=2`, `Glory=3`, `Might=4`, `Custom=5`, `Sandbox=6`, `Tutorial=7` |
| `GameType` | `GameType` | SP path sets this to `SinglePlayer=0` |
| `Difficulty` | `BotDifficulty` | `Easy=0` … `Crazy=3`, `Frozen=4` |
| `OpponentCount` | `int` | number of CPU opponents |
| `MapSize` | `int` | tile width; UI enum `MapSize` Tiny=1 … Massive=6 via `MapSizeExtensions.ToMapWidth` |
| `mapPreset` | `MapPreset` | `None=0`, `Dryland=1`, `Lakes=2`, `Continents=3`, `Archipelago=4`, `WaterWorld=5`, `Pangea=6` |
| `rules` | `GameRules` | win conditions |
| `players` | `List<PlayerData>` | optional explicit seats |
| `disabledTribes` | `List<TribeType>` | |
| `GameName` | `string` | |

`CreateSinglePlayerGame` **Read closely**: if `mapPreset == None`, it stores `Continents` (3). `GameType` is forced to 0 (`SinglePlayer`).

`GameRules` (`LoadPreset(GameMode)` **Read closely**):

| Mode | `TurnLimit` | `ScoreLimit` | `WinByCapital` | `WinByExtermination` |
|---|---|---|---|---|
| Perfection | **30** (constant pool first word = 0x1E) | 0 | false | false |
| Domination | 0 | 0 | false | **true** |
| Might | 0 | 0 | **true** | **true** |
| Glory | packed constant at +0x10 | (not decoded) | false | false |
| Custom / Sandbox | 0 | 0 | false | false |

Also: `AllowSpecialTribes` starts true, `AllowTechSharing` true, `PlayerDeathCondition` `Cities=0` / `Units=1`.

`PlayerData` for a seat: `type` (`Bot=1`, `LocalUser=2`, `OnlineUser=4`), `tribe`, `tribeMix`, `climate`, `botDifficulty`, `skinType`.

CPU players: `GameStateUtils.CreateAIOpponent(int id, TribeType tribe, int handicap, SkinType skin, TribeType climate=None)` **Read closely** sets `Id`, `AutoPlay=true` (+0x34), `tribe`, `skinType`, `handicap`. `AddAIOpponent(GameState, TribeType, int handicap, SkinType)` appends one. `GameSettings.HandicapFromDifficulty(BotDifficulty)` maps Easy–Frozen (table at a static; out of range → 0).

If `OpponentCount >= 1` and you do not pre-fill `players` with bots, `CreateLocalGame` / `CreateSession` picks tribes with `GetRandomPickableTribe`.

Human tribe: `GameManager.SetStartingTribeValues(TribeType tribe, SkinType skin, TribeType climate=None, TribeType tribeMix=None)` then `StartingTribe` / `StartingSkin` / `StartingClimate` / `StartingTribeMix`.

Helpers: `GameSettings.ApplyGameTypeDefaults(GameType, GameMode)`, `GameRules.LoadPreset(GameMode)`, `GameSettingsExtensions.SaveToDisk` / `TryLoadFromDisk` (last UI choices).

### Seed

`GameState.Seed` exists. `GameSettings` has **no** seed field. Stock generate is `MapGenerator.Generate(GameState, MapGeneratorSettings, Action onComplete=null, int numIterations=-1)`, which draws `RandomNumberGenerator.GetInt32(0x7fffffff)` then `GenerateInternal(int seed, GameState, MapGeneratorSettings)`.

Reproducible maps: `MapGenerator.GenerateWithSeed(int seed, GameState state, MapGeneratorSettings settings, Action onComplete=null)`. The SP create path does **not** call that. `SettingsUtils.RandomSeed` is a player-pref string; **not** seen as an argument to `Generate`. Plugin that needs a fixed seed must Harmony-prefix `Generate` or build the state itself.

`GameSettings.GetMapGeneratorSettings()` → `MapGeneratorSettings` (`mapType` = preset, wetness/richness, …).

### The start method — can the plugin call it?

```
void GameManager.CreateSinglePlayerGame()
CreateSessionResult ClientBase.CreateSession(GameSettings settings, Guid gameId)
CreateSessionResult ClientBase.CreateSession(byte[] gameStateData, Guid gameId)  // resume
void GameManager.LoadLevel()
enum CreateSessionResult { Success=0, FailedCreate=1, FailedOpen=2 }
GameState GameStateUtils.CreateLocalGame(int gameVersion, GameSettings settings, PlayerState ownPlayerState, List<PlayerState> opponents=null)
void GameManager.SetLocalClient()
void GameManager.OnGameReady()
```

`CreateSinglePlayerGame` **Read closely**: `SetLoadingGame(true)` → `new LocalClient()` stored as `GameManager.client` → `CreateSession(settings, Guid.NewGuid())` → on `Success`, `LoadLevel()`. `CreateSession` builds players, `MapGenerator.Generate`, starting units (`TrainUnitScored`), `new StartMatchCommand(1)`, `UpdateGameStateImmediate`, `SaveSession`, `PrepareSession`.

Yes, the plugin can call `GameManager.Instance.CreateSinglePlayerGame()` and skip the menus, **if** `GameManager.Instance` is alive and `PreliminaryGameSettings` is filled. That object lives on the boot/start scene (`GameManager` is a `MonoBehaviour`). Do not call it from a destroyed level.

`LoadLevel` **Read closely**: `PopupManager.RemoveAllPopups()`, `InputManager.DisableAllInput()`, `SceneManager.LoadScene(string, Single)`. The scene name is a hardcoded Il2Cpp string (not decoded here). After load: `OnSceneLoaded` → `OnLevelLoaded` → `OnGameReady` (`MapRenderer.RenderMap`, camera center, `ClientActionManager.Resume`, fade).

Recipe (inferred from the UI path):

1. Be on the start scene (`GameManager.Instance != null`, level not loaded).
2. Fill `PreliminaryGameSettings` (mode, difficulty, opponent count, map size, preset, rules).
3. `SetStartingTribeValues(...)`.
4. `CreateSinglePlayerGame()`.
5. Wait for `GameEvents.OnMatchStart` / `OnTurnStarted` and `IsWaitingForCommand`.

`NewGameIntent` is the deep-link equivalent (parses gameMode / tribe / difficulty from a URI) — same destination, not needed for the harness.

---

## 9. Detecting the end of a game

**Read closely** (`EndTurnAction.Execute` → `TryGetWinner` → `GameOverAction`; `EndMatchCommand`; `EndMatchReaction.Execute` → `GameManager.MatchEnded`).

### How a match ends

`GameState.TryGetWinner(out PlayerState winner)` → `TryGetWinnerDefault` **Skimmed**:

1. `GameStateUtils.CountRealAlivePlayers <= 1` (elimination / last human).
2. `rules.WinByExtermination` and `CountAlivePlayers == 1`.
3. `rules.WinByCapital` and `PlayerExtensions.CountCapitals` (Might / capital capture).
4. `rules.TurnLimit > 0` and `CurrentTurn` has reached it (Perfection 30).
5. `rules.ScoreLimit > 0` and a player’s `score` (+0xA0) meets it (Glory).

`EndTurnAction.Execute` **Read closely**: `EndPlayerTurn`, then `TryGetWinner`. On a winner it queues `new GameOverAction(playerId, winningPlayerId)` and does **not** start the next turn. `GameOverAction.Execute` logs the winner (and the later `mov w8, #3` is consistent with `CurrentState = FinalTurn`).

`EndMatchCommand.IsValid` **Read closely**: requires `CurrentState == FinalTurn` (3). `Execute` sets state **4** (`Ended`) and queues `EndMatchAction`.

Two-step: winner found → `FinalTurn` / `GameOverAction` (popup via `GameOverReaction`) → `EndMatchCommand` → `Ended`.

### Result, winner, score, events

| What | Where |
|---|---|
| Phase | `GameState.CurrentState`: `FinalTurn=3`, `Ended=4` |
| Winner | `TryGetWinner(out PlayerState)`; `GameOverAction.WinningPlayerId` |
| Running / final score cache | `PlayerState.score` (`uint`, +0xA0); also `endScore` |
| Breakdown | `PlayerExtensions.GetScore(PlayerState player, GameState state)` → `ScoreDetails` |
| UI | `ResultScreen.Show(bool localPlayerIsWinner, ScoreDetails scoreDetails, byte winnerId=0)` |
| Hook | `EndMatchReaction.Execute` **Read closely** calls `GameManager.MatchEnded(localPlayerIsWinner, scoreDetails, winnerId)` after `GetScore(LocalPlayer, GameState)` |

`GameEvents.OnMatchEnd` / `MatchEnd(bool localPlayerIsWinner, ScoreDetails scoreDetails)` exists. `MatchEnded` itself was not seen calling it (it calls `SendEndGameEvents` = analytics, then `ResultScreen.Show`, then `Client.EndSession`). Subscribe to **both** `OnMatchEnd` and a Harmony postfix on `GameManager.MatchEnded` / `ResultScreen.Show`.

`ScoreDetails`: `territoryScore`, `cultureScore`, `cityScore`, `techScore`, `totalScore`, `difficultyBonus`, `difficultyBonusMultiplier`, `TotalScoreIncludingBonus`.

### Back to a startable state

`ResultScreen.OnReturnToMenu` **Read closely** → `ResultScreen.Hide()` → `GameManager.ReturnToMenu()`.

`ReturnToMenu` unloads the level (`UnloadLevelScene`) and loads the start scene (`LoadStartScene`). `MatchEnded` already calls `Client.EndSession()`.

Unattended loop: postfix `MatchEnded` (or `OnMatchEnd`), read winner + `ScoreDetails`, `ResultScreen.Hide()` if `IsShowing()`, `ReturnToMenu()`, wait until `Instance` is up and level is unloaded, then `CreateSinglePlayerGame()` again.

Risk: `CreateSession` can `DeleteAllSaveFilesOfType` for local SP. Consent / highscore popups in `MatchEnded` can block. `ResultScreen` tweens.

---

## 10. Speed

**Skimmed** (settings + debug fields). There is **no** user-facing animation-speed slider. `SettingsScreen` only has volume, language, UI scale, SFX/ambience/music, suggestions, confirm-turn, replay fog.

| Name | Kind | Safe? |
|---|---|---|
| `ClientBase.SkipRecap()` | public | **Yes** — skips opponent-turn recap playback. Recap is `ClientActionManager.StartRecap` / `IsRecap` / `isRecapping`. |
| `ClientActionManager.HoldExecution(bool)` | public | pauses the reaction queue; opposite of speed |
| `GameManager.Simulate(ClientActionManager actionManager, int commands, Action onComplete=null)` | public static | fast-forwards N commands via `SimulateRoutine`; sets `IsSimulating`. Meant for debug/sim, not the live SP match |
| `ClientActionManager.IsSimulating` / `SimulateCommand()` | | drain reactions without waiting a frame each; `SIMULATION_STEPS_PER_FRAME = 100` |
| `GameManager.debugShouldSkipReactions` | static bool | **debug-only**. Field exists; **no** other C# dump reference — may be compiled out of `POLY_DEBUG` or only tested in IL. Do not rely on it for Steam |
| `debugAutoPlayLocalPlayer` / `debugSkipNextSend` / `debugShowGameUI` | static | debug-only |
| `StartTurnAction.START_TURN_DELAY = 500` | const ms | baked into start-turn presentation |
| `ReactionUtils.CAMERA_FOCUS_DURATION = 0.8f` | const | camera moves |
| `SettingsUtils.ConfirmTurn` | bool | extra end-turn prompt; turn **off** for a harness |
| Unity `Time.timeScale` | engine | not a named game setting. Would speed DOTween and waits; unverified, can desync audio / MP |

CPU turns are not independently time-scaled. They are `TryCreateAndExecuteAICommands` + the same reaction queue. Fast unattended play = `SkipRecap` + `ConfirmTurn=false` + optionally Harmony-shorten reaction `Execute` / camera focus. `debugShouldSkipReactions` is the intended skip-animations flag if it is live on Steam; treat as debug until you see it read.

`GameSettings.IsAutoSkipEnabled` is multiplayer auto-skip of idle players, not animation skip.

---

## 11. Opponent event log

**Skimmed** (fields + recap / command-stack APIs).

Sources, in order of usefulness:

1. **`GameState.CommandStack`** (`List<CommandBase>`) plus `CurrentCommand` (`ushort`). Slice from the last local-turn index to now. `GameState.GetCommandStack()` serializes; `GameStateUtils.GetLastPerformedCommandByPlayer(this GameState, byte playerId)` helps find the cut.
2. **`ClientBase.lastTurnGameState`** — snapshot of the previous local turn. Diff against `currentGameState` after recap.
3. **`GameEvents.OnCommandExecuted`** — `void`, no payload. Use it only as a “queue advanced” tick, then read `CommandStack[^1]`.
4. **`GameState.ActionStack`** — expanded `ActionBase` list (heals, score pops). Noisier than commands.
5. **Recap** — `ClientActionManager.StartRecap` / `EndRecap` / `IsRecap`; `ClientBase.IsRecap`; `SkipRecap()`. This is the UI’s opponent-turn replay. `ReactionBase.IsRecapOrOpponentAction(ActionBase)` gates camera/FX. For a JSON log, prefer the stack, then `SkipRecap` so the harness is not waiting on it.
6. **`GameStateUtils.RegisterCommandResultEvent`** — `CommandResultEvent` is only `Unknown=0`, `GameEnded=2`, `PlayerTurnEnded=3`, `WholeTurnEnded=4`. Not a move log.

Fog rule for the local player `p` (**Inferred** from `TileData` visibility helpers + command shapes):

- Always include: `EndTurnCommand`, and any command whose `PlayerId == p`.
- For a command with a tile (`MoveCommand.To` / `From`, `AttackCommand.Target` / `Origin`, `TrainCommand.Coordinates`, `BuildCommand.Coordinates`, `CaptureCommand`, …): include only if `tile.GetExplored(p)` (or the destination becomes explored by that command). Do not emit a unit type/HP from `GetUnit(state, p, includeHidden: false)` when that returns null.
- Opponent `ResearchCommand`: **omit** (tech is not public). Same for diplomacy the local player has not met (`PlayerState.knownPlayers` / `KnowsPlayer`).
- Hidden units: `UnitState.IsInvisible(state, p)` → omit or mark “unknown unit”.
- Do not walk raw `TileData.unit` / `resource` on unexplored tiles.

Keep `ClientActionManager.LastSeenCommand` / `Client.GetLastSeenCommand()` as the cursor between local turns.

---

## 12. Score in-game (Perfection)

**Read closely** (`IncreaseScoreAction.Execute` → `ActionUtils.AddScore`; `GetScore` overloads).

`PlayerState.score` (`uint` at +0xA0) **is** updated during the match. `IncreaseScoreAction.Execute` calls `ActionUtils.AddScore(GameState, PlayerState, int)` which does `score += amount`. Explore, cities, tech, etc. enqueue that action. `GetScore(this PlayerState player)` is `return player.score` — cheap, live.

`GameState.RecalculatePlayerStateValues()` only refreshes `capitalCountCache` (+0x144). It does **not** recompute score.

Breakdown (walks the map; fine once per turn):

```
ScoreDetails PlayerExtensions.GetScore(this PlayerState player, GameState state)   // 0x018E5BE0
int ScoreSheet.GetUnitScore(UnitState unitState, GameState gameState)
float ScoreSheet.GetTechScore(GameState state, TechData.Type type)
float ScoreSheet.GetTechScore(TechData tech)
int ScoreSheet.GetNumberOfStars(GameMode gameMode, int score)
```

`EndMatchReaction` uses `GetScore(LocalPlayer, GameState)` for the result screen. The harness can call the same on every local turn.

`AddScore` **Read closely** also calls `TryGetWinner` after the increment when `CurrentState == Started` (2) — a Glory score-limit win can fire `GameOverAction` mid-action, not only on end turn.

---

## 13. Unattended loop (inferred)

1. Start scene, `GameManager.Instance` live.
2. Fill `PreliminaryGameSettings` + `SetStartingTribeValues`.
3. `CreateSinglePlayerGame()` → `CreateSession` → `LoadLevel` → `OnGameReady`.
4. Each local turn: wait `OnTurnStarted` + `IsWaitingForCommand`; export; `SendCommand`s; `EndTurnCommand`.
5. CPU: let `TryCreateAndExecuteAICommands` run; `SkipRecap()`; optional command-stack slice for the log.
6. End: `TryGetWinner` / `CurrentState` FinalTurn|Ended / postfix `MatchEnded`.
7. `ResultScreen.Hide()`; `ReturnToMenu()`; wait; goto 2.

Mac 16376 vs Steam 16375: if a name is missing on Steam, dump that build’s C# the same way (`Il2CppInspector --cs-out`). Offsets will differ; names should not.
