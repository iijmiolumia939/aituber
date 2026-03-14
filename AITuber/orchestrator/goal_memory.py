"""Goal memory — persistent medium-horizon themes for continuity.

FR-GOAL-MEM-01: Runtime memory keeps a compact set of active medium-horizon
goals distinct from short-lived scheduler drives, allowing repeated topics to
influence future replies, narrative synthesis, and autonomous life bias.
"""

from __future__ import annotations

import json
import logging
import time
import uuid
from dataclasses import asdict, dataclass
from pathlib import Path

from orchestrator.semantic_memory import extract_topics

logger = logging.getLogger(__name__)

_DEFAULT_STORE_PATH = Path(__file__).parent.parent / "config" / "goal_memory.jsonl"
_FOLLOW_UP_MARKERS: tuple[str, ...] = ("続き", "つづき", "また", "次回", "later", "follow up")


@dataclass
class GoalEntry:
    """A persistent medium-horizon goal distilled from repeated themes."""

    goal_id: str
    category: str
    subject: str
    value: str
    focus_type: str
    status: str
    mention_count: int
    confidence: float
    last_updated: float

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> GoalEntry:
        return cls(
            goal_id=str(data.get("goal_id", uuid.uuid4().hex[:12])),
            category=str(data.get("category", "topic_goal")),
            subject=str(data.get("subject", "")),
            value=str(data.get("value", "")),
            focus_type=str(data.get("focus_type", "learning")),
            status=str(data.get("status", "warming")),
            mention_count=int(data.get("mention_count", 1) or 1),
            confidence=float(data.get("confidence", 0.3) or 0.3),
            last_updated=float(data.get("last_updated", 0.0) or 0.0),
        )


class GoalMemory:
    """Persistent medium-horizon goals for runtime continuity.

    Initial M28 scope intentionally stays small: repeated conversation topics
    warm up into active "learning" goals that can bias reply prompts,
    narrative synthesis, and the life scheduler.
    """

    def __init__(
        self,
        path: Path | str | None = None,
        *,
        time_fn: callable | None = None,
    ) -> None:
        self._path = Path(path) if path else _DEFAULT_STORE_PATH
        self._time_fn = time_fn or time.time
        self._goals: list[GoalEntry] = []
        self._load()

    @property
    def count(self) -> int:
        return len(self._goals)

    def get_goals(
        self,
        *,
        status: str | None = None,
        focus_type: str | None = None,
        subject: str | None = None,
    ) -> list[GoalEntry]:
        goals = self._goals
        if status is not None:
            goals = [goal for goal in goals if goal.status == status]
        if focus_type is not None:
            goals = [goal for goal in goals if goal.focus_type == focus_type]
        if subject is not None:
            goals = [goal for goal in goals if goal.subject == subject]
        return list(goals)

    def observe_conversation(
        self,
        *,
        author: str,
        user_text: str,
        ai_response: str = "",
    ) -> None:
        """Update medium-horizon learning goals from repeated themes.

        FR-GOAL-MEM-01: repeated viewer topics become active goals that remain
        compact and interpretable.
        """

        now = float(self._time_fn())
        user_topics = extract_topics(user_text)
        response_topics = extract_topics(ai_response)
        for topic in user_topics:
            self._upsert_goal(
                category="topic_goal",
                subject="",
                value=topic,
                focus_type="learning",
                now=now,
                active_threshold=3,
            )
        if self._has_follow_up_signal(user_text, ai_response):
            for topic in self._shared_topics(user_topics, response_topics):
                self._upsert_goal(
                    category="follow_up_goal",
                    subject=author,
                    value=f"{topic} の続き",
                    focus_type="social",
                    now=now,
                    active_threshold=2,
                )
        self._save()

    def observe_behavior_result(
        self,
        *,
        behavior: str,
        success: bool,
        reason: str = "",
        room_name: str = "",
    ) -> None:
        """Update medium-horizon goals from autonomous behavior outcomes.

        FR-GOAL-MEM-01: non-conversation events also shape continuity so the
        avatar can keep a stable sense of what to deepen or stabilise.
        """

        del room_name

        now = float(self._time_fn())
        goal_spec = self._goal_from_behavior(behavior=behavior, success=success, reason=reason)
        if goal_spec is None:
            return
        self._upsert_goal(now=now, **goal_spec)
        self._save()

    def current_goal(self, *, author: str = "", familiarity_score: int = 0) -> GoalEntry | None:
        goals = self._prioritized_goals(author=author)
        active = [goal for goal in goals if goal.status == "active"]
        candidates = active if active else goals
        if not candidates:
            return None
        return max(
            candidates,
            key=lambda goal: self._sort_key(
                goal,
                query_topics=set(),
                author=author,
                familiarity_score=familiarity_score,
            ),
        )

    def to_prompt_fragment(
        self,
        *,
        author: str = "",
        query: str = "",
        top_k: int = 2,
        familiarity_score: int = 0,
    ) -> str:
        query_topics = set(extract_topics(query))
        goals = self._prioritized_goals(author=author)
        goals.sort(
            key=lambda goal: self._sort_key(
                goal,
                query_topics=query_topics,
                author=author,
                familiarity_score=familiarity_score,
            ),
            reverse=True,
        )
        if author:
            author_follow_ups = [
                goal
                for goal in goals
                if goal.category == "follow_up_goal" and goal.subject == author
            ]
            if author_follow_ups and familiarity_score >= 1:
                goals = author_follow_ups
        lines: list[str] = []
        for goal in goals[:top_k]:
            lines.append(self._goal_line(goal))
        if not lines:
            return ""
        return "[GOALS]\n" + "\n".join(lines)

    def to_idle_hint(self) -> str:
        goal = self.current_goal()
        if goal is None:
            return ""
        return self._goal_line(goal)

    def top_goal_lines(
        self,
        *,
        author: str = "",
        top_k: int = 2,
        familiarity_score: int = 0,
    ) -> list[str]:
        goals = self._prioritized_goals(author=author)
        goals.sort(
            key=lambda goal: self._sort_key(
                goal,
                query_topics=set(),
                author=author,
                familiarity_score=familiarity_score,
            ),
            reverse=True,
        )
        return [self._goal_line(goal) for goal in goals[:top_k]]

    def top_goal_values(
        self,
        *,
        author: str = "",
        top_k: int = 2,
        familiarity_score: int = 0,
    ) -> list[str]:
        goals = self._prioritized_goals(author=author)
        goals.sort(
            key=lambda goal: self._sort_key(
                goal,
                query_topics=set(),
                author=author,
                familiarity_score=familiarity_score,
            ),
            reverse=True,
        )
        return [goal.value for goal in goals[:top_k]]

    def get_scheduler_focus(self) -> tuple[str, str | None]:
        goal = self.current_goal()
        if goal is None:
            return "", None
        if goal.category == "follow_up_goal":
            return f"{goal.value} を拾い直したい", goal.focus_type
        return f"{goal.value} を深めたい", goal.focus_type

    def _load(self) -> None:
        if not self._path.exists():
            return
        loaded: list[GoalEntry] = []
        try:
            for line in self._path.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if not line:
                    continue
                try:
                    loaded.append(GoalEntry.from_dict(json.loads(line)))
                except (json.JSONDecodeError, TypeError, ValueError):
                    logger.debug("Skipping malformed goal memory line")
        except OSError as exc:
            logger.warning("Failed to load goal memory: %s", exc)
        self._goals = loaded

    def _save(self) -> None:
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            with self._path.open("w", encoding="utf-8") as fh:
                for goal in self._goals:
                    fh.write(json.dumps(goal.to_dict(), ensure_ascii=False) + "\n")
        except OSError as exc:
            logger.warning("Failed to save goal memory: %s", exc)

    def _upsert_goal(
        self,
        *,
        category: str,
        subject: str,
        value: str,
        focus_type: str,
        now: float,
        active_threshold: int,
    ) -> None:
        goal = next(
            (
                item
                for item in self._goals
                if item.category == category and item.subject == subject and item.value == value
            ),
            None,
        )
        mention_count = 1 if goal is None else goal.mention_count + 1
        confidence = min(0.95, 0.24 + mention_count * 0.16)
        status = "active" if mention_count >= active_threshold else "warming"
        if goal is None:
            self._goals.append(
                GoalEntry(
                    goal_id=uuid.uuid4().hex[:12],
                    category=category,
                    subject=subject,
                    value=value,
                    focus_type=focus_type,
                    status=status,
                    mention_count=mention_count,
                    confidence=confidence,
                    last_updated=now,
                )
            )
            return
        goal.mention_count = mention_count
        goal.confidence = confidence
        goal.status = status
        goal.last_updated = now

    @staticmethod
    def _goal_from_behavior(
        *,
        behavior: str,
        success: bool,
        reason: str,
    ) -> dict[str, str | int] | None:
        behavior_lc = behavior.lower()
        reason_lc = reason.lower()

        if not success:
            if reason_lc == "locomotion_blocked":
                return {
                    "category": "maintenance_goal",
                    "subject": "",
                    "value": "移動の安定性",
                    "focus_type": "exploration",
                    "active_threshold": 2,
                }
            if reason_lc == "interrupted":
                return {
                    "category": "maintenance_goal",
                    "subject": "",
                    "value": "行動の継続性",
                    "focus_type": "social",
                    "active_threshold": 2,
                }
            return {
                "category": "maintenance_goal",
                "subject": "",
                "value": "行動の完遂性",
                "focus_type": "learning",
                "active_threshold": 2,
            }

        if any(token in behavior_lc for token in ("stream", "chat", "talk", "reply")):
            return {
                "category": "behavior_goal",
                "subject": "",
                "value": "会話と配信の流れ",
                "focus_type": "social",
                "active_threshold": 2,
            }
        if any(token in behavior_lc for token in ("walk", "move", "room", "bed", "desk")):
            return {
                "category": "behavior_goal",
                "subject": "",
                "value": "部屋の移動と探索",
                "focus_type": "exploration",
                "active_threshold": 2,
            }
        return None

    @staticmethod
    def _has_follow_up_signal(user_text: str, ai_response: str) -> bool:
        combined = f"{user_text}\n{ai_response}".lower()
        return any(marker in combined for marker in _FOLLOW_UP_MARKERS)

    @staticmethod
    def _shared_topics(user_topics: list[str], response_topics: list[str]) -> list[str]:
        if not response_topics:
            return user_topics[:2]
        response_topic_set = set(response_topics)
        shared = [topic for topic in user_topics if topic in response_topic_set]
        return shared or user_topics[:2]

    @staticmethod
    def _goal_matches_query(goal: GoalEntry, query_topics: set[str]) -> int:
        return 1 if any(topic in goal.value for topic in query_topics) else 0

    @staticmethod
    def _subject_matches(goal: GoalEntry, author: str, familiarity_score: int) -> int:
        if not author:
            return 0
        return 1 + familiarity_score if goal.subject == author else 0

    def _prioritized_goals(self, *, author: str = "") -> list[GoalEntry]:
        goals = list(self._goals)
        if not author:
            return goals
        author_goals = [goal for goal in goals if goal.subject == author]
        global_goals = [goal for goal in goals if goal.subject != author]
        return author_goals + global_goals

    def _sort_key(
        self,
        goal: GoalEntry,
        *,
        query_topics: set[str],
        author: str,
        familiarity_score: int,
    ) -> tuple:
        return (
            self._subject_matches(goal, author, familiarity_score),
            self._goal_matches_query(goal, query_topics),
            goal.status == "active",
            goal.mention_count,
            goal.confidence,
            goal.last_updated,
        )

    @staticmethod
    def _goal_line(goal: GoalEntry) -> str:
        prefix = "今は" if goal.status == "active" else "最近は"
        if goal.category == "follow_up_goal":
            return f"{prefix} {goal.value} を拾い直したい"
        return f"{prefix} {goal.value} をもう少し深めたい"
