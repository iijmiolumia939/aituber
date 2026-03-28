#!/usr/bin/env pwsh
$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $PSScriptRoot
Push-Location $repoRoot
try {
    & git config core.hooksPath .githooks
    Write-Host "Configured git hooks path: .githooks" -ForegroundColor Green
    Write-Host "pre-commit will now run scripts/copilot_pre_commit.ps1" -ForegroundColor Green
    Write-Host "This auto-generates copilot-temp/review-packet.md and then runs the changed-files quality gate." -ForegroundColor Green
}
finally {
    Pop-Location
}