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
import time
import uuid
from collections.abc import Callable
from dataclasses import asdict, dataclass
from pathlib import Path

logger = logging.getLogger(__name__)

_DEFAULT_STORE_PATH = Path(__file__).parent.parent / "config" / "episodic_memory.jsonl"
_DEFAULT_CAPACITY = 200  # max episodes kept in file (FIFO eviction)
_DEFAULT_TOP_K = 5  # default retrieval count


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
        )


class EpisodicStore:
    """Persistent episodic memory backed by JSONL.

    FR-E2-01, FR-E2-02.
    """

    def __init__(
        self,
        path: Path | str | None = None,
        capacity: int = _DEFAULT_CAPACITY,
    ) -> None:
        self._path = Path(path) if path else _DEFAULT_STORE_PATH
        self._capacity = capacity
        self._episodes: list[EpisodeEntry] = []
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

        ep = EpisodeEntry(
            episode_id=uuid.uuid4().hex[:12],
            timestamp=time.time(),
            author=author,
            user_text=user_text,
            ai_response=ai_response,
            importance=importance,
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

    def get_relevant(self, query: str, top_k: int = _DEFAULT_TOP_K) -> list[EpisodeEntry]:
        """Retrieve episodes most relevant to *query* using keyword overlap.

        FR-E2-02: Simple tf-style overlap (no vector index required for MVP).
        Higher-importance episodes are boosted.
        """
        if not self._episodes:
            return []
        query_tokens = set(query.lower().split())
        scored: list[tuple[float, EpisodeEntry]] = []
        for ep in self._episodes:
            doc_tokens = set((ep.user_text + " " + ep.ai_response).lower().split())
            overlap = len(query_tokens & doc_tokens)
            score = overlap * 1.0 + (ep.importance - 5) * 0.2
            scored.append((score, ep))
        scored.sort(key=lambda x: x[0], reverse=True)
        return [ep for _, ep in scored[:top_k] if _ > 0]

    def to_prompt_fragment(self, query: str | None = None, top_k: int = _DEFAULT_TOP_K) -> str:
        """Return a [MEMORY] block to inject into the LLM system prompt.

        FR-E2-01: Empty string if no relevant episodes.
        """
        episodes = self.get_relevant(query, top_k) if query else self.get_recent(top_k)
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
