"""Tests for life_scheduler module.

TC-LIFE-06 .. TC-LIFE-22
FR-LIFE-01: Autonomous daily life scheduling with time-of-day + energy.
FR-GOAL-01: GoalState (curiosity/social_drive/exploration) biases activity selection.
"""

from __future__ import annotations

from datetime import datetime

import pytest

from orchestrator.life_activity import ActivityType
from orchestrator.life_scheduler import (
    _CRITICAL_ENERGY,
    _MIN_ACTIVITY_DURATION_SEC,
    GoalState,
    LifeScheduler,
)

# ── Test helpers ──────────────────────────────────────────────────────


def _make_scheduler(hour: int = 10, start_mono: float = 1000.0):
    """Create a LifeScheduler pinned to a deterministic clock.

    Returns (scheduler, mono_container) where mono_container[0] is the
    current fake monotonic time mutable by the test.
    """
    dt = datetime(2026, 3, 4, hour, 0, 0)
    mono = [start_mono]

    return (
        LifeScheduler(
            time_fn=lambda: dt,
            monotonic_fn=lambda: mono[0],
        ),
        mono,
    )


# ── Tests ─────────────────────────────────────────────────────────────


# TC-LIFE-06: tick returns None before minimum activity duration
def test_tick_returns_none_before_min_duration():
    scheduler, mono = _make_scheduler(hour=10)
    # elapsed = 0.0 < _MIN_ACTIVITY_DURATION_SEC
    result = scheduler.tick()
    assert result is None


# TC-LIFE-07: tick returns activity after minimum duration when schedule differs
def test_tick_returns_activity_after_min_duration():
    # hour=10 → READ; initial state=IDLE → should switch after min duration
    scheduler, mono = _make_scheduler(hour=10)
    mono[0] += _MIN_ACTIVITY_DURATION_SEC + 1.0
    result = scheduler.tick()
    assert result is not None
    assert result.activity_type == ActivityType.READ


# TC-LIFE-08: schedule hours 0-5 map to SLEEP
def test_schedule_midnight_hours_is_sleep():
    scheduler, _ = _make_scheduler()
    for hour in [0, 1, 3, 5]:
        assert scheduler._desired_activity(hour) == ActivityType.SLEEP


# TC-LIFE-09: schedule hour 7 maps to EAT
def test_schedule_hour_7_is_eat():
    scheduler, _ = _make_scheduler()
    assert scheduler._desired_activity(7) == ActivityType.EAT


# TC-LIFE-10: schedule hours 13-14 map to TINKER
def test_schedule_tinker_hours():
    scheduler, _ = _make_scheduler()
    for hour in [13, 14]:
        assert scheduler._desired_activity(hour) == ActivityType.TINKER


# TC-LIFE-11: energy depletes during energy-consuming activities
def test_energy_depletes_during_active_work():
    scheduler, mono = _make_scheduler(hour=14)
    scheduler.force_activity(ActivityType.TINKER)
    initial_energy = scheduler.state.energy
    # Simulate 1 hour
    mono[0] += 3600.0
    scheduler.tick()
    assert scheduler.state.energy < initial_energy


# TC-LIFE-12: energy recovers during sleep
def test_energy_recovers_during_sleep():
    scheduler, mono = _make_scheduler(hour=2)
    scheduler.force_activity(ActivityType.SLEEP)
    scheduler.state.energy = 0.5
    mono[0] += 3600.0
    scheduler.tick()
    assert scheduler.state.energy > 0.5


# TC-LIFE-13: force_activity immediately overrides schedule
def test_force_activity_overrides_schedule():
    scheduler, _ = _make_scheduler(hour=14)  # would be TINKER
    result = scheduler.force_activity(ActivityType.READ)
    assert result.activity_type == ActivityType.READ
    assert scheduler.state.current_activity == ActivityType.READ


# TC-LIFE-14: critical energy forces sleep even outside sleep hours
def test_critical_energy_forces_sleep():
    scheduler, _ = _make_scheduler(hour=14)  # TINKER time
    scheduler.force_activity(ActivityType.TINKER)
    scheduler.state.energy = _CRITICAL_ENERGY - 0.01  # below critical
    # tick immediately (elapsed=0 which is < min_duration, but critical overrides)
    result = scheduler.tick()
    assert result is not None
    assert result.activity_type == ActivityType.SLEEP


# TC-LIFE-15a: state.current_activity updates after force_activity
def test_state_current_activity_updates_after_force():
    scheduler, _ = _make_scheduler()
    assert scheduler.state.current_activity == ActivityType.IDLE
    scheduler.force_activity(ActivityType.READ)
    assert scheduler.state.current_activity == ActivityType.READ


# TC-LIFE-15b: activities_done_today accumulates history
def test_activities_done_today_accumulates():
    scheduler, mono = _make_scheduler(hour=10)
    scheduler.force_activity(ActivityType.READ)
    scheduler.force_activity(ActivityType.EAT)
    assert ActivityType.READ in scheduler.state.activities_done_today
    assert ActivityType.EAT in scheduler.state.activities_done_today


# TC-LIFE-15c: energy stays within [0.0, 1.0] bounds
def test_energy_stays_within_bounds():
    scheduler, mono = _make_scheduler(hour=2)
    scheduler.force_activity(ActivityType.SLEEP)
    scheduler.state.energy = 0.95
    # Simulate 24 hours of sleep (would overflow without clamping)
    mono[0] += 86400.0
    scheduler.tick()
    assert scheduler.state.energy <= 1.0

    scheduler2, mono2 = _make_scheduler(hour=14)
    scheduler2.force_activity(ActivityType.TINKER)
    scheduler2.state.energy = 0.02
    mono2[0] += 86400.0
    scheduler2.tick()
    assert scheduler2.state.energy >= 0.0


# ── FR-GOAL-01 tests ──────────────────────────────────────────────────


# TC-LIFE-16: GoalState default values
def test_goal_state_defaults():
    gs = GoalState()
    assert gs.curiosity == 0.5
    assert gs.social_drive == 0.3
    assert gs.exploration == 0.4


# TC-LIFE-17: observe_comment raises social_drive
def test_observe_comment_raises_social_drive():
    scheduler, _ = _make_scheduler()
    before = scheduler.state.goal.social_drive
    scheduler.observe_comment()
    assert scheduler.state.goal.social_drive > before


# TC-LIFE-18: observe_intellectual_topic raises curiosity
def test_observe_intellectual_topic_raises_curiosity():
    scheduler, _ = _make_scheduler()
    before = scheduler.state.goal.curiosity
    scheduler.observe_intellectual_topic()
    assert scheduler.state.goal.curiosity > before
    # social_drive and exploration are untouched
    assert scheduler.state.goal.social_drive == pytest.approx(0.3)
    assert scheduler.state.goal.exploration == pytest.approx(0.4)


# TC-LIFE-19: GoalState.decay() moves values toward 0.5
def test_goal_state_decay_toward_midpoint():
    gs = GoalState(curiosity=1.0, social_drive=0.0, exploration=1.0)
    gs.decay()
    assert gs.curiosity < 1.0
    assert gs.social_drive > 0.0
    assert gs.exploration < 1.0


# TC-LIFE-20: social_drive capped at 1.0 after repeated observe_comment
def test_observe_comment_capped_at_one():
    scheduler, _ = _make_scheduler()
    for _ in range(20):
        scheduler.observe_comment()
    assert scheduler.state.goal.social_drive <= 1.0


# TC-LIFE-21: SLEEP is never overridden by GoalState even with max exploration
def test_sleep_not_overridden_by_goal_state():
    scheduler, _ = _make_scheduler(hour=2)  # 0-6 → SLEEP
    # Push exploration to maximum
    scheduler.state.goal.exploration = 1.0
    scheduler.state.goal.curiosity = 1.0
    assert scheduler._desired_activity(2) == ActivityType.SLEEP


# TC-LIFE-22: high exploration overrides READ schedule with WALK
def test_high_exploration_overrides_read_with_walk():
    # hour=10 → READ (curiosity=0.5 default → sched_bonus = 0.8*0.5=0.4)
    # WALK score with exploration=1.0 → 0.9*1.0=0.9; margin=0.5 > _GOAL_INFLUENCE(0.35)
    scheduler, _ = _make_scheduler(hour=10)
    scheduler.state.goal.curiosity = 0.01  # very low curiosity
    scheduler.state.goal.exploration = 1.0  # very high exploration
    result = scheduler._desired_activity(10)
    assert result == ActivityType.WALK


# TC-LIFE-23: medium-horizon learning goal can bias WALK block toward READ
def test_learning_goal_focus_biases_walking_slot_toward_read():
    scheduler, _ = _make_scheduler(hour=15)  # baseline schedule is WALK
    scheduler.state.goal.curiosity = 0.3
    scheduler.state.goal.social_drive = 0.0
    scheduler.state.goal.exploration = 0.0

    assert scheduler._desired_activity(15) == ActivityType.WALK

    scheduler.set_goal_focus("shader を深めたい", focus_type="learning")
    assert scheduler._desired_activity(15) == ActivityType.READ
