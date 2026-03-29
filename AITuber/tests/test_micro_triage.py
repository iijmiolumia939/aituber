"""Tests for orchestrator.micro_triage.

TC-MEM-TRIAGE-01 to TC-MEM-TRIAGE-04.
FR-MEM-TRIAGE-01: Post-reply contradiction detection for semantic facts.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from orchestrator.micro_triage import triage_episode
from orchestrator.semantic_memory import SemanticMemory


@pytest.fixture()
def memory(tmp_path: Path) -> tuple[SemanticMemory, list[float]]:
    now = [1_700_000_000.0]
    semantic = SemanticMemory(
        path=tmp_path / "semantic_memory.jsonl",
        time_fn=lambda: now[0],
    )
    return semantic, now


class TestMicroTriage:
    def test_no_contradiction_when_no_negation(
        self, memory: tuple[SemanticMemory, list[float]]
    ) -> None:
        """TC-MEM-TRIAGE-01: normal conversation does not flag contradictions."""
        semantic, now = memory
        semantic.observe_conversation(author="Alice", user_text="shader setup help")
        semantic.observe_conversation(author="Alice", user_text="shader graph tip")

        flagged = triage_episode(
            semantic=semantic,
            author="Alice",
            user_text="shader is interesting",
            ai_response="",
            time_fn=lambda: now[0],
        )
        assert flagged == 0

    def test_negation_flags_existing_interest(
        self, memory: tuple[SemanticMemory, list[float]]
    ) -> None:
        """TC-MEM-TRIAGE-02: negation language flags existing interest fact."""
        semantic, now = memory
        semantic.observe_conversation(author="Alice", user_text="shader setup help")
        semantic.observe_conversation(author="Alice", user_text="shader graph tip")

        flagged = triage_episode(
            semantic=semantic,
            author="Alice",
            user_text="shader もういい、飽きた",
            ai_response="",
            time_fn=lambda: now[0],
        )
        assert flagged >= 1

        # Verify fact was actually flagged
        facts = semantic.get_facts(category="viewer_interest", subject="Alice")
        shader_fact = next(f for f in facts if f.value == "shader")
        assert shader_fact.last_contradicted > 0

    def test_negation_without_matching_topic_does_not_flag(
        self, memory: tuple[SemanticMemory, list[float]]
    ) -> None:
        """TC-MEM-TRIAGE-03: negation about unknown topic flags nothing."""
        semantic, now = memory
        semantic.observe_conversation(author="Alice", user_text="shader setup help")
        semantic.observe_conversation(author="Alice", user_text="shader graph tip")

        flagged = triage_episode(
            semantic=semantic,
            author="Alice",
            user_text="python もういい、飽きた",
            ai_response="",
            time_fn=lambda: now[0],
        )
        assert flagged == 0

    def test_empty_text_returns_zero(self, memory: tuple[SemanticMemory, list[float]]) -> None:
        """TC-MEM-TRIAGE-04: empty input returns 0."""
        semantic, now = memory
        flagged = triage_episode(
            semantic=semantic,
            author="Alice",
            user_text="",
            ai_response="",
            time_fn=lambda: now[0],
        )
        assert flagged == 0
