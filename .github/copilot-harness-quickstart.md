# Copilot Harness Quickstart (Non-AITuber Repositories)

This repository uses a shared GitHub Copilot harness package.

## 1) Enable tracked hooks

Run:

```powershell
./scripts/install_git_hooks.ps1
```

Then verify:

```powershell
git config --local --get core.hooksPath
```

Expected value: `.githooks`

## 2) What pre-commit does

The tracked pre-commit hook runs:

- `scripts/copilot_pre_commit.ps1`
- Regenerates `copilot-temp/review-packet.md`
- Runs `scripts/copilot_quality_gate.ps1 -ChangedOnly`

For non-AITuber repositories, the quality gate currently no-ops (success) unless you add repository-specific checks.

## 3) Unity projects: required marker gate

If changed files include `Assets/**/*.cs`, pre-commit additionally requires:

- `copilot-temp/unity-validation.json`

Create or refresh this marker only after Unity compile/console checks pass:

```powershell
./scripts/copilot_unity_validation.ps1 -Action mark
```

Check status anytime:

```powershell
./scripts/copilot_unity_validation.ps1 -Action status
```

## 4) Aegis setup (recommended)

1. Ensure `.mcp.json` includes both `aegis` and `aegis-admin`
2. Run:

```powershell
./scripts/setup_aegis.ps1
```

3. In admin surface, initialize and import documents:

- `aegis_init_detect`
- `aegis_init_confirm`
- `aegis_import_doc` (with edge hints)

4. During development, always call `aegis_compile_context` before coding
5. If guidance is missing, report with `aegis_observe` (`compile_miss`)

## 5) Daily flow

1. Make code changes
2. Consult Aegis context (`aegis_compile_context`) for target files
3. Run review or checks as needed
4. For Unity C# changes, validate in Unity and refresh marker
5. Commit (pre-commit runs automatically)

## 6) Troubleshooting

- Hook not running: re-run `./scripts/install_git_hooks.ps1`
- Aegis tools not available: check `.mcp.json` and restart the IDE agent session
- Unity marker missing: run Unity validation, then `-Action mark`
- Marker stale: C# changed after marking; re-run Unity checks and mark again

### Why admin MCP tools may be unavailable

- This chat runtime only exposes tools that were loaded when the session started.
- Even if `.mcp.json` is correct, newly added MCP servers may not appear until the IDE/Copilot session is reloaded.
- If only `aegis` appears but `aegis-admin` does not, check the exact server key and args in `.mcp.json`.
- Codex MCP support depends on CLI/version; update tooling if MCP servers do not appear.

### Recovery checklist

1. Verify `.mcp.json` contains both `aegis` and `aegis-admin`.
2. Restart VS Code window and start a new Copilot chat session.
3. Re-run `Task: Harness: Setup Aegis Adapters`.
4. In admin surface, run `aegis_init_detect` and `aegis_init_confirm` again if needed.
