# Headline benchmark: Perfection, 30 turns, Small 14x14 Lakes map, 2 Hard CPUs; the model picks one of the four core tribes.
# Usage: scripts\bench.ps1 -games name:Hard:Perfection:<model>:<effort>:neutral:fresh:2:14[,...] -marker <name>
param([string]$games, [string]$marker = "bench")
& C:\Users\caleb\Workspace\projects\polytopia\scripts\game.ps1 -games $games -marker $marker -compact -extra "--map-preset Lakes --choose-tribe --plan-chars 3000"
