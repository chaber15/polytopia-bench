# Shared locations for the PowerShell scripts. Override with environment variables.
$w = Split-Path $PSScriptRoot -Parent                                   # this repo
$gameDir = if ($env:POLYTOPIA_DIR) { $env:POLYTOPIA_DIR } else { "C:\Program Files (x86)\Steam\steamapps\common\The Battle of Polytopia" }
$bridgeDir = if ($env:POLYBRIDGE_DIR) { $env:POLYBRIDGE_DIR } else { "$env:LOCALAPPDATA\PolyBridge" }   # must match the plugin
$claude = if ($env:CLAUDE_EXE) { $env:CLAUDE_EXE } elseif (Test-Path "$env:USERPROFILE\.local\bin\claude.exe") { "$env:USERPROFILE\.local\bin\claude.exe" } else { "claude" }
$dotnet = if (Get-Command dotnet -ErrorAction SilentlyContinue) { "dotnet" } else { "C:\Program Files\dotnet\dotnet.exe" }
