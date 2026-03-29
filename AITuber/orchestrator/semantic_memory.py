"""Semantic memory — durable viewer and topic facts extracted from episodes.

FR-MEMORY-SEM-01: Runtime memory stores compact, durable facts distinct from
episodic traces so repeated interactions influence future replies without
injecting large transcript fragments.
"""

from __future__ import annotations

import json
import logging
import re
import time
import uuid
from dataclasses import asdict, dataclass
from pathlib import Path

logger = logging.getLogger(__name__)

_DEFAULT_STORE_PATH = Path(__file__).parent.parent / "config" / "semantic_memory.jsonl"
_STOPWORDS: frozenset[str] = frozenset(
    {
        "です",
        "ます",
        "した",
        "する",
        "いる",
        "ある",
        "こと",
        "これ",
        "それ",
        "今日",
        "昨日",
        "配信",
        "話",
        "続き",
        "ありがとう",
        "please",
        "about",
        "with",
        "have",
        "that",
        "this",
    }
)
_TOPIC_PATTERN = re.compile(r"[A-Za-z][A-Za-z0-9_+-]{2,}|[一-龠ぁ-んァ-ヴー]{2,}")


def extract_topics(text: str) -> list[str]:
    """Extract compact topic tokens from free text.

    FR-MEMORY-SEM-01: shared deterministic topic extraction for runtime memory
    layers so semantic and goal memory react to the same repeated themes.
    """

    topics: list[str] = []
    for match in _TOPIC_PATTERN.findall(text.lower()):
        token = match.strip("-_+")
        if len(token) < 2 or token in _STOPWORDS:
            continue
        topics.append(token)
    seen: set[str] = set()
    ordered_topics: list[str] = []
    for topic in topics:
        if topic in seen:
            continue
        seen.add(topic)
        ordered_topics.append(topic)
    return ordered_topics


_CONFIDENCE_HALF_LIFE_DAYS = 30.0


@dataclass
class SemanticFact:
    """A compact durable fact distilled from repeated interactions."""

    fact_id: str
    category: str
    subject: str
    value: str
    mention_count: int
    confidence: float
    last_updated: float
    evidence_ids: list[str] | None = None
    last_contradicted: float = 0.0

    def effective_confidence(self, now: float) -> float:
        """FR-MEM-DECAY-01: time-decayed confidence.

        Confidence decays with a 30-day half-life from *last_updated*.
        A recent contradiction accelerates the decay.
        """
        import math

        age_days = max(0.0, now - self.last_updated) / 86400.0
        decay = math.exp(-math.log(2.0) * age_days / _CONFIDENCE_HALF_LIFE_DAYS)
        base = self.confidence * decay
        if self.last_contradicted > 0:
            contra_age = max(0.0, now - self.last_contradicted) / 86400.0
            if contra_age < 7.0:
                base *= 0.5
        return round(min(0.95, max(0.0, base)), 4)

    def to_dict(self) -> dict:
        d = asdict(self)
        if not d.get("evidence_ids"):
            d.pop("evidence_ids", None)
        if not d.get("last_contradicted"):
            d.pop("last_contradicted", None)
        return d

    @classmethod
    def from_dict(cls, data: dict) -> SemanticFact:
        return cls(
            fact_id=str(data.get("fact_id", uuid.uuid4().hex[:12])),
            category=str(data.get("category", "")),
            subject=str(data.get("subject", "")),
            value=str(data.get("value", "")),
            mention_count=int(data.get("mention_count", 1) or 1),
            confidence=float(data.get("confidence", 0.5) or 0.5),
            last_updated=float(data.get("last_updated", 0.0) or 0.0),
            evidence_ids=list(data.get("evidence_ids") or []) or None,
            last_contradicted=float(data.get("last_contradicted", 0.0) or 0.0),
        )


class SemanticMemory:
    """Persistent durable facts for runtime prompts.

    Initial M27 scope keeps facts intentionally small:
    - viewer familiarity tiers
    - repeated viewer-specific topic interests
    """

    def __init__(
        self,
        path: Path | str | None = None,
        *,
        time_fn: callable | None = None,
    ) -> None:
        self._path = Path(path) if path else _DEFAULT_STORE_PATH
        self._time_fn = time_fn or time.time
        self._facts: list[SemanticFact] = []
        self._load()

    @property
    def count(self) -> int:
        return len(self._facts)

    def get_facts(
        self,
        *,
        category: str | None = None,
        subject: str | None = None,
    ) -> list[SemanticFact]:
        facts = self._facts
        if category is not None:
            facts = [fact for fact in facts if fact.category == category]
        if subject is not None:
            facts = [fact for fact in facts if fact.subject == subject]
        return list(facts)

    def get_viewer_profile(self, author: str) -> SemanticFact | None:
        return next(
            (
                fact
                for fact in self._facts
                if fact.category == "viewer_profile" and fact.subject == author
            ),
            None,
        )

    def familiarity_score(self, author: str) -> int:
        profile = self.get_viewer_profile(author)
        if profile is None:
            return 0
        return self._familiarity_score(profile.value)

    def observe_conversation(
        self,
        *,
        author: str,
        user_text: str,
        ai_response: str = "",
        episode_id: str = "",
    ) -> None:
        now = float(self._time_fn())
        self._upsert_viewer_profile(author, now)
        for topic in extract_topics(user_text):
            self._upsert_topic_interest(author, topic, now, episode_id=episode_id)
        if ai_response:
            for topic in extract_topics(ai_response):
                self._upsert_topic_interest(
                    author, topic, now, confidence_step=0.03, episode_id=episode_id
                )
        self._save()

    def to_prompt_fragment(
        self,
        *,
        author: str,
        query: str = "",
        top_k: int = 4,
        exclude_topics: list[str] | None = None,
    ) -> str:
        lines: list[str] = []
        profile = next(
            (
                fact
                for fact in self._facts
                if fact.category == "viewer_profile" and fact.subject == author
            ),
            None,
        )
        if profile is not None:
            lines.append(f"{author} は {profile.value} 寄りの視聴者で、会話の連続性を期待できる")

        now = float(self._time_fn())
        query_topics = set(extract_topics(query))
        excluded_tokens = self._normalize_excluded_topics(exclude_topics)
        topic_facts = self.get_facts(category="viewer_interest", subject=author)
        topic_facts = [fact for fact in topic_facts if fact.mention_count >= 2]
        topic_facts = [
            fact
            for fact in topic_facts
            if not self._topic_is_excluded(fact.value, excluded_tokens)
        ]
        if query_topics:
            topic_facts.sort(
                key=lambda fact: (
                    1 if fact.value in query_topics else 0,
                    fact.mention_count,
                    fact.effective_confidence(now),
                ),
                reverse=True,
            )
        else:
            topic_facts.sort(
                key=lambda fact: (fact.mention_count, fact.effective_confidence(now)),
                reverse=True,
            )

        for fact in topic_facts[:top_k]:
            if fact.value in query_topics:
                lines.append(f"{author} は {fact.value} の話題を繰り返し持ち込みやすい")
            else:
                lines.append(f"{author} は {fact.value} に継続的な関心がある")

        if not lines:
            return ""
        return "[FACTS]\n" + "\n".join(lines)

    def to_overview_fragment(
        self,
        *,
        top_k: int = 3,
        exclude_topics: list[str] | None = None,
    ) -> str:
        """Return a compact global facts summary for narrative synthesis.

        FR-MEMORY-SEM-01: summary stays short and focuses on repeated themes
        that should influence narrative continuity rather than single replies.
        """

        excluded_tokens = self._normalize_excluded_topics(exclude_topics)
        topic_facts = [
            fact
            for fact in self._facts
            if fact.category == "viewer_interest"
            and fact.mention_count >= 2
            and not self._topic_is_excluded(fact.value, excluded_tokens)
        ]
        topic_facts.sort(
            key=lambda fact: (fact.mention_count, fact.confidence, fact.last_updated),
            reverse=True,
        )
        lines: list[str] = []
        for fact in topic_facts[:top_k]:
            lines.append(f"{fact.subject} は {fact.value} の話題を継続している")
        if not lines:
            return ""
        return "[FACTS]\n" + "\n".join(lines)

    @staticmethod
    def _normalize_excluded_topics(topics: list[str] | None) -> set[str]:
        excluded: set[str] = set()
        for topic in topics or []:
            excluded.update(extract_topics(topic))
        return excluded

    @staticmethod
    def _topic_is_excluded(topic: str, excluded_tokens: set[str]) -> bool:
        if not excluded_tokens:
            return False
        topic_tokens = set(extract_topics(topic)) or {topic.lower()}
        return not topic_tokens.isdisjoint(excluded_tokens)

    def clear(self) -> None:
        self._facts = []
        self._save()

    def _load(self) -> None:
        if not self._path.exists():
            return
        loaded: list[SemanticFact] = []
        try:
            for line in self._path.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if not line:
                    continue
                try:
                    loaded.append(SemanticFact.from_dict(json.loads(line)))
                except (json.JSONDecodeError, TypeError, ValueError):
                    logger.debug("Skipping malformed semantic fact line")
        except OSError as exc:
            logger.warning("Failed to load semantic memory: %s", exc)
        self._facts = loaded

    def _save(self) -> None:
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            with self._path.open("w", encoding="utf-8") as fh:
                for fact in self._facts:
                    fh.write(json.dumps(fact.to_dict(), ensure_ascii=False) + "\n")
        except OSError as exc:
            logger.warning("Failed to save semantic memory: %s", exc)

    def _upsert_viewer_profile(self, author: str, now: float) -> None:
        fact = next(
            (
                item
                for item in self._facts
                if item.category == "viewer_profile" and item.subject == author
            ),
            None,
        )
        interactions = 1 if fact is None else fact.mention_count + 1
        value = self._familiarity_from_count(interactions)
        confidence = min(0.95, 0.45 + interactions * 0.08)
        if fact is None:
            self._facts.append(
                SemanticFact(
                    fact_id=uuid.uuid4().hex[:12],
                    category="viewer_profile",
                    subject=author,
                    value=value,
                    mention_count=interactions,
                    confidence=confidence,
                    last_updated=now,
                )
            )
            return
        fact.value = value
        fact.mention_count = interactions
        fact.confidence = confidence
        fact.last_updated = now

    def _upsert_topic_interest(
        self,
        author: str,
        topic: str,
        now: float,
        *,
        confidence_step: float = 0.06,
        episode_id: str = "",
    ) -> None:
        fact = self._find_fact("viewer_interest", author, topic)
        if fact is None:
            self._facts.append(
                SemanticFact(
                    fact_id=uuid.uuid4().hex[:12],
                    category="viewer_interest",
                    subject=author,
                    value=topic,
                    mention_count=1,
                    confidence=0.35,
                    last_updated=now,
                    evidence_ids=[episode_id] if episode_id else None,
                )
            )
            return
        fact.mention_count += 1
        fact.confidence = min(0.95, fact.confidence + confidence_step)
        fact.last_updated = now
        if episode_id:
            if fact.evidence_ids is None:
                fact.evidence_ids = []
            if episode_id not in fact.evidence_ids:
                fact.evidence_ids.append(episode_id)
                # Keep bounded to avoid unbounded growth
                if len(fact.evidence_ids) > 20:
                    fact.evidence_ids = fact.evidence_ids[-20:]

    def _find_fact(self, category: str, subject: str, value: str) -> SemanticFact | None:
        for fact in self._facts:
            if fact.category == category and fact.subject == subject and fact.value == value:
                return fact
        return None

    @staticmethod
    def _familiarity_from_count(interactions: int) -> str:
        if interactions >= 15:
            return "superchatter"
        if interactions >= 3:
            return "regular"
        return "newcomer"

    @staticmethod
    def _familiarity_score(value: str) -> int:
        if value == "superchatter":
            return 2
        if value == "regular":
            return 1
        return 0
