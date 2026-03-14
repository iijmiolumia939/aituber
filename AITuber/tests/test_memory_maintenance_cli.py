"""Tests for orchestrator.memory_maintenance_cli.

TC-M29-01 to TC-M29-04.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from orchestrator.goal_memory import GoalMemory
from orchestrator.memory_maintenance_cli import MemoryMaintenanceCLI
from orchestrator.semantic_memory import SemanticMemory


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "\n".join(json.dumps(row, ensure_ascii=False) for row in rows) + "\n",
        encoding="utf-8",
    )


class TestMemoryMaintenanceCLI:
    def test_dry_run_reports_without_mutating_files(self, tmp_path: Path) -> None:
        """TC-M29-01: dry-run is inspectable and leaves JSONL files untouched."""
        episodic_path = tmp_path / "episodic_memory.jsonl"
        semantic_path = tmp_path / "semantic_memory.jsonl"
        goal_path = tmp_path / "goal_memory.jsonl"
        archive_path = tmp_path / "episodic_memory.archive.jsonl"

        original_rows = [
            {
                "episode_id": "ep1",
                "timestamp": 1_700_000_000.0 + 29 * 86400,
                "author": "Alice",
                "user_text": "shader setup help",
                "ai_response": "shader setup hint",
                "importance": 3,
                "time_bucket": "night",
            },
            {
                "episode_id": "ep2",
                "timestamp": 1_700_000_060.0 + 29 * 86400,
                "author": "Alice",
                "user_text": "shader   setup   help",
                "ai_response": "shader setup hint",
                "importance": 4,
                "time_bucket": "night",
            },
            {
                "episode_id": "ep3",
                "timestamp": 1_699_000_000.0,
                "author": "system",
                "user_text": "idle tick",
                "ai_response": "noop",
                "importance": 2,
                "time_bucket": "morning",
                "source_type": "behavior",
            },
        ]
        _write_jsonl(episodic_path, original_rows)

        cli = MemoryMaintenanceCLI(
            episodic_path=str(episodic_path),
            semantic_path=str(semantic_path),
            goal_path=str(goal_path),
            archive_path=str(archive_path),
            stale_days=7.0,
            dry_run=True,
            time_fn=lambda: 1_700_000_000.0 + 30 * 86400,
        )

        report = cli.run()

        assert report.dry_run is True
        assert report.merged_episode_count == 1
        assert report.archived_episode_count == 1
        assert episodic_path.read_text(encoding="utf-8") == (
            "\n".join(json.dumps(row, ensure_ascii=False) for row in original_rows) + "\n"
        )
        assert not archive_path.exists()

    def test_apply_merges_duplicates_and_archives_stale_episode(self, tmp_path: Path) -> None:
        """TC-M29-02: apply consolidates duplicate bursts and archives stale low-signal context."""
        episodic_path = tmp_path / "episodic_memory.jsonl"
        archive_path = tmp_path / "episodic_memory.archive.jsonl"

        _write_jsonl(
            episodic_path,
            [
                {
                    "episode_id": "ep1",
                    "timestamp": 1_700_000_000.0 + 29 * 86400,
                    "author": "Alice",
                    "user_text": "shader setup help",
                    "ai_response": "shader setup hint",
                    "importance": 3,
                    "emotion_tags": ["curious"],
                    "nearby_objects": ["monitor"],
                    "time_bucket": "night",
                },
                {
                    "episode_id": "ep2",
                    "timestamp": 1_700_000_100.0 + 29 * 86400,
                    "author": "Alice",
                    "user_text": "shader setup help",
                    "ai_response": "shader setup hint extended",
                    "importance": 4,
                    "access_count": 2,
                    "emotion_tags": ["focused"],
                    "nearby_objects": ["keyboard"],
                    "time_bucket": "night",
                },
                {
                    "episode_id": "ep3",
                    "timestamp": 1_699_000_000.0,
                    "author": "system",
                    "user_text": "idle tick",
                    "ai_response": "noop",
                    "importance": 2,
                    "time_bucket": "morning",
                    "source_type": "behavior",
                },
            ],
        )

        cli = MemoryMaintenanceCLI(
            episodic_path=str(episodic_path),
            semantic_path=str(tmp_path / "semantic_memory.jsonl"),
            goal_path=str(tmp_path / "goal_memory.jsonl"),
            archive_path=str(archive_path),
            stale_days=7.0,
            dry_run=False,
            time_fn=lambda: 1_700_000_000.0 + 30 * 86400,
        )

        report = cli.run()

        active_rows = [
            json.loads(line)
            for line in episodic_path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        archived_rows = [
            json.loads(line)
            for line in archive_path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]

        assert report.merged_episode_count == 1
        assert report.archived_episode_count == 1
        assert len(active_rows) == 1
        assert len(archived_rows) == 1
        assert active_rows[0]["importance"] == 4
        assert active_rows[0]["access_count"] == 2
        assert active_rows[0]["emotion_tags"] == ["curious", "focused"]
        assert active_rows[0]["nearby_objects"] == ["monitor", "keyboard"]
        assert archived_rows[0]["episode_id"] == "ep3"

    def test_apply_backfills_missing_semantic_and_goal_entries(self, tmp_path: Path) -> None:
        """TC-M29-03: archived repeated topics promote missing semantic facts and goals."""
        episodic_path = tmp_path / "episodic_memory.jsonl"
        semantic_path = tmp_path / "semantic_memory.jsonl"
        goal_path = tmp_path / "goal_memory.jsonl"

        _write_jsonl(
            episodic_path,
            [
                {
                    "episode_id": "ep1",
                    "timestamp": 1_699_000_000.0,
                    "author": "Alice",
                    "user_text": "shader setup help",
                    "ai_response": "shader setup hint",
                    "importance": 2,
                    "source_type": "reflection",
                },
                {
                    "episode_id": "ep2",
                    "timestamp": 1_699_000_100.0,
                    "author": "Alice",
                    "user_text": "shader graph question",
                    "ai_response": "shader graph hint",
                    "importance": 2,
                    "source_type": "reflection",
                },
                {
                    "episode_id": "ep3",
                    "timestamp": 1_699_000_200.0,
                    "author": "Bob",
                    "user_text": "shader tip please",
                    "ai_response": "shader tip ready",
                    "importance": 2,
                    "source_type": "reflection",
                },
            ],
        )
        _write_jsonl(
            semantic_path,
            [
                {
                    "fact_id": "fact1",
                    "category": "viewer_profile",
                    "subject": "Alice",
                    "value": "regular",
                    "mention_count": 4,
                    "confidence": 0.77,
                    "last_updated": 1_700_000_000.0,
                }
            ],
        )

        cli = MemoryMaintenanceCLI(
            episodic_path=str(episodic_path),
            semantic_path=str(semantic_path),
            goal_path=str(goal_path),
            stale_days=7.0,
            dry_run=False,
            time_fn=lambda: 1_700_000_000.0 + 30 * 86400,
        )

        report = cli.run()
        semantic = SemanticMemory(path=semantic_path, time_fn=lambda: 0.0)
        goals = GoalMemory(path=goal_path, time_fn=lambda: 0.0)

        assert report.semantic_facts_added == 3
        assert report.goal_entries_added == 1

        viewer_interest = semantic.get_facts(category="viewer_interest", subject="Alice")
        bob_profile = semantic.get_facts(category="viewer_profile", subject="Bob")
        shader_goals = [goal for goal in goals.get_goals() if goal.value == "shader"]

        assert any(fact.value == "shader" and fact.mention_count == 2 for fact in viewer_interest)
        assert bob_profile
        assert shader_goals
        assert shader_goals[0].status == "active"

    def test_conversation_episode_is_not_archived_without_related_viewer(
        self, tmp_path: Path
    ) -> None:
        """TC-M29-04: author-backed conversation rows stay active when related_viewer is blank."""
        episodic_path = tmp_path / "episodic_memory.jsonl"
        archive_path = tmp_path / "episodic_memory.archive.jsonl"

        _write_jsonl(
            episodic_path,
            [
                {
                    "episode_id": "ep1",
                    "timestamp": 1_699_000_000.0,
                    "author": "Alice",
                    "user_text": "legacy chat",
                    "ai_response": "legacy reply",
                    "importance": 2,
                }
            ],
        )

        cli = MemoryMaintenanceCLI(
            episodic_path=str(episodic_path),
            semantic_path=str(tmp_path / "semantic_memory.jsonl"),
            goal_path=str(tmp_path / "goal_memory.jsonl"),
            archive_path=str(archive_path),
            stale_days=7.0,
            dry_run=False,
            time_fn=lambda: 1_700_000_000.0 + 30 * 86400,
        )

        report = cli.run()

        assert report.archived_episode_count == 0
        assert not archive_path.exists()
        rows = [
            json.loads(line) for line in episodic_path.read_text(encoding="utf-8").splitlines()
        ]
        assert rows[0]["episode_id"] == "ep1"

    def test_old_episode_schema_is_accepted(self, tmp_path: Path) -> None:
        """TC-M29-05: maintenance accepts old JSONL rows without newer metadata fields."""
        episodic_path = tmp_path / "episodic_memory.jsonl"

        _write_jsonl(
            episodic_path,
            [
                {
                    "episode_id": "legacy1",
                    "timestamp": 1_699_500_000.0,
                    "author": "Alice",
                    "user_text": "legacy chat",
                    "ai_response": "legacy reply",
                    "importance": 3,
                }
            ],
        )

        cli = MemoryMaintenanceCLI(
            episodic_path=str(episodic_path),
            semantic_path=str(tmp_path / "semantic_memory.jsonl"),
            goal_path=str(tmp_path / "goal_memory.jsonl"),
            stale_days=60.0,
            dry_run=False,
            time_fn=lambda: 1_700_000_000.0,
        )

        report = cli.run()

        assert report.active_episode_count_before == 1
        assert report.active_episode_count_after == 1
        rows = [
            json.loads(line) for line in episodic_path.read_text(encoding="utf-8").splitlines()
        ]
        assert rows[0]["episode_id"] == "legacy1"
        assert rows[0]["scene_name"] == ""

    def test_archive_write_failure_leaves_active_store_unchanged(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """TC-M29-06: apply does not rewrite the active store before archive write succeeds."""
        episodic_path = tmp_path / "episodic_memory.jsonl"
        archive_path = tmp_path / "episodic_memory.archive.jsonl"
        original_rows = [
            {
                "episode_id": "ep1",
                "timestamp": 1_699_000_000.0,
                "author": "system",
                "user_text": "idle tick",
                "ai_response": "noop",
                "importance": 2,
                "source_type": "behavior",
            }
        ]
        _write_jsonl(episodic_path, original_rows)

        cli = MemoryMaintenanceCLI(
            episodic_path=str(episodic_path),
            semantic_path=str(tmp_path / "semantic_memory.jsonl"),
            goal_path=str(tmp_path / "goal_memory.jsonl"),
            archive_path=str(archive_path),
            stale_days=7.0,
            dry_run=False,
            time_fn=lambda: 1_700_000_000.0 + 30 * 86400,
        )

        original_writer = cli._write_text_atomically

        def fail_on_archive(path: Path, payload: str) -> None:
            if path == archive_path:
                raise OSError("archive write failed")
            original_writer(path, payload)

        monkeypatch.setattr(cli, "_write_text_atomically", fail_on_archive)

        with pytest.raises(OSError, match="archive write failed"):
            cli.run()

        assert episodic_path.read_text(encoding="utf-8") == (
            "\n".join(json.dumps(row, ensure_ascii=False) for row in original_rows) + "\n"
        )
        assert not archive_path.exists()
