"""Tests for life_scheduler module.

TC-LIFE-06 .. TC-LIFE-15
FR-LIFE-01: Autonomous daily life scheduling with time-of-day + energy.
"""

from __future__ import annotations

from datetime import datetime

from orchestrator.life_activity import ActivityType
from orchestrator.life_scheduler import (
    _CRITICAL_ENERGY,
    _MIN_ACTIVITY_DURATION_SEC,
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
