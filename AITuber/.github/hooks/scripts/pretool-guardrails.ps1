#requires -Version 5.1
$inputJson = Get-Content -Raw -Encoding UTF8
$obj = $inputJson | ConvertFrom-Json
function Deny([string]$Reason){ (@{permissionDecision="deny";permissionDecisionReason=$Reason} | ConvertTo-Json -Compress); exit 0 }
$toolName = $obj.toolName
$toolArgs = $null; try { $toolArgs = ($obj.toolArgs | ConvertFrom-Json) } catch { $toolArgs = $null }
if ($toolName -eq "bash" -or $toolName -eq "powershell") {
  $cmd=""; if ($toolArgs -ne $null -and $toolArgs.PSObject.Properties.Name -contains "command") { $cmd=[string]$toolArgs.command }
  if ($cmd -match "(rm\s+-rf\s+/|rm\s+-rf\s+\.|del\s+/s|format\s|mkfs\.|shutdown\s|reboot\s)") { Deny "Dangerous command detected" }
}
if ($toolName -eq "edit") {
  $path=""; if ($toolArgs -ne $null -and $toolArgs.PSObject.Properties.Name -contains "path") { $path=[string]$toolArgs.path }
  if ($path -match "^(Unity/|Assets/|ProjectSettings/|OBS/|obs/)") { Deny "Editing Unity/OBS paths requires explicit user request" }
}
(@{permissionDecision="allow"} | ConvertTo-Json -Compress)
