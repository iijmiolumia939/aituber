"""Tests for orchestrator.memory_budget.

TC-MEM-BUDGET-01 to TC-MEM-BUDGET-05.
FR-MEM-BUDGET-01: Token budget capping for memory fragment injection.
"""

from __future__ import annotations

from orchestrator.memory_budget import compile_fragments, estimate_tokens


class TestEstimateTokens:
    def test_empty_string_returns_zero(self) -> None:
        """TC-MEM-BUDGET-01: empty input costs 0 tokens."""
        assert estimate_tokens("") == 0

    def test_english_text_estimation(self) -> None:
        """TC-MEM-BUDGET-01b: English text uses ~4 chars per token heuristic."""
        tokens = estimate_tokens("hello world test case")
        assert 1 <= tokens <= 10

    def test_japanese_text_estimation(self) -> None:
        """TC-MEM-BUDGET-01c: Japanese text uses ~1 char per token heuristic."""
        tokens = estimate_tokens("こんにちは世界テスト")
        assert tokens >= 5  # 9 JP chars → ~9 tokens

    def test_mixed_text_estimation(self) -> None:
        """TC-MEM-BUDGET-01d: mixed JP/EN text combines both heuristics."""
        tokens = estimate_tokens("shader のテスト")
        assert tokens >= 4  # "shader" ≈ 1-2 tokens + JP chars


class TestCompileFragments:
    def test_empty_fragments_returns_empty(self) -> None:
        """TC-MEM-BUDGET-02: no fragments yields empty string."""
        assert compile_fragments([]) == ""

    def test_single_small_fragment_passes_through(self) -> None:
        """TC-MEM-BUDGET-02b: fragment within budget passes through intact."""
        fragment = "[WORLD]\n時間帯: 夜\n場所: 自室"
        result = compile_fragments([fragment], token_budget=500)
        assert "[WORLD]" in result
        assert "時間帯" in result

    def test_budget_caps_total_output(self) -> None:
        """TC-MEM-BUDGET-03: total output respects token budget."""
        fragments = [
            "[WORLD]\n" + "A " * 100,
            "[FACTS]\n" + "B " * 100,
            "[GOALS]\n" + "C " * 100,
            "[MEMORY]\n" + "D " * 100,
        ]
        result = compile_fragments(fragments, token_budget=50)
        tokens = estimate_tokens(result)
        assert tokens <= 60  # allow small overshoot from per-line granularity

    def test_priority_order_keeps_world_over_memory(self) -> None:
        """TC-MEM-BUDGET-04: [WORLD] takes precedence over [MEMORY] under tight budget."""
        world = "[WORLD]\n時間帯: 夜"
        memory = "[MEMORY]\nAlice: old conversation\n→ reply"
        result = compile_fragments([memory, world], token_budget=20)
        assert "[WORLD]" in result

    def test_zero_budget_returns_empty(self) -> None:
        """TC-MEM-BUDGET-05: zero budget yields empty."""
        assert compile_fragments(["[WORLD]\ntest"], token_budget=0) == ""

    def test_large_budget_includes_all(self) -> None:
        """TC-MEM-BUDGET-05b: large budget includes all fragments."""
        fragments = [
            "[WORLD]\nworld",
            "[FACTS]\nfacts",
            "[GOALS]\ngoals",
            "[MEMORY]\nmemory",
        ]
        result = compile_fragments(fragments, token_budget=5000)
        assert "[WORLD]" in result
        assert "[FACTS]" in result
        assert "[GOALS]" in result
        assert "[MEMORY]" in result
