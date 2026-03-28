#!/usr/bin/env pwsh
param(
    [string]$BaseRef = "main"
)

$ErrorActionPreference = "Stop"
if (Get-Variable -Name PSNativeCommandUseErrorActionPreference -ErrorAction SilentlyContinue) {
    $PSNativeCommandUseErrorActionPreference = $false
}

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
        foreach ($path in $pathSet) {
            if ([string]::IsNullOrWhiteSpace($path)) {
                continue
            }

            $normalized = $path.Replace('\\', '/')
            $allPaths.Add($normalized) | Out-Null
        }
    }

    return @([string[]]$allPaths | Sort-Object)
}

function Add-Line {
    param(
        [System.Collections.Generic.List[string]]$Buffer,
        [string]$Text = ""
    )

    $Buffer.Add($Text) | Out-Null
}

function Add-Reviewer {
    param(
        [System.Collections.Generic.List[string]]$Buffer,
        [string]$Reviewer
    )

    if (-not $Buffer.Contains($Reviewer)) {
        $Buffer.Add($Reviewer) | Out-Null
    }
}

function Test-AnyPath {
    param(
        [string[]]$Paths,
        [string[]]$Patterns
    )

    foreach ($path in $Paths) {
        foreach ($pattern in $Patterns) {
            if ($path -match $pattern) {
                return $true
            }
        }
    }

    return $false
}

$repoRoot = Get-RepoRoot
$packetPath = Join-Path $repoRoot "copilot-temp\review-packet.md"
$changedPaths = Get-ChangedPaths -RepoRoot $repoRoot
$branch = (Get-GitOutput -RepoRoot $repoRoot -Arguments @("rev-parse", "--abbrev-ref", "HEAD") | Select-Object -First 1)
$mergeBase = (Get-GitOutput -RepoRoot $repoRoot -Arguments @("merge-base", "HEAD", $BaseRef) | Select-Object -First 1)
$diffStat = @(
    Get-GitOutput -RepoRoot $repoRoot -Arguments @("diff", "--cached", "--stat")
    Get-GitOutput -RepoRoot $repoRoot -Arguments @("diff", "--stat")
)

$changedCs = @($changedPaths | Where-Object { $_ -match '(^|.*/)Assets/.*\.cs$' })
$changedPython = @($changedPaths | Where-Object { $_ -match '^AITuber/(orchestrator|tests)/.*\.py$' })
$changedDocs = @($changedPaths | Where-Object { $_ -match '\.(md|prompt\.md|instructions\.md)$' })
$changedProtocol = @($changedPaths | Where-Object { $_ -match '^AITuber/\.github/srs/' -or $_ -match 'schema' -or $_ -match 'protocol' })
$changedTests = @($changedPaths | Where-Object { $_ -match '^AITuber/tests/' -or $_ -match '(^|.*/)Assets/Tests/' })
$changedRuntime = @($changedPaths | Where-Object { $_ -match '^AITuber/(orchestrator|overlays|minecraft_bridge)/' -or $_ -match '(^|.*/)Assets/Scripts/' })
$changedHarness = @($changedPaths | Where-Object { $_ -match '^\.github/' -or $_ -match '^scripts/copilot_' -or $_ -match '^AITuber/\.github/' })

$isDocOnly = $changedPaths.Count -gt 0 -and ($changedPaths.Count -eq $changedDocs.Count)
$hasCodeChanges = $changedCs.Count -gt 0 -or $changedPython.Count -gt 0
$hasRuntimeChanges = $changedRuntime.Count -gt 0
$hasHarnessChanges = $changedHarness.Count -gt 0
$hasProtocolChanges = $changedProtocol.Count -gt 0
$hasTestChanges = $changedTests.Count -gt 0

$needsArchitecture = $hasRuntimeChanges -or $hasProtocolChanges -or $hasHarnessChanges
$needsReliability = $hasRuntimeChanges -or $hasProtocolChanges -or (Test-AnyPath -Paths $changedPaths -Patterns @('websocket', 'queue', 'scheduler', 'memory', 'overlay', 'audio', 'retry', 'timeout', 'navmesh', 'anim', 'lipsync'))
$needsSecurity = $hasProtocolChanges -or (Test-AnyPath -Paths $changedPaths -Patterns @('security', 'auth', 'token', 'secret', 'credential', '\.env', 'config/', 'youtube', 'openai', 'voicevox', 'aivis', 'prompt'))
$needsPerformance = $hasRuntimeChanges -and (Test-AnyPath -Paths $changedPaths -Patterns @('audio', 'overlay', 'memory', 'scheduler', 'sentis', 'bandit', 'llm', 'ws', 'websocket', 'avatar', 'behavior', 'navmesh', 'room', 'gesture', 'lipsync'))
$needsRequirements = $hasCodeChanges -or $hasProtocolChanges -or $changedDocs.Count -gt 0
$needsTests = $hasCodeChanges -or $hasTestChanges -or $hasHarnessChanges

$reviewers = New-Object System.Collections.Generic.List[string]

if ($changedPaths.Count -eq 0) {
    Add-Reviewer -Buffer $reviewers -Reviewer "Lead Reviewer"
} else {
    if ($needsRequirements) {
        Add-Reviewer -Buffer $reviewers -Reviewer "Requirements Reviewer"
    }
    if ($needsArchitecture) {
        Add-Reviewer -Buffer $reviewers -Reviewer "Architecture Reviewer"
    }
    if ($needsReliability -and -not $isDocOnly) {
        Add-Reviewer -Buffer $reviewers -Reviewer "Reliability Reviewer"
    }
    if ($needsSecurity -and -not $isDocOnly) {
        Add-Reviewer -Buffer $reviewers -Reviewer "Security Reviewer"
    }
    if ($needsPerformance -and -not $isDocOnly) {
        Add-Reviewer -Buffer $reviewers -Reviewer "Performance Reviewer"
    }
    if ($needsTests) {
        Add-Reviewer -Buffer $reviewers -Reviewer "Test Reviewer"
    }
    Add-Reviewer -Buffer $reviewers -Reviewer "Lead Reviewer"
}
$reviewers = @([string[]]$reviewers)

$validations = New-Object System.Collections.Generic.List[string]
if ($changedPython.Count -gt 0) {
    $validations.Add("Run Task: Harness: Quality Gate (changed files)") | Out-Null
}
if ($changedCs.Count -gt 0) {
    $validations.Add("Run Unity MCP compile/console workflow from .github/instructions/unity-mcp.instructions.md") | Out-Null
    $validations.Add("After Unity MCP checks pass, run Task: Harness: Mark Unity Validation Done") | Out-Null
}
if ($changedProtocol.Count -gt 0) {
    $validations.Add("Re-run protocol/schema review with Requirements Reviewer and Architecture Reviewer") | Out-Null
}
if ($hasHarnessChanges) {
    $validations.Add("Use /run-harness-review-loop to verify the updated harness flow end-to-end") | Out-Null
}
if ($validations.Count -eq 0) {
    $validations.Add("No code changes detected. Review whether a review loop is necessary.") | Out-Null
}

$slashCommands = New-Object System.Collections.Generic.List[string]
if ($changedPaths.Count -gt 0) {
    $slashCommands.Add("/run-harness-review-loop") | Out-Null
    $slashCommands.Add("/review-pr") | Out-Null
}
if ($reviewers.Contains("Requirements Reviewer")) {
    $slashCommands.Add("Requirements Reviewer") | Out-Null
}
if ($reviewers.Contains("Architecture Reviewer")) {
    $slashCommands.Add("Architecture Reviewer") | Out-Null
}
if ($reviewers.Contains("Reliability Reviewer")) {
    $slashCommands.Add("Reliability Reviewer") | Out-Null
}
if ($reviewers.Contains("Security Reviewer")) {
    $slashCommands.Add("Security Reviewer") | Out-Null
}
if ($reviewers.Contains("Performance Reviewer")) {
    $slashCommands.Add("Performance Reviewer") | Out-Null
}
if ($reviewers.Contains("Test Reviewer")) {
    $slashCommands.Add("Test Reviewer") | Out-Null
}
if ($changedPaths.Count -gt 0) {
    $slashCommands.Add("/triage-review-findings") | Out-Null
    $slashCommands.Add("/validate-review-fixes") | Out-Null
}

$lines = New-Object System.Collections.Generic.List[string]
Add-Line -Buffer $lines -Text "# Review Packet"
Add-Line -Buffer $lines
Add-Line -Buffer $lines -Text "- Branch: $branch"
Add-Line -Buffer $lines -Text "- Base ref: $BaseRef"
if ($mergeBase) {
    Add-Line -Buffer $lines -Text "- Merge base: $mergeBase"
}
Add-Line -Buffer $lines
Add-Line -Buffer $lines -Text "## Changed Files"
if ($changedPaths.Count -eq 0) {
    Add-Line -Buffer $lines -Text "- <none>"
} else {
    foreach ($path in $changedPaths) {
        Add-Line -Buffer $lines -Text "- $path"
    }
}

Add-Line -Buffer $lines
Add-Line -Buffer $lines -Text "## Diff Stat"
if ($diffStat.Count -eq 0) {
    Add-Line -Buffer $lines -Text "- <unavailable>"
} else {
    foreach ($line in $diffStat) {
        Add-Line -Buffer $lines -Text "- $line"
    }
}

Add-Line -Buffer $lines
Add-Line -Buffer $lines -Text "## Scope Hints"
Add-Line -Buffer $lines -Text "- C# files: $($changedCs.Count)"
Add-Line -Buffer $lines -Text "- Python files: $($changedPython.Count)"
Add-Line -Buffer $lines -Text "- Docs/instructions: $($changedDocs.Count)"
Add-Line -Buffer $lines -Text "- Protocol/schema: $($changedProtocol.Count)"
Add-Line -Buffer $lines -Text "- Harness files: $($changedHarness.Count)"
Add-Line -Buffer $lines -Text "- Test files: $($changedTests.Count)"

Add-Line -Buffer $lines
Add-Line -Buffer $lines -Text "## Recommended Reviewers"
foreach ($reviewer in $reviewers) {
    Add-Line -Buffer $lines -Text "- $reviewer"
}

Add-Line -Buffer $lines
Add-Line -Buffer $lines -Text "## Suggested Commands"
foreach ($command in @([string[]]$slashCommands | Select-Object -Unique)) {
    Add-Line -Buffer $lines -Text "- $command"
}

Add-Line -Buffer $lines
Add-Line -Buffer $lines -Text "## Required Validations"
foreach ($validation in $validations) {
    Add-Line -Buffer $lines -Text "- $validation"
}

Add-Line -Buffer $lines
Add-Line -Buffer $lines -Text "## Auto Triggers"
Add-Line -Buffer $lines -Text "- pre-commit runs scripts/copilot_pre_commit.ps1 and regenerates this packet automatically"
Add-Line -Buffer $lines -Text "- AI triage and validation are not deterministic shell checks, so they are assisted by slash prompts rather than enforced by the git hook"
if ($changedCs.Count -gt 0) {
    Add-Line -Buffer $lines -Text "- pre-commit will fail until copilot-temp/unity-validation.json is refreshed after Unity compile/console validation"
}

Add-Line -Buffer $lines
Add-Line -Buffer $lines -Text "## Harness Loop"
Add-Line -Buffer $lines -Text "1. Run the recommended reviewers against the current diff."
Add-Line -Buffer $lines -Text "2. Feed the findings into /triage-review-findings to drop low-value or out-of-scope issues and emit directives."
Add-Line -Buffer $lines -Text "3. Apply fixes only for Must Fix findings and keep directives stable between iterations."
Add-Line -Buffer $lines -Text "4. Run /validate-review-fixes to reject band-aid fixes and confirm root-cause coverage."
Add-Line -Buffer $lines -Text "5. Re-run the quality gate and stop when Must Fix is empty."

$packetDir = Split-Path -Parent $packetPath
if (-not (Test-Path $packetDir)) {
    New-Item -ItemType Directory -Path $packetDir | Out-Null
}

[System.IO.File]::WriteAllLines($packetPath, $lines)

Write-Host "== GitHub Copilot Review Packet ==" -ForegroundColor Cyan
Write-Host "wrote: $packetPath" -ForegroundColor Green
Write-Host ""
$lines | ForEach-Object { Write-Host $_ }