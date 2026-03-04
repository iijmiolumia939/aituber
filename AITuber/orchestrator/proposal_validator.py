"""ProposalValidator: schema + safety validation for LLM-generated BehaviorPolicy proposals.

LLM-Modulo pattern: LLM generates YAML proposals; this validator certifies each
entry before PolicyUpdater writes it to behavior_policy.yml.

Supports two proposal_type values (Phase 2a / 2b):
  - "behavior_policy_entry" (default): intent + cmd + action fields
  - "ws_intent_definition" (Phase 2b): intent + ws_cmd fields

SRS refs: FR-REFL-03, FR-SCOPE-02.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from enum import Enum

logger = logging.getLogger(__name__)


# ── Result types ───────────────────────────────────────────────────────────


class ValidationStatus(Enum):
    """Outcome of a ProposalValidator.validate() call."""

    VALID = "valid"
    INVALID = "invalid"
    DUPLICATE = "duplicate"


@dataclass
class ValidationResult:
    """Structured result returned by ProposalValidator.validate()."""

    status: ValidationStatus
    reason: str = ""

    def __bool__(self) -> bool:
        return self.status == ValidationStatus.VALID


# ── ProposalValidator ──────────────────────────────────────────────────────

# Words that must not appear in any string field value (safety gate).
_BLOCKED_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"\brm\b", re.IGNORECASE),
    re.compile(r"\bexec\b", re.IGNORECASE),
    re.compile(r"\bshutdown\b", re.IGNORECASE),
    re.compile(r"\bdelete_all\b", re.IGNORECASE),
    re.compile(r"rm\s+-rf", re.IGNORECASE),
    re.compile(r";\s*drop\b", re.IGNORECASE),
]

# Valid intent name pattern: lowercase letters, digits, underscores only.
_INTENT_RE = re.compile(r"^[a-z][a-z0-9_]*$")

# Fields that count as "action payload" — at least one must be present.
_ACTION_FIELDS = frozenset({"gesture", "emotion", "look_target", "event"})


# Valid ws_cmd values for ws_intent_definition proposals.
_WS_CMD_ALLOWLIST: frozenset[str] = frozenset({"avatar_intent", "avatar_update"})


class ProposalValidator:
    """Validate a single BehaviorPolicy entry dict produced by ReflectionRunner.

    FR-REFL-03, FR-SCOPE-02
    Checks (in order):
      1. Required fields (intent, cmd) — for behavior_policy_entry
         Required fields (intent, ws_cmd) — for ws_intent_definition
      2. intent naming convention (snake_case, no special chars)
      3. cmd / ws_cmd allowlist
      4. At least one action-payload field present (behavior_policy_entry only)
      5. Safety: no blocked words in any string field
      6. Duplicate check against existing policy intents

    Args:
        existing_policy: List of existing BehaviorPolicy entry dicts.
                         Used exclusively for duplicate-intent detection.
    """

    ALLOWED_CMDS: frozenset[str] = frozenset({"avatar_update", "avatar_event"})

    def __init__(self, existing_policy: list[dict] | None = None) -> None:
        self._existing_intents: frozenset[str] = frozenset(
            e.get("intent", "") for e in (existing_policy or []) if e.get("intent")
        )

    # ── Public API ─────────────────────────────────────────────────────────

    def validate(self, entry: dict) -> ValidationResult:
        """Validate *entry* and return a ValidationResult.

        FR-REFL-03  Never raises; returns INVALID with a human-readable reason.
        """
        # 1. Required field: intent
        intent = entry.get("intent")
        if not intent or not isinstance(intent, str) or not intent.strip():
            return ValidationResult(
                ValidationStatus.INVALID, reason="missing or empty 'intent' field"
            )

        # 2. intent naming convention
        if not _INTENT_RE.match(intent):
            return ValidationResult(
                ValidationStatus.INVALID,
                reason=(
                    f"intent '{intent}' must match ^[a-z][a-z0-9_]*$"
                    " (no spaces or special chars)"
                ),
            )

        proposal_type = entry.get("proposal_type", "behavior_policy_entry")
        if proposal_type == "ws_intent_definition":
            return self._validate_ws_intent(entry, intent)
        return self._validate_behavior_policy(entry, intent)

    # ── Type-specific validation ────────────────────────────────────────────

    def _validate_behavior_policy(self, entry: dict, intent: str) -> ValidationResult:
        """Validate a behavior_policy_entry proposal."""
        # 3. Required field: cmd
        cmd = entry.get("cmd")
        if not cmd or not isinstance(cmd, str):
            return ValidationResult(ValidationStatus.INVALID, reason="missing 'cmd' field")

        # 4. cmd allowlist
        if cmd not in self.ALLOWED_CMDS:
            return ValidationResult(
                ValidationStatus.INVALID,
                reason=f"cmd '{cmd}' not in allowed set {sorted(self.ALLOWED_CMDS)}",
            )

        # 5. At least one action-payload field
        if not any(entry.get(f) for f in _ACTION_FIELDS):
            return ValidationResult(
                ValidationStatus.INVALID,
                reason=f"entry must have at least one of {sorted(_ACTION_FIELDS)}",
            )

        # 6. Safety check on all string field values
        safety_result = self._check_safety(entry)
        if safety_result is not None:
            return safety_result

        # 7. Duplicate intent
        if intent in self._existing_intents:
            return ValidationResult(
                ValidationStatus.DUPLICATE,
                reason=f"intent '{intent}' already exists in policy",
            )

        return ValidationResult(ValidationStatus.VALID)

    def _validate_ws_intent(self, entry: dict, intent: str) -> ValidationResult:
        """Validate a ws_intent_definition proposal (Phase 2b).

        Required fields: intent (already checked), ws_cmd.
        ws_cmd must be in _WS_CMD_ALLOWLIST.
        FR-SCOPE-02
        """
        ws_cmd = entry.get("ws_cmd")
        if not ws_cmd or not isinstance(ws_cmd, str):
            return ValidationResult(
                ValidationStatus.INVALID, reason="missing 'ws_cmd' field for ws_intent_definition"
            )
        if ws_cmd not in _WS_CMD_ALLOWLIST:
            return ValidationResult(
                ValidationStatus.INVALID,
                reason=f"ws_cmd '{ws_cmd}' not in allowed set {sorted(_WS_CMD_ALLOWLIST)}",
            )
        safety_result = self._check_safety(entry)
        if safety_result is not None:
            return safety_result
        if intent in self._existing_intents:
            return ValidationResult(
                ValidationStatus.DUPLICATE,
                reason=f"intent '{intent}' already exists in policy",
            )
        return ValidationResult(ValidationStatus.VALID)

    # ── Internal helpers ───────────────────────────────────────────────────

    def _check_safety(self, entry: dict) -> ValidationResult | None:
        """Scan all string values in *entry* for blocked patterns.

        Returns ValidationResult(INVALID) on first match, else None.
        """
        for key, value in entry.items():
            if not isinstance(value, str):
                continue
            for pattern in _BLOCKED_PATTERNS:
                if pattern.search(value):
                    return ValidationResult(
                        ValidationStatus.INVALID,
                        reason=f"blocked pattern '{pattern.pattern}' found in field '{key}'",
                    )
        return None
