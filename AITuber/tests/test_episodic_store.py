"""Tests for orchestrator.episodic_store.

TC-MEM-01 to TC-MEM-10.
Issue: #12 E-2 Episodic Memory. FR-E2-01, FR-E2-02.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from orchestrator.episodic_store import EpisodeEntry, EpisodicStore

# ── Fixtures ──────────────────────────────────────────────────────────


@pytest.fixture()
def store(tmp_path: Path) -> EpisodicStore:
    return EpisodicStore(path=tmp_path / "ep.jsonl", capacity=50)


def _add(s: EpisodicStore, author: str = "A", user: str = "hello", ai: str = "hi") -> EpisodeEntry:
    return s.append(author=author, user_text=user, ai_response=ai)


# ── TC-MEM-01 ──────────────────────────────────────────────────────────


class TestEpisodicStoreBasic:
    def test_empty_store_count_zero(self, store: EpisodicStore) -> None:
        """TC-MEM-01: fresh store has 0 episodes."""
        assert store.count == 0

    def test_append_increments_count(self, store: EpisodicStore) -> None:
        """TC-MEM-02: append increments count."""
        _add(store)
        assert store.count == 1
        _add(store)
        assert store.count == 2

    def test_append_returns_entry(self, store: EpisodicStore) -> None:
        """TC-MEM-03: append returns populated EpisodeEntry."""
        ep = _add(store, author="Alice", user="こんにちは", ai="こんにちは！")
        assert ep.author == "Alice"
        assert ep.user_text == "こんにちは"
        assert ep.ai_response == "こんにちは！"
        assert ep.importance == 5  # default
        assert len(ep.episode_id) == 12

    def test_custom_importance(self, store: EpisodicStore) -> None:
        """TC-MEM-04: custom importance is stored."""
        ep = store.append("B", "重要な質問", "重要な回答", importance=9)
        assert ep.importance == 9

    def test_score_fn_overrides_importance(self, store: EpisodicStore) -> None:
        """TC-MEM-04b: score_fn result overrides importance param."""
        ep = store.append("B", "text", "resp", importance=3, score_fn=lambda u, a: 8)
        assert ep.importance == 8

    def test_score_fn_clamped(self, store: EpisodicStore) -> None:
        """TC-MEM-04c: score_fn result is clamped 1-10."""
        ep = store.append("B", "text", "resp", score_fn=lambda u, a: 99)
        assert ep.importance == 10
        ep2 = store.append("B", "text", "resp", score_fn=lambda u, a: -5)
        assert ep2.importance == 1


# ── TC-MEM-05: Persistence ─────────────────────────────────────────────


class TestEpisodicStorePersistence:
    def test_persists_and_reloads(self, tmp_path: Path) -> None:
        """TC-MEM-05: episodes survive reload from JSONL file."""
        path = tmp_path / "ep.jsonl"
        s1 = EpisodicStore(path=path)
        s1.append("Alice", "Question", "Answer")
        s1.append("Bob", "Hi", "Hello")

        s2 = EpisodicStore(path=path)
        assert s2.count == 2
        recent = s2.get_recent(2)
        assert recent[0].author == "Alice"
        assert recent[1].author == "Bob"

    def test_capacity_eviction(self, tmp_path: Path) -> None:
        """TC-MEM-06: FIFO eviction when capacity is exceeded."""
        s = EpisodicStore(path=tmp_path / "ep.jsonl", capacity=3)
        for i in range(5):
            s.append("U", f"msg{i}", f"rep{i}")
        assert s.count == 3
        recent = s.get_recent(3)
        user_texts = [ep.user_text for ep in recent]
        assert "msg4" in user_texts
        assert "msg0" not in user_texts

    def test_malformed_lines_skipped(self, tmp_path: Path) -> None:
        """TC-MEM-07: malformed JSONL lines are silently skipped."""
        path = tmp_path / "ep.jsonl"
        # Both lines are invalid JSON — neither parses
        path.write_text("not_json_at_all\n{invalid json: true\n", encoding="utf-8")
        s = EpisodicStore(path=path)
        assert s.count == 0  # nothing loadable


# ── TC-MEM-08: Retrieval ───────────────────────────────────────────────


class TestEpisodicStoreRetrieval:
    def test_get_by_author(self, store: EpisodicStore) -> None:
        """TC-MEM-08: get_by_author filters by author name."""
        store.append("Alice", "q1", "a1")
        store.append("Bob", "q2", "a2")
        store.append("Alice", "q3", "a3")
        alice_eps = store.get_by_author("Alice", n=5)
        assert len(alice_eps) == 2
        assert all(ep.author == "Alice" for ep in alice_eps)

    def test_get_relevant_keyword_match(self, store: EpisodicStore) -> None:
        """TC-MEM-09: get_relevant returns keyword-matching episodes."""
        # Use space-separated English tokens so split() tokenises correctly
        store.append("U", "Python unity game", "Python is fun")
        store.append("U", "weather today nice", "sunny day")
        results = store.get_relevant("Python game")
        assert any("Python" in ep.user_text for ep in results)

    def test_get_relevant_empty_when_no_match(self, store: EpisodicStore) -> None:
        """TC-MEM-09b: get_relevant returns empty list when nothing matches."""
        store.append("U", "全然関係ない話", "うん")
        results = store.get_relevant("xyzabc123 nomatchtopic")
        # All scores will be 0 so nothing returned
        assert results == []

    def test_to_prompt_fragment_empty(self, store: EpisodicStore) -> None:
        """TC-MEM-10: to_prompt_fragment returns empty string for empty store."""
        assert store.to_prompt_fragment() == ""

    def test_to_prompt_fragment_has_memory_header(self, store: EpisodicStore) -> None:
        """TC-MEM-10b: to_prompt_fragment starts with [MEMORY]."""
        store.append("Alice", "test query", "test answer")
        frag = store.to_prompt_fragment("test")
        assert frag.startswith("[MEMORY]")
        assert "Alice" in frag
