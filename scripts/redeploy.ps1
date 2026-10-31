. "$PSScriptRoot\paths.ps1"
Set-Location "$w\PolyBridge"
$env:POLYTOPIA_DIR = $gameDir; & $dotnet build -c Release -v q -nologo 2>&1 | Select-String "error|Build succeeded" | Select -First 15
Stop-Process -Name Polytopia -Force -ErrorAction SilentlyContinue; Start-Sleep 3
Copy-Item "$w\PolyBridge\bin\Release\PolyBridge.dll" "$gameDir\BepInEx\plugins\" -Force
Remove-Item "$bridgeDir\*" -ErrorAction SilentlyContinue
# launch on the desktop: a scheduled task named PolyLaunch if you made one (needed when running over SSH), else directly
if (Get-ScheduledTask -TaskName PolyLaunch -ErrorAction SilentlyContinue) { Start-ScheduledTask -TaskName PolyLaunch } else { Start-Process "$gameDir\Polytopia.exe" }
Start-Sleep 35
Select-String -Path "$gameDir\BepInEx\LogOutput.log" -Pattern "PolyBridge" | Select -Last 8 | % Line
