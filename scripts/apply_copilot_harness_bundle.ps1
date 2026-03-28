#!/usr/bin/env pwsh
param(
    [Parameter(Mandatory = $true)]
    [string]$TargetRepo,
    [string]$BundleRoot = "$HOME/.copilot-harness/bundle",
    [switch]$Force
)

$ErrorActionPreference = "Stop"

function Get-GitOutput {
    param(
        [string]$RepoRoot,
        [string[]]$Arguments
    )

    $escapedArguments = @("-C", $RepoRoot) + $Arguments | ForEach-Object {
        if ($_ -match '\s') {
            '"{0}"' -f $_.Replace('"', '\\"')
        } else {
            $_
        }
    }

    $startInfo = New-Object System.Diagnostics.ProcessStartInfo
    $startInfo.FileName = "git"
    $startInfo.Arguments = [string]::Join(" ", $escapedArguments)
    $startInfo.UseShellExecute = $false
    $startInfo.RedirectStandardOutput = $true
    $startInfo.RedirectStandardError = $true
    $startInfo.CreateNoWindow = $true

    $process = New-Object System.Diagnostics.Process
    $process.StartInfo = $startInfo
    $null = $process.Start()
    $stdout = $process.StandardOutput.ReadToEnd()
    $process.StandardError.ReadToEnd() | Out-Null
    $process.WaitForExit()

    if ($process.ExitCode -ne 0) {
        return @()
    }

    return @($stdout -split "`r?`n" | Where-Object { -not [string]::IsNullOrWhiteSpace($_) })
}

function Get-ChangedPaths {
    param([string]$RepoRoot)

    $allPaths = New-Object System.Collections.Generic.HashSet[string]
    $pathSets = @(
        (Get-GitOutput -RepoRoot $RepoRoot -Arguments @("diff", "--cached", "--name-only", "--diff-filter=ACMR")),
        (Get-GitOutput -RepoRoot $RepoRoot -Arguments @("diff", "--name-only", "--diff-filter=ACMR")),
        (Get-GitOutput -RepoRoot $RepoRoot -Arguments @("ls-files", "--others", "--exclude-standard"))
    )

    foreach ($pathSet in $pathSets) {
        foreach ($path in @($pathSet)) {
            if ([string]::IsNullOrWhiteSpace($path)) {
                continue
            }

            $allPaths.Add($path.Replace('\\', '/')) | Out-Null
        }
    }

    return @([string[]]$allPaths | Sort-Object)
}

if (-not (Test-Path $TargetRepo)) {
    throw "Target repository does not exist: $TargetRepo"
}

if (-not (Test-Path $BundleRoot)) {
    throw "Bundle directory does not exist: $BundleRoot"
}

$manifestPath = Join-Path $BundleRoot "manifest.json"
if (-not (Test-Path $manifestPath)) {
    throw "Bundle manifest was not found: $manifestPath"
}

$manifest = Get-Content -Raw -Encoding UTF8 -Path $manifestPath | ConvertFrom-Json
$files = @($manifest.files)

$targetHasAituberDir = Test-Path (Join-Path $TargetRepo "AITuber")
$copiedCount = 0
$skippedCount = 0

foreach ($relativePath in $files) {
    if ($relativePath -like "AITuber/*" -and -not $targetHasAituberDir) {
        Write-Warning "Skipped AITuber-scoped file (target has no AITuber directory): $relativePath"
        $skippedCount++
        continue
    }

    $sourcePath = Join-Path $BundleRoot ($relativePath -replace '/', [System.IO.Path]::DirectorySeparatorChar)
    if (-not (Test-Path $sourcePath)) {
        Write-Warning "Skipped missing bundle file: $relativePath"
        $skippedCount++
        continue
    }

    $destinationPath = Join-Path $TargetRepo ($relativePath -replace '/', [System.IO.Path]::DirectorySeparatorChar)
    $destinationDir = Split-Path -Parent $destinationPath
    if (-not (Test-Path $destinationDir)) {
        New-Item -ItemType Directory -Path $destinationDir -Force | Out-Null
    }

    if ((Test-Path $destinationPath) -and -not $Force) {
        Write-Warning "Skipped existing file (use -Force to overwrite): $relativePath"
        $skippedCount++
        continue
    }

    Copy-Item -Path $sourcePath -Destination $destinationPath -Force
    $copiedCount++
}

Write-Host "Applied Copilot harness bundle" -ForegroundColor Green
Write-Host "Target: $TargetRepo"
Write-Host "Copied: $copiedCount file(s)"
Write-Host "Skipped: $skippedCount file(s)"
Write-Host "Next: run scripts/install_git_hooks.ps1 in the target repository"

$changedPaths = Get-ChangedPaths -RepoRoot $TargetRepo
$unityCsChanges = @($changedPaths | Where-Object { $_ -match '(^|.*/)Assets/.*\.cs$' })
if ($unityCsChanges.Count -gt 0) {
    Write-Warning "Target repository already has Unity C# changes. pre-commit will require a fresh copilot-temp/unity-validation.json marker before commit."
    Write-Host "Next after Unity compile/console checks: run Task: Harness: Mark Unity Validation Done" -ForegroundColor Yellow
}