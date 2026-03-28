---
description: 'Triage AI review findings: classify severity, drop low-value issues, enforce changed-scope, and emit stable directives.'
---
Triage the current review findings for this repository.

Inputs:
- The current diff or PR scope
- Findings from one or more reviewers
- Optional findings or directives from the previous iteration

Rules:
- Keep only issues that are in the changed scope, unless the diff clearly exposes a production blocker in adjacent code
- Discard low-value edge cases, speculative regressions, and style-only comments
- Classify surviving items as `CRITICAL`, `IMPORTANT`, or `LOW`
- Drop all `LOW` findings from the fix queue
- Detect oscillation when the current findings would revert a previous accepted direction
- If oscillation is detected, compare both approaches and emit a single directive that the fix step must follow

Output exactly these sections:

## Must Fix This Iteration
List only `CRITICAL` and `IMPORTANT` findings that survive triage.

For each finding include:
- Title
- Severity
- Why it is in scope
- Root cause hypothesis
- Concrete fix target

## Discarded Findings
List dropped findings with a one-line reason.

## Oscillation Watch
State `none` or describe the A -> B -> A pattern and which direction is now fixed.

## Directives For Fix Step
Write short mandatory directives. These should be stable and reusable in the next iteration.

## Stop Decision
Return `STOP` only if `Must Fix This Iteration` is empty. Otherwise return `CONTINUE`.