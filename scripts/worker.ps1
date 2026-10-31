# Runs one headless Claude Code worker; output streams to logs\<name>.jsonl. Started via scheduled task so it survives ssh.
param([string]$name, [string]$model, [string]$task, [string]$effort = "medium")
$w = "C:\Users\caleb\Workspace\projects\polytopia"
Set-Location $w
New-Item -ItemType Directory -Force "$w\logs" | Out-Null
$prompt = "Read CLAUDE.md, then do the task in tasks/$task. Write your report at the bottom of that file when done or blocked."
# stdin from NUL: claude -p otherwise waits for stdin when it isn't a terminal.
cmd /c "C:\Users\caleb\.local\bin\claude.exe -p `"$prompt`" --model $model --effort $effort --permission-mode auto --output-format stream-json --verbose < NUL > `"$w\logs\$name.jsonl`" 2>&1"
"exit $LASTEXITCODE $(Get-Date)" | Out-File "$w\logs\$name.done"
