"""llm_modulo_validator: 3-gate validator for LLM-generated proposals.

Implements the LLM-Modulo pattern (Kambhampati et al., 2024):
  Gate 1 — scope_gate:      proposal_type is permitted by ScopeConfig
  Gate 2 — safety_gate:     ProposalValidator finds no blocked words / invalid fields
  Gate 3 — diff_size_gate:  total estimated diff lines ≤ ScopeConfig.max_diff_lines

Usage::

    from orchestrator.scope_config import ScopeConfig
    from orchestrator.llm_modulo_validator import LLMModuloValidator

    cfg = ScopeConfig()
    validator = LLMModuloValidator(cfg)
    passed, report = validator.validate(proposals)

SRS refs: FR-SCOPE-02, autonomous-growth.md Phase 2.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from orchestrator.scope_config import ScopeConfig

from orchestrator.proposal_validator import ProposalValidator

logger = logging.getLogger(__name__)

# Estimated diff lines added per proposal by type.
_LINES_PER_PROPOSAL_TYPE: dict[str, int] = {
    "behavior_policy_entry": 5,
    "ws_intent_definition": 10,
    "animator_parameter": 15,
    "action_dispatcher_intent": 30,
    "csharp_script": 100,
}
_DEFAULT_LINES_PER_PROPOSAL = 10  # fallback for unknown types


# ── Result types ───────────────────────────────────────────────────────────


class GateStatus(Enum):
    """Outcome of a single validation gate."""

    PASS = "pass"
    FAIL = "fail"


@dataclass
class GateResult:
    """Result of one gate check on one proposal.

    Attributes
    ----------
    gate_name:  Which gate produced this result ("scope_gate", "safety_gate", etc.)
    status:     PASS or FAIL
    reason:     Human-readable explanation (empty string on PASS)
    proposal_idx: Index of the proposal in the input list (0-based)
    """

    gate_name: str
    status: GateStatus
    reason: str = ""
    proposal_idx: int = 0


@dataclass
class LLMModuloReport:
    """Aggregate report of all gate checks across all proposals.

    Attributes
    ----------
    n_validated:   Total number of proposals submitted.
    n_passed:      Proposals that passed all gates.
    n_failed:      Proposals that failed at least one gate.
    gate_results:  List of all GateResult objects (one per failing check).
    """

    n_validated: int
    n_passed: int
    n_failed: int
    gate_results: list[GateResult] = field(default_factory=list)


# ── LLMModuloValidator ─────────────────────────────────────────────────────


class LLMModuloValidator:
    """Three-gate validator for LLM-generated Growth proposals.

    Gates (applied in order; a proposal fails immediately on first FAIL):
      1. scope_gate     — proposal_type must be permitted by ScopeConfig
      2. safety_gate    — ProposalValidator must not reject the proposal
      3. diff_size_gate — cumulative estimated diff for *all* proposals so far must
                          remain within ScopeConfig.max_diff_lines

    FR-SCOPE-02
    """

    def __init__(self, scope_config: ScopeConfig) -> None:
        self._scope = scope_config
        self._base_validator = ProposalValidator()  # no existing policy; we only need safety

    # ── Public API ─────────────────────────────────────────────────────────

    def validate(self, proposals: list[dict]) -> tuple[list[dict], LLMModuloReport]:
        """Validate *proposals* through all gates.

        Parameters
        ----------
        proposals:
            List of proposal dicts.  Each may optionally contain a
            ``"proposal_type"`` key; omitting it defaults to
            ``"behavior_policy_entry"``.

        Returns
        -------
        passed_proposals:
            Sub-list of proposals that passed all gates.
        report:
            Aggregate LLMModuloReport with per-gate detail.

        FR-SCOPE-02
        """
        if not proposals:
            return [], LLMModuloReport(n_validated=0, n_passed=0, n_failed=0)

        passed: list[dict] = []
        all_gate_results: list[GateResult] = []
        cumulative_diff = 0

        for idx, proposal in enumerate(proposals):
            ptype = proposal.get("proposal_type", "behavior_policy_entry")
            failed_result = self._check_proposal(idx, proposal, ptype, cumulative_diff)

            if failed_result is not None:
                all_gate_results.append(failed_result)
            else:
                passed.append(proposal)
                cumulative_diff += _LINES_PER_PROPOSAL_TYPE.get(ptype, _DEFAULT_LINES_PER_PROPOSAL)

        n_failed = len(proposals) - len(passed)
        return passed, LLMModuloReport(
            n_validated=len(proposals),
            n_passed=len(passed),
            n_failed=n_failed,
            gate_results=all_gate_results,
        )

    # ── Internal gates ─────────────────────────────────────────────────────

    def _check_proposal(
        self, idx: int, proposal: dict, ptype: str, cumulative_diff: int
    ) -> GateResult | None:
        """Run all gates on *proposal*.  Return first failing GateResult or None."""

        # Gate 1: scope_gate
        if not self._scope.allows_proposal_type(ptype):
            return GateResult(
                gate_name="scope_gate",
                status=GateStatus.FAIL,
                reason=(
                    f"proposal_type '{ptype}' is not allowed in scope "
                    f"'{self._scope.scope.name.lower()}'"
                ),
                proposal_idx=idx,
            )

        # Gate 2: safety_gate (reuse ProposalValidator's _check_safety)
        safety = self._base_validator._check_safety(proposal)
        if safety is not None:
            return GateResult(
                gate_name="safety_gate",
                status=GateStatus.FAIL,
                reason=safety.reason,
                proposal_idx=idx,
            )

        # Gate 3: diff_size_gate
        new_lines = _LINES_PER_PROPOSAL_TYPE.get(ptype, _DEFAULT_LINES_PER_PROPOSAL)
        if cumulative_diff + new_lines > self._scope.max_diff_lines:
            return GateResult(
                gate_name="diff_size_gate",
                status=GateStatus.FAIL,
                reason=(
                    f"accepting this proposal would bring cumulative diff to "
                    f"{cumulative_diff + new_lines} lines, "
                    f"exceeding limit of {self._scope.max_diff_lines}"
                ),
                proposal_idx=idx,
            )

        return None  # all gates passed
