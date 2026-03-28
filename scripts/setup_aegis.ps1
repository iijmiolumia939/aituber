#!/usr/bin/env pwsh
param(
    [string]$ProjectRoot,
    [string]$Targets = "codex"
)

$ErrorActionPreference = "Stop"

if ([string]::IsNullOrWhiteSpace($ProjectRoot)) {
    $ProjectRoot = Split-Path -Parent $PSScriptRoot
}

$resolvedRoot = Resolve-Path $ProjectRoot
$dbPath = Join-Path $resolvedRoot ".aegis\aegis.db"

if (-not (Get-Command npx -ErrorAction SilentlyContinue)) {
    throw "npx was not found. Install Node.js (with npm/npx) before running Aegis setup."
}

if (-not (Test-Path $dbPath)) {
    throw "Aegis database was not found at $dbPath. Initialize Aegis first via admin surface (aegis_init_detect -> aegis_init_confirm), then rerun this script."
}

Write-Host "[aegis] deploy adapters" -ForegroundColor Cyan
& npx -y @fuwasegu/aegis deploy-adapters --project-root $resolvedRoot --targets $Targets

Write-Host "[aegis] adapters deployed" -ForegroundColor Green
Write-Host "Next steps:" -ForegroundColor Yellow
Write-Host "1) Ensure MCP servers are configured in .mcp.json (aegis + aegis-admin)" -ForegroundColor Yellow
Write-Host "2) In admin surface: run aegis_init_detect then aegis_init_confirm" -ForegroundColor Yellow
Write-Host "3) Import architecture/docs via aegis_import_doc with edge_hints" -ForegroundColor Yellow
Write-Host "4) Use aegis_compile_context before code changes; report misses via aegis_observe" -ForegroundColor Yellow
