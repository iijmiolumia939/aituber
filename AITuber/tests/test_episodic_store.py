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


@pytest.fixture()
def timed_store(tmp_path: Path) -> tuple[EpisodicStore, list[float]]:
    now = [1_700_000_000.0]
    store = EpisodicStore(
        path=tmp_path / "timed_ep.jsonl",
        capacity=50,
        time_fn=lambda: now[0],
    )
    return store, now


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

    def test_from_dict_backwards_compatible_with_legacy_fields(self) -> None:
        """TC-MEM-07b: legacy payloads deserialize with safe defaults for new metadata."""
        ep = EpisodeEntry.from_dict(
            {
                "episode_id": "legacy001",
                "timestamp": 1234.0,
                "author": "Alice",
                "user_text": "hello",
                "ai_response": "hi",
                "importance": 7,
            }
        )
        assert ep.source_type == "conversation"
        assert ep.emotion_tags == []
        assert ep.arousal == 0.0
        assert ep.access_count == 0
        assert ep.time_bucket == ""
        assert ep.related_viewer == ""


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


class TestEpisodicStoreM26Ranking:
    def test_append_persists_metadata_fields(
        self, timed_store: tuple[EpisodicStore, list[float]]
    ) -> None:
        """TC-MEM-11: append stores new metadata fields for runtime memory events."""
        store, _now = timed_store
        ep = store.append(
            author="system",
            user_text="behavior_completed: go_sleep",
            ai_response="success",
            importance=6,
            source_type="behavior",
            emotion_tags=["thinking"],
            arousal=0.4,
            scene_name="yuia_home",
            room_name="bedroom",
            nearby_objects=["Desk", "Lamp", "Desk"],
            activity_type="go_sleep",
            related_viewer="Alice",
            outcome="success",
            time_bucket="night",
        )
        assert ep.source_type == "behavior"
        assert ep.emotion_tags == ["thinking"]
        assert ep.arousal == pytest.approx(0.4)
        assert ep.scene_name == "yuia_home"
        assert ep.room_name == "bedroom"
        assert ep.nearby_objects == ["desk", "lamp"]
        assert ep.activity_type == "go_sleep"
        assert ep.related_viewer == "Alice"
        assert ep.outcome == "success"
        assert ep.time_bucket == "night"

    def test_get_relevant_boosts_same_viewer_continuity(
        self, timed_store: tuple[EpisodicStore, list[float]]
    ) -> None:
        """TC-MEM-12: same-viewer memories rank above unrelated viewer memories on tie."""
        store, _now = timed_store
        store.append("Alice", "stream plan", "let's continue", importance=5)
        store.append("Bob", "stream plan", "different thread", importance=5)

        results = store.get_relevant("stream plan", author="Alice")

        assert results[0].author == "Alice"

    def test_get_relevant_prefers_fresher_matching_episode(
        self, timed_store: tuple[EpisodicStore, list[float]]
    ) -> None:
        """TC-MEM-13: fresher episodes outrank older ones with otherwise similar relevance."""
        store, now = timed_store
        store.append("Alice", "python shader", "old memory", importance=6)
        now[0] += 14 * 24 * 3600
        store.append("Alice", "python shader", "recent memory", importance=6)

        results = store.get_relevant("python shader", author="Alice")

        assert results[0].ai_response == "recent memory"

    def test_get_relevant_boosts_matching_time_bucket(
        self, timed_store: tuple[EpisodicStore, list[float]]
    ) -> None:
        """TC-MEM-14: time bucket match breaks ties in favor of current context."""
        store, _now = timed_store
        store.append(
            "Alice",
            "study topic",
            "night memory",
            importance=5,
            time_bucket="night",
        )
        store.append(
            "Alice",
            "study topic",
            "morning memory",
            importance=5,
            time_bucket="morning",
        )

        results = store.get_relevant("study topic", author="Alice", time_bucket="morning")

        assert results[0].ai_response == "morning memory"

    def test_get_relevant_boosts_matching_room_name(
        self, timed_store: tuple[EpisodicStore, list[float]]
    ) -> None:
        """TC-MEM-14b: room match breaks ties in favor of current place continuity."""
        store, _now = timed_store
        store.append(
            "Alice",
            "study topic",
            "desk memory",
            importance=5,
            room_name="desk_area",
        )
        store.append(
            "Alice",
            "study topic",
            "kitchen memory",
            importance=5,
            room_name="kitchen",
        )

        results = store.get_relevant("study topic", author="Alice", room_name="desk_area")

        assert results[0].ai_response == "desk memory"

    def test_get_relevant_boosts_matching_scene_name(
        self, timed_store: tuple[EpisodicStore, list[float]]
    ) -> None:
        """TC-MEM-14c: scene match breaks ties in favor of current environment."""
        store, _now = timed_store
        store.append(
            "Alice",
            "study topic",
            "home memory",
            importance=5,
            scene_name="yuia_home",
        )
        store.append(
            "Alice",
            "study topic",
            "studio memory",
            importance=5,
            scene_name="stream_studio",
        )

        results = store.get_relevant("study topic", author="Alice", scene_name="yuia_home")

        assert results[0].ai_response == "home memory"

    def test_get_relevant_boosts_matching_nearby_objects(
        self, timed_store: tuple[EpisodicStore, list[float]]
    ) -> None:
        """TC-MEM-14d: nearby object overlap favors the currently grounded episode."""
        store, _now = timed_store
        store.append(
            "Alice",
            "study topic",
            "desk memory",
            importance=5,
            nearby_objects=["desk", "monitor"],
        )
        store.append(
            "Alice",
            "study topic",
            "sofa memory",
            importance=5,
            nearby_objects=["sofa", "plant"],
        )

        results = store.get_relevant(
            "study topic",
            author="Alice",
            nearby_objects=["desk", "lamp", "monitor"],
        )

        assert results[0].ai_response == "desk memory"

    def test_get_relevant_reinforces_access_count_on_recall(
        self, timed_store: tuple[EpisodicStore, list[float]]
    ) -> None:
        """TC-MEM-15: recalled episodes update access_count and last_accessed."""
        store, now = timed_store
        ep = store.append("Alice", "favorite tea", "jasmine", importance=6)

        before_last_accessed = ep.last_accessed
        results = store.get_relevant("favorite tea", author="Alice")

        assert results[0].access_count == 1
        assert results[0].last_accessed >= before_last_accessed

        now[0] += 60.0
        results = store.get_relevant("favorite tea", author="Alice")
        assert results[0].access_count == 2

    def test_retrieval_side_decay_keeps_weak_old_episode_below_recent_stronger_match(
        self, timed_store: tuple[EpisodicStore, list[float]]
    ) -> None:
        """TC-MEM-16: old low-importance episodes decay instead of dominating retrieval forever."""
        store, now = timed_store
        store.append("Alice", "memory topic", "weak old", importance=5)
        now[0] += 30 * 24 * 3600
        store.append("Alice", "memory topic", "newer stronger", importance=7)

        results = store.get_relevant("memory topic", author="Alice")

        assert results[0].ai_response == "newer stronger"
