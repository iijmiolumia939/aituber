---
description: 'Validate AI-applied fixes: confirm root-cause coverage, reject band-aid patches, and check directive compliance.'
---
Validate the latest fixes for this repository.

Inputs:
- The current diff after fixes
- The triaged findings from the previous step
- The directives emitted for the fix step

Checks:
- Did the change address the root cause rather than only the symptom?
- Did the fix introduce a new regression or hidden complexity?
- Did the implementation follow the directives exactly?
- Are tests or validation steps still missing?
- Is there any remaining blocker before merge?

Output exactly these sections:

## Root Cause Coverage
For each must-fix item, say `fixed`, `partially fixed`, or `not fixed` with a short reason.

## Band-Aid Risks
List any symptom-only fixes, overfitting, or workaround logic.

## Regression Risks
List concrete regressions or coupling risks introduced by the fix.

## Directive Compliance
State whether the fix followed each directive. If not, explain the deviation.

## Validation Gaps
List missing tests, missing Unity verification, or missing quality-gate steps.

## Merge Gate
Return `PASS` only if all must-fix items are fully fixed and no blocker remains. Otherwise return `FAIL`.