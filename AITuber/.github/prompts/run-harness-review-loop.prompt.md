---
description: 'Run the harness review loop on the current diff: read the review packet, run scoped reviewers, triage findings, validate fixes, and report merge blockers.'
---
Run the harness review loop for the current diff in this repository.

Workflow:
1. Read `copilot-temp/review-packet.md`. If it is missing or stale, tell the user to run `Task: Harness: Review Packet` first.
2. Use the recommended reviewers from the packet, not every reviewer by default.
3. Produce findings focused on bugs, regressions, reliability risks, missing tests, and requirement mismatches.
4. Immediately triage those findings using the rules from `.github/prompts/triage-review-findings.prompt.md`.
5. If the triage result is `STOP`, say there are no must-fix items.
6. If must-fix items remain, list only those items and the directives for the fix step.
7. After fixes are applied, validate them using `.github/prompts/validate-review-fixes.prompt.md`.
8. Persist the result by overwriting `copilot-temp/review-loop-latest.md` and appending one JSON object line to `copilot-temp/review-loop-history.jsonl`.

Persistence format:
- `copilot-temp/review-loop-latest.md`: markdown report with the same final sections you return to the user
- `copilot-temp/review-loop-history.jsonl`: append one compact JSON object with these keys:
	- `timestampUtc`
	- `mergeStatus`
	- `mustFixCount`
	- `mustFixTitles`
	- `directives`
	- `requiredValidations`
	- `recommendedReviewers`
	- `changedFiles`
	- `packetPath`
	- `latestReportPath`
	- `historyPath`

Persistence rules:
- Create the files if they do not exist
- Keep JSONL machine-readable: one single-line JSON object per iteration
- Do not store speculative notes outside the defined fields
- If the packet says Unity validation is required, include that requirement in `requiredValidations`

Output sections:

## Review Scope
Summarize the packet: changed files, recommended reviewers, and required validations.

## Must Fix
List only must-fix findings after triage.

## Directives
List mandatory directives for the fix step.

## Validation Plan
List the exact checks that must pass after the fix.

## Merge Status
Return `READY`, `FIX_REQUIRED`, or `BLOCKED`.