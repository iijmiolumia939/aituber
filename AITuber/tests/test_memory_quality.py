"""Tests for M30 memory quality enhancements.

TC-MEM-EVIDENCE-01 to TC-MEM-EVIDENCE-03: Evidence-linked facts.
TC-MEM-DECAY-01 to TC-MEM-DECAY-04: Time-decayed confidence.
FR-MEM-EVIDENCE-01, FR-MEM-DECAY-01.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from orchestrator.goal_memory import GoalEntry, GoalMemory
from orchestrator.semantic_memory import SemanticFact, SemanticMemory


@pytest.fixture()
def semantic(tmp_path: Path) -> tuple[SemanticMemory, list[float]]:
    now = [1_700_000_000.0]
    mem = SemanticMemory(
        path=tmp_path / "semantic_memory.jsonl",
        time_fn=lambda: now[0],
    )
    return mem, now


@pytest.fixture()
def goals(tmp_path: Path) -> tuple[GoalMemory, list[float]]:
    now = [1_700_000_000.0]
    mem = GoalMemory(
        path=tmp_path / "goal_memory.jsonl",
        time_fn=lambda: now[0],
    )
    return mem, now


class TestEvidenceLinkedFacts:
    def test_observe_stores_episode_id(self, semantic: tuple[SemanticMemory, list[float]]) -> None:
        """TC-MEM-EVIDENCE-01: observe_conversation links episode_id to fact."""
        mem, _now = semantic
        mem.observe_conversation(
            author="Alice",
            user_text="shader setup help",
            episode_id="ep001",
        )
        mem.observe_conversation(
            author="Alice",
            user_text="shader graph help",
            episode_id="ep002",
        )
        facts = mem.get_facts(category="viewer_interest", subject="Alice")
        shader_fact = next(f for f in facts if f.value == "shader")
        assert shader_fact.evidence_ids is not None
        assert "ep001" in shader_fact.evidence_ids
        assert "ep002" in shader_fact.evidence_ids

    def test_evidence_ids_backward_compatible(self) -> None:
        """TC-MEM-EVIDENCE-02: loading legacy facts without evidence_ids works."""
        fact = SemanticFact.from_dict(
            {
                "fact_id": "legacy1",
                "category": "viewer_interest",
                "subject": "Alice",
                "value": "shader",
                "mention_count": 3,
                "confidence": 0.6,
                "last_updated": 1_700_000_000.0,
            }
        )
        assert fact.evidence_ids is None
        assert fact.last_contradicted == 0.0

    def test_evidence_ids_serialization_roundtrip(self) -> None:
        """TC-MEM-EVIDENCE-03: evidence_ids survive to_dict/from_dict roundtrip."""
        original = SemanticFact(
            fact_id="test1",
            category="viewer_interest",
            subject="Alice",
            value="shader",
            mention_count=2,
            confidence=0.5,
            last_updated=1_700_000_000.0,
            evidence_ids=["ep001", "ep002"],
            last_contradicted=1_700_000_100.0,
        )
        d = original.to_dict()
        restored = SemanticFact.from_dict(d)
        assert restored.evidence_ids == ["ep001", "ep002"]
        assert restored.last_contradicted == 1_700_000_100.0


class TestTimeDecayedConfidence:
    def test_fresh_fact_retains_confidence(self) -> None:
        """TC-MEM-DECAY-01: recently updated fact keeps near-original confidence."""
        fact = SemanticFact(
            fact_id="f1",
            category="viewer_interest",
            subject="Alice",
            value="shader",
            mention_count=5,
            confidence=0.8,
            last_updated=1_700_000_000.0,
        )
        eff = fact.effective_confidence(1_700_000_000.0 + 86400)  # 1 day later
        assert eff >= 0.75

    def test_old_fact_decays_significantly(self) -> None:
        """TC-MEM-DECAY-02: fact not updated for 60 days decays substantially."""
        fact = SemanticFact(
            fact_id="f1",
            category="viewer_interest",
            subject="Alice",
            value="shader",
            mention_count=5,
            confidence=0.8,
            last_updated=1_700_000_000.0,
        )
        # 60 days = 2 half-lives → ~25% of original
        eff = fact.effective_confidence(1_700_000_000.0 + 60 * 86400)
        assert eff < 0.3

    def test_contradicted_fact_halves_confidence(self) -> None:
        """TC-MEM-DECAY-03: recently contradicted fact gets extra penalty."""
        now = 1_700_000_000.0
        fact = SemanticFact(
            fact_id="f1",
            category="viewer_interest",
            subject="Alice",
            value="shader",
            mention_count=5,
            confidence=0.8,
            last_updated=now,
            last_contradicted=now,
        )
        normal_eff = SemanticFact(
            fact_id="f2",
            category="viewer_interest",
            subject="Alice",
            value="python",
            mention_count=5,
            confidence=0.8,
            last_updated=now,
        ).effective_confidence(now + 86400)

        contradicted_eff = fact.effective_confidence(now + 86400)
        assert contradicted_eff < normal_eff * 0.6

    def test_goal_effective_confidence_decays(self, goals: tuple[GoalMemory, list[float]]) -> None:
        """TC-MEM-DECAY-04: GoalEntry effective_confidence decays over time."""
        goal = GoalEntry(
            goal_id="g1",
            category="topic_goal",
            subject="",
            value="shader",
            focus_type="learning",
            status="warming",
            mention_count=2,
            confidence=0.56,
            last_updated=1_700_000_000.0,
        )
        fresh = goal.effective_confidence(1_700_000_000.0 + 86400)
        old = goal.effective_confidence(1_700_000_000.0 + 42 * 86400)  # 2 half-lives
        assert fresh > old
        assert old < 0.2
