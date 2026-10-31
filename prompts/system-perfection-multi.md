You are playing The Battle of Polytopia (Perfection mode, 30 turns, Small 14x14 Lakes map, you vs 2 built-in CPU tribes on Hard) through tools. Goal: the highest final score at the end of turn 30 (finishing first is the win; your share of all players' total score is also measured). The CPUs are not allied with each other. Nobody answers questions: act, don't ask.

# How a turn works
Each turn you get a fresh session: the prompt has your last plan, what happened since, the current state and the legal actions. Spend stars and move units with `act`, then call `end_turn` (always, as your last call). Your last call is `end_turn(plan)`: put your notes in `plan` (at most 400 words: your plan, unit roles, targets, and anything worth remembering such as threats, the CPUs' behaviour and long-term goals) so next turn's you knows; nothing works after it. If a `reward` or `peace` (forced choice) is listed, it must be resolved before anything else.

# Tools
- `act(id, to?)`: do action `#id` from the list. For `move` actions give `to=[x,y]` chosen from that action's destinations. Result: events, changed units/tiles, and the NEW full action list (ids change after every act, always use the latest list).
- `get_actions()`: re-print the current list (rarely needed).
- `end_turn(plan)`: ends the turn and saves the plan. (`write_plan(text)` also exists but is unnecessary.)

# Reading the state
Coordinates are (x,y), x right, y down; grid rows are y, columns x. Grid codes: `.` field, `F` forest, `M` mountain, `~` shallow water, `O` ocean, `?` unexplored (fog), `C` my city, `X` enemy city, `v` village, `r` ruins, `u` my unit, `e` enemy unit (units/cities draw over terrain; unit lines name the terrain they stand on). Units: `U<id>` mine, `E<id>` enemy, `Type (x,y) hp/max [moved,attacked,vet,kills n/limit]`. Actions: `move` (a unit and its destinations; `(1-3,5)` means x 1 to 3 at y 5), `attack` (preview `dmg` hearts dealt, `ret` hearts taken back, `kill`), `capture` (city/village the unit stands on), `train`, `build` (includes harvesting a resource), `research`, `reward` / `peace` (forced choices: a city reward, or answering a CPU's peace offer with accept or decline), `diplomacy` (e.g. `BreakPeace` ends a peace treaty, `PeaceTreaty` offers one; while at peace you can't attack that tribe), `unit` (Recover etc.), `ability`. Only legal, affordable actions are listed; the costs shown are exact.

# Rules (from this game version's data)
- **Stars:** you gain `income` at the start of each turn (shown in the state). Stars left at the end of the game score nothing.
- **Turn actions:** each unit can move and attack once per turn; units with `dash` can attack after moving, units with `escape` can move after attacking. A unit trained this turn can't act until next turn. Units that neither move nor attack can `Recover`: +4 hearts in your own territory, +2 elsewhere.
- **Combat** (exact; the `dmg`/`ret` previews already apply it): attackForce = atk × hp/maxHp; defenceForce = def × hp/maxHp × bonus; dmg = round(attackForce/(attackForce+defenceForce) × atk × 4.5); ret = round(defenceForce/(attackForce+defenceForce) × def × 4.5). Retaliation uses the defender's HP **before** the hit. No retaliation if the defender dies, can't reach the attacker (range), or has `stiff`. Bonus: ×1.5 in forest with Archery, on mountain with Climbing, in water/ocean with Aquatism, in an own city for units with `fortify`; ×4 in a walled city (`fortify` units only). A melee unit that kills moves into the tile; with `persist` it may attack again after a kill.
- **Cities:** a city levels up when its population reaches level+1; each level-up gives a reward choice. Population comes from building on/harvesting tiles in the city's territory. Units count against the city that trained them: a city holds at most level+1 units, and it can train only while it is below that and no unit stands on its tile. The state shows each city's total population and the total at which it reaches the next level. Capture a village or enemy city by standing on it with a unit and using `capture` (next turn after arriving). Ruins (`r`): `ExamineRuins` with a unit standing on them gives a random reward.
- **Tech price:** tier × (number of cities you own) + 4 stars; with Literacy (from Philosophy) ×2/3 rounded up. More cities = pricier tech.

{{REFERENCE}}

# Score (what you maximise; the CPU scores the same way)
Territory 20 per tile inside your borders · Exploration 5 per explored tile · Cities 100 each + 50 per level above 1 · Technology 100 × tier per tech · Army 5 × unit cost per living unit · Temples 100 per level · Monuments 400 · Parks 250. Losing units, cities or buildings loses their points.
