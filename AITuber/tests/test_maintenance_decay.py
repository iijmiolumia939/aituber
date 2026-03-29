"""Tests for M30 maintenance decay pruning.

TC-M30-MAINT-01 to TC-M30-MAINT-03.
FR-MEM-DECAY-01: Maintenance prunes decayed semantic/goal entries.
"""

from __future__ import annotations

import json
from pathlib import Path

from orchestrator.memory_maintenance_cli import MemoryMaintenanceCLI
from orchestrator.semantic_memory import SemanticMemory


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "\n".join(json.dumps(row, ensure_ascii=False) for row in rows) + "\n",
        encoding="utf-8",
    )


class TestMaintenanceDecay:
    def test_maintenance_prunes_decayed_semantic_facts(self, tmp_path: Path) -> None:
        """TC-M30-MAINT-01: very old low-mention facts are pruned by maintenance."""
        semantic_path = tmp_path / "semantic_memory.jsonl"
        # Fact from 120 days ago with low confidence → should decay below 0.10
        _write_jsonl(
            semantic_path,
            [
                {
                    "fact_id": "f1",
                    "category": "viewer_interest",
                    "subject": "Alice",
                    "value": "shader",
                    "mention_count": 2,
                    "confidence": 0.35,
                    "last_updated": 1_700_000_000.0,
                },
                {
                    "fact_id": "f2",
                    "category": "viewer_profile",
                    "subject": "Alice",
                    "value": "regular",
                    "mention_count": 5,
                    "confidence": 0.85,
                    "last_updated": 1_700_000_000.0,
                },
            ],
        )

        # Run maintenance 120 days later
        now = 1_700_000_000.0 + 120 * 86400
        cli = MemoryMaintenanceCLI(
            episodic_path=str(tmp_path / "episodic_memory.jsonl"),
            semantic_path=str(semantic_path),
            goal_path=str(tmp_path / "goal_memory.jsonl"),
            stale_days=14.0,
            dry_run=False,
            time_fn=lambda: now,
        )

        report = cli.run()
        assert report.decayed_semantic_facts >= 1

        # viewer_profile should survive (not viewer_interest category)
        reloaded = SemanticMemory(path=semantic_path, time_fn=lambda: now)
        profiles = reloaded.get_facts(category="viewer_profile")
        assert len(profiles) == 1

    def test_maintenance_keeps_fresh_facts(self, tmp_path: Path) -> None:
        """TC-M30-MAINT-02: recently updated facts survive maintenance."""
        now = 1_700_000_000.0 + 30 * 86400
        semantic_path = tmp_path / "semantic_memory.jsonl"
        _write_jsonl(
            semantic_path,
            [
                {
                    "fact_id": "f1",
                    "category": "viewer_interest",
                    "subject": "Alice",
                    "value": "shader",
                    "mention_count": 5,
                    "confidence": 0.8,
                    "last_updated": now - 86400,  # 1 day ago
                },
            ],
        )

        cli = MemoryMaintenanceCLI(
            episodic_path=str(tmp_path / "episodic_memory.jsonl"),
            semantic_path=str(semantic_path),
            goal_path=str(tmp_path / "goal_memory.jsonl"),
            stale_days=14.0,
            dry_run=False,
            time_fn=lambda: now,
        )

        report = cli.run()
        assert report.decayed_semantic_facts == 0

    def test_maintenance_report_includes_decay_counts(self, tmp_path: Path) -> None:
        """TC-M30-MAINT-03: maintenance report includes decay statistics."""
        now = 1_700_000_000.0
        cli = MemoryMaintenanceCLI(
            episodic_path=str(tmp_path / "episodic_memory.jsonl"),
            semantic_path=str(tmp_path / "semantic_memory.jsonl"),
            goal_path=str(tmp_path / "goal_memory.jsonl"),
            stale_days=14.0,
            dry_run=False,
            time_fn=lambda: now,
        )

        report = cli.run()
        d = report.to_dict()
        assert "decayed_semantic_facts" in d
        assert "decayed_goal_entries" in d
