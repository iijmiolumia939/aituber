"""Broadcast Lifecycle Manager — orchestrates autonomous OBS streaming.

FR-BCAST-01..04: Evaluates desire, gets human approval, starts OBS, manages
pre/on-air/post broadcast phases.
Issue: #17 E-7. OBS Autonomous Broadcast Lifecycle.

State machine:
  IDLE → DESIRING → AWAITING_APPROVAL → PRE_BROADCAST → ON_AIR → POST_BROADCAST → IDLE
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import StrEnum

logger = logging.getLogger(__name__)


class BroadcastPhase(StrEnum):
    IDLE = "idle"
    DESIRING = "desiring"
    AWAITING_APPROVAL = "awaiting_approval"
    PRE_BROADCAST = "pre_broadcast"
    ON_AIR = "on_air"
    POST_BROADCAST = "post_broadcast"


@dataclass
class BroadcastSession:
    """Records state for a single broadcast session.

    FR-BCAST-01..04.
    """

    phase: BroadcastPhase = BroadcastPhase.IDLE
    title: str = ""
    started_at: float = 0.0  # time.time() when stream started
    ended_at: float = 0.0
    desire_score: float = 0.0
    approved: bool = False
    errors: list[str] = field(default_factory=list)

    @property
    def duration_sec(self) -> float:
        if self.started_at and self.ended_at:
            return self.ended_at - self.started_at
        if self.started_at:
            return time.time() - self.started_at
        return 0.0


class BroadcastLifecycleManager:
    """Manages the full autonomous broadcast lifecycle.

    FR-BCAST-01: Evaluates desire and decides whether to broadcast.
    FR-BCAST-02: Delegates OBS start/stop to an OBSController.
    FR-BCAST-03: Generates broadcast title via llm_fn.
    FR-BCAST-04: Ends broadcast on timer or stop intent.
    NFR-BCAST-02: Requires human approval before going on-air.

    All external calls (OBS, LLM, approval) are injected as callables
    to keep this class fully testable without live services.

    Args:
        desire_evaluator: callable(energy, content_count, hours_since_last) → DesireState.
        obs_start: callable() → bool — starts OBS and returns success.
        obs_stop: callable() → None.
        stream_start: callable() → bool.
        stream_stop: callable() → bool.
        approval_fn: callable(desire_score) → bool — human approval gate.
        llm_fn: callable(prompt) → str — generates broadcast title.
        max_duration_sec: auto-stop stream after this many seconds (0 = unlimited).
    """

    _TITLE_PROMPT = (
        "YUI.Aとして、今日のYouTube配信タイトルを20文字以内で考えてください。"
        "AIの観測システムらしいタイトルにしてください。タイトルだけを返してください。"
    )

    def __init__(
        self,
        *,
        desire_evaluator: Callable[..., object] | None = None,
        obs_start: Callable[[], bool] | None = None,
        obs_stop: Callable[[], None] | None = None,
        stream_start: Callable[[], bool] | None = None,
        stream_stop: Callable[[], bool] | None = None,
        approval_fn: Callable[[float], bool] | None = None,
        llm_fn: Callable[[str], str] | None = None,
        max_duration_sec: float = 0.0,
    ) -> None:
        from orchestrator.broadcast_desire import BroadcastDesireEvaluator

        self._desire_eval = desire_evaluator or BroadcastDesireEvaluator().evaluate
        self._obs_start = obs_start or (lambda: False)
        self._obs_stop = obs_stop or (lambda: None)
        self._stream_start = stream_start or (lambda: False)
        self._stream_stop = stream_stop or (lambda: False)
        self._approval_fn = approval_fn or (lambda score: False)  # deny by default
        self._llm_fn = llm_fn
        self._max_duration_sec = max_duration_sec
        self._session = BroadcastSession()
        self._is_live = False

    # ── Public interface ──────────────────────────────────────────────

    @property
    def phase(self) -> BroadcastPhase:
        return self._session.phase

    @property
    def is_live(self) -> bool:
        return self._is_live

    @property
    def session(self) -> BroadcastSession:
        return self._session

    def evaluate_desire(
        self,
        energy: float = 0.5,
        content_count: int = 0,
        hours_since_last: float = 0.0,
    ) -> float:
        """Compute broadcast desire score without side-effects.

        FR-BCAST-01.
        """
        from orchestrator.broadcast_desire import BroadcastDesireEvaluator

        bde = BroadcastDesireEvaluator()
        state = bde.evaluate(energy, content_count, hours_since_last)
        self._session.desire_score = state.desire_score
        self._session.phase = BroadcastPhase.DESIRING
        return state.desire_score

    def request_approval(self, desire_score: float) -> bool:
        """Ask human for approval to go live.

        NFR-BCAST-02: No stream starts without approval.
        """
        self._session.phase = BroadcastPhase.AWAITING_APPROVAL
        approved = self._approval_fn(desire_score)
        self._session.approved = approved
        logger.info("[BroadcastLifecycle] Human approval: %s (score=%.2f)", approved, desire_score)
        return approved

    def pre_broadcast(self) -> bool:
        """Launch OBS and generate title.

        FR-BCAST-02, FR-BCAST-03: Starts OBS, generates title.
        Returns True if OBS launched successfully.
        """
        self._session.phase = BroadcastPhase.PRE_BROADCAST
        title = self._generate_title()
        self._session.title = title
        logger.info("[BroadcastLifecycle] Broadcast title: %s", title)

        ok = self._obs_start()
        if not ok:
            err = "OBS launch failed"
            self._session.errors.append(err)
            logger.warning("[BroadcastLifecycle] %s", err)
            self._session.phase = BroadcastPhase.IDLE
            return False
        return True

    def go_live(self) -> bool:
        """Start the stream.

        FR-BCAST-02: Calls stream_start. Marks session as on-air.
        """
        if self._is_live:
            logger.warning("[BroadcastLifecycle] Already live — ignoring go_live()")
            return False
        ok = self._stream_start()
        if ok:
            self._is_live = True
            self._session.started_at = time.time()
            self._session.phase = BroadcastPhase.ON_AIR
            logger.info("[BroadcastLifecycle] Stream started: %s", self._session.title)
        else:
            self._session.errors.append("stream_start failed")
            logger.error("[BroadcastLifecycle] stream_start() returned False")
        return ok

    def end_broadcast(self, reason: str = "manual") -> None:
        """Stop stream and teardown.

        FR-BCAST-04: Stop by timer or intent_broadcast_stop.
        """
        self._session.phase = BroadcastPhase.POST_BROADCAST
        logger.info("[BroadcastLifecycle] Ending broadcast (reason=%s)", reason)
        self._stream_stop()
        self._obs_stop()
        self._is_live = False
        self._session.ended_at = time.time()
        self._session.phase = BroadcastPhase.IDLE

    def check_auto_stop(self) -> bool:
        """Return True if the stream should auto-stop due to duration limit.

        FR-BCAST-04: Triggers end_broadcast if max_duration exceeded.
        """
        if not self._is_live or self._max_duration_sec <= 0:
            return False
        if self._session.duration_sec >= self._max_duration_sec:
            self.end_broadcast(reason="auto_timer")
            return True
        return False

    # ── Private helpers ───────────────────────────────────────────────

    def _generate_title(self) -> str:
        if self._llm_fn is None:
            return "YUI.A 観測配信"
        try:
            return self._llm_fn(self._TITLE_PROMPT).strip()[:60] or "YUI.A 観測配信"
        except Exception as exc:  # noqa: BLE001
            logger.warning("[BroadcastLifecycle] Title LLM failed: %s", exc)
            return "YUI.A 観測配信"
