"""Episodic Memory — JSONL-based persistent conversation store.

FR-E2-01: Records conversation episodes and retrieves relevant ones for the LLM.
Issue: #12 E-2 Episodic Memory

References:
  Park et al. (2023), Generative Agents, arXiv:2304.03442 §3 "Memory"
  Sumers et al. (2023), CoALA, arXiv:2309.02427 §4 "Memory Components"
"""

from __future__ import annotations

import json
import logging
import math
import time
import uuid
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from pathlib import Path

logger = logging.getLogger(__name__)

_DEFAULT_STORE_PATH = Path(__file__).parent.parent / "config" / "episodic_memory.jsonl"
_DEFAULT_CAPACITY = 200  # max episodes kept in file (FIFO eviction)
_DEFAULT_TOP_K = 5  # default retrieval count
_HALF_LIFE_DAYS = 14.0


@dataclass
class EpisodeEntry:
    """A single conversation episode.

    FR-E2-01: Stores user utterance + AI response with importance scoring.
    """

    episode_id: str
    timestamp: float  # monotonic-equivalent; use time.time() for portability
    author: str
    user_text: str
    ai_response: str
    importance: int = 5  # 1 (low) – 10 (high)
    source_type: str = "conversation"
    emotion_tags: list[str] = field(default_factory=list)
    arousal: float = 0.0
    scene_name: str = ""
    room_name: str = ""
    nearby_objects: list[str] = field(default_factory=list)
    activity_type: str = ""
    last_accessed: float = 0.0
    access_count: int = 0
    time_bucket: str = ""
    related_viewer: str = ""
    outcome: str = ""

    # ── Serialization ─────────────────────────────────────────────────

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> EpisodeEntry:
        return cls(
            episode_id=d.get("episode_id", uuid.uuid4().hex[:12]),
            timestamp=float(d.get("timestamp", 0.0)),
            author=d.get("author", ""),
            user_text=d.get("user_text", ""),
            ai_response=d.get("ai_response", ""),
            importance=int(d.get("importance", 5)),
            source_type=str(d.get("source_type", "conversation") or "conversation"),
            emotion_tags=[str(tag) for tag in (d.get("emotion_tags", []) or [])],
            arousal=float(d.get("arousal", 0.0) or 0.0),
            scene_name=str(d.get("scene_name", "") or ""),
            room_name=str(d.get("room_name", "") or ""),
            nearby_objects=[str(item) for item in (d.get("nearby_objects", []) or [])],
            activity_type=str(d.get("activity_type", "") or ""),
            last_accessed=float(d.get("last_accessed", 0.0) or 0.0),
            access_count=int(d.get("access_count", 0) or 0),
            time_bucket=str(d.get("time_bucket", "") or ""),
            related_viewer=str(d.get("related_viewer", "") or ""),
            outcome=str(d.get("outcome", "") or ""),
        )


class EpisodicStore:
    """Persistent episodic memory backed by JSONL.

    FR-E2-01, FR-E2-02.
    """

    def __init__(
        self,
        path: Path | str | None = None,
        capacity: int = _DEFAULT_CAPACITY,
        *,
        time_fn: Callable[[], float] | None = None,
    ) -> None:
        self._path = Path(path) if path else _DEFAULT_STORE_PATH
        self._capacity = capacity
        self._episodes: list[EpisodeEntry] = []
        self._time_fn: Callable[[], float] = time_fn or time.time
        self._load()

    # ── Persistence ───────────────────────────────────────────────────

    def _load(self) -> None:
        """Load episodes from JSONL file (best-effort)."""
        if not self._path.exists():
            return
        loaded: list[EpisodeEntry] = []
        try:
            for line in self._path.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if not line:
                    continue
                try:
                    loaded.append(EpisodeEntry.from_dict(json.loads(line)))
                except (json.JSONDecodeError, KeyError, TypeError):
                    logger.debug("Skipping malformed episode line")
        except OSError as exc:
            logger.warning("Failed to load episodic store: %s", exc)
        # Keep only last `_capacity` episodes (in-order)
        self._episodes = loaded[-self._capacity :]
        logger.info("[EpisodicStore] Loaded %d episodes from %s", len(self._episodes), self._path)

    def _save(self) -> None:
        """Persist all episodes to the JSONL file."""
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            with self._path.open("w", encoding="utf-8") as fh:
                for ep in self._episodes:
                    fh.write(json.dumps(ep.to_dict(), ensure_ascii=False) + "\n")
        except OSError as exc:
            logger.warning("Failed to save episodic store: %s", exc)

    # ── Write ─────────────────────────────────────────────────────────

    def append(
        self,
        author: str,
        user_text: str,
        ai_response: str,
        importance: int = 5,
        *,
        score_fn: Callable[[str, str], int] | None = None,
        source_type: str = "conversation",
        emotion_tags: list[str] | None = None,
        arousal: float = 0.0,
        scene_name: str = "",
        room_name: str = "",
        nearby_objects: list[str] | None = None,
        activity_type: str = "",
        related_viewer: str = "",
        outcome: str = "",
        time_bucket: str = "",
    ) -> EpisodeEntry:
        """Record a new episode.

        FR-E2-01: Optionally call *score_fn(user_text, ai_response)* → int(1-10)
        to compute importance (e.g. LLM-based; defaults to *importance* param).
        """
        if score_fn is not None:
            try:
                importance = max(1, min(10, score_fn(user_text, ai_response)))
            except Exception:  # noqa: BLE001
                logger.debug("Importance scoring failed; using default")

        timestamp = self._time_fn()
        ep = EpisodeEntry(
            episode_id=uuid.uuid4().hex[:12],
            timestamp=timestamp,
            author=author,
            user_text=user_text,
            ai_response=ai_response,
            importance=importance,
            source_type=source_type,
            emotion_tags=list(emotion_tags or []),
            arousal=max(0.0, min(1.0, arousal)),
            scene_name=scene_name,
            room_name=room_name,
            nearby_objects=self._normalize_nearby_objects(nearby_objects),
            activity_type=activity_type,
            related_viewer=related_viewer,
            outcome=outcome,
            time_bucket=time_bucket or self._derive_time_bucket(timestamp),
        )
        self._episodes.append(ep)
        # FIFO eviction
        if len(self._episodes) > self._capacity:
            self._episodes = self._episodes[-self._capacity :]
        self._save()
        return ep

    # ── Read ──────────────────────────────────────────────────────────

    def get_recent(self, n: int = 10) -> list[EpisodeEntry]:
        """Return the *n* most recent episodes."""
        return self._episodes[-n:]

    def get_by_author(self, author: str, n: int = 5) -> list[EpisodeEntry]:
        """Return the *n* most recent episodes for a specific author."""
        return [ep for ep in reversed(self._episodes) if ep.author == author][:n]

    def get_relevant(
        self,
        query: str,
        top_k: int = _DEFAULT_TOP_K,
        *,
        author: str | None = None,
        time_bucket: str | None = None,
        scene_name: str | None = None,
        room_name: str | None = None,
        nearby_objects: list[str] | None = None,
    ) -> list[EpisodeEntry]:
        """Retrieve episodes most relevant to *query* with composite recall scoring.

        FR-E2-02: lexical overlap remains the base signal, but freshness,
        access reinforcement, viewer continuity, and time bucket context also
        shape ranking so recall becomes more context-sensitive.
        """
        if not self._episodes:
            return []
        query_tokens = set(query.lower().split())
        now = self._time_fn()
        scored: list[tuple[float, EpisodeEntry]] = []
        for ep in self._episodes:
            score = self._score_episode(
                ep,
                query_tokens=query_tokens,
                author=author,
                time_bucket=time_bucket,
                scene_name=scene_name,
                room_name=room_name,
                nearby_objects=nearby_objects,
                now=now,
            )
            scored.append((score, ep))
        scored.sort(key=lambda x: x[0], reverse=True)
        selected = [ep for score, ep in scored[:top_k] if score > 0]
        if selected:
            self._touch_recalled_episodes(selected, now)
        return selected

    def to_prompt_fragment(
        self,
        query: str | None = None,
        top_k: int = _DEFAULT_TOP_K,
        *,
        author: str | None = None,
        time_bucket: str | None = None,
        scene_name: str | None = None,
        room_name: str | None = None,
        nearby_objects: list[str] | None = None,
    ) -> str:
        """Return a [MEMORY] block to inject into the LLM system prompt.

        FR-E2-01: Empty string if no relevant episodes.
        """
        episodes = (
            self.get_relevant(
                query,
                top_k,
                author=author,
                time_bucket=time_bucket,
                scene_name=scene_name,
                room_name=room_name,
                nearby_objects=nearby_objects,
            )
            if query
            else self.get_recent(top_k)
        )
        if not episodes:
            return ""
        lines = ["[MEMORY]"]
        for ep in episodes:
            lines.append(f"{ep.author}: {ep.user_text}")
            lines.append(f"→ {ep.ai_response[:80]}")
        return "\n".join(lines)

    @property
    def count(self) -> int:
        return len(self._episodes)

    def clear(self) -> None:
        self._episodes = []
        self._save()

    @staticmethod
    def _derive_time_bucket(timestamp: float) -> str:
        hour = time.localtime(timestamp).tm_hour
        if 5 <= hour < 12:
            return "morning"
        if 12 <= hour < 17:
            return "afternoon"
        if 17 <= hour < 22:
            return "evening"
        return "night"

    def _score_episode(
        self,
        ep: EpisodeEntry,
        *,
        query_tokens: set[str],
        author: str | None,
        time_bucket: str | None,
        scene_name: str | None,
        room_name: str | None,
        nearby_objects: list[str] | None,
        now: float,
    ) -> float:
        doc_tokens = set((ep.user_text + " " + ep.ai_response).lower().split())
        overlap = len(query_tokens & doc_tokens)
        continuity_match = bool(author) and (ep.author == author or ep.related_viewer == author)

        if overlap == 0 and not continuity_match:
            return 0.0

        base_score = overlap * 1.5
        if continuity_match:
            base_score += 0.75
        base_score += max(0, ep.importance - 5) * 0.15

        freshness_factor = self._freshness_factor(ep.timestamp, now)
        access_boost = min(1.25, 1.0 + ep.access_count * 0.05)
        time_boost = 1.05 if time_bucket and ep.time_bucket == time_bucket else 1.0
        scene_boost = 1.08 if scene_name and ep.scene_name == scene_name else 1.0
        room_boost = 1.08 if room_name and ep.room_name == room_name else 1.0
        object_boost = self._nearby_object_boost(ep.nearby_objects, nearby_objects)
        source_boost = 1.05 if ep.source_type == "conversation" and continuity_match else 1.0
        arousal_boost = 1.0 + min(max(ep.arousal, 0.0), 1.0) * 0.1

        return (
            base_score
            * freshness_factor
            * access_boost
            * time_boost
            * scene_boost
            * room_boost
            * object_boost
            * source_boost
            * arousal_boost
        )

    @staticmethod
    def _normalize_nearby_objects(items: list[str] | None) -> list[str]:
        normalized: list[str] = []
        seen: set[str] = set()
        for item in items or []:
            token = str(item).strip().lower()
            if not token or token in seen:
                continue
            seen.add(token)
            normalized.append(token)
        return normalized[:5]

    @classmethod
    def _nearby_object_boost(
        cls,
        episode_objects: list[str],
        current_objects: list[str] | None,
    ) -> float:
        current = set(cls._normalize_nearby_objects(current_objects))
        if not current:
            return 1.0
        episode = set(cls._normalize_nearby_objects(episode_objects))
        overlap = len(current & episode)
        if overlap <= 0:
            return 1.0
        return min(1.12, 1.0 + overlap * 0.04)

    @staticmethod
    def _freshness_factor(timestamp: float, now: float) -> float:
        age_days = max(0.0, now - timestamp) / 86400.0
        freshness = math.exp(-math.log(2.0) * age_days / _HALF_LIFE_DAYS)
        # FR-MEM-DECAY-01: floor lowered from 0.7 → 0.3 so old memories
        # genuinely fade rather than forever dominating retrieval.
        return 0.3 + freshness * 0.7

    def _touch_recalled_episodes(self, episodes: list[EpisodeEntry], now: float) -> None:
        for ep in episodes:
            ep.access_count += 1
            ep.last_accessed = now
        self._save()
