$l = Join-Path (Split-Path $PSScriptRoot -Parent) "logs"
Get-Date
$names = ((Get-Content "$l\queue.txt") + "," + (Get-Content "$l\queue2.txt")).Split(",") | % { $_.Split(":")[0] }
foreach ($n in $names) {
  $o = "$l\game-$n.out"
  if (-not (Test-Path $o)) { "{0,-38} queued" -f $n; continue }
  $c = Get-Content $o
  $res = $c | Select-String "^result:" | Select -First 1
  $cost = ($c | Select-String 'turn \d+ done: cost \$([\d.]+)' -AllMatches | % { [double]$_.Matches[0].Groups[1].Value } | Measure -Sum).Sum
  $turns = ($c | Select-String "turn \d+ done").Count
  if ($res) {
    $j = $res.Line.Substring(8) | ConvertFrom-Json
    $s = ($j.scores | % { "$($_.tribe)=$($_.score)" }) -join " "
    $w = if ($j.winner -eq 1) { "WON" } else { "lost" }
    "{0,-38} {1,-4} t{2,-3} `${3:N2}  {4}" -f $n, $w, $j.turn, $cost, $s
  } elseif (Test-Path "$l\game-$n.done") { "{0,-38} ended, no result, {1} turns, `${2:N2}" -f $n, $turns, $cost }
  else { "{0,-38} RUNNING turn {1}, `${2:N2} so far" -f $n, $turns, $cost }
}
