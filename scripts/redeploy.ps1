$g="C:\Program Files (x86)\Steam\steamapps\common\The Battle of Polytopia"; $w="C:\Users\caleb\Workspace\projects\polytopia"
Set-Location "$w\PolyBridge"
& "C:\Program Files\dotnet\dotnet.exe" build -c Release -v q -nologo 2>&1 | Select-String "error|Build succeeded" | Select -First 15
Stop-Process -Name Polytopia -Force -ErrorAction SilentlyContinue; Start-Sleep 3
Copy-Item "$w\PolyBridge\bin\Release\PolyBridge.dll" "$g\BepInEx\plugins\" -Force
Remove-Item "$w\bridge\*" -ErrorAction SilentlyContinue
Start-ScheduledTask -TaskName PolyLaunch; Start-Sleep 35
Select-String -Path "$g\BepInEx\LogOutput.log" -Pattern "PolyBridge" | Select -Last 8 | % Line
