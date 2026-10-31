# Polytopia 2.17.3 — game mechanics

Read from the installed Mac app (build 16376, Unity 6000.3.17f1, IL2CPP metadata v39). **Nothing here has been checked against a real played game.** Addresses are file offsets in `UnityFramework` for this build only.

Confidence labels:

- **Read closely**: instruction-by-instruction. The formula is written as found.
- **Skimmed**: calls, constants and comparisons only.
- **Inferred**: names, tables or how a value is used.

---

## 0. Where the rules live

**Read closely** (data layout).

Bundled tables are JSON TextAssets `GameLogicData1` … `GameLogicData28` inside `data.unity3d`. Latest: `extracted/gamelogic/GameLogicData28.json`. The game keeps older snapshots (replay / versioning). Code picks a snapshot via `VersionManager.GetGameLogicDataVersionFromGameVersion`.

Top-level keys: `tribeData` (18), `techData` (49), `unitData` (59), `improvementData` (49), `terrainData` (9), `resourceData` (10), `taskData` (9), `skinData` (3), `diplomacyData`.

Logic is in `GameLogicAssembly`. Combat is `BattleHelpers.GetBattleResults` at `0x018A6258`. Score is `PlayerExtensions.GetScore(PlayerState, GameState)` at `0x018E5BE0`. Income is `ResourceDataUtils.CalculateIncomeFor` at `0x018FBD20`.

---

## 1. Combat

**Read closely** (`BattleHelpers.GetBattleResults`, `Round`, `Floor`, `GetAttack`, `GetDefence`, `GetDefenceBonus`, `GetMaxHealth`, `CanDefenderRetaliate`).

### Scale

Unit JSON stores warrior as `attack=20`, `defence=20`, `health=100`. `GetAttack` multiplies the table attack by 10 (200). `GetDefence` is `tableDefence * defenceBonus` (bonus defaults to 10, so 200). Current HP is a `uint16` at unit `+0x50`. Max HP is table `health` plus `50 *` a promotion field at `+0x52`. **Inferred:** 100 HP = 10 public hearts; 10 internal damage = 1 heart. Confirm in play.

### Ability and effect names

**Read closely** (Il2CppInspector C# dump of enum field defaults: `extracted/il2cpp/cs/UnitAbility.cs`, `UnitEffect.cs`). Numbers used in combat:

| Number | Name | Role in combat |
|---|---|---|
| ability 8 | Convert | attacker with Convert: no retaliation |
| ability 0x12 (18) | Freeze | attacker with Freeze, game version `> 0x77`: no retaliation |
| ability 0x16 (22) | Fortify | required for friendly-city defence 15 / wall 40 |
| ability 0x1f (31) | Surprise | attacker with Surprise: no retaliation |
| ability 0x26 (38) | Stiff | defender with Stiff: no retaliation |
| ability 0x2c (44) | Tentacles | attacker: replace attack with `10 * nestedInt` (object at unit `+0x60`, int at `+0x20`) |
| effect 0 | Frozen | defender Frozen: no retaliation |
| effect 1 | Poisoned | halves defence bonus on current versions; old versions return bonus 7 |
| effect 2 | Boosted | `GetAttack` +50. `BoostAction` writes this only when game version `<= 0x72`; current boost writes effect 6 (Swift) |
| effect 3 | Invisible | after a kill, ORs a flag into the “move onto tile” pack |

`PromoteAction` increments the promotion halfword at unit `+0x52` and heals to `GetMaxHealth`. It does **not** add Boosted. Veteran HP is `table.health + 50 * promotions`. Veteran attack was **not** found in `GetAttack`.

### Attack stat

```
if unit has effect Boosted (2):   attack = table.attack * 10 + 50
else:                             attack = table.attack * 10
if attacker has Tentacles (0x2c): attack = 10 * nestedInt   // overwrites
```

On current versions mindbender Boost is Swift (6), not Boosted (2). Whether Swift changes attack was **not** read in `GetAttack` (it does not check 6).

### Defence bonus (returned as an integer, default 10)

`UnitDataExtensions.GetDefenceBonus`:

1. Game version `<= 0x72` and unit is **Poisoned** (effect 1) → return **7** (old poison path).
2. Else start at **10**.
3. Terrain: `GetUnlockedDefenceBonus(player, terrain)` (tech such as archery / spiritualism / climbing). If that value is `>= 2`, bonus becomes **15**, else stays 10.
4. If the tile is a city (`HasImprovement(1)`) owned by the unit’s owner, **and the unit has Fortify (0x16)**:
   - city with wall reward (`HasReward(city, CityWall=1)`) → **40**
   - city without → **15**
5. Game version `>= 0x73` and Poisoned: `bonus >>= 1` (so 10→5, 15→7, 40→20).

`GetDefence` = that bonus × table defence. So a wall (40) on a defender (30) is 1200 vs a field defender at 300.

**Fortify** applies here: it is the gate on the friendly-city 15 / wall 40 bonuses. There is no “did not move this turn” bonus in this routine. Units without Fortify (catapults have Stiff but not Fortify) do not get the city/wall bonus from this function.

### Damage

`GetBattleResults(state, attacker, defender, checkPeace, extraFlag)`:

1. If `checkPeace` and the defender has an active peace treaty with the attacker’s owner → no fight.
2. `attackForce = attack * attackerHP * 100 / attackerMaxHP`
3. `defenceForce = GetDefence(defender) * defenderHP * 100 / defenderMaxHP`
4. `total = attackForce + defenceForce` (if `<= 0`, log and abort)
5. `raw = attack * attackForce * 450 / (total * 1000)`
6. `attackDamage = Round(raw)` where `Round` snaps to the nearest multiple of 10; **a remainder of 5 rounds up**.

Integer identity of step 5:

```
raw = attack * attackForce * 450 / (totalForce * 1000)
```

Worked example, **not play-tested**: full-HP warrior vs warrior, no bonus, no veteran.

- attack = 200, GetDefence = 200, HP = max = 100
- attackForce = defenceForce = 20000, total = 40000
- raw = 200 * 20000 * 450 / 40_000_000 = **45**
- Round(45) = **50** (tie at 5)

If 10 internal = 1 heart, that is **5 hearts**. That matches Tribes and PolyEnv (`round(0.5 * 2 * 4.5) = 5`), not the older wiki form `4.5 * af/(af+df)` which gives 2.25. Still play-test it.

`Floor(x)` is `10 * (x / 10)` toward zero. `GetFlooredHalfAttackDamage` is `Floor(attackDamage / 2)` (splash / area **inferred** from the name).

### Retaliation

**Read closely** (`GetBattleResults` `0x018A6258`, second Round after `CanDefenderRetaliate` `0x018A6A5C`).

Retaliation uses the defender’s health **before** the attack lands. There is no `strh` to `UnitState.health` (+0x50) in this function. After the attack Round, `x24` is still the original `defenceForce` from `ldrh [defender, #0x50]`. The second Round reads that same `x24`. A remaining-HP formula (warrior vs warrior ≈ 3 hearts back) is **not** what this routine does.

If `CanDefenderRetaliate` is false, retaliation is stored as `-1` (none). Otherwise:

```
retRaw = defenceForce * GetDefence * 4500 / (totalForce * 1000 * defenceBonus)
       = defenceForce * tableDefence * 4500 / (totalForce * 1000)
retaliation = Round(retRaw)     // same nearest-10, .5 up
```

`defenceForce` already uses `GetDefence`, which includes wall/terrain. The extra `/ defenceBonus` strips the bonus from the retaliation *attack stat* (it behaves like table defence × 10, i.e. open-ground defence), but the bonus remains in `defenceForce` and `totalForce`.

Worked example, warrior vs warrior, **open ground**, both full HP: same forces as the attack (20000 / 20000 / 40000) → ret raw 45 → **50** (5 hearts). Both should end **5/10**.

Worked example, warrior vs warrior, **walled city** (bonus 40), both full HP:

- attackForce = 20000, defenceForce = 80000, total = 100000
- attack raw = 18 → **20** (2 hearts)
- ret raw = 72 → **70** (7 hearts)

Walls **do** increase retaliation relative to the open-ground 5-heart counter. That matches Tribes (bonused `defenceForce` in the counter) and not PolyEnv (PolyEnv rebuilds an unbonused force for the counter).

`CanDefenderRetaliate` returns false if:

- defender has **Stiff**
- attacker has **Convert** or **Surprise**
- defender is **Frozen**
- game version `> 0x77` and attacker has **Freeze**
- (older path, version `<= 0x77`) defender attack is 0, or defender table weapon `== 10`
- else: defender’s `GetAttackOptions` must include the attacker’s tile

Packed as `(attackDamage | retaliation << 32)`.

### After a kill

If `attackDamage >= defenderHP` and `extraFlag` is set, the code pathfinds from attacker to defender (`CreateForUnit`, `GetPath`). A reachable path sets “should move onto the tile”. Defender **Invisible** (effect 3) can change a packed flag. Matches the log string `shouldMoveToDefeatedEnemyTile`.

---

## 2. Perfection-mode score

**Skimmed** (`PlayerExtensions.GetScore(PlayerState, GameState)` at `0x018E5BE0`, `ScoreSheet.*`).

`GetScore(PlayerState)` without a game is just `player[+0xa0]` (cached total). The breakdown walks the map and fills a `ScoreDetails` object.

Seen components:

| Source | How |
|---|---|
| Units | `GetUnitScore`: **5 × unit cost**. Game version `> 100` uses `GetFullCost`; older uses table cost. |
| Tech | `GetTechScore`: **100 × tech.cost** (the JSON field is the tier). Riding (tier 1) = 100. |
| Cities vs other buildings | Tiles owned by the player with an improvement: `CalculateImprovementScore`. Improvement type `1` is a city (separate accumulator). Temples and monuments are counted. |
| Territory / exploration | Owned-tile count and explored-tile count are multiplied by two static integers (`madd`) and added. The two constants were not read from memory. |
| Difficulty | `GetDifficultyBonusMultiplier(BotDifficulty, n1, n2)` — a 5-entry float table divided by 5, plus an opponent-count term. Table values not dumped. |

`GetNumberOfStars(GameMode, score)` walks a threshold array (different array for `GameMode == 1`). First threshold `> score` wins; the index is the star count. Thresholds not dumped.

UI strings name the familiar Perfection buckets (army & territory, battle, cities, culture, science, monuments & temples, speed, bonus). Battle/culture/speed were **not** isolated in the skim of `GetScore`. `GetBattleScore` exists as a name; not read.

**In-game test:** start a 1-opponent Perfection game, research Riding only, train nothing, end and read the science line. Predict 100.

---

## 3. Economy

### Tech price

**Read closely** (`GameLogicData.GetTechPrice` at `0x01923F24`). JSON `cost` is the **tier**, not the star price. `TechData.cost` is at `+0x14`. `PlayerState.cities` is at `+0xA8` (incremented in `CaptureCityAction`). The `GameState` argument is unused.

```
if tech is null or tier == 0: return 0
price = 4 + tier * cities
if player has Literacy (PlayerAbility 2, unlocked by Philosophy):
    price *= 0x3f2aaa3b   // float ≈ 0.66666 (two thirds)
return ceil(price)        // fcvtps, round toward +∞
```

Riding (tier 1): **5** stars with 1 city, **6** with 2. With Literacy: `ceil(5 × 2/3) = 4`. Ai-Mo starts with Philosophy, so they see the discounted price from turn 1.

Matches Tribes’ `4 + tier × nCities` on the undiscounted path. Tribes’ philosophy path is `cost * 0.2` truncated, not ×2/3 ceil.

`diplomacyData.embassyTechPriceMultiplier = 0.5` exists in JSON. `GetTechPrice` does not read it. No other price routine was found this pass.

### Star income

**Read closely** (`CalculateIncomeFor` `0x018FBD20`, `CalculateWork` 4-arg `0x018FBDC8` / 3-arg `0x018FC990`).

`CalculateIncomeFor` walks every map tile, and for each tile with an improvement adds `CalculateWork(tile, state, player, cityOrBuilding.level)`.

4-arg wrapper: if the tile owner is this player, call the 3-arg routine; else if the tile is still held by its founder and has no opponent unit on it, add `GetIncomeFromEmbassy`; else 0.

3-arg, **city** (improvement type 1):

- Enemy unit standing in the city → 0.
- Game version `>= 0x5e` and city has effect `robbed` (1) → 0.
- Else `stars = level + production - 1`, then if the tile is the player’s `startTile`, add `player.handicap`. If `xp < 0`, add that (no-op when xp is ≥ 0). Clamp at 0.
- Embassy income is summed on the capital path via `GetIncomeFromEmbassy`.

City JSON `work` is 1. Spawn defaults for `level` / `production` were **not** read in the constructor (they start at 0; some spawn path must set them). A normal capital showing 1 star/turn is consistent with `level=1, production=1, handicap=0`.

3-arg, **not a city**: `stars = max(ImprovementData.work * level, 0)`, then doubled if `IsImprovementDoubled`.

Diplomacy table (data): embassy cost 5, income 2, growth time 3, max level 3, `embassyTechPriceMultiplier` 0.5, upgrade 20, dividend 2. Embassy *income* is in `CalculateWork`. The 0.5 tech multiplier is not in `GetTechPrice`.

### City level-up (skimmed)

`ShouldLevelUp`: `xp > level` (`ImprovementState.xp` at `+0x1A`, `level` at `+0x16`). `AddPopulation` adds the same amount to `population` (`+0x1C`) and `xp`. `LevelUp` does `level++`, then `xp -= level`, then `upgrade--`. So level 1→2 spends 2 xp, 2→3 spends 3, and so on. Reward menu not read. `CityReward.CityWall = 1`.

Tech / unit / building **table** numbers are still in `GameLogicData28` (`extracted/gamelogic/*_summary.json`). Example unit costs: warrior 2, rider 3, defender 3, knight 8. Example **tiers**: riding 1, freespirit 2, chivalry 3.

---

## 4. Map generation

**Skimmed** (names and one settings log only).

`MapGenerator.GenerateWithSeed(seed, state, settings)` → `GenerateInternal`. Settings log: `wetness`, `richness`, `smoothIterations`. Spawn check: `Too close spawn at {0} for player {1} map width {2} min dist {3}`.

`GameState` holds `Seed` and `VillageNameSeed`. RNG is `XXHash` (`GameState.RandomHash`). A pre-naval generator (`MapGenerator_prenaval`) is still in the binary.

Map types (loc): archipelago, continents, dryland, lakes, pangea, waterworld. Sizes: tiny, small, normal, large, huge, massive. How size becomes width/height was **not** read.

`MapFairnessCalculations` exists; not read.

---

## 5. Built-in AI

**Skimmed** (method names only).

Only three AI files: `AI.cs`, `OpinionManager.cs`, `OpinionState.cs`.

Turn loop (from names): `GetMove` → `AnalyzeSituationIfNeeded` / `AnalyzeSituation` → `MakeMissionsForCity`, `UpdateHitlistForUnit`, `AdjustMilitaryNeeds` → `GetBestUnitMove` which scores `AddUnitMoveOptions`, `AddAttackOptions`, `AddUnitActionOptions` into `AI.ScoredCommand` → `EndCommand`.

Difficulty names: easy, normal, hard, crazy, frozen. `BotDifficulty` and `GetDifficultyBonusMultiplier` / `DifficultyBonusMultiplier` exist. How they change mission weights was **not** read.

---

## 6. Game state and actions (forward model)

**Skimmed.**

There is **no** `GameState.CopyState`. The metadata string `CopyState` is Unity Input System.

What does exist:

- `GameState.Serialize` / `Deserialize` (`0x018B85E8` / `0x018B8AB8`)
- `GameState.LoadCommandStack` / `GetCommandStack`
- `ActionManager.ExecuteCommand` / `ExecuteCommands`
- `ActionManagerUtils.SimulateAction` / `PerformAllQueuedActions`
- `GameStateUtils.PerformCommands` / `ExecuteCommands`

Commands (player input) and Actions (state mutations) are separate. Commands include Attack, Move, Build, Research, Train, EndTurn, Promote, Capture, … Actions include the same plus `IncreaseCurrency`, `IncreaseScore`, `CityLevelUp`, diplomacy, Cymanti/naval extras.

**Inferred, not proven:** a benchmark forward model can `Serialize` a state, `Deserialize` a copy, then `ExecuteCommands`. Determinism depends on whether those paths touch `XXHash` / time; not read. `SimulateAction` is the name that most looks like a dry-run.

`GameState` fields of interest: `Version`, `Seed`, `CurrentTurn`, `CurrentPlayerIndex`, `Settings`, `Map`, `PlayerStates`, `CommandStack`, `ActionStack`.

---

## Play tests that would confirm this file

See `03-play-tests.md` (20-minute sheet: warrior vs warrior, Riding science, Riding price at 1 and 2 cities, walled-city retaliation). Extra checks not on that sheet: poisoned defence halved; unit score of a warrior = 10; Ai-Mo Riding = 4 stars.
