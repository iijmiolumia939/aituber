#!/usr/bin/env pwsh
$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $PSScriptRoot
Push-Location $repoRoot
try {
    & git config core.hooksPath .githooks
    Write-Host "Configured git hooks path: .githooks" -ForegroundColor Green
    Write-Host "pre-commit will now run scripts/copilot_quality_gate.ps1 -ChangedOnly" -ForegroundColor Green
}
finally {
    Pop-Location
}