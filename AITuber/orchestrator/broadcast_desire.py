"""Broadcast Desire Evaluator — decides if YUI.A wants to stream today.

FR-BCAST-01: Evaluates internal state to produce a desire score [0.0, 1.0].
Issue: #17 E-7. OBS Autonomous Broadcast Lifecycle.

References:
  Park et al. (2023), Generative Agents, arXiv:2304.03442 §3 "Planning"
  Durante et al. (2024), Agent AI, arXiv:2401.03568 §3 "Intentions"
"""

from __future__ import annotations

from dataclasses import dataclass

# Thresholds for desire components
_HIGH_ENERGY_THRESHOLD = 0.7      # energy level that substantially boosts desire
_MIN_CONTENT_FOR_DESIRE = 2       # number of new episode/narrative items before wanting to share
_RECENCY_DECAY_HOURS = 24.0       # hours since last broadcast after which desire resets to max
_HIGH_DESIRE_THRESHOLD = 0.8      # desire_score above which broadcast is considered
_MIN_DESIRE_THRESHOLD = 0.3       # below this score, YUI.A definitely does not want to broadcast


@dataclass
class DesireState:
    """Snapshot of the inputs used to compute broadcast desire.

    FR-BCAST-01.
    """

    energy: float          # 0.0 (exhausted) – 1.0 (fully energised)
    content_count: int     # new episodes / action-plan items ready to share
    hours_since_last: float  # hours since last broadcast (0 = just ended)
    desire_score: float    # computed output

    @property
    def should_broadcast(self) -> bool:
        return self.desire_score >= _HIGH_DESIRE_THRESHOLD


class BroadcastDesireEvaluator:
    """Compute YUI.A's autonomous intent to start a broadcast.

    FR-BCAST-01: Based on energy level, accumulated content, and time since
    last broadcast.  Rule-based MVP — can be upgraded to an LLM/RL scorer.
    """

    def evaluate(
        self,
        energy: float = 0.5,
        content_count: int = 0,
        hours_since_last: float = 0.0,
    ) -> DesireState:
        """Compute desire score.

        Args:
            energy: current avatar energy [0.0, 1.0].
            content_count: number of new episodes or narrative items to share.
            hours_since_last: hours elapsed since the last broadcast.

        Returns:
            DesireState with computed desire_score.
        """
        energy = max(0.0, min(1.0, float(energy)))

        # Component 1: Energy boost
        energy_component = energy * 0.4  # max 0.4 contribution

        # Component 2: Content availability
        content_ratio = min(1.0, content_count / max(1, _MIN_CONTENT_FOR_DESIRE))
        content_component = content_ratio * 0.3  # max 0.3

        # Component 3: Recency (the longer since last broadcast, the more desire)
        recency_ratio = min(1.0, hours_since_last / _RECENCY_DECAY_HOURS)
        recency_component = recency_ratio * 0.3  # max 0.3

        score = round(energy_component + content_component + recency_component, 4)
        score = max(0.0, min(1.0, score))

        return DesireState(
            energy=energy,
            content_count=content_count,
            hours_since_last=hours_since_last,
            desire_score=score,
        )

    @property
    def high_threshold(self) -> float:
        return _HIGH_DESIRE_THRESHOLD

    @property
    def min_threshold(self) -> float:
        return _MIN_DESIRE_THRESHOLD
