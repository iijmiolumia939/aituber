"""Tests for RuleEngine (FR-GAME-02).

TC-RULE-01: No reflex returned for safe state
TC-RULE-02: Low health + has potion → use_item
TC-RULE-03: Critical health + hostile nearby → flee (move)
TC-RULE-04: Hostile nearby + healthy → attack
TC-RULE-05: Low health without potion → no rule fires (no item to use)
TC-RULE-06: Multiple hostiles — first hostile evaluation still fires
TC-RULE-07: Exception in state dict is swallowed; returns None
TC-RULE-08: GameAction.to_dict() shape
"""

from __future__ import annotations

import pytest

from orchestrator.rule_engine import GameAction, RuleEngine


@pytest.fixture
def engine() -> RuleEngine:
    return RuleEngine()


# ── State helpers ─────────────────────────────────────────────────────────────


def _state(
    health: float = 20.0,
    max_health: float = 20.0,
    nearby_entities: list | None = None,
    inventory: list | None = None,
) -> dict:
    return {
        "health": health,
        "max_health": max_health,
        "nearby_entities": nearby_entities or [],
        "inventory": inventory or [],
    }


def _hostile(distance: float = 5.0) -> dict:
    return {"type": "hostile", "distance": distance}


def _passive(distance: float = 3.0) -> dict:
    return {"type": "passive", "distance": distance}


def _potion() -> dict:
    return {"name": "potion", "count": 1}


# ── TC-RULE-01: safe state → None ────────────────────────────────────────────


def test_no_reflex_for_safe_state(engine: RuleEngine) -> None:
    """TC-RULE-01"""
    result = engine.evaluate(_state(health=20.0))
    assert result is None


# ── TC-RULE-02: low HP + potion → use_item ───────────────────────────────────


def test_low_health_with_potion_uses_item(engine: RuleEngine) -> None:
    """TC-RULE-02"""
    state = _state(health=5.0, inventory=[_potion()])  # 25% HP
    result = engine.evaluate(state)
    assert result is not None
    assert result.type == "use_item"
    assert result.args["item"] == "potion"
    assert result.source == "reflex"


# ── TC-RULE-03: critical HP + hostile → flee ─────────────────────────────────


def test_critical_health_and_hostile_flees(engine: RuleEngine) -> None:
    """TC-RULE-03"""
    state = _state(health=2.0, nearby_entities=[_hostile(distance=4.0)])
    result = engine.evaluate(state)
    assert result is not None
    assert result.type == "move"
    assert result.args["direction"] == "away_from_threat"


# ── TC-RULE-04: hostile nearby + healthy → attack ────────────────────────────


def test_hostile_nearby_attacks(engine: RuleEngine) -> None:
    """TC-RULE-04"""
    state = _state(health=20.0, nearby_entities=[_hostile(distance=5.0)])
    result = engine.evaluate(state)
    assert result is not None
    assert result.type == "attack"
    assert result.args["target"] == "nearest_hostile"


# ── TC-RULE-05: low HP without potion → None ─────────────────────────────────


def test_low_health_no_potion_no_reflex(engine: RuleEngine) -> None:
    """TC-RULE-05: Rule 2 needs a potion; no hostile so Rule 1/3 also skip."""
    state = _state(health=5.0, inventory=[])
    result = engine.evaluate(state)
    assert result is None


# ── TC-RULE-06: distant hostile → no reflex ──────────────────────────────────


def test_distant_hostile_no_reflex(engine: RuleEngine) -> None:
    """TC-RULE-06: hostile outside 8m aggro range does not trigger attack."""
    state = _state(health=20.0, nearby_entities=[_hostile(distance=10.0)])
    result = engine.evaluate(state)
    assert result is None


# ── TC-RULE-07: exception is swallowed ───────────────────────────────────────


def test_exception_in_state_returns_none(engine: RuleEngine) -> None:
    """TC-RULE-07"""
    # Pass a non-dict to trigger an internal exception path
    result = engine.evaluate(None)  # type: ignore[arg-type]
    assert result is None


# ── TC-RULE-08: GameAction.to_dict() ─────────────────────────────────────────


def test_game_action_to_dict() -> None:
    """TC-RULE-08"""
    action = GameAction(type="use_item", args={"item": "potion"}, source="reflex")
    d = action.to_dict()
    assert d == {"type": "use_item", "args": {"item": "potion"}, "source": "reflex"}


# ── TC-RULE-09: passive entity only → no attack ──────────────────────────────


def test_passive_entity_no_attack(engine: RuleEngine) -> None:
    """TC-RULE-09: nearby passive mob must not trigger attack."""
    state = _state(health=20.0, nearby_entities=[_passive(distance=2.0)])
    result = engine.evaluate(state)
    assert result is None


# ── TC-RULE-10: missing health key → treated as safe ─────────────────────────


def test_missing_health_key_safe(engine: RuleEngine) -> None:
    """TC-RULE-10: state without 'health' key → _health() returns 1.0 → no HP rule fires."""
    state: dict = {"nearby_entities": []}
    result = engine.evaluate(state)
    assert result is None
