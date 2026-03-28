#!/usr/bin/env pwsh
param(
    [string]$SharedRoot = "$HOME/.copilot-harness",
    [string]$WorkspaceRoot = "C:/Users/iijmi/st/"
)

$ErrorActionPreference = "Stop"

function Normalize-GitDirPath {
    param([string]$Path)

    $fullPath = [System.IO.Path]::GetFullPath($Path)
    $normalized = $fullPath.Replace('\\', '/')
    if (-not $normalized.EndsWith('/')) {
        $normalized = "$normalized/"
    }
    return $normalized
}

$sharedRootFull = [System.IO.Path]::GetFullPath($SharedRoot)
$globalHooksDir = Join-Path $sharedRootFull "git/hooks"
$globalConfigDir = Join-Path $sharedRootFull "git"
$includeConfigPath = Join-Path $globalConfigDir "config-work.inc"

if (-not (Test-Path $globalHooksDir)) {
    New-Item -ItemType Directory -Path $globalHooksDir -Force | Out-Null
}

$globalPreCommitPath = Join-Path $globalHooksDir "pre-commit"
$globalPreCommit = @'
#!/usr/bin/env sh
set -eu

repo_root="$(git rev-parse --show-toplevel)"
cd "$repo_root"

if [ -f "./scripts/copilot_pre_commit.ps1" ]; then
  if command -v pwsh >/dev/null 2>&1; then
    pwsh -NoProfile -ExecutionPolicy Bypass -File "./scripts/copilot_pre_commit.ps1"
    exit $?
  elif command -v powershell.exe >/dev/null 2>&1; then
    powershell.exe -NoProfile -ExecutionPolicy Bypass -File "./scripts/copilot_pre_commit.ps1"
    exit $?
  fi
fi

echo "[global-hook] scripts/copilot_pre_commit.ps1 not found in this repo. Skipping Copilot harness hook." >&2
exit 0
'@

[System.IO.File]::WriteAllText($globalPreCommitPath, $globalPreCommit, [System.Text.Encoding]::UTF8)

$includeConfig = @'
[alias]
  harness-precommit = !powershell -NoProfile -ExecutionPolicy Bypass -File scripts/copilot_pre_commit.ps1
  harness-review-packet = !powershell -NoProfile -ExecutionPolicy Bypass -File scripts/copilot_review_packet.ps1
'@

[System.IO.File]::WriteAllText($includeConfigPath, $includeConfig, [System.Text.Encoding]::UTF8)

$workspaceRootNormalized = Normalize-GitDirPath -Path $WorkspaceRoot

& git config --global core.hooksPath $globalHooksDir
& git config --global --replace-all "includeIf.gitdir:$workspaceRootNormalized.path" $includeConfigPath

Write-Host "Configured global Copilot harness Git settings" -ForegroundColor Green
Write-Host "core.hooksPath = $globalHooksDir"
Write-Host "includeIf.gitdir:$workspaceRootNormalized.path = $includeConfigPath"
Write-Host ""
Write-Host "To distribute harness files, run:" -ForegroundColor Yellow
Write-Host "  1) scripts/publish_copilot_harness_bundle.ps1"
Write-Host "  2) scripts/apply_copilot_harness_bundle.ps1 -TargetRepo <path> -Force"