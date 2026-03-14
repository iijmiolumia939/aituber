"""Life Scheduler — autonomous daily activity driver.

Implements a Sims-like activity loop: time-of-day + energy level
+ GoalState determine what YUI.A does when not streaming.

FR-LIFE-01: time-of-day aware, energy-gated, variety-seeking scheduler.
FR-GOAL-01: GoalState (curiosity / social_drive / exploration) biases
            activity selection toward goal-aligned behaviours.
            Viewer comments nudge GoalState in real time (inZOI Smart Zoi
            concept — react to environment/events).

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


# ── Goal state ───────────────────────────────────────────────────────


@dataclass
class GoalState:
    """YUI.A の動機パラメータ (FR-GOAL-01).

    各値は 0.0〜1.0。高いほどその動機が強く、関連する活動が選ばれやすくなる。

    Attributes:
        curiosity:    知的好奇心 (READ / TINKER / PONDER に対応)
        social_drive: 交流欲求 (視聴者コメントで上昇、IDLE で減衰)
        exploration:  探索欲求 (WALK に対応)
    """

    curiosity: float = 0.5
    social_drive: float = 0.3
    exploration: float = 0.4

    # 減衰定数: 1 tick (≈60s) あたりの自然減衰量
    _DECAY_PER_TICK: float = 0.02

    def decay(self) -> None:
        """自然減衰: tick ごとに全パラメータを少しずつ中央値 (0.5) に戻す。"""
        for attr in ("curiosity", "social_drive", "exploration"):
            v = getattr(self, attr)
            target = 0.5
            setattr(self, attr, v + (target - v) * self._DECAY_PER_TICK)

    def observe_comment(self) -> None:
        """視聴者コメント受信時: social_drive を上昇させる (FR-GOAL-01)."""
        self.social_drive = min(1.0, self.social_drive + 0.15)

    def observe_intellectual_topic(self) -> None:
        """知的テーマ (SF/哲学/宇宙) のコメント受信時: curiosity を上昇させる。"""
        self.curiosity = min(1.0, self.curiosity + 0.20)

    def observe_on_air(self) -> None:
        """配信開始: social_drive を満たす方向に動かす (外部刺激)."""
        self.social_drive = min(1.0, self.social_drive + 0.10)


# ── Goal → activity weight mapping (FR-GOAL-01) ─────────────────────
# 各 ActivityType に対して GoalState の各次元が与えるボーナス重み係数。
# LifeScheduler._goal_bonus() で参照する。

_GOAL_WEIGHTS: dict[ActivityType, dict[str, float]] = {
    ActivityType.READ: {"curiosity": 0.8, "social_drive": 0.0, "exploration": 0.0},
    ActivityType.TINKER: {"curiosity": 0.7, "social_drive": 0.0, "exploration": 0.1},
    ActivityType.PONDER: {"curiosity": 0.6, "social_drive": 0.1, "exploration": 0.0},
    ActivityType.WALK: {"curiosity": 0.0, "social_drive": 0.1, "exploration": 0.9},
    ActivityType.STRETCH: {"curiosity": 0.0, "social_drive": 0.0, "exploration": 0.2},
    ActivityType.EAT: {"curiosity": 0.0, "social_drive": 0.2, "exploration": 0.0},
    ActivityType.SLEEP: {"curiosity": 0.0, "social_drive": 0.0, "exploration": 0.0},
    ActivityType.WAKE: {"curiosity": 0.0, "social_drive": 0.0, "exploration": 0.0},
    ActivityType.IDLE: {"curiosity": 0.0, "social_drive": 0.0, "exploration": 0.0},
}

# GoalState が足元のスケジュールを覆せる最大ボーナス(0.0〜1.0)。
# 小さいほど時刻スケジュール優先; 大きいほど目標優先。
_GOAL_INFLUENCE = 0.35

_LONG_TERM_GOAL_BONUS: dict[str, dict[ActivityType, float]] = {
    "learning": {
        ActivityType.READ: 0.18,
        ActivityType.TINKER: 0.16,
        ActivityType.PONDER: 0.14,
    },
    "exploration": {
        ActivityType.WALK: 0.18,
        ActivityType.READ: 0.05,
    },
    "social": {
        ActivityType.PONDER: 0.12,
        ActivityType.EAT: 0.08,
    },
}


# ── Life state ────────────────────────────────────────────────────────


@dataclass
class LifeState:
    """Runtime mutable state of avatar's daily life.

    FR-LIFE-01, FR-GOAL-01.

    Attributes:
        energy: 0.0 (exhausted) – 1.0 (full energy).
        goal: GoalState (curiosity/social_drive/exploration drives).
        current_activity: currently running ActivityType.
        activity_started_at: monotonic timestamp when activity began.
        activities_done_today: ordered history for today's session.
        current_zone: last-known Unity zone/room from WorldContext.  Populated
            by tick(current_zone=...) so the scheduler can observe avatar
            position (BDI Beliefs layer, Issue #46).
    """

    energy: float = 1.0
    goal: GoalState = field(default_factory=GoalState)
    current_activity: ActivityType = ActivityType.IDLE
    activity_started_at: float = field(default_factory=time.monotonic)
    activities_done_today: list[ActivityType] = field(default_factory=list)
    current_zone: str | None = None
    goal_focus: str = ""
    goal_focus_type: str | None = None


# ── Time-of-day schedule ──────────────────────────────────────────────
# (start_hour_inclusive, end_hour_exclusive, preferred_ActivityType)
# 24hの時刻ブロックで優先活動を定義。エネルギーが十分あれば従う。

_HOUR_SCHEDULE: list[tuple[int, int, ActivityType]] = [
    (0, 6, ActivityType.SLEEP),
    (6, 7, ActivityType.WAKE),
    (7, 8, ActivityType.EAT),
    (8, 12, ActivityType.READ),
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
    ActivityType.SLEEP: +0.00005,  # 回復: 1h=+0.18
    ActivityType.WAKE: 0.0,
    ActivityType.EAT: +0.00003,  # 微回復: 食事で補充
    ActivityType.READ: -0.00004,  # 消費: 集中力使用
    ActivityType.TINKER: -0.00005,  # 消費: 高集中作業
    ActivityType.WALK: -0.00002,  # 軽微消費
    ActivityType.PONDER: -0.00003,  # 消費: 深い思索
    ActivityType.STRETCH: +0.00001,  # 微回復
    ActivityType.IDLE: -0.00001,  # ほぼ消費なし
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

    def observe_comment(self) -> None:
        """視聴者コメント受信: social_drive を上昇させる (FR-GOAL-01)."""
        self._state.goal.observe_comment()

    def observe_intellectual_topic(self) -> None:
        """知的テーマ (SF/哲学/宇宙) のコメント: curiosity を上昇させる (FR-GOAL-01)."""
        self._state.goal.observe_intellectual_topic()

    def observe_on_air(self) -> None:
        """配信開始: social_drive を上昇させる (FR-GOAL-01)."""
        self._state.goal.observe_on_air()

    def set_goal_focus(self, goal_text: str = "", *, focus_type: str | None = None) -> None:
        """Set medium-horizon goal focus supplied by GoalMemory.

        FR-GOAL-MEM-01: persistent goals bias scheduler choices without
        replacing short-horizon GoalState.
        """

        self._state.goal_focus = goal_text
        self._state.goal_focus_type = focus_type

    def tick(self, *, current_zone: str | None = None) -> LifeActivity | None:
        """Poll for activity change. Call roughly every 60s real-time.

        Args:
            current_zone: Current Unity zone/room name from WorldContext
                (e.g. "living_room", "sleep_area").  None when unknown.
                Used to ground the scheduler in the avatar's actual world
                position (BDI Beliefs layer, Issue #46 / FR-E1-01).

        Returns:
            LifeActivity if a new activity should start, else None.

        Side effects:
            Updates energy; logs activity transitions.

        FR-LIFE-01: Critical energy overrides schedule and forces sleep.
        """
        # Store current zone for downstream consumers (closes BDI Beliefs loop)
        if current_zone is not None and current_zone != self._state.current_zone:
            logger.debug(
                "[LifeScheduler] zone updated: %s → %s", self._state.current_zone, current_zone
            )
        self._state.current_zone = current_zone
        now_mono = self._mono_fn()
        now_dt = self._time_fn()

        # 1. Update energy (based on wall-clock time since last tick)
        energy_elapsed = now_mono - self._last_energy_sample
        self._last_energy_sample = now_mono
        self._update_energy(energy_elapsed)

        # 2. FR-GOAL-01: natural decay of GoalState toward baseline each tick
        self._state.goal.decay()

        # 3. Critical energy → force sleep regardless of schedule or duration
        if (
            self._state.energy <= _CRITICAL_ENERGY
            and self._state.current_activity != ActivityType.SLEEP
        ):
            logger.info(
                "[LifeScheduler] Energy critical (%.2f) — forcing SLEEP",
                self._state.energy,
            )
            return self._switch_to(ActivityType.SLEEP)

        # 4. Don't switch before minimum activity duration
        activity_elapsed = now_mono - self._state.activity_started_at
        if activity_elapsed < _MIN_ACTIVITY_DURATION_SEC:
            return None

        # 5. Compare desired activity to current
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
        """Map hour-of-day + GoalState to preferred ActivityType.

        FR-LIFE-01: time-of-day schedule defines base preference.
        FR-GOAL-01: GoalState can override when an alternative activity's
                    goal alignment exceeds the schedule activity's alignment
                    by at least _GOAL_INFLUENCE (hysteresis prevents jitter).
        """
        # Time-of-day baseline
        schedule_act = ActivityType.SLEEP
        for start, end, act_type in _HOUR_SCHEDULE:
            if start <= hour < end:
                schedule_act = act_type
                break

        # SLEEP/WAKE are never overridden by GoalState
        if schedule_act in (ActivityType.SLEEP, ActivityType.WAKE):
            return schedule_act

        # FR-GOAL-01: find goal-aligned alternative that strongly beats schedule
        sched_bonus = self._goal_bonus(schedule_act)
        best_act = schedule_act
        best_bonus = sched_bonus
        for candidate in _GOAL_WEIGHTS:
            if candidate in (
                schedule_act,
                ActivityType.SLEEP,
                ActivityType.WAKE,
                ActivityType.IDLE,
            ):
                continue
            bonus = self._goal_bonus(candidate)
            if bonus - sched_bonus > _GOAL_INFLUENCE and bonus > best_bonus:
                best_act = candidate
                best_bonus = bonus

        if best_act != schedule_act:
            logger.debug(
                "[LifeScheduler] GoalState override: %s → %s (score %.2f → %.2f)",
                schedule_act,
                best_act,
                sched_bonus,
                best_bonus,
            )
        return best_act

    def _goal_bonus(self, activity_type: ActivityType) -> float:
        """GoalState による活動の目標整合スコア (0.0〜最大約1.0).

        FR-GOAL-01: 各 ActivityType の _GOAL_WEIGHTS と現在の GoalState の
        内積を返す。高いほど現在の動機状態と活動が整合している。
        """
        weights = _GOAL_WEIGHTS.get(activity_type, {})
        gs = self._state.goal
        bonus = (
            weights.get("curiosity", 0.0) * gs.curiosity
            + weights.get("social_drive", 0.0) * gs.social_drive
            + weights.get("exploration", 0.0) * gs.exploration
        )
        focus_type = self._state.goal_focus_type
        if focus_type:
            bonus += _LONG_TERM_GOAL_BONUS.get(focus_type, {}).get(activity_type, 0.0)
        return bonus

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
