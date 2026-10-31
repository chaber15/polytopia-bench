param([string]$c, [int]$wait = 3)
. "$PSScriptRoot\paths.ps1"; $b = $bridgeDir; New-Item -ItemType Directory -Force $b | Out-Null
$o = "$b\out.log"; $n = if (Test-Path $o) { (Get-Content $o).Count } else { 0 }
Set-Content "$b\cmd.txt" $c
Start-Sleep $wait
if (Test-Path $o) { Get-Content $o | Select -Skip $n }
