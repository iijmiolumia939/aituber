"""Life Scheduler — autonomous daily activity driver.

Implements a Sims-like activity loop: time-of-day + energy level
determine what YUI.A does when not streaming.

FR-LIFE-01: time-of-day aware, energy-gated, variety-seeking scheduler.

References:
  Park et al. (2023), Generative Agents, arXiv:2304.03442 §4 "Agent Architecture"
  Sims (1989) — Energy/Hunger motive system
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime

from orchestrator.life_activity import ActivityType, LifeActivity, get_activity

logger = logging.getLogger(__name__)


# ── Life state ────────────────────────────────────────────────────────


@dataclass
class LifeState:
    """Runtime mutable state of avatar's daily life.

    FR-LIFE-01.

    Attributes:
        energy: 0.0 (exhausted) – 1.0 (full energy).
        current_activity: currently running ActivityType.
        activity_started_at: monotonic timestamp when activity began.
        activities_done_today: ordered history for today's session.
    """

    energy: float = 1.0
    current_activity: ActivityType = ActivityType.IDLE
    activity_started_at: float = field(default_factory=time.monotonic)
    activities_done_today: list[ActivityType] = field(default_factory=list)


# ── Time-of-day schedule ──────────────────────────────────────────────
# (start_hour_inclusive, end_hour_exclusive, preferred_ActivityType)
# 24hの時刻ブロックで優先活動を定義。エネルギーが十分あれば従う。

_HOUR_SCHEDULE: list[tuple[int, int, ActivityType]] = [
    (0,  6,  ActivityType.SLEEP),
    (6,  7,  ActivityType.WAKE),
    (7,  8,  ActivityType.EAT),
    (8,  12, ActivityType.READ),
    (12, 13, ActivityType.EAT),
    (13, 15, ActivityType.TINKER),
    (15, 16, ActivityType.WALK),
    (16, 18, ActivityType.READ),
    (18, 19, ActivityType.EAT),
    (19, 21, ActivityType.PONDER),
    (21, 22, ActivityType.WALK),
    (22, 23, ActivityType.STRETCH),
    (23, 24, ActivityType.SLEEP),
]

# Energy rate per second for each activity.
# Positive = recovery (energy increases), negative = consumption (energy decreases).
# Rename from "drain" to "rate" for clarity.
_ENERGY_DRAIN: dict[ActivityType, float] = {
    ActivityType.SLEEP:   +0.00005,   # 回復: 1h=+0.18
    ActivityType.WAKE:     0.0,
    ActivityType.EAT:     +0.00003,   # 微回復: 食事で補充
    ActivityType.READ:    -0.00004,   # 消費: 集中力使用
    ActivityType.TINKER:  -0.00005,   # 消費: 高集中作業
    ActivityType.WALK:    -0.00002,   # 軽微消費
    ActivityType.PONDER:  -0.00003,   # 消費: 深い思索
    ActivityType.STRETCH: +0.00001,   # 微回復
    ActivityType.IDLE:    -0.00001,   # ほぼ消費なし
}

# Force sleep below this energy threshold (overrides schedule)
_CRITICAL_ENERGY = 0.10

# Minimum real-world seconds before considering an activity switch
_MIN_ACTIVITY_DURATION_SEC = 60.0


# ── Scheduler ────────────────────────────────────────────────────────


class LifeScheduler:
    """Time-of-day + energy aware autonomous daily life scheduler.

    FR-LIFE-01.

    Usage (in async context)::

        scheduler = LifeScheduler()
        # call tick() every 60s
        activity = scheduler.tick()
        if activity:
            await avatar.send_update(gesture=activity.gesture, ...)

    Fully injectable for testing::

        scheduler = LifeScheduler(
            time_fn=lambda: datetime(2026, 3, 4, 10, 0),
            monotonic_fn=lambda: pinned_clock,
        )
    """

    def __init__(
        self,
        *,
        time_fn: Callable[[], datetime] | None = None,
        monotonic_fn: Callable[[], float] | None = None,
    ) -> None:
        self._time_fn: Callable[[], datetime] = time_fn or datetime.now
        self._mono_fn: Callable[[], float] = monotonic_fn or time.monotonic

        t0 = self._mono_fn()
        self._state = LifeState(activity_started_at=t0)
        self._last_energy_sample: float = t0

    # ── Public API ────────────────────────────────────────────────

    @property
    def state(self) -> LifeState:
        """Read-only view of current life state (mutable internally)."""
        return self._state

    def tick(self) -> LifeActivity | None:
        """Poll for activity change. Call roughly every 60s real-time.

        Returns:
            LifeActivity if a new activity should start, else None.

        Side effects:
            Updates energy; logs activity transitions.

        FR-LIFE-01: Critical energy overrides schedule and forces sleep.
        """
        now_mono = self._mono_fn()
        now_dt = self._time_fn()

        # 1. Update energy (based on wall-clock time since last tick)
        energy_elapsed = now_mono - self._last_energy_sample
        self._last_energy_sample = now_mono
        self._update_energy(energy_elapsed)

        # 2. Critical energy → force sleep regardless of schedule or duration
        if (
            self._state.energy <= _CRITICAL_ENERGY
            and self._state.current_activity != ActivityType.SLEEP
        ):
            logger.info(
                "[LifeScheduler] Energy critical (%.2f) — forcing SLEEP",
                self._state.energy,
            )
            return self._switch_to(ActivityType.SLEEP)

        # 3. Don't switch before minimum activity duration
        activity_elapsed = now_mono - self._state.activity_started_at
        if activity_elapsed < _MIN_ACTIVITY_DURATION_SEC:
            return None

        # 4. Compare desired activity to current
        desired = self._desired_activity(now_dt.hour)
        if desired == self._state.current_activity:
            return None

        return self._switch_to(desired)

    def force_activity(self, activity_type: ActivityType) -> LifeActivity:
        """Immediately switch to the given activity (external override).

        FR-LIFE-01: Used by tests, REPL, or manual commands.
        """
        return self._switch_to(activity_type)

    # ── Internal ──────────────────────────────────────────────────

    def _desired_activity(self, hour: int) -> ActivityType:
        """Map hour-of-day to preferred ActivityType per schedule."""
        for start, end, act_type in _HOUR_SCHEDULE:
            if start <= hour < end:
                return act_type
        return ActivityType.SLEEP  # midnight fallback

    def _switch_to(self, activity_type: ActivityType) -> LifeActivity:
        self._state.current_activity = activity_type
        self._state.activity_started_at = self._mono_fn()
        self._state.activities_done_today.append(activity_type)
        activity = get_activity(activity_type)
        logger.info(
            "[LifeScheduler] → %s (gesture=%s emotion=%s energy=%.2f)",
            activity_type,
            activity.gesture,
            activity.emotion,
            self._state.energy,
        )
        return activity

    def _update_energy(self, elapsed_sec: float) -> None:
        drain = _ENERGY_DRAIN.get(self._state.current_activity, 0.0)
        delta = drain * elapsed_sec
        self._state.energy = max(0.0, min(1.0, self._state.energy + delta))
