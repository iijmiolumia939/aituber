#!/usr/bin/env pwsh
param(
    [switch]$ChangedOnly,
    [switch]$SkipLint,
    [switch]$SkipFormat,
    [switch]$SkipTests
)

$ErrorActionPreference = "Stop"

function Get-RepoRoot {
    return Split-Path -Parent $PSScriptRoot
}

function Get-PythonCommand {
    $repoRoot = Get-RepoRoot
    $candidates = @(
        (Join-Path $repoRoot ".venv\Scripts\python.exe"),
        (Join-Path $repoRoot "AITuber\.venv\Scripts\python.exe")
    )

    foreach ($candidate in $candidates) {
        if (Test-Path $candidate) {
            return $candidate
        }
    }

    return "python"
}

function Get-ChangedPaths {
    param([string]$RepoRoot)

    $allPaths = New-Object System.Collections.Generic.HashSet[string]
    $gitAvailable = $null -ne (Get-Command git -ErrorAction SilentlyContinue)
    if (-not $gitAvailable) {
        return @()
    }

    $staged = & git -C $RepoRoot diff --cached --name-only --diff-filter=ACMR
    $unstaged = & git -C $RepoRoot diff --name-only --diff-filter=ACMR

    foreach ($path in @($staged + $unstaged)) {
        if ([string]::IsNullOrWhiteSpace($path)) {
            continue
        }

        $normalized = $path.Replace('\\', '/')
        $allPaths.Add($normalized) | Out-Null
    }

    return @([string[]]$allPaths | Sort-Object)
}

function Invoke-Step {
    param(
        [string]$Name,
        [scriptblock]$Action
    )

    Write-Host "[harness] $Name" -ForegroundColor Cyan
    & $Action
    if ($LASTEXITCODE -ne 0) {
        throw "$Name failed with exit code $LASTEXITCODE"
    }
}

$repoRoot = Get-RepoRoot
$projectRoot = Join-Path $repoRoot "AITuber"
$python = Get-PythonCommand

$isAituberMode = Test-Path $projectRoot
if (-not $isAituberMode) {
    Write-Host "[harness] skip quality gate: AITuber project root was not found at $projectRoot" -ForegroundColor DarkYellow
    Write-Host "[harness] non-AITuber repository detected; no repository-specific Python gate configured" -ForegroundColor DarkYellow
    return
}

$changedPaths = @()
if ($ChangedOnly) {
    $changedPaths = Get-ChangedPaths -RepoRoot $repoRoot
}

$changedPythonPaths = @(
    $changedPaths | Where-Object {
        $_ -match '^AITuber/(orchestrator|tests)/.*\.py$'
    }
)

$projectRelativePythonPaths = @(
    $changedPythonPaths | ForEach-Object {
        $_.Substring("AITuber/".Length)
    }
)

$shouldRunPythonChecks = -not $ChangedOnly -or $projectRelativePythonPaths.Count -gt 0
$shouldRunTests = -not $SkipTests -and (
    -not $ChangedOnly -or
    ($changedPaths | Where-Object {
        $_ -match '^AITuber/(orchestrator|tests)/' -or $_ -eq 'AITuber/pyproject.toml'
    }).Count -gt 0
)

Push-Location $projectRoot
try {
    if (-not $SkipLint -and $shouldRunPythonChecks) {
        Invoke-Step -Name "ruff check" -Action {
            if ($ChangedOnly) {
                & $python -m ruff check @projectRelativePythonPaths
            } else {
                & $python -m ruff check orchestrator tests
            }
        }
    } elseif (-not $SkipLint) {
        Write-Host "[harness] skip ruff check: no changed Python files in AITuber/orchestrator or AITuber/tests" -ForegroundColor DarkYellow
    }

    if (-not $SkipFormat -and $shouldRunPythonChecks) {
        Invoke-Step -Name "black --check" -Action {
            if ($ChangedOnly) {
                & $python -m black --check @projectRelativePythonPaths
            } else {
                & $python -m black --check orchestrator tests
            }
        }
    } elseif (-not $SkipFormat) {
        Write-Host "[harness] skip black --check: no changed Python files in AITuber/orchestrator or AITuber/tests" -ForegroundColor DarkYellow
    }

    if ($shouldRunTests) {
        Invoke-Step -Name "batch pytest" -Action {
            & (Join-Path $projectRoot "run_tests.ps1") -FailFast
        }
    } else {
        Write-Host "[harness] skip tests: no orchestrator or Python test changes detected" -ForegroundColor DarkYellow
    }
}
finally {
    Pop-Location
}