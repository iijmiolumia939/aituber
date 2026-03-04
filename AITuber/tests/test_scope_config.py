"""Tests for orchestrator/scope_config.py — TC-M8-01 to TC-M8-06.

SRS refs: FR-SCOPE-01.
"""

from __future__ import annotations

from orchestrator.scope_config import GrowthScope, ScopeConfig

# ── TC-M8-01: Defaults ─────────────────────────────────────────────────────


class TestScopeConfigDefaults:
    """TC-M8-01: ScopeConfig() uses sensible, well-defined defaults."""

    def test_default_scope_is_yaml_only(self) -> None:
        cfg = ScopeConfig()
        assert cfg.scope == GrowthScope.YAML_ONLY

    def test_default_max_proposals_is_5(self) -> None:
        cfg = ScopeConfig()
        assert cfg.max_proposals_per_run == 5

    def test_default_max_diff_lines_is_200(self) -> None:
        cfg = ScopeConfig()
        assert cfg.max_diff_lines == 200

    def test_default_allowed_files_is_empty(self) -> None:
        cfg = ScopeConfig()
        assert cfg.allowed_files == []


# ── TC-M8-02: YAML round-trip ──────────────────────────────────────────────


class TestScopeConfigYaml:
    """TC-M8-02: from_yaml / to_yaml round-trip preserves all fields."""

    def test_round_trip_yaml_only(self, tmp_path) -> None:
        path = str(tmp_path / "scope.yml")
        original = ScopeConfig(
            scope=GrowthScope.YAML_ONLY,
            max_proposals_per_run=3,
            max_diff_lines=100,
        )
        original.to_yaml(path)
        loaded = ScopeConfig.from_yaml(path)
        assert loaded.scope == GrowthScope.YAML_ONLY
        assert loaded.max_proposals_per_run == 3
        assert loaded.max_diff_lines == 100

    def test_round_trip_ws_protocol(self, tmp_path) -> None:
        path = str(tmp_path / "scope.yml")
        original = ScopeConfig(scope=GrowthScope.WS_PROTOCOL)
        original.to_yaml(path)
        loaded = ScopeConfig.from_yaml(path)
        assert loaded.scope == GrowthScope.WS_PROTOCOL

    def test_from_yaml_missing_file_returns_defaults(self, tmp_path) -> None:
        cfg = ScopeConfig.from_yaml(str(tmp_path / "nonexistent.yml"))
        assert cfg.scope == GrowthScope.YAML_ONLY
        assert cfg.max_proposals_per_run == 5

    def test_from_yaml_unknown_scope_falls_back_to_yaml_only(self, tmp_path) -> None:
        p = tmp_path / "bad.yml"
        p.write_text("scope: totally_unknown\n", encoding="utf-8")
        cfg = ScopeConfig.from_yaml(str(p))
        assert cfg.scope == GrowthScope.YAML_ONLY


# ── TC-M8-03: Scope ordering ───────────────────────────────────────────────


class TestScopeOrdering:
    """TC-M8-03: GrowthScope enum has a strict ordering."""

    def test_yaml_only_is_smallest(self) -> None:
        assert GrowthScope.YAML_ONLY.value < GrowthScope.WS_PROTOCOL.value

    def test_ws_protocol_less_than_animator(self) -> None:
        assert GrowthScope.WS_PROTOCOL.value < GrowthScope.ANIMATOR.value

    def test_animator_less_than_action_dispatcher(self) -> None:
        assert GrowthScope.ANIMATOR.value < GrowthScope.ACTION_DISPATCHER.value

    def test_action_dispatcher_less_than_full_cs(self) -> None:
        assert GrowthScope.ACTION_DISPATCHER.value < GrowthScope.FULL_CS.value

    def test_at_least_same_scope(self) -> None:
        cfg = ScopeConfig(scope=GrowthScope.WS_PROTOCOL)
        assert cfg.at_least(GrowthScope.YAML_ONLY)
        assert cfg.at_least(GrowthScope.WS_PROTOCOL)
        assert not cfg.at_least(GrowthScope.ANIMATOR)


# ── TC-M8-04 / TC-M8-05: allowed_proposal_types ────────────────────────────


class TestAllowedProposalTypes:
    """TC-M8-04 / TC-M8-05: each scope permits the right proposal types."""

    def test_yaml_only_allows_behavior_policy_entry(self) -> None:
        cfg = ScopeConfig(scope=GrowthScope.YAML_ONLY)
        assert "behavior_policy_entry" in cfg.allowed_proposal_types()

    def test_yaml_only_does_not_allow_ws_intent_definition(self) -> None:
        cfg = ScopeConfig(scope=GrowthScope.YAML_ONLY)
        assert "ws_intent_definition" not in cfg.allowed_proposal_types()

    def test_ws_protocol_allows_both(self) -> None:
        cfg = ScopeConfig(scope=GrowthScope.WS_PROTOCOL)
        types = cfg.allowed_proposal_types()
        assert "behavior_policy_entry" in types
        assert "ws_intent_definition" in types

    def test_full_cs_allows_all_types(self) -> None:
        cfg = ScopeConfig(scope=GrowthScope.FULL_CS)
        types = cfg.allowed_proposal_types()
        for ptype in (
            "behavior_policy_entry",
            "ws_intent_definition",
            "animator_parameter",
            "action_dispatcher_intent",
            "csharp_script",
        ):
            assert ptype in types, f"{ptype} should be allowed at full_cs scope"


# ── TC-M8-06: allows_proposal_type ────────────────────────────────────────


class TestAllowsProposalType:
    """TC-M8-06: unknown proposal types are rejected."""

    def test_unknown_type_returns_false(self) -> None:
        cfg = ScopeConfig()
        assert cfg.allows_proposal_type("totally_unknown_type") is False

    def test_known_type_returns_true_at_right_scope(self) -> None:
        cfg = ScopeConfig(scope=GrowthScope.WS_PROTOCOL)
        assert cfg.allows_proposal_type("ws_intent_definition") is True

    def test_known_type_returns_false_at_too_low_scope(self) -> None:
        cfg = ScopeConfig(scope=GrowthScope.YAML_ONLY)
        assert cfg.allows_proposal_type("ws_intent_definition") is False
