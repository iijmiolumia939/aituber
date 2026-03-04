"""Tests for orchestrator/llm_modulo_validator.py — TC-M8-07 to TC-M8-15.

SRS refs: FR-SCOPE-02.
"""
from __future__ import annotations

from orchestrator.llm_modulo_validator import LLMModuloReport, LLMModuloValidator
from orchestrator.scope_config import GrowthScope, ScopeConfig

# ── Fixtures / helpers ────────────────────────────────────────────────────

_VALID_BEHAVIOR = {
    "intent": "dance_move",
    "cmd": "avatar_update",
    "gesture": "wave",
    "priority": 0,
    "notes": "test entry",
}

_VALID_WS_INTENT = {
    "proposal_type": "ws_intent_definition",
    "intent": "point_at_screen",
    "ws_cmd": "avatar_intent",
    "notes": "Phase 2b test",
}


def _make_validator(scope: GrowthScope = GrowthScope.YAML_ONLY) -> LLMModuloValidator:
    return LLMModuloValidator(ScopeConfig(scope=scope))


# ── TC-M8-07: scope_gate PASS for behavior_policy_entry ───────────────────


class TestScopeGate:
    """TC-M8-07 / TC-M8-08 / TC-M8-09: scope gate allows/rejects by scope level."""

    def test_behavior_policy_passes_in_yaml_only(self) -> None:
        _, report = _make_validator(GrowthScope.YAML_ONLY).validate([_VALID_BEHAVIOR])
        assert report.n_passed == 1
        assert report.n_failed == 0

    def test_ws_intent_fails_in_yaml_only(self) -> None:
        """TC-M8-08: ws_intent_definition is rejected when scope=yaml_only."""
        passed, report = _make_validator(GrowthScope.YAML_ONLY).validate([_VALID_WS_INTENT])
        assert report.n_failed == 1
        assert len(passed) == 0
        assert any(r.gate_name == "scope_gate" for r in report.gate_results)

    def test_ws_intent_passes_in_ws_protocol(self) -> None:
        """TC-M8-09: ws_intent_definition is accepted when scope=ws_protocol."""
        passed, report = _make_validator(GrowthScope.WS_PROTOCOL).validate([_VALID_WS_INTENT])
        assert report.n_passed == 1
        assert report.n_failed == 0
        assert len(passed) == 1


# ── TC-M8-10: safety_gate ─────────────────────────────────────────────────


class TestSafetyGate:
    """TC-M8-10: proposals containing blocked words are rejected at safety_gate."""

    def test_blocked_word_rm_rf_fails(self) -> None:
        malicious = {
            "intent": "bad_intent",
            "cmd": "avatar_update",
            "gesture": "nod",
            "notes": "rm -rf /",
        }
        passed, report = _make_validator().validate([malicious])
        assert report.n_failed == 1
        assert len(passed) == 0
        assert any(r.gate_name == "safety_gate" for r in report.gate_results)

    def test_blocked_word_exec_fails(self) -> None:
        malicious = {
            "intent": "exec_intent",
            "cmd": "avatar_update",
            "gesture": "nod",
            "notes": "exec shell command",
        }
        passed, report = _make_validator().validate([malicious])
        assert report.n_failed == 1


# ── TC-M8-11 / TC-M8-12: diff_size_gate ───────────────────────────────────


class TestDiffSizeGate:
    """TC-M8-11 / TC-M8-12: diff-size gate rejects when cumulative lines exceed limit."""

    def test_too_many_proposals_triggers_diff_gate(self) -> None:
        """TC-M8-11: 41 behavior_policy_entry proposals × 5 lines = 205 > 200."""
        cfg = ScopeConfig(max_diff_lines=200)
        proposals = [
            {
                "intent": f"intent_{i}",
                "cmd": "avatar_update",
                "gesture": "nod",
            }
            for i in range(41)  # 41 × 5 = 205 lines
        ]
        passed, report = LLMModuloValidator(cfg).validate(proposals)
        # First 40 should pass (40 × 5 = 200), 41st should fail diff_size_gate
        assert report.n_passed == 40
        assert report.n_failed == 1
        assert any(r.gate_name == "diff_size_gate" for r in report.gate_results)

    def test_exact_limit_passes(self) -> None:
        """TC-M8-12: 40 proposals × 5 lines = 200 = limit → all pass."""
        cfg = ScopeConfig(max_diff_lines=200)
        proposals = [
            {
                "intent": f"intent_{i}",
                "cmd": "avatar_update",
                "gesture": "nod",
            }
            for i in range(40)
        ]
        passed, report = LLMModuloValidator(cfg).validate(proposals)
        assert report.n_passed == 40
        assert report.n_failed == 0


# ── TC-M8-13: mixed valid/invalid ─────────────────────────────────────────


class TestMixed:
    """TC-M8-13: a mix of valid and invalid proposals produces correct counts."""

    def test_one_valid_one_invalid(self) -> None:
        invalid = {
            "intent": "bad",
            "cmd": "avatar_update",
            "gesture": "nod",
            "notes": "exec shell",  # safety failure
        }
        passed, report = _make_validator().validate([_VALID_BEHAVIOR, invalid])
        assert report.n_validated == 2
        assert report.n_passed == 1
        assert report.n_failed == 1


# ── TC-M8-14: empty proposals ─────────────────────────────────────────────


class TestEmptyProposals:
    """TC-M8-14: empty input produces a zero-count report."""

    def test_empty_list(self) -> None:
        passed, report = _make_validator().validate([])
        assert report.n_validated == 0
        assert report.n_passed == 0
        assert report.n_failed == 0
        assert passed == []


# ── TC-M8-15: LLMModuloReport equality ────────────────────────────────────


class TestReport:
    """TC-M8-15: LLMModuloReport is a proper dataclass with equality."""

    def test_report_equality(self) -> None:
        r1 = LLMModuloReport(n_validated=2, n_passed=1, n_failed=1)
        r2 = LLMModuloReport(n_validated=2, n_passed=1, n_failed=1)
        assert r1 == r2

    def test_report_zero(self) -> None:
        r = LLMModuloReport(n_validated=0, n_passed=0, n_failed=0)
        assert r.n_validated == 0
        assert r.gate_results == []
