# ADR 0001: GitHub Copilot Harness Baseline

- Status: Accepted
- Date: 2026-03-14

## Context

The repository already has strong product-level assets: AGENTS pointers, Copilot instructions, CI, Python linting, and batch-safe tests. What it lacks is a consistent local harness for GitHub Copilot sessions.

The article on harness engineering recommends tool lifecycle hooks, completion gates, ADRs, and standardized startup routines. GitHub Copilot in VS Code does not expose Claude-style PreToolUse and PostToolUse hooks, so that exact design is not portable here.

Without a Copilot-specific baseline, quality checks depend on memory and manual discipline. That creates drift across sessions and makes local feedback slower than necessary.

## Decision

We standardize on a GitHub Copilot-friendly harness with these tracked components:

1. A workspace task-based entrypoint in `.vscode/tasks.json`.
2. A tracked pre-commit hook in `.githooks/pre-commit`.
3. A repository-owned quality gate script in `scripts/copilot_quality_gate.ps1`.
4. A repository-owned startup routine in `scripts/copilot_startup.ps1`.
5. A one-time installer for `core.hooksPath` in `scripts/install_git_hooks.ps1`.

The quality gate runs existing deterministic tooling instead of inventing a parallel stack:

- `ruff check`
- `black --check`
- `AITuber/run_tests.ps1 -FailFast`

The changed-files mode is the default local path. Full validation remains available as a task.

## Consequences

Positive:

- GitHub Copilot users get a repeatable startup and validation path.
- The harness is versioned in the repository and reviewable.
- Quality enforcement reuses existing project tooling instead of adding a new dependency chain.
- The setup works on Windows-first developer machines with PowerShell.

Negative:

- This is weaker than Claude-style lifecycle hooks because checks run at task and commit boundaries rather than after every edit.
- The pre-commit hook depends on PowerShell availability.
- The harness currently targets Python-side quality gates; Unity C# compile validation still depends on existing Unity workflows and manual execution.

## References

- Root `AGENTS.md`
- `.github/copilot-instructions.md`
- `.vscode/tasks.json`
- `scripts/copilot_quality_gate.ps1`
- `scripts/copilot_startup.ps1`
- `scripts/install_git_hooks.ps1`