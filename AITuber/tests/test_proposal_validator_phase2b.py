"""Tests for ProposalValidator Phase 2b (ws_intent_definition) — TC-M8-16 to TC-M8-20.

SRS refs: FR-REFL-03, FR-SCOPE-02.
"""

from __future__ import annotations

from orchestrator.proposal_validator import ProposalValidator, ValidationStatus

# ── Helpers ────────────────────────────────────────────────────────────────


def _valid_ws_intent(**overrides) -> dict:
    base = {
        "proposal_type": "ws_intent_definition",
        "intent": "point_at_screen",
        "ws_cmd": "avatar_intent",
        "notes": "Phase 2b test entry",
    }
    base.update(overrides)
    return base


def _valid_behavior(**overrides) -> dict:
    base = {
        "intent": "wave_hello",
        "cmd": "avatar_update",
        "gesture": "wave",
        "notes": "behavior policy test",
    }
    base.update(overrides)
    return base


# ── TC-M8-16: valid ws_intent_definition ──────────────────────────────────


class TestWsIntentDefinition:
    """TC-M8-16 to TC-M8-19: ProposalValidator handles ws_intent_definition type."""

    def test_valid_ws_intent_is_valid(self) -> None:
        """TC-M8-16: a well-formed ws_intent_definition proposal passes validation."""
        result = ProposalValidator().validate(_valid_ws_intent())
        assert result.status == ValidationStatus.VALID

    def test_missing_ws_cmd_is_invalid(self) -> None:
        """TC-M8-17: ws_cmd field is required for ws_intent_definition."""
        entry = _valid_ws_intent()
        del entry["ws_cmd"]
        result = ProposalValidator().validate(entry)
        assert result.status == ValidationStatus.INVALID
        assert "ws_cmd" in result.reason

    def test_missing_intent_is_invalid(self) -> None:
        """TC-M8-18: intent field is always required."""
        entry = _valid_ws_intent()
        del entry["intent"]
        result = ProposalValidator().validate(entry)
        assert result.status == ValidationStatus.INVALID

    def test_ws_cmd_not_in_allowlist_is_invalid(self) -> None:
        """TC-M8-19: ws_cmd must be in the allowed set."""
        entry = _valid_ws_intent(ws_cmd="dangerous_cmd")
        result = ProposalValidator().validate(entry)
        assert result.status == ValidationStatus.INVALID
        assert "dangerous_cmd" in result.reason

    def test_ws_intent_with_allowed_avatar_update(self) -> None:
        entry = _valid_ws_intent(ws_cmd="avatar_update")
        result = ProposalValidator().validate(entry)
        assert result.status == ValidationStatus.VALID

    def test_duplicate_ws_intent_is_duplicate(self) -> None:
        existing = [_valid_ws_intent()]
        result = ProposalValidator(existing_policy=existing).validate(_valid_ws_intent())
        assert result.status == ValidationStatus.DUPLICATE

    def test_safety_blocked_in_ws_intent(self) -> None:
        entry = _valid_ws_intent(notes="rm -rf /")
        result = ProposalValidator().validate(entry)
        assert result.status == ValidationStatus.INVALID


# ── TC-M8-20: behavior_policy_entry back-compat ───────────────────────────


class TestBehaviorPolicyBackcompat:
    """TC-M8-20: existing behavior_policy_entry validation is unchanged."""

    def test_no_proposal_type_field_works_as_before(self) -> None:
        result = ProposalValidator().validate(_valid_behavior())
        assert result.status == ValidationStatus.VALID

    def test_explicit_behavior_policy_entry_type_works(self) -> None:
        entry = _valid_behavior(proposal_type="behavior_policy_entry")
        result = ProposalValidator().validate(entry)
        assert result.status == ValidationStatus.VALID

    def test_behavior_policy_still_requires_action_field(self) -> None:
        entry = {"intent": "empty_action", "cmd": "avatar_update"}
        result = ProposalValidator().validate(entry)
        assert result.status == ValidationStatus.INVALID

    def test_behavior_policy_still_rejects_unknown_cmd(self) -> None:
        entry = _valid_behavior(cmd="unknown_cmd")
        result = ProposalValidator().validate(entry)
        assert result.status == ValidationStatus.INVALID
