#!/usr/bin/env pwsh
$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $PSScriptRoot
Push-Location $repoRoot
try {
    $branch = (& git rev-parse --abbrev-ref HEAD) 2>$null
    $status = (& git status --short) 2>$null
    $recentCommits = (& git log --oneline -5) 2>$null

    Write-Host "== GitHub Copilot Startup Routine ==" -ForegroundColor Cyan
    Write-Host "repo: $repoRoot"
    if ($branch) {
        Write-Host "branch: $branch"
    }

    Write-Host ""
    Write-Host "Read first:" -ForegroundColor Yellow
    Write-Host "  AGENTS.md"
    Write-Host "  PLANS.md"
    Write-Host "  QUALITY_SCORE.md"
    Write-Host "  AITuber/docs/adr/0001-github-copilot-harness.md"

    Write-Host ""
    Write-Host "Recommended next commands:" -ForegroundColor Yellow
    Write-Host "  Task: Harness: Quality Gate (changed files)"
    Write-Host "  Task: Harness: Install Git Hooks"
    Write-Host ""

    Write-Host "Recent commits:" -ForegroundColor Yellow
    if ($recentCommits) {
        $recentCommits | ForEach-Object { Write-Host "  $_" }
    } else {
        Write-Host "  <unavailable>"
    }

    Write-Host ""
    Write-Host "Working tree:" -ForegroundColor Yellow
    if ($status) {
        $status | ForEach-Object { Write-Host "  $_" }
    } else {
        Write-Host "  clean"
    }
}
finally {
    Pop-Location
}