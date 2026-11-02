# Keeps one long unattended game going until it ends, optionally screen-recording it.
#   scripts\watch-game.ps1 -name <name> -playArgs "<play.py arguments>" [-record] [-fastMinutes 4]
# Run it in the signed-in desktop session (a scheduled task with an Interactive principal, started through
# scripts\hidden.py so no window covers the game). Windows only draws the screen while someone is connected, so a
# disconnected Remote Desktop session records black (the game itself keeps going).
#
# What it recovers from, instead of stopping for the night:
# - play.py stopping mid-game (provider error, session failed twice, timeout, wall-clock limit): runs it again on the
#   live game, or with --resume from the autosave if the game is back at the menu, passing the model's last plan.
# - a Claude usage limit: waits (30 min at a time) and tries again.
# - the game not answering, or stuck off our turn: kills it, relaunches it (scheduled task PolyLaunch) and resumes.
# - ffmpeg dying: starts a new recording segment.
# It gives up after -maxAttempts runs of play.py. Everything it does goes to logs\watch\<name>.log.
# At the end: logs\rec\<name>.mkv (all segments joined) and <name>-fast.mp4 (about -fastMinutes long).
param([string]$name, [string]$playArgs, [switch]$record, [double]$fastMinutes = 4, [int]$maxAttempts = 40)
. "$PSScriptRoot\paths.ps1"
$ErrorActionPreference = "Continue"
$wd = "$w\logs\watch"; $rd = "$w\logs\rec"
New-Item -ItemType Directory -Force $wd, $rd | Out-Null
$wlog = "$wd\$name.log"
function Say($m) { "$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')  $m" | Tee-Object -FilePath $wlog -Append | Out-Host }
function Status { try { (Invoke-WebRequest http://localhost:7777/status -UseBasicParsing -TimeoutSec 20).Content | ConvertFrom-Json } catch { $null } }
$ff = (Get-ChildItem "$w\tools" -Recurse -Filter ffmpeg.exe -ErrorAction SilentlyContinue | Select-Object -First 1).FullName
if ($record -and -not $ff) { Say "no ffmpeg under tools\; recording off"; $record = $false }

$seg = 0; $rec = $null
function Ensure-Recording {
  if (-not $record) { return }
  if ($script:rec -and -not $script:rec.HasExited) { return }
  $script:seg++
  $out = "$rd\$name-$('{0:d2}' -f $script:seg).mkv"
  # whole desktop: capturing the game window by title gives stale frames (the game draws with DirectX)
  $script:rec = Start-Process $ff -PassThru -NoNewWindow -ArgumentList "-nostdin -y -loglevel error -f gdigrab -framerate 10 -draw_mouse 0 -i desktop -c:v libx264 -preset veryfast -crf 24 -pix_fmt yuv420p -vf crop=trunc(iw/2)*2:trunc(ih/2)*2 `"$out`""
  Say "recording segment $script:seg -> $out"
}

# BepInEx opens a log console window over the game at launch; hide it so it isn't in the recording (logs still go to the file)
Add-Type @"
using System; using System.Text; using System.Runtime.InteropServices;
public class PolyWin {
  public delegate bool P(IntPtr h, IntPtr l);
  [DllImport("user32.dll")] public static extern bool EnumWindows(P f, IntPtr l);
  [DllImport("user32.dll")] public static extern bool IsWindowVisible(IntPtr h);
  [DllImport("user32.dll")] public static extern int GetWindowText(IntPtr h, StringBuilder s, int n);
  [DllImport("user32.dll")] public static extern bool ShowWindow(IntPtr h, int c);
  [DllImport("kernel32.dll")] public static extern uint SetThreadExecutionState(uint f);
}
"@
function Hide-Console {
  [PolyWin]::EnumWindows({ param($h, $l)
    $sb = New-Object Text.StringBuilder 256; [PolyWin]::GetWindowText($h, $sb, 256) | Out-Null
    if ([PolyWin]::IsWindowVisible($h) -and $sb.ToString().StartsWith("BepInEx")) { [PolyWin]::ShowWindow($h, 0) | Out-Null; Say "hid the BepInEx console" }
    $true }, [IntPtr]::Zero) | Out-Null
}

function Restart-Game {
  Say "restarting the game"
  Get-Process Polytopia -ErrorAction SilentlyContinue | Stop-Process -Force
  Start-Sleep 5
  Start-ScheduledTask PolyLaunch
  for ($i = 0; $i -lt 60; $i++) { Start-Sleep 5; $s = Status; if ($s -and $s.phase -eq "menu") { Say "game back at the menu"; return $true } }
  Say "game did not come back within 5 minutes"; return $false
}

# Waits for the game to be at the menu, on our turn, or over; restarts it if it doesn't answer or stays busy.
function Settle {
  $t0 = Get-Date
  while ($true) {
    $s = Status
    if ($s -and $s.phase -in @("menu", "my_turn", "game_over")) { Hide-Console; return $s }
    if (((Get-Date) - $t0).TotalMinutes -gt 15) {
      Say "game stuck ($(if ($s) { $s.phase } else { 'no answer' })) for 15 minutes"
      Restart-Game | Out-Null; $t0 = Get-Date
    }
    Start-Sleep 10
  }
}

# keep the PC awake and the display on (an idle display can turn off or lock, which records black)
[PolyWin]::SetThreadExecutionState(0x80000003) | Out-Null   # ES_CONTINUOUS | ES_SYSTEM_REQUIRED | ES_DISPLAY_REQUIRED
$logs = @()          # harness logs of this game, oldest first (a resumed game continues in a new log)
$attempt = 0; $quiet = 0; $started = $false   # $started: this game exists (newgame done), so --resume is safe
Say "watching ${name}: play.py $playArgs"
if (-not (Status)) { Restart-Game | Out-Null }
$s = Status
if ($s -and $s.phase -ne "menu") {   # an old game is open: start from the menu
  Say "quitting the open game ($($s.phase))"
  try { Invoke-WebRequest http://localhost:7777/quit -Method POST -Body "{}" -UseBasicParsing -TimeoutSec 120 | Out-Null } catch {}
}
while ($attempt -lt $maxAttempts) {
  $s = Settle
  Ensure-Recording
  if ($s.phase -eq "game_over" -and $attempt -gt 0) { Say "game over"; break }
  $attempt++
  $extra = ""
  if ($attempt -gt 1) {
    if ($s.phase -eq "menu" -and $started) { $extra += " --resume" }
    $last = if ($logs.Count) { $logs[-1] } else { $null }
    if ($last) {
      $plan = Get-ChildItem "$w\harness\logs\$last-turns" -Recurse -Filter plan.txt -ErrorAction SilentlyContinue | Sort-Object LastWriteTime | Select-Object -Last 1
      if ($plan) { $extra += " --plan-file `"$($plan.FullName)`"" }
    }
  }
  $out = "$wd\$name-$('{0:d2}' -f $attempt).out"
  Say "attempt $attempt (game $($s.phase)$(if ($s.turn) { ", turn $($s.turn)" }))$extra"
  Push-Location "$w\harness"
  cmd /c ".venv\Scripts\python.exe -u -m play $playArgs $extra --claude `"$claude`" < NUL > `"$out`" 2>&1"
  Pop-Location
  $text = Get-Content $out -Raw -ErrorAction SilentlyContinue
  if ("$text" -match "newgame: |resume: |log: ") { $started = $true }
  if ($text -match "log: .*[\\/]([^\\/]+)\.jsonl") { if ($logs -notcontains $Matches[1]) { $logs += $Matches[1] } }
  $logs -join "`n" | Out-File "$wd\$name.logs"
  $turns = ([regex]::Matches("$text", "turn \d+ done")).Count
  if ("$text" -match "result: ") { Say "game finished: $([regex]::Match($text, 'result: .*').Value.Substring(0, [math]::Min(300, [regex]::Match($text, 'result: .*').Value.Length)))"; break }
  $tail = (Get-Content $out -Tail 3 -ErrorAction SilentlyContinue) -join " | "
  Say "play.py stopped after $turns turns: $tail"
  if ("$text" -match "hit your (session|usage|weekly) limit|usage limit|rate limit") {
    Say "usage limit: waiting 30 minutes"; Start-Sleep 1800; continue
  }
  $quiet = if ($turns -eq 0) { $quiet + 1 } else { 0 }
  if ($quiet -ge 3) { Say "three runs in a row without a turn: restarting the game"; Restart-Game | Out-Null; $quiet = 0 }
  Start-Sleep ([math]::Min(600, 60 * [math]::Max(1, $quiet * 3)))
}
if ($attempt -ge $maxAttempts) { Say "gave up after $maxAttempts attempts" }

# keep the final screen in the recording for a moment, then stop recording, quit to the menu and stitch
Start-Sleep 20
if ($rec -and -not $rec.HasExited) { Stop-Process -Id $rec.Id; Start-Sleep 5 }
try { Invoke-WebRequest http://localhost:7777/quit -Method POST -Body "{}" -UseBasicParsing -TimeoutSec 120 | Out-Null } catch {}
if ($record -and $seg -gt 0) {
  $parts = Get-ChildItem "$rd\$name-??.mkv" | Sort-Object Name
  $parts | ForEach-Object { "file '$($_.FullName)'" } | Set-Content "$rd\$name.txt" -Encoding ascii
  & $ff -y -loglevel error -f concat -safe 0 -i "$rd\$name.txt" -c copy "$rd\$name.mkv"
  $fp = Join-Path (Split-Path $ff) "ffprobe.exe"
  $secs = [double](& $fp -v error -show_entries format=duration -of csv=p=0 "$rd\$name.mkv")
  $speed = [math]::Max(1, $secs / ($fastMinutes * 60))
  & $ff -y -loglevel error -i "$rd\$name.mkv" -vf "setpts=PTS/$speed,fps=30" -an -c:v libx264 -preset medium -crf 22 -pix_fmt yuv420p "$rd\$name-fast.mp4"
  Say "recording: $([math]::Round($secs / 60)) min, fast copy at $([math]::Round($speed))x -> $rd\$name-fast.mp4"
}
"done $(Get-Date)" | Out-File "$wd\$name.done"
