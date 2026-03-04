"""Contextual bandit for chat action selection.

SRS refs: FR-RL-01, FR-BANDIT-EPS-01, bandit.yml, TC-D-01.
Actions: reply_now | queue_and_reply_later | summarize_cluster | ignore.
Reward formula v1.0 params: k=0.10, m=0.05, n=0.10, S=5.0.
ε auto-adjustment: epsilon decreases linearly as chat_rate_15s increases,
  clamped to [epsilon_min, epsilon_max] from BanditConfig.
"""

from __future__ import annotations

import json
import logging
import time
import uuid
from collections import OrderedDict
from collections.abc import Sequence
from dataclasses import asdict, dataclass, field
from pathlib import Path

import numpy as np

from orchestrator.config import BanditConfig

logger = logging.getLogger(__name__)

# ── 報酬パラメータ デフォルト (bandit.yml formula_version=1.0) ────────
# BanditConfig から上書き可能。compute_reward() は引数で受け取る。
_DEFAULT_K = 0.10  # エンゲージメント係数
_DEFAULT_M = 0.05  # センチメント係数
_DEFAULT_N = 0.10  # 沈黙ペナルティ係数
_DEFAULT_S = 5.0  # 沈黙閾値(秒)


@dataclass
class BanditContext:
    """Minimal context features (from bandit.yml context_features_min)."""

    t_since_last_reply_sec: float = 0.0
    chat_rate_15s: int = 0
    # Recommended features
    unique_authors_60s: int = 0
    is_summary_mode: bool = False
    topic_phase: str = "normal"
    silence_risk: float = 0.0
    viewer_sentiment_hint: float = 0.0
    safety_risk: float = 0.0


@dataclass
class BanditDecision:
    decision_id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    context: BanditContext = field(default_factory=BanditContext)
    action: str = ""
    probabilities: dict[str, float] = field(default_factory=dict)
    ts: float = field(default_factory=time.time)


@dataclass
class BanditReward:
    decision_id: str = ""
    reward: float = 0.0
    safe: bool = False
    ts: float = field(default_factory=time.time)

    # 報酬計算の入力信号
    engagement_signal: float = 0.0  # 視聴者反応 (0..1)
    sentiment_bonus: float = 0.0  # 正のセンチメント (0..1)
    silence_sec: float = 0.0  # 無音時間
    delta_chat_rate: float = 0.0  # チャットレート変化量


def compute_reward(
    base: float,
    engagement: float = 0.0,
    sentiment: float = 0.0,
    silence_sec: float = 0.0,
    *,
    action: str = "",
    is_summary_mode: bool = False,
    delta_chat_rate: float = 0.0,
    safety_risk: float = 0.0,
    k: float = _DEFAULT_K,
    m: float = _DEFAULT_M,
    n: float = _DEFAULT_N,
    s: float = _DEFAULT_S,
) -> float:
    """Compute reward using formula v1.0.

    R = base + k*engagement + m*sentiment - n*max(0, silence - S)
        + action_adjustment

    パラメータ k/m/n/s は BanditConfig から渡すことで上書き可能。
    """
    silence_penalty = n * max(0.0, silence_sec - s)
    r = base + k * engagement + m * sentiment - silence_penalty

    # action_adjustments (bandit.yml)
    if action == "summarize_cluster":
        if is_summary_mode and delta_chat_rate >= 0:
            r += 0.5
    elif action == "ignore" and safety_risk > 0.8:
        r = max(r, 0.3)
        # base_otherwise → 0.0 (no adjustment)

    return round(r, 4)


class ContextualBandit:
    """ε-greedy contextual bandit with JSONL logging.

    FR-RL-01: Log each decision pre/post. Do not update model on safe=true.
    """

    # 直近のdecision_id→action マッピング (最大1000件, 古いものから削除)
    _MAX_PENDING = 1000

    def __init__(
        self,
        config: BanditConfig | None = None,
        log_path: Path | None = None,
        epsilon: float = 0.15,
        auto_adapt: bool = False,
    ) -> None:
        self._cfg = config or BanditConfig()
        self._actions = list(self._cfg.actions)
        self._epsilon = epsilon
        self._auto_adapt = auto_adapt
        self._log_path = log_path or Path("bandit_log.jsonl")

        # 各アクションの累積報酬 (action → [cumulative, count])
        self._weights: dict[str, list[float]] = {a: [0.0, 0.0] for a in self._actions}
        # decision_id → (action, context) 追跡
        self._pending: OrderedDict[str, tuple[str, BanditContext]] = OrderedDict()

    @property
    def actions(self) -> Sequence[str]:
        return self._actions

    def adapt_epsilon(self, chat_rate_15s: int) -> float:
        """Compute adaptive ε from viewer chat rate and cache it.

        FR-BANDIT-EPS-01: epsilon decreases linearly as chat_rate_15s rises.
          - chat_rate_15s == 0            → epsilon_max (explore)
          - chat_rate_15s >= threshold    → epsilon_min (exploit)
          - in between                    → linear interpolation

        The computed value is stored in self._epsilon for the next select_action call.
        Returns the new epsilon value.
        """
        lo = self._cfg.epsilon_min
        hi = self._cfg.epsilon_max
        threshold = max(1, self._cfg.viewer_rate_threshold)
        rate = max(0, chat_rate_15s)
        ratio = min(1.0, rate / threshold)
        new_eps = hi - (hi - lo) * ratio
        self._epsilon = round(new_eps, 6)
        return self._epsilon

    def select_action(self, ctx: BanditContext) -> BanditDecision:
        """Select an action using ε-greedy policy.

        FR-BANDIT-EPS-01: Auto-adapts epsilon from ctx.chat_rate_15s before
        each decision to reflect current viewer activity.
        Returns a BanditDecision (logged as 'pre').
        """
        # FR-BANDIT-EPS-01: realtime epsilon adaptation (opt-in)
        if self._auto_adapt:
            self.adapt_epsilon(ctx.chat_rate_15s)
        # Heuristic overrides
        if ctx.safety_risk > 0.8:
            action = "ignore"
            probs = {a: (1.0 if a == action else 0.0) for a in self._actions}
        elif ctx.is_summary_mode:
            action = "summarize_cluster"
            probs = {a: (1.0 if a == action else 0.0) for a in self._actions}
        elif np.random.random() < self._epsilon:
            action = np.random.choice(self._actions)
            probs = {a: 1.0 / len(self._actions) for a in self._actions}
        else:
            action = self._best_action()
            probs = {a: (0.0 if a != action else 1.0 - self._epsilon) for a in self._actions}
            probs[action] = max(probs[action], 1.0 - self._epsilon)

        decision = BanditDecision(context=ctx, action=action, probabilities=probs)
        self._log("pre", decision)

        # 追跡に登録
        self._pending[decision.decision_id] = (action, ctx)
        while len(self._pending) > self._MAX_PENDING:
            self._pending.popitem(last=False)

        return decision

    def record_reward(self, reward: BanditReward) -> None:
        """Record outcome and update model.

        FR-RL-01: Do not update model on safe=true outcomes.
        """
        self._log("post", reward)
        if reward.safe:
            logger.debug("Reward safe=True for %s; skipping model update.", reward.decision_id)
            return

        # decision_id から action と context を取得
        pending = self._pending.pop(reward.decision_id, None)
        if pending is not None:
            action, ctx = pending
            computed = compute_reward(
                base=reward.reward,
                engagement=reward.engagement_signal,
                sentiment=reward.sentiment_bonus,
                silence_sec=reward.silence_sec,
                action=action,
                is_summary_mode=ctx.is_summary_mode,
                delta_chat_rate=reward.delta_chat_rate,
                safety_risk=ctx.safety_risk,
                k=self._cfg.k,
                m=self._cfg.m,
                n=self._cfg.n,
                s=self._cfg.s,
            )
            self._update_weights(action, computed)
        else:
            logger.warning("Unknown decision_id: %s; applying raw reward.", reward.decision_id)

    def update_action_reward(self, action: str, reward_value: float, safe: bool = False) -> None:
        """Directly update an action's running average."""
        if safe:
            return
        self._update_weights(action, reward_value)

    def _update_weights(self, action: str, reward_value: float) -> None:
        if action in self._weights:
            total, count = self._weights[action]
            self._weights[action] = [total + reward_value, count + 1]

    def _best_action(self) -> str:
        best_avg = -float("inf")
        best_action = self._actions[0]
        for a in self._actions:
            total, count = self._weights[a]
            avg = total / count if count > 0 else 0.0
            if avg > best_avg:
                best_avg = avg
                best_action = a
        return best_action

    def _log(self, phase: str, data: BanditDecision | BanditReward) -> None:
        """Append JSONL log entry. Rotate when file exceeds _ROTATE_MB."""
        try:
            self._maybe_rotate()
            entry = {
                "phase": phase,
                "ts": time.time(),
                "data": asdict(data) if hasattr(data, "__dataclass_fields__") else str(data),
            }
            with open(self._log_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(entry, ensure_ascii=False, default=str) + "\n")
        except Exception:
            logger.exception("Failed to write bandit log")

    # ── ログローテーション (bandit.yml: rotate_mb=50, retention_days=90) ──

    _ROTATE_MB = 50
    _RETENTION_DAYS = 90

    def _maybe_rotate(self) -> None:
        """ファイルが _ROTATE_MB を超えたら .bak にリネーム。"""
        try:
            if not self._log_path.exists():
                return
            size_mb = self._log_path.stat().st_size / (1024 * 1024)
            if size_mb >= self._ROTATE_MB:
                bak = self._log_path.with_suffix(".jsonl.bak")
                if bak.exists():
                    bak.unlink()
                self._log_path.rename(bak)
                logger.info("Bandit log rotated: %.1f MB → %s", size_mb, bak)
        except Exception:
            logger.warning("Bandit log rotation failed")

        # 日付ベース保持: .bak が _RETENTION_DAYS 日以上古い場合は削除
        self._cleanup_old_backups()

    def _cleanup_old_backups(self) -> None:
        """retention_days を超えた .bak ファイルを削除。"""
        try:
            bak = self._log_path.with_suffix(".jsonl.bak")
            if not bak.exists():
                return
            age_days = (time.time() - bak.stat().st_mtime) / 86400
            if age_days >= self._RETENTION_DAYS:
                bak.unlink()
                logger.info("Bandit backup deleted (age=%.0f days): %s", age_days, bak)
        except Exception:
            logger.warning("Bandit backup cleanup failed")
