#!/usr/bin/env pwsh
param(
    [string]$BaseRef = "main"
)

$ErrorActionPreference = "Stop"

function Get-RepoRoot {
    return Split-Path -Parent $PSScriptRoot
}

function Get-GitOutput {
    param(
        [string]$RepoRoot,
        [string[]]$Arguments
    )

    $escapedArguments = @("-C", $RepoRoot) + $Arguments | ForEach-Object {
        if ($_ -match '\s') {
            '"{0}"' -f $_.Replace('"', '\"')
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
    $stderr = $process.StandardError.ReadToEnd()
    $process.WaitForExit()

    if ($process.ExitCode -ne 0) {
        if (-not [string]::IsNullOrWhiteSpace($stderr)) {
            Write-Verbose $stderr
        }
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

$repoRoot = Get-RepoRoot
$changedPaths = Get-ChangedPaths -RepoRoot $repoRoot
$hasUnityCsChanges = @($changedPaths | Where-Object { $_ -match '(^|.*/)Assets/.*\.cs$' }).Count -gt 0

Push-Location $repoRoot
try {
    Write-Host "[harness] generate review packet" -ForegroundColor Cyan
    & (Join-Path $repoRoot "scripts\copilot_review_packet.ps1") -BaseRef $BaseRef

    Write-Host "[harness] run changed-files quality gate" -ForegroundColor Cyan
    & (Join-Path $repoRoot "scripts\copilot_quality_gate.ps1") -ChangedOnly

    if ($hasUnityCsChanges) {
        Write-Host "[harness] verify Unity validation marker" -ForegroundColor Cyan
        & (Join-Path $repoRoot "scripts\copilot_unity_validation.ps1") -Action status -BaseRef $BaseRef
    }
}
finally {
    Pop-Location
}