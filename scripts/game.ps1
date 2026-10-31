# Runs model games one after another; output to logs\game-<name>.out, marker logs\game-<name>.done.
# -games is a comma list of name:difficulty:mode:model:effort[:framing[:memory[:opponents[:mapSize]]]]
#   framing: neutral (default) | competitive; memory: fresh (default) | persist; opponents default 1; mapSize default 11.
# Domination with opponents > 1 uses prompts\system-domination-multi.md, an 80-turn cap and 100 tool calls per turn.
# Might (win by taking the CPU capital) uses prompts\system-might.md and a 60-turn cap.
# -extra adds play.py arguments to every game (e.g. "--resume --until-turn 80 --plan-file <file>").
# -compact runs every game with play.py --compact (batched act, turn-stable ids, diff-only results).
# -after <name> waits for logs\game-<name>.done first. The queue stops if the Claude usage limit is hit.
# After each game, the game's own save (.state) and a screenshot go to logs\saves\<name>.* before quitting to the menu.
param([string]$games, [string]$after = "", [string]$marker = "queue", [switch]$compact, [string]$extra = "")
$w = "C:\Users\caleb\Workspace\projects\polytopia"
Set-Location "$w\harness"
if ($after) { while (-not (Test-Path "$w\logs\game-$after.done")) { Start-Sleep 30 } }
foreach ($g in $games.Split(",")) {
  $name, $diff, $mode, $model, $effort, $framing, $memory, $opp, $size = $g.Split(":")
  if (-not $opp) { $opp = 1 }; if (-not $size) { $size = 11 }
  $module = if ($memory -eq "persist") { "play_persist" } else { "play" }
  $prompt = if ($mode -eq "Might") { "system-might" } elseif ($mode -eq "Domination") { if ([int]$opp -gt 1) { "system-domination-multi" } else { "system-domination" } } elseif ([int]$opp -gt 1) { "system-perfection-multi" } else { "system" }
  if ($framing -eq "competitive") { $prompt += "-competitive" }
  $turns = if ($mode -eq "Might") { "--turns 60 --max-minutes 240" } elseif ($mode -ne "Domination") { "--turns 30" } elseif ([int]$opp -gt 1) { "--turns 80 --max-minutes 600 --max-calls 100 --turn-timeout 900" } else { "--turns 60 --max-minutes 240" }
  cmd /c ".venv\Scripts\python.exe -u -m $module --model $model --effort $effort --difficulty $diff --mode $mode --opponents $opp --map-size $size --system-prompt $w\prompts\$prompt.md $turns $(if ($compact) { "--compact" }) $extra --claude C:\Users\caleb\.local\bin\claude.exe < NUL > `"$w\logs\game-$name.out`" 2>&1"
  $code = $LASTEXITCODE
  New-Item -ItemType Directory -Force "$w\logs\saves" | Out-Null
  $sp = Get-ChildItem "$env:USERPROFILE\AppData\LocalLow\Midjiwan\Polytopia\*\Data\Singleplayer\*.state" -ErrorAction SilentlyContinue | Sort LastWriteTime -Descending | Select -First 1
  if ($sp) { Copy-Item $sp.FullName "$w\logs\saves\$name.state" }
  Start-ScheduledTask PolyShot; Start-Sleep 6
  Copy-Item "$w\shot.png" "$w\logs\saves\$name.png" -ErrorAction SilentlyContinue
  try { Invoke-WebRequest http://localhost:7777/quit -Method POST -Body "{}" -UseBasicParsing -TimeoutSec 120 | Out-Null } catch {}
  "exit $code $(Get-Date)" | Out-File "$w\logs\game-$name.done"
  if (Select-String -Path "$w\logs\game-$name.out" -Pattern "hit your (session|usage|weekly) limit" -Quiet) {
    "stopped: usage limit during $name $(Get-Date)" | Out-File "$w\logs\$marker.limit"; break
  }
}
"queue finished $(Get-Date)" | Out-File "$w\logs\$marker.done"
