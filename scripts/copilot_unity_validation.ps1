#!/usr/bin/env pwsh
param(
    [ValidateSet("mark", "status", "clear")]
    [string]$Action = "status",
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
        foreach ($path in $pathSet) {
            if ([string]::IsNullOrWhiteSpace($path)) {
                continue
            }

            $allPaths.Add($path.Replace('\\', '/')) | Out-Null
        }
    }

    return @([string[]]$allPaths | Sort-Object)
}

function Get-StringSha256 {
    param([string]$Text)

    $sha = [System.Security.Cryptography.SHA256]::Create()
    try {
        $bytes = [System.Text.Encoding]::UTF8.GetBytes($Text)
        $hashBytes = $sha.ComputeHash($bytes)
        return ([System.BitConverter]::ToString($hashBytes)).Replace("-", "").ToLowerInvariant()
    }
    finally {
        $sha.Dispose()
    }
}

function Get-UnitySnapshot {
    param(
        [string]$RepoRoot,
        [string[]]$UnityPaths
    )

    $normalizedPaths = @($UnityPaths | Sort-Object)
    $components = New-Object System.Collections.Generic.List[string]

    foreach ($path in $normalizedPaths) {
        $absolutePath = Join-Path $RepoRoot ($path.Replace('/', [System.IO.Path]::DirectorySeparatorChar))
        if (-not (Test-Path $absolutePath)) {
            continue
        }

        $hash = (Get-FileHash -Algorithm SHA256 -Path $absolutePath).Hash.ToLowerInvariant()
            $components.Add("${path}:$hash") | Out-Null
    }

    $fingerprint = ""
    if ($components.Count -gt 0) {
        $fingerprint = Get-StringSha256 -Text ([string]::Join("|", $components))
    }

    return [PSCustomObject]@{
        paths = $normalizedPaths
        fingerprint = $fingerprint
    }
}

$repoRoot = Get-RepoRoot
$markerPath = Join-Path $repoRoot "copilot-temp\unity-validation.json"
$changedPaths = Get-ChangedPaths -RepoRoot $repoRoot
$unityPaths = @($changedPaths | Where-Object { $_ -match '(^|.*/)Assets/.*\.cs$' })

switch ($Action) {
    "clear" {
        if (Test-Path $markerPath) {
            Remove-Item -Path $markerPath -Force
            Write-Host "Cleared Unity validation marker: $markerPath" -ForegroundColor Yellow
        } else {
            Write-Host "Unity validation marker does not exist." -ForegroundColor Yellow
        }
        break
    }
    "mark" {
        if ($unityPaths.Count -eq 0) {
            Write-Host "No changed Unity C# files were detected. No marker was written." -ForegroundColor Yellow
            break
        }

        $snapshot = Get-UnitySnapshot -RepoRoot $repoRoot -UnityPaths $unityPaths
        $markerDir = Split-Path -Parent $markerPath
        if (-not (Test-Path $markerDir)) {
            New-Item -ItemType Directory -Path $markerDir | Out-Null
        }

        $payload = [ordered]@{
            createdAtUtc = (Get-Date).ToUniversalTime().ToString("o")
            baseRef = $BaseRef
            fingerprint = $snapshot.fingerprint
            fileCount = $snapshot.paths.Count
            unityPaths = $snapshot.paths
            note = "Refresh this marker only after Unity compile and console checks succeed."
        } | ConvertTo-Json -Depth 5

        [System.IO.File]::WriteAllText($markerPath, $payload, [System.Text.Encoding]::UTF8)
        Write-Host "Recorded Unity validation marker: $markerPath" -ForegroundColor Green
        Write-Host "Tracked files: $($snapshot.paths.Count)" -ForegroundColor Green
        break
    }
    "status" {
        if ($unityPaths.Count -eq 0) {
            Write-Host "No changed Unity C# files detected. Unity validation marker is not required." -ForegroundColor Green
            break
        }

        if (-not (Test-Path $markerPath)) {
            Write-Error "Unity C# changes are present, but copilot-temp/unity-validation.json is missing. Run the Unity MCP compile/console checks, then run Task: Harness: Mark Unity Validation Done."
            exit 1
        }

        $marker = Get-Content -Raw -Encoding UTF8 -Path $markerPath | ConvertFrom-Json
        $current = Get-UnitySnapshot -RepoRoot $repoRoot -UnityPaths $unityPaths

        if ([string]$marker.fingerprint -ne $current.fingerprint) {
            Write-Error "Unity validation marker is stale. Unity C# files changed after the marker was recorded. Re-run the Unity MCP checks, then refresh the marker with Task: Harness: Mark Unity Validation Done."
            exit 1
        }

        Write-Host "Unity validation marker is current." -ForegroundColor Green
        Write-Host "validatedAtUtc: $($marker.createdAtUtc)" -ForegroundColor Green
        Write-Host "trackedFiles: $($marker.fileCount)" -ForegroundColor Green
        break
    }
}