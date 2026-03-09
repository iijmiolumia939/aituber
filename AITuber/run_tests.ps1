#!/usr/bin/env pwsh
<#
.SYNOPSIS
  Memory-safe batch test runner for AITuber.

.DESCRIPTION
  Runs pytest N files at a time in separate Python processes.
  Each batch process exits cleanly so the OS reclaims all memory
  before the next batch starts -- preventing 32GB OOM crashes.

  Root cause:
  - pytest imports all 48 test modules upfront (keeps everything in RAM)
  - asyncio_mode=auto creates a new event loop per async test function
  - Running all 700 tests in one process = cumulative memory pressure

.PARAMETER BatchSize
  Number of test files per batch. Smaller = less RAM per batch, more startup overhead.
  Default: 4

.PARAMETER Marker
  Expression passed to pytest -m. Default: "not slow" (excludes real WS server tests).

.PARAMETER FailFast
  Stop after the first failing batch.

.EXAMPLE
  .\run_tests.ps1                     # normal run (sequential batches)
  .\run_tests.ps1 -BatchSize 2        # when RAM is very tight
  .\run_tests.ps1 -Marker "slow"      # run only WS server tests
  .\run_tests.ps1 -FailFast           # stop on first failure

  # Alternative: pytest-xdist (install once: pip install pytest-xdist)
  #   python -m pytest -n 2 --dist=loadfile -m "not slow" -q   <- 2 workers, Unity Editor open
  #   python -m pytest -n 4 --dist=loadfile -m "not slow" -q   <- 4 workers, Unity closed
#>
param(
    [int]    $BatchSize = 4,
    [string] $Marker    = "not slow",
    [switch] $FailFast
)

$ErrorActionPreference = "Continue"
$ScriptDir  = Split-Path -Parent $MyInvocation.MyCommand.Path
$TestDir    = Join-Path $ScriptDir "tests"

# Switch to the project root so pytest can find pyproject.toml and tests/
Push-Location $ScriptDir

$testFiles = Get-ChildItem "$TestDir\*.py" |
             Where-Object { $_.Name -ne "conftest.py" } |
             Sort-Object Name

$totalFiles = $testFiles.Count
$batchCount = [Math]::Ceiling($totalFiles / $BatchSize)

Write-Host ""
Write-Host "-------------------------------------------" -ForegroundColor Cyan
Write-Host "  AITuber batch test runner" -ForegroundColor Cyan
Write-Host "  files=$totalFiles  batches=$batchCount  batchSize=$BatchSize" -ForegroundColor Cyan
Write-Host "  marker: -m `"$Marker`"" -ForegroundColor Cyan
Write-Host "-------------------------------------------" -ForegroundColor Cyan

$failedBatches = @()
$passedFiles   = 0
$batchNum      = 0

for ($i = 0; $i -lt $totalFiles; $i += $BatchSize) {
    $batchNum++
    $end      = [Math]::Min($i + $BatchSize - 1, $totalFiles - 1)
    $batch    = $testFiles[$i..$end]
    $relPaths = $batch | ForEach-Object { "tests/$($_.Name)" }

    Write-Host ""
    Write-Host "-- Batch $batchNum/$batchCount" -ForegroundColor Yellow
    $relPaths | ForEach-Object { Write-Host "   $_" -ForegroundColor DarkYellow }

    python -m pytest $relPaths -m "$Marker" --tb=short -q
    $exitCode = $LASTEXITCODE

    if ($exitCode -ne 0) {
        Write-Host "  FAILED (exit $exitCode)" -ForegroundColor Red
        $failedBatches += $relPaths
        if ($FailFast) {
            Write-Host "FailFast: stopping on first failure." -ForegroundColor Red
            break
        }
    } else {
        Write-Host "  passed" -ForegroundColor Green
        $passedFiles += $batch.Count
    }

    # brief pause so OS can reclaim memory between batches
    Start-Sleep -Milliseconds 500
}

Write-Host ""
Write-Host "-------------------------------------------" -ForegroundColor Cyan
if ($failedBatches.Count -eq 0) {
    Write-Host "  ALL PASSED ($passedFiles files)" -ForegroundColor Green
    Pop-Location
    exit 0
} else {
    Write-Host "  FAILED:" -ForegroundColor Red
    $failedBatches | ForEach-Object { Write-Host "    $_" -ForegroundColor Red }
    Pop-Location
    exit 1
}
