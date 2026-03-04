"""Tests for orchestrator.narrative_builder.

TC-NARR-01 to TC-NARR-05.
Issue: #16 E-6. FR-E6-01.
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from orchestrator.episodic_store import EpisodeEntry
from orchestrator.narrative_builder import NarrativeBuilder, NarrativeEntry


def _make_episodes(n: int = 3) -> list[EpisodeEntry]:
    return [
        EpisodeEntry(
            episode_id=f"ep{i:04d}",
            timestamp=1700000000.0 + i,
            author=f"user{i}",
            user_text=f"コメント{i}",
            ai_response=f"返答{i}",
            importance=5,
        )
        for i in range(n)
    ]


@pytest.fixture()
def builder(tmp_path: Path) -> NarrativeBuilder:
    log_path = tmp_path / "narrative_log.jsonl"
    return NarrativeBuilder(
        log_path=str(log_path),
        llm_fn=None,
    )


class TestNarrativeBuilderFallback:
    def test_build_empty_returns_entry(self, builder: NarrativeBuilder) -> None:
        """TC-NARR-01: build([]) returns a NarrativeEntry."""
        entry = builder.build([])
        assert isinstance(entry, NarrativeEntry)
        assert entry.narrative  # non-empty

    def test_build_fallback_contains_no_llm(self, builder: NarrativeBuilder) -> None:
        """TC-NARR-02: without llm_fn, fallback text is generated."""
        episodes = _make_episodes(3)
        entry = builder.build(episodes)
        assert isinstance(entry, NarrativeEntry)
        assert len(entry.narrative) > 0

    def test_build_writes_jsonl(self, builder: NarrativeBuilder, tmp_path: Path) -> None:
        """TC-NARR-05: build() appends a line to the JSONL log."""
        episodes = _make_episodes(2)
        builder.build(episodes)
        log_file = tmp_path / "narrative_log.jsonl"
        assert log_file.exists()
        lines = log_file.read_text(encoding="utf-8").strip().splitlines()
        assert len(lines) >= 1
        parsed = json.loads(lines[-1])
        assert "narrative" in parsed
        assert "timestamp" in parsed

    def test_get_latest_returns_most_recent(self, builder: NarrativeBuilder) -> None:
        """TC-NARR-04: get_latest() returns most recent narrative text after build."""
        builder.build([])
        builder.build(_make_episodes(2))
        latest = builder.get_latest()
        assert latest  # non-empty string
        assert isinstance(latest, str)

    def test_get_latest_none_before_build(self, builder: NarrativeBuilder) -> None:
        """TC-NARR-04b: get_latest() returns empty string before any build."""
        assert builder.get_latest() == ""


class TestNarrativeBuilderWithLLM:
    def test_build_uses_llm_fn(self, tmp_path: Path) -> None:
        """TC-NARR-03: when llm_fn is provided, its return value is used."""
        mock_llm = MagicMock(return_value="LLMが生成したナラティブです。")
        builder = NarrativeBuilder(
            log_path=str(tmp_path / "narr.jsonl"),
            llm_fn=mock_llm,
        )
        episodes = _make_episodes(3)
        entry = builder.build(episodes)
        assert entry.narrative == "LLMが生成したナラティブです。"
        mock_llm.assert_called_once()

    def test_build_llm_fn_receives_prompt(self, tmp_path: Path) -> None:
        """TC-NARR-03b: llm_fn is called with a non-empty prompt string."""
        received_prompts: list[str] = []

        def capture_llm(prompt: str) -> str:
            received_prompts.append(prompt)
            return "テスト結果"

        builder = NarrativeBuilder(
            log_path=str(tmp_path / "narr.jsonl"),
            llm_fn=capture_llm,
        )
        builder.build(_make_episodes(3))
        assert len(received_prompts) == 1
        assert len(received_prompts[0]) > 10  # non-trivial prompt
