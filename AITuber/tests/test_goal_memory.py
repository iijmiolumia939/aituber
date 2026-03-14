"""Tests for orchestrator.goal_memory.

TC-GOALMEM-01 to TC-GOALMEM-05.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from orchestrator.goal_memory import GoalMemory


@pytest.fixture()
def memory(tmp_path: Path) -> tuple[GoalMemory, list[float]]:
    now = [1_700_000_000.0]
    goals = GoalMemory(
        path=tmp_path / "goal_memory.jsonl",
        time_fn=lambda: now[0],
    )
    return goals, now


class TestGoalMemory:
    def test_repeated_topic_promotes_active_goal(
        self, memory: tuple[GoalMemory, list[float]]
    ) -> None:
        """TC-GOALMEM-01: repeated topics become an active medium-horizon goal."""
        goals, _now = memory

        goals.observe_conversation(author="Alice", user_text="shader setup help")
        goals.observe_conversation(author="Alice", user_text="shader graph question")
        goals.observe_conversation(author="Bob", user_text="shader pipeline note")

        current = goals.current_goal()
        assert current is not None
        assert current.value == "shader"
        assert current.status == "active"

    def test_prompt_fragment_surfaces_matching_goal(
        self, memory: tuple[GoalMemory, list[float]]
    ) -> None:
        """TC-GOALMEM-02: prompt fragment exposes active goal lines."""
        goals, _now = memory

        goals.observe_conversation(author="Alice", user_text="shader setup help")
        goals.observe_conversation(author="Alice", user_text="shader graph question")
        goals.observe_conversation(author="Alice", user_text="shader tip")

        fragment = goals.to_prompt_fragment(query="shader の続き")

        assert fragment.startswith("[GOALS]")
        assert "shader" in fragment

    def test_scheduler_focus_comes_from_current_goal(
        self, memory: tuple[GoalMemory, list[float]]
    ) -> None:
        """TC-GOALMEM-03: current goal is converted into scheduler focus."""
        goals, _now = memory

        goals.observe_conversation(author="Alice", user_text="shader setup help")
        goals.observe_conversation(author="Alice", user_text="shader graph question")
        goals.observe_conversation(author="Alice", user_text="shader tip")

        goal_text, focus_type = goals.get_scheduler_focus()
        assert "shader" in goal_text
        assert focus_type == "learning"

    def test_behavior_failure_creates_exploration_goal(
        self, memory: tuple[GoalMemory, list[float]]
    ) -> None:
        """TC-GOALMEM-04: locomotion failures warm up an exploration maintenance goal."""
        goals, _now = memory

        goals.observe_behavior_result(
            behavior="walk_to_bed",
            success=False,
            reason="locomotion_blocked",
        )
        goals.observe_behavior_result(
            behavior="walk_to_desk",
            success=False,
            reason="locomotion_blocked",
        )

        current = goals.current_goal()
        assert current is not None
        assert current.value == "移動の安定性"
        assert current.focus_type == "exploration"
        assert current.status == "active"

    def test_follow_up_signal_creates_follow_up_goal(
        self, memory: tuple[GoalMemory, list[float]]
    ) -> None:
        """TC-GOALMEM-05: repeated follow-up requests become a continuation goal."""
        goals, _now = memory

        goals.observe_conversation(
            author="Alice",
            user_text="shader の続き教えて",
            ai_response="shader の続きを話そう",
        )
        goals.observe_conversation(
            author="Alice",
            user_text="shader の続きまだある?",
            ai_response="shader の続きも見ていこう",
        )

        current = goals.current_goal()
        assert current is not None
        assert current.category == "follow_up_goal"
        assert current.subject == "Alice"
        assert current.value == "shader の続き"
        assert current.focus_type == "social"

        fragment = goals.to_prompt_fragment(author="Alice", query="shader")
        assert "拾い直したい" in fragment

    def test_author_specific_follow_up_goal_is_prioritized(
        self, memory: tuple[GoalMemory, list[float]]
    ) -> None:
        """TC-GOALMEM-06: reply prompt prefers continuation goals for the same viewer."""
        goals, _now = memory

        goals.observe_conversation(
            author="Alice",
            user_text="shader の続き教えて",
            ai_response="shader の続きを話そう",
        )
        goals.observe_conversation(
            author="Alice",
            user_text="shader の続きまだある?",
            ai_response="shader の続きも見ていこう",
        )
        goals.observe_conversation(
            author="Bob",
            user_text="math の続き教えて",
            ai_response="math の続きを話そう",
        )
        goals.observe_conversation(
            author="Bob",
            user_text="math の続きまだある?",
            ai_response="math の続きも見ていこう",
        )

        fragment = goals.to_prompt_fragment(
            author="Alice",
            query="続き",
            familiarity_score=1,
        )

        assert "shader の続き" in fragment
        assert "math の続き" not in fragment

    def test_newcomer_still_sees_global_goals_alongside_follow_up(
        self, memory: tuple[GoalMemory, list[float]]
    ) -> None:
        """TC-GOALMEM-07: newcomer threads do not fully suppress global goals."""
        goals, _now = memory

        goals.observe_conversation(author="Alice", user_text="shader setup help")
        goals.observe_conversation(author="Alice", user_text="shader graph question")
        goals.observe_conversation(author="Alice", user_text="shader tip")
        goals.observe_conversation(
            author="Alice",
            user_text="shader の続き教えて",
            ai_response="shader の続きを話そう",
        )
        goals.observe_conversation(
            author="Alice",
            user_text="shader の続きまだある?",
            ai_response="shader の続きも見ていこう",
        )

        fragment = goals.to_prompt_fragment(
            author="Alice",
            query="shader",
            familiarity_score=0,
        )

        assert "shader の続き" in fragment
        assert "もう少し深めたい" in fragment

    def test_idle_hint_uses_current_goal(self, memory: tuple[GoalMemory, list[float]]) -> None:
        """TC-GOALMEM-08: idle hint reflects the strongest current goal."""
        goals, _now = memory

        goals.observe_conversation(author="Alice", user_text="shader setup help")
        goals.observe_conversation(author="Alice", user_text="shader graph question")
        goals.observe_conversation(author="Alice", user_text="shader tip")

        hint = goals.to_idle_hint()
        assert "shader" in hint

    def test_goal_memory_persists_and_reloads(self, tmp_path: Path) -> None:
        """TC-GOALMEM-09: saved goals survive reload."""
        path = tmp_path / "goal_memory.jsonl"
        goals = GoalMemory(path=path, time_fn=lambda: 1_700_000_000.0)
        goals.observe_conversation(author="Alice", user_text="shader setup help")
        goals.observe_conversation(author="Alice", user_text="shader graph question")
        goals.observe_conversation(author="Alice", user_text="shader tip")

        reloaded = GoalMemory(path=path, time_fn=lambda: 1_700_000_060.0)
        assert reloaded.current_goal() is not None
        assert reloaded.current_goal().value == "shader"
