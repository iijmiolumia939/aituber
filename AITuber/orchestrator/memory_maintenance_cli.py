"""memory_maintenance_cli: post-stream runtime memory consolidation.

M29 scope keeps maintenance outside latency-sensitive reply and scheduler paths.
It operates on persisted JSONL stores only, supporting inspectable dry-run output
and conservative apply-time consolidation.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import time
import uuid
from collections import defaultdict
from dataclasses import asdict, dataclass
from pathlib import Path

from orchestrator.episodic_store import EpisodeEntry
from orchestrator.goal_memory import GoalEntry, GoalMemory
from orchestrator.semantic_memory import SemanticFact, SemanticMemory, extract_topics

logger = logging.getLogger(__name__)

_DEFAULT_EPISODIC = Path(__file__).parent.parent / "config" / "episodic_memory.jsonl"
_DEFAULT_SEMANTIC = Path(__file__).parent.parent / "config" / "semantic_memory.jsonl"
_DEFAULT_GOALS = Path(__file__).parent.parent / "config" / "goal_memory.jsonl"
_DEFAULT_STALE_DAYS = 14.0
_DEFAULT_STALE_IMPORTANCE = 4
_DEFAULT_STALE_AROUSAL = 0.35
_DEFAULT_MERGE_WINDOW_HOURS = 6.0


@dataclass
class MaintenanceReport:
    dry_run: bool
    active_episode_count_before: int
    active_episode_count_after: int
    merged_episode_groups: int
    merged_episode_count: int
    archived_episode_count: int
    semantic_facts_added: int
    goal_entries_added: int
    archive_path: str

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="memory_maintenance_cli",
        description="Consolidate episodic/semantic/goal memory stores after a stream.",
    )
    parser.add_argument(
        "--episodic",
        default=str(_DEFAULT_EPISODIC),
        metavar="JSONL",
        help="Path to episodic memory JSONL.",
    )
    parser.add_argument(
        "--semantic",
        default=str(_DEFAULT_SEMANTIC),
        metavar="JSONL",
        help="Path to semantic memory JSONL.",
    )
    parser.add_argument(
        "--goals",
        default=str(_DEFAULT_GOALS),
        metavar="JSONL",
        help="Path to goal memory JSONL.",
    )
    parser.add_argument(
        "--archive",
        default=None,
        metavar="JSONL",
        help="Archive path for stale episodes (default: alongside episodic store).",
    )
    parser.add_argument(
        "--stale-days",
        type=float,
        default=_DEFAULT_STALE_DAYS,
        metavar="DAYS",
        help="Archive low-signal episodes older than this many days (default: 14).",
    )
    parser.add_argument(
        "--stale-importance",
        type=int,
        default=_DEFAULT_STALE_IMPORTANCE,
        metavar="N",
        help="Maximum importance eligible for archival (default: 4).",
    )
    parser.add_argument(
        "--stale-arousal",
        type=float,
        default=_DEFAULT_STALE_AROUSAL,
        metavar="FLOAT",
        help="Maximum arousal eligible for archival (default: 0.35).",
    )
    parser.add_argument(
        "--merge-window-hours",
        type=float,
        default=_DEFAULT_MERGE_WINDOW_HOURS,
        metavar="HOURS",
        help="Merge duplicate episode bursts within this window (default: 6).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        default=False,
        help="Inspect changes without writing files.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        default=False,
        help="Print the final report as compact JSON.",
    )
    return parser


class MemoryMaintenanceCLI:
    """Conservative post-stream consolidation for runtime memory stores."""

    def __init__(
        self,
        *,
        episodic_path: str,
        semantic_path: str,
        goal_path: str,
        archive_path: str | None = None,
        stale_days: float = _DEFAULT_STALE_DAYS,
        stale_importance: int = _DEFAULT_STALE_IMPORTANCE,
        stale_arousal: float = _DEFAULT_STALE_AROUSAL,
        merge_window_hours: float = _DEFAULT_MERGE_WINDOW_HOURS,
        dry_run: bool = False,
        time_fn: callable | None = None,
    ) -> None:
        self.episodic_path = Path(episodic_path)
        self.semantic_path = Path(semantic_path)
        self.goal_path = Path(goal_path)
        self.archive_path = (
            Path(archive_path)
            if archive_path
            else self.episodic_path.with_name(f"{self.episodic_path.stem}.archive.jsonl")
        )
        self.stale_days = stale_days
        self.stale_importance = stale_importance
        self.stale_arousal = stale_arousal
        self.merge_window_seconds = max(0.0, merge_window_hours) * 3600.0
        self.dry_run = dry_run
        self._time_fn = time_fn or time.time

    def run(self) -> MaintenanceReport:
        now = float(self._time_fn())
        episodes = self._load_episode_entries(self.episodic_path)
        semantic = SemanticMemory(path=self.semantic_path, time_fn=self._time_fn)
        goals = GoalMemory(path=self.goal_path, time_fn=self._time_fn)

        merged_episodes, merged_groups, merged_removed = self._merge_duplicate_episodes(episodes)
        active_episodes, archived_episodes = self._split_archived_episodes(
            merged_episodes,
            now=now,
        )
        semantic_added = self._promote_semantic_facts(archived_episodes, semantic, now=now)
        goal_added = self._promote_goals(archived_episodes, goals, now=now)

        report = MaintenanceReport(
            dry_run=self.dry_run,
            active_episode_count_before=len(episodes),
            active_episode_count_after=len(active_episodes),
            merged_episode_groups=merged_groups,
            merged_episode_count=merged_removed,
            archived_episode_count=len(archived_episodes),
            semantic_facts_added=semantic_added,
            goal_entries_added=goal_added,
            archive_path=str(self.archive_path),
        )

        if not self.dry_run:
            active_payload = self._serialize_episode_entries(active_episodes)
            archive_payload = ""
            if archived_episodes:
                existing_archive = self._load_episode_entries(self.archive_path)
                archive_payload = self._serialize_episode_entries(
                    [*existing_archive, *archived_episodes]
                )
            semantic_payload = self._serialize_semantic_facts(semantic.get_facts())
            goal_payload = self._serialize_goal_entries(goals.get_goals())

            # Keep the active episodic store as the last replacement so a downstream
            # write failure cannot drop the only copy of an episode.
            if archived_episodes:
                self._write_text_atomically(self.archive_path, archive_payload)
            self._write_text_atomically(self.semantic_path, semantic_payload)
            self._write_text_atomically(self.goal_path, goal_payload)
            self._write_text_atomically(self.episodic_path, active_payload)

        return report

    @staticmethod
    def _load_episode_entries(path: Path) -> list[EpisodeEntry]:
        if not path.exists():
            return []
        loaded: list[EpisodeEntry] = []
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                loaded.append(EpisodeEntry.from_dict(json.loads(line)))
            except (json.JSONDecodeError, TypeError, ValueError):
                logger.debug("Skipping malformed episode during maintenance")
        return loaded

    @staticmethod
    def _serialize_episode_entries(episodes: list[EpisodeEntry]) -> str:
        if not episodes:
            return ""
        return "".join(
            json.dumps(episode.to_dict(), ensure_ascii=False) + "\n" for episode in episodes
        )

    @staticmethod
    def _serialize_semantic_facts(facts: list[SemanticFact]) -> str:
        if not facts:
            return ""
        return "".join(json.dumps(fact.to_dict(), ensure_ascii=False) + "\n" for fact in facts)

    @staticmethod
    def _serialize_goal_entries(goals: list[GoalEntry]) -> str:
        if not goals:
            return ""
        return "".join(json.dumps(goal.to_dict(), ensure_ascii=False) + "\n" for goal in goals)

    @staticmethod
    def _write_text_atomically(path: Path, payload: str) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        temp_path = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
        try:
            temp_path.write_text(payload, encoding="utf-8")
            os.replace(temp_path, path)
        finally:
            if temp_path.exists():
                temp_path.unlink(missing_ok=True)

    @staticmethod
    def _normalize_text(text: str) -> str:
        return " ".join(text.lower().split())

    @classmethod
    def _episode_fingerprint(cls, episode: EpisodeEntry) -> tuple[str, ...]:
        return (
            episode.author,
            episode.source_type,
            cls._normalize_text(episode.user_text),
            episode.activity_type,
            episode.outcome,
            episode.scene_name,
            episode.room_name,
            episode.related_viewer,
            episode.time_bucket,
        )

    @classmethod
    def _responses_are_mergeable(cls, left: str, right: str) -> bool:
        left_normalized = cls._normalize_text(left)
        right_normalized = cls._normalize_text(right)
        if left_normalized == right_normalized:
            return True
        return left_normalized in right_normalized or right_normalized in left_normalized

    def _merge_duplicate_episodes(
        self,
        episodes: list[EpisodeEntry],
    ) -> tuple[list[EpisodeEntry], int, int]:
        if not episodes:
            return [], 0, 0

        merged: list[EpisodeEntry] = []
        trackers: dict[tuple[str, ...], dict[str, object]] = {}
        merged_groups = 0
        merged_removed = 0

        for episode in sorted(episodes, key=lambda item: item.timestamp):
            key = self._episode_fingerprint(episode)
            tracker = trackers.get(key)
            if tracker is None:
                merged.append(episode)
                trackers[key] = {"anchor": episode, "last_timestamp": episode.timestamp, "size": 1}
                continue

            last_timestamp = float(tracker["last_timestamp"])
            if episode.timestamp - last_timestamp > self.merge_window_seconds:
                merged.append(episode)
                trackers[key] = {"anchor": episode, "last_timestamp": episode.timestamp, "size": 1}
                continue

            anchor = tracker["anchor"]
            if not self._responses_are_mergeable(anchor.ai_response, episode.ai_response):
                merged.append(episode)
                trackers[key] = {"anchor": episode, "last_timestamp": episode.timestamp, "size": 1}
                continue
            if int(tracker["size"]) == 1:
                merged_groups += 1
            self._merge_episode(anchor, episode)
            tracker["last_timestamp"] = episode.timestamp
            tracker["size"] = int(tracker["size"]) + 1
            merged_removed += 1

        merged.sort(key=lambda item: item.timestamp)
        return merged, merged_groups, merged_removed

    @classmethod
    def _merge_episode(cls, anchor: EpisodeEntry, duplicate: EpisodeEntry) -> None:
        anchor.timestamp = min(anchor.timestamp, duplicate.timestamp)
        anchor.importance = max(anchor.importance, duplicate.importance)
        anchor.arousal = max(anchor.arousal, duplicate.arousal)
        anchor.user_text = (
            anchor.user_text
            if len(anchor.user_text) >= len(duplicate.user_text)
            else duplicate.user_text
        )
        anchor.ai_response = (
            anchor.ai_response
            if len(anchor.ai_response) >= len(duplicate.ai_response)
            else duplicate.ai_response
        )
        anchor.last_accessed = max(anchor.last_accessed, duplicate.last_accessed)
        anchor.access_count += duplicate.access_count
        anchor.emotion_tags = cls._merge_lists(
            anchor.emotion_tags,
            duplicate.emotion_tags,
        )
        anchor.nearby_objects = cls._merge_lists(
            anchor.nearby_objects,
            duplicate.nearby_objects,
        )[:5]

    @staticmethod
    def _merge_lists(left: list[str], right: list[str]) -> list[str]:
        merged: list[str] = []
        seen: set[str] = set()
        for item in [*left, *right]:
            token = str(item).strip()
            if not token or token in seen:
                continue
            seen.add(token)
            merged.append(token)
        return merged

    def _split_archived_episodes(
        self,
        episodes: list[EpisodeEntry],
        *,
        now: float,
    ) -> tuple[list[EpisodeEntry], list[EpisodeEntry]]:
        active: list[EpisodeEntry] = []
        archived: list[EpisodeEntry] = []
        for episode in episodes:
            if self._should_archive(episode, now=now):
                archived.append(episode)
            else:
                active.append(episode)
        return active, archived

    def _should_archive(self, episode: EpisodeEntry, *, now: float) -> bool:
        age_days = max(0.0, now - episode.timestamp) / 86400.0
        if age_days < self.stale_days:
            return False
        if episode.access_count > 0 or episode.last_accessed > 0:
            return False
        if episode.importance > self.stale_importance:
            return False
        if episode.arousal > self.stale_arousal:
            return False
        return not self._viewer_identity(episode)

    @staticmethod
    def _viewer_identity(episode: EpisodeEntry) -> str:
        if episode.related_viewer:
            return episode.related_viewer
        if episode.source_type == "conversation":
            return episode.author
        return ""

    @staticmethod
    def _episode_topics(episode: EpisodeEntry) -> list[str]:
        return extract_topics(f"{episode.user_text}\n{episode.ai_response}")

    def _promote_semantic_facts(
        self,
        archived_episodes: list[EpisodeEntry],
        semantic: SemanticMemory,
        *,
        now: float,
    ) -> int:
        if not archived_episodes:
            return 0

        added = 0
        conversations_by_author: dict[str, int] = defaultdict(int)
        topics_by_author: dict[tuple[str, str], int] = defaultdict(int)
        existing_profiles = {
            fact.subject for fact in semantic.get_facts(category="viewer_profile") if fact.subject
        }
        existing_topics = {
            (fact.subject, fact.value) for fact in semantic.get_facts(category="viewer_interest")
        }

        for episode in archived_episodes:
            if not episode.author:
                continue
            conversations_by_author[episode.author] += 1
            for topic in self._episode_topics(episode):
                topics_by_author[(episode.author, topic)] += 1

        for author, count in conversations_by_author.items():
            if author in existing_profiles:
                continue
            semantic._facts.append(
                SemanticFact(
                    fact_id=uuid.uuid4().hex[:12],
                    category="viewer_profile",
                    subject=author,
                    value=SemanticMemory._familiarity_from_count(count),
                    mention_count=count,
                    confidence=min(0.95, 0.45 + count * 0.08),
                    last_updated=now,
                )
            )
            added += 1

        for (author, topic), count in sorted(topics_by_author.items()):
            if count < 2 or (author, topic) in existing_topics:
                continue
            semantic._facts.append(
                SemanticFact(
                    fact_id=uuid.uuid4().hex[:12],
                    category="viewer_interest",
                    subject=author,
                    value=topic,
                    mention_count=count,
                    confidence=min(0.95, 0.29 + count * 0.06),
                    last_updated=now,
                )
            )
            added += 1

        return added

    def _promote_goals(
        self,
        archived_episodes: list[EpisodeEntry],
        goals: GoalMemory,
        *,
        now: float,
    ) -> int:
        if not archived_episodes:
            return 0

        added = 0
        topic_counts: dict[str, int] = defaultdict(int)
        existing_values = {goal.value for goal in goals.get_goals()}

        for episode in archived_episodes:
            for topic in self._episode_topics(episode):
                topic_counts[topic] += 1

        for topic, count in sorted(topic_counts.items()):
            if count < 3 or topic in existing_values:
                continue
            goals._goals.append(
                GoalEntry(
                    goal_id=uuid.uuid4().hex[:12],
                    category="topic_goal",
                    subject="",
                    value=topic,
                    focus_type="learning",
                    status="active" if count >= 3 else "warming",
                    mention_count=count,
                    confidence=min(0.95, 0.24 + count * 0.16),
                    last_updated=now,
                )
            )
            added += 1

        return added


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(levelname)s:%(name)s:%(message)s")

    cli = MemoryMaintenanceCLI(
        episodic_path=args.episodic,
        semantic_path=args.semantic,
        goal_path=args.goals,
        archive_path=args.archive,
        stale_days=args.stale_days,
        stale_importance=args.stale_importance,
        stale_arousal=args.stale_arousal,
        merge_window_hours=args.merge_window_hours,
        dry_run=args.dry_run,
    )
    report = cli.run()

    if args.json:
        print(json.dumps(report.to_dict(), ensure_ascii=False, sort_keys=True))
    else:
        mode = "DRY-RUN" if report.dry_run else "APPLY"
        print(
            f"[{mode}] active {report.active_episode_count_before} "
            f"-> {report.active_episode_count_after}, "
            f"merged={report.merged_episode_count} ({report.merged_episode_groups} groups), "
            f"archived={report.archived_episode_count}, semantic+={report.semantic_facts_added}, "
            f"goals+={report.goal_entries_added}"
        )
        if report.archived_episode_count:
            print(f"Archive: {report.archive_path}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
