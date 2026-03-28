#!/usr/bin/env pwsh
param(
    [string]$BundleRoot = "$HOME/.copilot-harness/bundle"
)

$ErrorActionPreference = "Stop"

function Get-RepoRoot {
    return Split-Path -Parent $PSScriptRoot
}

$repoRoot = Get-RepoRoot

$pathsToShare = @(
    ".mcp.json",
    "AGENTS.md",
    ".github/aegis-bootstrap-checklist.md",
    ".github/copilot-harness-quickstart.md",
    ".github/copilot-instructions.md",
    ".github/instructions/aituber-csharp.instructions.md",
    ".github/instructions/aituber-tests.instructions.md",
    ".github/instructions/golden-principles.instructions.md",
    ".github/instructions/sync-docs.instructions.md",
    ".github/instructions/unity-mcp.instructions.md",
    ".vscode/tasks.json",
    ".githooks/pre-commit",
    "scripts/copilot_startup.ps1",
    "scripts/copilot_review_packet.ps1",
    "scripts/copilot_quality_gate.ps1",
    "scripts/copilot_pre_commit.ps1",
    "scripts/copilot_unity_validation.ps1",
    "scripts/setup_aegis.ps1",
    "scripts/aegis_step4_guide.md",
    "scripts/aegis_seed_import_payloads.json",
    "scripts/install_git_hooks.ps1",
    "AITuber/.github/copilot-review-workflow.md",
    "AITuber/.github/prompts/review-pr.prompt.md",
    "AITuber/.github/prompts/run-harness-review-loop.prompt.md",
    "AITuber/.github/prompts/triage-review-findings.prompt.md",
    "AITuber/.github/prompts/validate-review-fixes.prompt.md",
    "AITuber/.github/agents/harness-review-orchestrator.agent.md",
    "AITuber/.github/copilot-review-prompts/requirements-reviewer.md",
    "AITuber/.github/copilot-review-prompts/architecture-reviewer.md",
    "AITuber/.github/copilot-review-prompts/reliability-reviewer.md",
    "AITuber/.github/copilot-review-prompts/security-reviewer.md",
    "AITuber/.github/copilot-review-prompts/performance-reviewer.md",
    "AITuber/.github/copilot-review-prompts/test-reviewer.md",
    "AITuber/.github/copilot-review-prompts/lead-reviewer.md",
    "AITuber/.github/PULL_REQUEST_TEMPLATE.md"
)

if (-not (Test-Path $BundleRoot)) {
    New-Item -ItemType Directory -Path $BundleRoot -Force | Out-Null
}

$copiedCount = 0
$skippedCount = 0

foreach ($relativePath in $pathsToShare) {
    $sourcePath = Join-Path $repoRoot ($relativePath -replace '/', [System.IO.Path]::DirectorySeparatorChar)
    if (-not (Test-Path $sourcePath)) {
        Write-Warning "Skipped missing path: $relativePath"
        $skippedCount++
        continue
    }

    $destinationPath = Join-Path $BundleRoot ($relativePath -replace '/', [System.IO.Path]::DirectorySeparatorChar)
    $destinationDir = Split-Path -Parent $destinationPath
    if (-not (Test-Path $destinationDir)) {
        New-Item -ItemType Directory -Path $destinationDir -Force | Out-Null
    }

    Copy-Item -Path $sourcePath -Destination $destinationPath -Force
    $copiedCount++
}

$manifestPath = Join-Path $BundleRoot "manifest.json"
$manifest = [ordered]@{
    generatedAtUtc = (Get-Date).ToUniversalTime().ToString("o")
    sourceRepo = $repoRoot
    fileCount = $copiedCount
    files = $pathsToShare
} | ConvertTo-Json -Depth 4

[System.IO.File]::WriteAllText($manifestPath, $manifest, [System.Text.Encoding]::UTF8)

Write-Host "Published Copilot harness bundle" -ForegroundColor Green
Write-Host "Bundle: $BundleRoot"
Write-Host "Copied: $copiedCount file(s)"
Write-Host "Skipped: $skippedCount file(s)"
Write-Host "Manifest: $manifestPath"