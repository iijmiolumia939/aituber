# ADR 0001: GitHub Copilot Harness Baseline

- Status: Accepted
- Date: 2026-03-14

## Context

The repository already has strong product-level assets: AGENTS pointers, Copilot instructions, CI, Python linting, and batch-safe tests. What it lacked was a consistent local harness for GitHub Copilot sessions and a repeatable review loop that can converge without human ad hoc triage.

The article on harness engineering recommends tool lifecycle hooks, completion gates, ADRs, and standardized startup routines. GitHub Copilot in VS Code does not expose Claude-style PreToolUse and PostToolUse hooks, so that exact design is not portable here.

Without a Copilot-specific baseline, quality checks depend on memory and manual discipline. That creates drift across sessions and makes local feedback slower than necessary. It also leaves review findings untriaged, which increases over-fixing and oscillation risk.

## Decision

We standardize on a GitHub Copilot-friendly harness with these tracked components:

1. A workspace task-based entrypoint in `.vscode/tasks.json`.
2. A tracked pre-commit hook in `.githooks/pre-commit`.
3. A repository-owned quality gate script in `scripts/copilot_quality_gate.ps1`.
4. A repository-owned startup routine in `scripts/copilot_startup.ps1`.
5. A one-time installer for `core.hooksPath` in `scripts/install_git_hooks.ps1`.
6. A repository-owned review packet generator in `scripts/copilot_review_packet.ps1`.
7. Prompt-based triage and validation steps in `AITuber/.github/prompts/`.
8. A repository-owned pre-commit orchestrator in `scripts/copilot_pre_commit.ps1`.
9. A repository-owned Unity validation marker in `copilot-temp/unity-validation.json`, refreshed via `scripts/copilot_unity_validation.ps1`.

The quality gate runs existing deterministic tooling instead of inventing a parallel stack:

- `ruff check`
- `black --check`
- `AITuber/run_tests.ps1 -FailFast`

The changed-files mode is the default local path. Full validation remains available as a task.

The review loop is explicit:

1. Generate a review packet for the current diff.
2. Run focused domain reviewers.
3. Triage findings into must-fix vs discard, with stable directives.
4. Fix only must-fix items.
5. Validate that fixes address root cause rather than symptoms.
6. Run the quality gate and repeat until must-fix is empty.

pre-commit automation is split intentionally:

- deterministic steps run in git hooks: review packet generation and changed-files quality gate
- Unity C# commit-time enforcement also runs in git hooks, but only through a marker file that confirms manual Unity validation already happened
- non-deterministic AI steps run through prompts and custom agents: scoped review, triage, and validation

The review loop persists its outputs in ignored local files:

- `copilot-temp/review-loop-latest.md`
- `copilot-temp/review-loop-history.jsonl`

## Consequences

Positive:

- GitHub Copilot users get a repeatable startup and validation path.
- GitHub Copilot users get a repeatable review loop with explicit stop conditions.
- The harness is versioned in the repository and reviewable.
- Quality enforcement reuses existing project tooling instead of adding a new dependency chain.
- The setup works on Windows-first developer machines with PowerShell.
- Review triage reduces low-value churn and helps prevent A -> B -> A oscillation across iterations.
- pre-commit automatically refreshes the review packet so the latest scope is always available before commit.
- pre-commit can block stale Unity C# commits without pretending to automate the Unity Editor itself.

Negative:

- This is weaker than Claude-style lifecycle hooks because checks run at task and commit boundaries rather than after every edit.
- The pre-commit hook depends on PowerShell availability.
- Unity C# compile validation still depends on existing Unity workflows and manual execution.
- VS Code Copilot cannot yet orchestrate the entire loop automatically across isolated model roles, so the operator still triggers each step.
- Git hooks cannot reliably execute LLM-based review steps, so prompts and agents remain the interface for triage and validation.
- The Unity marker is only as trustworthy as the operator; it improves enforcement, but it is not proof that the wrong scene or editor state was not used.

## References

- Root `AGENTS.md`
- `.github/copilot-instructions.md`
- `.vscode/tasks.json`
- `scripts/copilot_quality_gate.ps1`
- `scripts/copilot_startup.ps1`
- `scripts/install_git_hooks.ps1`
- `scripts/copilot_review_packet.ps1`
- `scripts/copilot_pre_commit.ps1`
- `scripts/copilot_unity_validation.ps1`
- `AITuber/.github/copilot-review-workflow.md`