$c = "C:\Users\caleb\.local\bin\claude.exe"
$q = "How many positive integers below 500 are divisible by 3 or 7 but not by 5? Reply with only the number."
Set-Location C:\Users\caleb\Workspace\polytopia-player
$env:CLAUDE_CODE_DISABLE_CLAUDE_MDS = "1"
Set-Content off.json '{"alwaysThinkingEnabled": false}'
Set-Content on.json '{"alwaysThinkingEnabled": true}'
foreach ($m in "haiku","sonnet","opus") {
  foreach ($mode in "on","off") {
    $out = cmd /c "$c -p `"$q`" --model $m --effort medium --settings $mode.json --tools `"`" --output-format json --no-session-persistence < NUL 2>&1"
    try { $j = $out | ConvertFrom-Json; "$m $mode result=$($j.result) out=$($j.usage.output_tokens) thinking=$($j.usage.output_tokens_details.thinking_tokens)" } catch { "$m $mode ERR $out" }
  }
}
Remove-Item off.json, on.json
