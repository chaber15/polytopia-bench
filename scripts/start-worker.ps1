param([string]$name, [string]$model, [string]$task, [string]$effort = "medium")
$arg = "-WindowStyle Hidden -ExecutionPolicy Bypass -File C:\Users\caleb\Workspace\projects\polytopia\scripts\worker.ps1 -name $name -model $model -task $task -effort $effort"
$a = New-ScheduledTaskAction -Execute "powershell.exe" -Argument $arg
$s = New-ScheduledTaskSettingsSet -ExecutionTimeLimit (New-TimeSpan -Hours 6)
Register-ScheduledTask -TaskName "PolyWorker-$name" -Action $a -Settings $s -Force | Out-Null
Start-ScheduledTask -TaskName "PolyWorker-$name"
"started $name"
