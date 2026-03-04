"""Tests for orchestrator.broadcast_lifecycle.

TC-BCAST-11 to TC-BCAST-15.
Issue: #17 E-7. FR-BCAST-01..04. NFR-BCAST-02.
"""

from __future__ import annotations

from orchestrator.broadcast_lifecycle import (
    BroadcastLifecycleManager,
    BroadcastPhase,
)


def _make_manager(
    *,
    obs_ok: bool = True,
    stream_ok: bool = True,
    approve: bool = True,
    llm_title: str = "テスト配信",
    max_duration: float = 0.0,
) -> BroadcastLifecycleManager:
    return BroadcastLifecycleManager(
        obs_start=lambda: obs_ok,
        obs_stop=lambda: None,
        stream_start=lambda: stream_ok,
        stream_stop=lambda: True,
        approval_fn=lambda score: approve,
        llm_fn=lambda prompt: llm_title,
        max_duration_sec=max_duration,
    )


class TestBroadcastLifecyclePhases:
    def test_initial_phase_idle(self) -> None:
        """TC-BCAST-11: Initial phase is IDLE."""
        mgr = _make_manager()
        assert mgr.phase == BroadcastPhase.IDLE
        assert mgr.is_live is False

    def test_evaluate_desire_transitions_to_desiring(self) -> None:
        """TC-BCAST-11b: evaluate_desire changes phase to DESIRING."""
        mgr = _make_manager()
        score = mgr.evaluate_desire(energy=0.9, content_count=5, hours_since_last=25.0)
        assert mgr.phase == BroadcastPhase.DESIRING
        assert 0.0 <= score <= 1.0

    def test_request_approval_approved(self) -> None:
        """TC-BCAST-12: approval_fn returning True → approved=True."""
        mgr = _make_manager(approve=True)
        result = mgr.request_approval(desire_score=0.9)
        assert result is True
        assert mgr.session.approved is True
        assert mgr.phase == BroadcastPhase.AWAITING_APPROVAL

    def test_request_approval_denied(self) -> None:
        """TC-BCAST-12b: NFR-BCAST-02 — denial keeps stream from going live."""
        mgr = _make_manager(approve=False)
        result = mgr.request_approval(desire_score=0.9)
        assert result is False
        assert mgr.session.approved is False


class TestBroadcastLifecycleStream:
    def test_pre_broadcast_success(self) -> None:
        """TC-BCAST-13: pre_broadcast() sets title and transitions to PRE_BROADCAST."""
        mgr = _make_manager(llm_title="YUI.A観測配信")
        ok = mgr.pre_broadcast()
        assert ok is True
        assert mgr.session.title == "YUI.A観測配信"

    def test_pre_broadcast_obs_fail(self) -> None:
        """TC-BCAST-13b: NFR-BCAST-01 — OBS launch failure returns False → IDLE."""
        mgr = _make_manager(obs_ok=False)
        ok = mgr.pre_broadcast()
        assert ok is False
        assert mgr.phase == BroadcastPhase.IDLE
        assert len(mgr.session.errors) > 0

    def test_go_live_success(self) -> None:
        """TC-BCAST-14: go_live() sets is_live=True and phase=ON_AIR."""
        mgr = _make_manager(stream_ok=True)
        ok = mgr.go_live()
        assert ok is True
        assert mgr.is_live is True
        assert mgr.phase == BroadcastPhase.ON_AIR
        assert mgr.session.started_at > 0

    def test_go_live_idempotent(self) -> None:
        """TC-BCAST-14b: second go_live() call while live returns False."""
        mgr = _make_manager()
        mgr.go_live()
        result = mgr.go_live()
        assert result is False

    def test_end_broadcast(self) -> None:
        """TC-BCAST-15: end_broadcast() sets is_live=False and phase=IDLE."""
        mgr = _make_manager()
        mgr.go_live()
        assert mgr.is_live is True
        mgr.end_broadcast(reason="test")
        assert mgr.is_live is False
        assert mgr.phase == BroadcastPhase.IDLE
        assert mgr.session.ended_at > 0

    def test_check_auto_stop_triggers_end(self) -> None:
        """TC-BCAST-15b: FR-BCAST-04 — auto-stop fires when max_duration exceeded."""
        import time
        mgr = _make_manager(max_duration=0.01)  # 10ms
        mgr.go_live()
        assert mgr.is_live is True
        time.sleep(0.05)  # exceed duration
        triggered = mgr.check_auto_stop()
        assert triggered is True
        assert mgr.is_live is False

    def test_check_auto_stop_no_limit(self) -> None:
        """TC-BCAST-15c: check_auto_stop does nothing when max_duration=0."""
        mgr = _make_manager(max_duration=0.0)
        mgr.go_live()
        assert mgr.check_auto_stop() is False
        assert mgr.is_live is True
