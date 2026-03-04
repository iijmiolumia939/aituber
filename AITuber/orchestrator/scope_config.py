"""scope_config: Growth scope configuration for the Phase 2 code-generation pipeline.

Defines which proposal types the LLM is allowed to generate at each phase of the
autonomous growth system (Phase 2a → 2e).  The scope is loaded from
``Assets/StreamingAssets/growth_scope.yml`` at runtime and can be overridden via
the ``--scope`` CLI flag.

SRS refs: FR-SCOPE-01, autonomous-growth.md Phase 2.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path

import yaml

logger = logging.getLogger(__name__)


# ── Scope enum ─────────────────────────────────────────────────────────────


class GrowthScope(Enum):
    """Ordered expansion of what the LLM is allowed to generate.

    The numeric values encode the ordering:
    YAML_ONLY < WS_PROTOCOL < ANIMATOR < ACTION_DISPATCHER < FULL_CS

    FR-SCOPE-01
    """

    YAML_ONLY = 1           # Phase 2a: behavior_policy.yml entries only
    WS_PROTOCOL = 2         # Phase 2b: avatar_intent WS command definitions
    ANIMATOR = 3            # Phase 2c: AnimatorController parameter additions
    ACTION_DISPATCHER = 4   # Phase 2d: ActionDispatcher.cs new intent handlers
    FULL_CS = 5             # Phase 2e: arbitrary new C# files


# ── Proposal-type → minimum required scope ────────────────────────────────

_PROPOSAL_TYPE_MIN_SCOPE: dict[str, GrowthScope] = {
    "behavior_policy_entry": GrowthScope.YAML_ONLY,
    "ws_intent_definition": GrowthScope.WS_PROTOCOL,
    "animator_parameter": GrowthScope.ANIMATOR,
    "action_dispatcher_intent": GrowthScope.ACTION_DISPATCHER,
    "csharp_script": GrowthScope.FULL_CS,
}


# ── ScopeConfig dataclass ─────────────────────────────────────────────────


@dataclass
class ScopeConfig:
    """Runtime configuration for the Growth Loop's generation scope.

    Attributes
    ----------
    scope:
        Current phase scope. Determines which proposal types are allowed.
    max_proposals_per_run:
        Hard ceiling on the number of proposals produced per loop execution.
    max_diff_lines:
        Estimated maximum number of lines that all proposals combined may add
        (used by LLMModuloValidator diff_size_gate).

    FR-SCOPE-01
    """

    scope: GrowthScope = GrowthScope.YAML_ONLY
    max_proposals_per_run: int = 5
    max_diff_lines: int = 200
    # Additional allowed files can be listed explicitly; empty means no override.
    allowed_files: list[str] = field(default_factory=list)

    # ── Scope queries ──────────────────────────────────────────────────────

    def allows_proposal_type(self, proposal_type: str) -> bool:
        """Return True if *proposal_type* is permitted in the current scope.

        Unknown proposal types are rejected.
        """
        min_scope = _PROPOSAL_TYPE_MIN_SCOPE.get(proposal_type)
        if min_scope is None:
            return False
        return self.scope.value >= min_scope.value

    def allowed_proposal_types(self) -> list[str]:
        """Return all proposal type names permitted at the current scope level."""
        return [
            ptype
            for ptype, min_scope in _PROPOSAL_TYPE_MIN_SCOPE.items()
            if self.scope.value >= min_scope.value
        ]

    def at_least(self, required: GrowthScope) -> bool:
        """Return True if the current scope is at or above *required*."""
        return self.scope.value >= required.value

    # ── Serialisation ─────────────────────────────────────────────────────

    @classmethod
    def from_yaml(cls, path: str) -> ScopeConfig:
        """Load a ScopeConfig from a YAML file.

        Missing keys use the dataclass defaults.  Unknown keys are ignored.
        The ``scope`` key must match a ``GrowthScope`` member name.
        """
        p = Path(path)
        if not p.exists():
            logger.warning("ScopeConfig: file not found '%s', using defaults.", path)
            return cls()
        raw = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
        scope_str = raw.get("scope", GrowthScope.YAML_ONLY.value)
        # Accept both the enum name ("yaml_only") and its value (1)
        try:
            scope = (
                GrowthScope[scope_str.upper()]
                if isinstance(scope_str, str)
                else GrowthScope(scope_str)
            )
        except (KeyError, ValueError):
            logger.warning(
                "ScopeConfig: unknown scope '%s', defaulting to yaml_only.", scope_str
            )
            scope = GrowthScope.YAML_ONLY
        return cls(
            scope=scope,
            max_proposals_per_run=int(raw.get("max_proposals_per_run", 5)),
            max_diff_lines=int(raw.get("max_diff_lines", 200)),
            allowed_files=list(raw.get("allowed_files", [])),
        )

    def to_yaml(self, path: str) -> None:
        """Persist this ScopeConfig to *path* as YAML."""
        data: dict = {
            "scope": self.scope.name.lower(),
            "max_proposals_per_run": self.max_proposals_per_run,
            "max_diff_lines": self.max_diff_lines,
        }
        if self.allowed_files:
            data["allowed_files"] = self.allowed_files
        Path(path).write_text(
            yaml.dump(data, allow_unicode=True, sort_keys=False),
            encoding="utf-8",
        )
        logger.info("ScopeConfig saved to '%s'.", path)
