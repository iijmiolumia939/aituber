"""Tests for GapTrigger (orchestrator/gap_trigger.py).

TC-GAP-TRIGGER-01: below threshold → DevAgent NOT kicked
TC-GAP-TRIGGER-02: at threshold → DevAgent kicked once
TC-GAP-TRIGGER-03: double-start prevention (same intent, second tick)
TC-GAP-TRIGGER-04: DevAgent success → gaps cleared from JSONL
TC-GAP-TRIGGER-05: DevAgent failure → gap entries retained
TC-GAP-TRIGGER-06: in_flight removed after DevAgent finishes (success)
TC-GAP-TRIGGER-07: in_flight removed after DevAgent finishes (failure)
TC-GAP-TRIGGER-08: _count_by_intent aggregates string and dict intended_action
TC-GAP-TRIGGER-09: _clear_gaps_for_intent only removes matching entries

SRS refs: FR-GAP-TRIGGER-01
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

# ── helpers ───────────────────────────────────────────────────────────────────


def _make_gaps_dir(tmp_path: Path, entries: list[dict]) -> Path:
    """Write entries to tmp_path/gap.jsonl and return the directory."""
    gaps_dir = tmp_path / "capability_gaps"
    gaps_dir.mkdir()
    jf = gaps_dir / "stream_001.jsonl"
    jf.write_text(
        "\n".join(json.dumps(e) for e in entries) + "\n",
        encoding="utf-8",
    )
    return gaps_dir


def _gap(intent_name: str, category: str = "missing_behavior") -> dict:
    return {
        "intended_action": {"name": intent_name},
        "gap_category": category,
        "fallback_used": True,
    }


# ── TC-GAP-TRIGGER-01: below threshold ───────────────────────────────────────


@pytest.mark.asyncio
async def test_below_threshold_no_kick(tmp_path: Path) -> None:
    """TC-GAP-TRIGGER-01: 2 entries < threshold(3) → DevAgent not kicked."""
    from orchestrator.gap_trigger import GapTrigger

    gaps_dir = _make_gaps_dir(tmp_path, [_gap("dance"), _gap("dance")])
    gt = GapTrigger(gaps_dir=gaps_dir, threshold=3, poll_interval=1000)

    with patch.object(gt, "_run_dev_agent", new_callable=AsyncMock) as mock_run:
        await gt._tick()
        mock_run.assert_not_called()


# ── TC-GAP-TRIGGER-02: at threshold → kicked once ─────────────────────────────


@pytest.mark.asyncio
async def test_at_threshold_kicks_dev_agent(tmp_path: Path) -> None:
    """TC-GAP-TRIGGER-02: 3 entries == threshold(3) → DevAgent kicked once."""
    from orchestrator.gap_trigger import GapTrigger

    gaps_dir = _make_gaps_dir(tmp_path, [_gap("dance")] * 3)
    gt = GapTrigger(gaps_dir=gaps_dir, threshold=3, poll_interval=1000)

    kicked: list[str] = []

    async def fake_run(intent: str) -> None:
        kicked.append(intent)

    with patch.object(gt, "_run_dev_agent", side_effect=fake_run):
        # ensure_future is used inside _tick, so we need to let the loop run
        await gt._tick()
        await asyncio.sleep(0)  # allow scheduled coroutines to run

    assert kicked == ["dance"]


# ── TC-GAP-TRIGGER-03: double-start prevention ────────────────────────────────


@pytest.mark.asyncio
async def test_double_start_prevention(tmp_path: Path) -> None:
    """TC-GAP-TRIGGER-03: second tick while intent in-flight → not kicked again."""
    from orchestrator.gap_trigger import GapTrigger

    gaps_dir = _make_gaps_dir(tmp_path, [_gap("dance")] * 5)
    gt = GapTrigger(gaps_dir=gaps_dir, threshold=3, poll_interval=1000)
    gt._in_flight.add("dance")  # simulate already in-flight

    kicked: list[str] = []

    async def fake_run(intent: str) -> None:
        kicked.append(intent)

    with patch.object(gt, "_run_dev_agent", side_effect=fake_run):
        await gt._tick()
        await asyncio.sleep(0)

    assert kicked == []


# ── TC-GAP-TRIGGER-04: success → gaps cleared ─────────────────────────────────


@pytest.mark.asyncio
async def test_success_clears_gaps(tmp_path: Path) -> None:
    """TC-GAP-TRIGGER-04: DevAgent success → gaps for intent removed from JSONL."""
    from orchestrator.gap_trigger import GapTrigger

    entries = [_gap("dance")] * 3 + [_gap("sit")]
    gaps_dir = _make_gaps_dir(tmp_path, entries)
    gt = GapTrigger(gaps_dir=gaps_dir, threshold=3, poll_interval=1000)

    with patch.object(gt, "_invoke_dev_agent", new_callable=AsyncMock, return_value=True):
        await gt._run_dev_agent("dance")

    # dance entries should be gone; sit should remain
    remaining = gt._load_gaps()
    names = [g.get("intended_action", {}).get("name") for g in remaining]
    assert "dance" not in names
    assert "sit" in names


# ── TC-GAP-TRIGGER-05: failure → gap entries retained ─────────────────────────


@pytest.mark.asyncio
async def test_failure_retains_gaps(tmp_path: Path) -> None:
    """TC-GAP-TRIGGER-05: DevAgent failure → gap entries NOT removed."""
    from orchestrator.gap_trigger import GapTrigger

    entries = [_gap("dance")] * 3
    gaps_dir = _make_gaps_dir(tmp_path, entries)
    gt = GapTrigger(gaps_dir=gaps_dir, threshold=3, poll_interval=1000)

    with patch.object(gt, "_invoke_dev_agent", new_callable=AsyncMock, return_value=False):
        await gt._run_dev_agent("dance")

    remaining = gt._load_gaps()
    names = [g.get("intended_action", {}).get("name") for g in remaining]
    assert names.count("dance") == 3


# ── TC-GAP-TRIGGER-06: in_flight cleared after success ────────────────────────


@pytest.mark.asyncio
async def test_in_flight_cleared_after_success(tmp_path: Path) -> None:
    """TC-GAP-TRIGGER-06: _in_flight entry removed after DevAgent succeeds."""
    from orchestrator.gap_trigger import GapTrigger

    gaps_dir = _make_gaps_dir(tmp_path, [])
    gt = GapTrigger(gaps_dir=gaps_dir, threshold=3, poll_interval=1000)
    gt._in_flight.add("dance")

    with (
        patch.object(gt, "_invoke_dev_agent", new_callable=AsyncMock, return_value=True),
        patch.object(gt, "_clear_gaps_for_intent"),
    ):
        await gt._run_dev_agent("dance")

    assert "dance" not in gt._in_flight


# ── TC-GAP-TRIGGER-07: in_flight cleared after failure ────────────────────────


@pytest.mark.asyncio
async def test_in_flight_cleared_after_failure(tmp_path: Path) -> None:
    """TC-GAP-TRIGGER-07: _in_flight entry removed even when DevAgent fails."""
    from orchestrator.gap_trigger import GapTrigger

    gaps_dir = _make_gaps_dir(tmp_path, [])
    gt = GapTrigger(gaps_dir=gaps_dir, threshold=3, poll_interval=1000)
    gt._in_flight.add("dance")

    with patch.object(gt, "_invoke_dev_agent", new_callable=AsyncMock, return_value=False):
        await gt._run_dev_agent("dance")

    assert "dance" not in gt._in_flight


# ── TC-GAP-TRIGGER-08: _count_by_intent handles string and dict ──────────────


def test_count_by_intent_mixed_types() -> None:
    """TC-GAP-TRIGGER-08: _count_by_intent counts dict and string intended_action."""
    from orchestrator.gap_trigger import GapTrigger

    gt = GapTrigger(gaps_dir="/tmp", threshold=3)
    gaps = [
        {"intended_action": {"name": "wave"}},
        {"intended_action": {"name": "wave"}},
        {"intended_action": "wave"},
        {"intended_action": {"name": "dance"}},
        {},  # no intended_action → skipped
    ]
    counts = gt._count_by_intent(gaps)
    assert counts["wave"] == 3
    assert counts["dance"] == 1
    assert len(counts) == 2


# ── TC-GAP-TRIGGER-09: _clear_gaps_for_intent leaves other entries ────────────


def test_clear_gaps_only_removes_matching(tmp_path: Path) -> None:
    """TC-GAP-TRIGGER-09: _clear_gaps_for_intent removes only matching intent."""
    from orchestrator.gap_trigger import GapTrigger

    entries = [_gap("dance"), _gap("sit"), _gap("dance"), _gap("wave")]
    gaps_dir = _make_gaps_dir(tmp_path, entries)
    gt = GapTrigger(gaps_dir=gaps_dir, threshold=3, poll_interval=1000)

    gt._clear_gaps_for_intent("dance")

    remaining = gt._load_gaps()
    names = [g.get("intended_action", {}).get("name") for g in remaining]
    assert "dance" not in names
    assert names.count("sit") == 1
    assert names.count("wave") == 1
