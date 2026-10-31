You are playing The Battle of Polytopia (Might mode, you vs 1 built-in CPU) through tools. Goal: **win by capturing the CPU's capital city**. There is no turn limit in Might; this test stops at turn 60, and a game still running then counts as not won. Score does not decide the winner. Nobody answers questions: act, don't ask.

# How a turn works
Each turn you get a fresh session: the prompt has your last plan, what happened since, the current state and the legal actions. Spend stars and move units with `act`, then call `end_turn` (always, as your last call). Your last call is `end_turn(plan)`: put a <=150-word plan in `plan` (strategy, unit roles, targets) so next turn's you knows; nothing works after it. If a `reward` or `peace` (forced choice) is listed, it must be resolved before anything else.

# Tools
- `act(id, to?)`: do action `#id` from the list. For `move` actions give `to=[x,y]` chosen from that action's destinations. Result: events, changed units/tiles, and the NEW full action list (ids change after every act, always use the latest list).
- `get_actions()`: re-print the current list (rarely needed).
- `end_turn(plan)`: ends the turn and saves the plan. (`write_plan(text)` also exists but is unnecessary.)

# Reading the state
Coordinates are (x,y), x right, y down; grid rows are y, columns x. Grid codes: `.` field, `F` forest, `M` mountain, `~` shallow water, `O` ocean, `?` unexplored (fog), `C` my city, `X` enemy city, `v` village, `r` ruins, `u` my unit, `e` enemy unit (units/cities draw over terrain; unit lines name the terrain they stand on). Units: `U<id>` mine, `E<id>` enemy, `Type (x,y) hp/max [moved,attacked,vet,kills n/limit]`. Actions: `move` (a unit and its destinations; `(1-3,5)` means x 1 to 3 at y 5), `attack` (preview `dmg` hearts dealt, `ret` hearts taken back, `kill`), `capture` (city/village the unit stands on), `train`, `build` (includes harvesting a resource), `research`, `reward` / `peace` (forced choices: a city reward, or answering a CPU's peace offer with accept or decline), `diplomacy` (e.g. `BreakPeace` ends a peace treaty, `PeaceTreaty` offers one; while at peace you can't attack that tribe), `unit` (Recover etc.), `ability`. Only legal, affordable actions are listed; the costs shown are exact.

# Rules (from this game version's data)
- **Stars:** you gain `income` at the start of each turn (shown in the state).
- **Losing:** if the CPU captures your capital, you lose.
- **Turn actions:** each unit can move and attack once per turn; units with `dash` can attack after moving, units with `escape` can move after attacking. A unit trained this turn can't act until next turn. Units that neither move nor attack can `Recover`: +4 hearts in your own territory, +2 elsewhere.
- **Combat** (exact; the `dmg`/`ret` previews already apply it): attackForce = atk Ã— hp/maxHp; defenceForce = def Ã— hp/maxHp Ã— bonus; dmg = round(attackForce/(attackForce+defenceForce) Ã— atk Ã— 4.5); ret = round(defenceForce/(attackForce+defenceForce) Ã— def Ã— 4.5). Retaliation uses the defender's HP **before** the hit. No retaliation if the defender dies, can't reach the attacker (range), or has `stiff`. Bonus: Ã—1.5 in forest with Archery, on mountain with Climbing, in water/ocean with Aquatism, in an own city for units with `fortify`; Ã—4 in a walled city (`fortify` units only). A melee unit that kills moves into the tile; with `persist` it may attack again after a kill.
- **Cities:** a city levels up when its population reaches level+1; each level-up gives a reward choice. Population comes from building on/harvesting tiles in the city's territory. Units count against the city that trained them: a city holds at most level+1 units, and it can train only while it is below that and no unit stands on its tile. The state shows each city's total population and the total at which it reaches the next level. Capture a village or enemy city by standing on it with a unit and using `capture` (next turn after arriving). Ruins (`r`): `ExamineRuins` with a unit standing on them gives a random reward.
- **Tech price:** tier Ã— (number of cities you own) + 4 stars; with Literacy (from Philosophy) Ã—2/3 rounded up. More cities = pricier tech.

{{REFERENCE}}

# Score (shown in the state; it does not decide the winner in Might)
Territory 20 per tile inside your borders Â· Exploration 5 per explored tile Â· Cities 100 each + 50 per level above 1 Â· Technology 100 Ã— tier per tech Â· Army 5 Ã— unit cost per living unit Â· Temples 100 per level Â· Monuments 400 Â· Parks 250. Losing units, cities or buildings loses their points.
