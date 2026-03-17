"""RuleEngine: reflex-action rules for game streaming (<50 ms latency).

Evaluates game_state and returns an immediate action_cmd without invoking the LLM.
Used by GameLoop for FR-GAME-02 reflex layer.

SRS refs: FR-GAME-02.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)


# ── Data types ─────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class GameAction:
    """A single action command sent to the game via GameBridge.

    type:  command name (e.g. "move", "use_item", "attack", "chat")
    args:  free-form payload forwarded to the game module as-is
    source: "reflex" | "strategy" — who generated this action
    """

    type: str
    args: dict[str, Any]
    source: str = "reflex"

    def to_dict(self) -> dict[str, Any]:
        return {"type": self.type, "args": self.args, "source": self.source}


# ── Rule helpers ──────────────────────────────────────────────────────────────


def _health(state: dict[str, Any]) -> float:
    """Return normalised health in [0.0, 1.0]. Defaults to 1.0 (safe)."""
    hp = state.get("health")
    max_hp = state.get("max_health") or 20.0
    if hp is None:
        return 1.0
    return max(0.0, min(1.0, float(hp) / float(max_hp)))


def _nearby_hostile(state: dict[str, Any]) -> bool:
    """True if any hostile entity is within aggro range."""
    entities = state.get("nearby_entities") or []
    return any(
        e.get("type") == "hostile" and float(e.get("distance", 999)) < 8.0
        for e in entities
        if isinstance(e, dict)
    )


def _has_item(state: dict[str, Any], item_name: str) -> bool:
    inventory = state.get("inventory") or []
    return any(isinstance(i, dict) and i.get("name") == item_name for i in inventory)


# ── Rule definitions ──────────────────────────────────────────────────────────


class RuleEngine:
    """Pure-function reflex engine.

    evaluate() is synchronous and must return within a few microseconds.
    No LLM calls, no I/O.

    FR-GAME-02: reflex actions (<50 ms) are handled here;
    strategy decisions (1-3 seconds) go to the LLM via game_loop.py.
    """

    # Thresholds
    LOW_HEALTH_THRESHOLD: float = 0.30  # 30% HP
    CRITICAL_HEALTH_THRESHOLD: float = 0.15  # 15% HP — flee even without potion

    def evaluate(self, state: dict[str, Any]) -> GameAction | None:
        """Return a reflex GameAction, or None if no rule fires.

        Rules are evaluated in priority order; first match wins.
        """
        try:
            return self._evaluate(state)
        except Exception:
            # Rules must never crash the main loop
            logger.exception("[RuleEngine] Unexpected error during evaluate()")
            return None

    def _evaluate(self, state: dict[str, Any]) -> GameAction | None:
        hp = _health(state)
        hostile = _nearby_hostile(state)

        # Rule 1: Critical health + nearby hostile → flee immediately
        if hp <= self.CRITICAL_HEALTH_THRESHOLD and hostile:
            logger.debug("[RuleEngine] Rule 1 fired: critical HP + hostile → flee")
            return GameAction(
                type="move",
                args={"direction": "away_from_threat", "sprint": True},
                source="reflex",
            )

        # Rule 2: Low health + has potion → use healing item
        if hp <= self.LOW_HEALTH_THRESHOLD and _has_item(state, "potion"):
            logger.debug("[RuleEngine] Rule 2 fired: low HP + has potion → use_item")
            return GameAction(
                type="use_item",
                args={"item": "potion"},
                source="reflex",
            )

        # Rule 3: Hostile nearby + normal health → equip sword and attack
        if hostile and hp > self.LOW_HEALTH_THRESHOLD:
            logger.debug("[RuleEngine] Rule 3 fired: hostile nearby → attack")
            return GameAction(
                type="attack",
                args={"target": "nearest_hostile"},
                source="reflex",
            )

        return None
