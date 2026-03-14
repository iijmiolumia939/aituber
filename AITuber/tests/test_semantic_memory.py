"""Tests for orchestrator.semantic_memory.

TC-SEMEM-01 to TC-SEMEM-05.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from orchestrator.semantic_memory import SemanticMemory


@pytest.fixture()
def memory(tmp_path: Path) -> tuple[SemanticMemory, list[float]]:
    now = [1_700_000_000.0]
    semantic = SemanticMemory(
        path=tmp_path / "semantic_memory.jsonl",
        time_fn=lambda: now[0],
    )
    return semantic, now


class TestSemanticMemory:
    def test_observe_conversation_creates_viewer_profile(
        self, memory: tuple[SemanticMemory, list[float]]
    ) -> None:
        """TC-SEMEM-01: first interaction creates a viewer familiarity fact."""
        semantic, _now = memory

        semantic.observe_conversation(author="Alice", user_text="hello there")

        facts = semantic.get_facts(category="viewer_profile", subject="Alice")
        assert len(facts) == 1
        assert facts[0].value == "newcomer"
        assert facts[0].mention_count == 1

    def test_repeated_conversation_promotes_regular_viewer(
        self, memory: tuple[SemanticMemory, list[float]]
    ) -> None:
        """TC-SEMEM-02: repeated interactions promote familiarity tier."""
        semantic, _now = memory

        semantic.observe_conversation(author="Alice", user_text="hello")
        semantic.observe_conversation(author="Alice", user_text="shader topic")
        semantic.observe_conversation(author="Alice", user_text="python topic")

        fact = semantic.get_facts(category="viewer_profile", subject="Alice")[0]
        assert fact.value == "regular"
        assert fact.mention_count == 3

    def test_repeated_topic_creates_durable_interest_fact(
        self, memory: tuple[SemanticMemory, list[float]]
    ) -> None:
        """TC-SEMEM-03: repeated topic mentions accumulate into viewer-interest facts."""
        semantic, _now = memory

        semantic.observe_conversation(author="Alice", user_text="shader setup help")
        semantic.observe_conversation(author="Alice", user_text="shader graph question")

        facts = semantic.get_facts(category="viewer_interest", subject="Alice")
        shader_fact = next(fact for fact in facts if fact.value == "shader")
        assert shader_fact.mention_count >= 2
        assert shader_fact.confidence > 0.35

    def test_prompt_fragment_uses_viewer_profile_and_matching_topics(
        self, memory: tuple[SemanticMemory, list[float]]
    ) -> None:
        """TC-SEMEM-04: prompt fragment surfaces familiarity and query-matching topics."""
        semantic, _now = memory

        semantic.observe_conversation(author="Alice", user_text="shader setup help")
        semantic.observe_conversation(author="Alice", user_text="shader graph question")
        semantic.observe_conversation(author="Alice", user_text="python shader tip")

        fragment = semantic.to_prompt_fragment(author="Alice", query="shader")

        assert fragment.startswith("[FACTS]")
        assert "regular" in fragment
        assert "shader" in fragment

    def test_overview_fragment_summarizes_repeated_topics(
        self, memory: tuple[SemanticMemory, list[float]]
    ) -> None:
        """TC-SEMEM-04b: overview fragment surfaces cross-session repeated themes."""
        semantic, _now = memory

        semantic.observe_conversation(author="Alice", user_text="shader setup help")
        semantic.observe_conversation(author="Alice", user_text="shader graph question")

        fragment = semantic.to_overview_fragment()

        assert fragment.startswith("[FACTS]")
        assert "Alice" in fragment
        assert "shader" in fragment

    def test_semantic_memory_persists_and_reloads(self, tmp_path: Path) -> None:
        """TC-SEMEM-05: saved semantic facts survive reload."""
        path = tmp_path / "semantic_memory.jsonl"
        semantic = SemanticMemory(path=path, time_fn=lambda: 1_700_000_000.0)
        semantic.observe_conversation(author="Alice", user_text="shader setup help")
        semantic.observe_conversation(author="Alice", user_text="shader graph question")

        reloaded = SemanticMemory(path=path, time_fn=lambda: 1_700_000_060.0)
        assert reloaded.count >= 2
        assert reloaded.to_prompt_fragment(author="Alice", query="shader").startswith("[FACTS]")

    def test_familiarity_score_maps_viewer_profile(
        self, memory: tuple[SemanticMemory, list[float]]
    ) -> None:
        """TC-SEMEM-06: familiarity score tracks viewer tier for downstream priority."""
        semantic, _now = memory

        semantic.observe_conversation(author="Alice", user_text="hello")
        assert semantic.familiarity_score("Alice") == 0

        semantic.observe_conversation(author="Alice", user_text="shader topic")
        semantic.observe_conversation(author="Alice", user_text="python topic")
        assert semantic.familiarity_score("Alice") == 1

    def test_prompt_fragment_excludes_topics_covered_by_goals(
        self, memory: tuple[SemanticMemory, list[float]]
    ) -> None:
        """TC-SEMEM-07: semantic prompt keeps relationship facts but omits active-goal topics."""
        semantic, _now = memory

        semantic.observe_conversation(author="Alice", user_text="shader setup help")
        semantic.observe_conversation(author="Alice", user_text="shader graph question")
        semantic.observe_conversation(author="Alice", user_text="tea preference chat")
        semantic.observe_conversation(author="Alice", user_text="tea ritual note")

        fragment = semantic.to_prompt_fragment(
            author="Alice",
            query="shader",
            exclude_topics=["shader の続き"],
        )

        assert "regular" in fragment
        assert "shader" not in fragment
        assert "tea" in fragment

    def test_overview_fragment_excludes_goal_topics(
        self, memory: tuple[SemanticMemory, list[float]]
    ) -> None:
        """TC-SEMEM-08: overview fragment omits themes already covered by current goals."""
        semantic, _now = memory

        semantic.observe_conversation(author="Alice", user_text="shader setup help")
        semantic.observe_conversation(author="Alice", user_text="shader graph question")
        semantic.observe_conversation(author="Bob", user_text="tea ritual note")
        semantic.observe_conversation(author="Bob", user_text="tea tasting chat")

        fragment = semantic.to_overview_fragment(exclude_topics=["shader の続き"])

        assert "shader" not in fragment
        assert "tea" in fragment
