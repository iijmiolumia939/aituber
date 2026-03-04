"""Bandit ε自動調整テスト — 視聴者数に応じた探索率動的変更。

SRS refs: FR-BANDIT-EPS-01.
TC-M11-01 〜 TC-M11-14
"""

from __future__ import annotations

import pytest

from orchestrator.bandit import BanditContext, ContextualBandit
from orchestrator.config import BanditConfig

# ── Helper ────────────────────────────────────────────────────────────


def _cfg(
    epsilon_min: float = 0.05,
    epsilon_max: float = 0.30,
    threshold: int = 20,
) -> BanditConfig:
    return BanditConfig(
        epsilon_min=epsilon_min,
        epsilon_max=epsilon_max,
        viewer_rate_threshold=threshold,
    )


def _bandit(
    epsilon_min: float = 0.05,
    epsilon_max: float = 0.30,
    threshold: int = 20,
    auto_adapt: bool = False,
) -> ContextualBandit:
    return ContextualBandit(
        config=_cfg(epsilon_min, epsilon_max, threshold),
        auto_adapt=auto_adapt,
        log_path=None,  # uses default path but won't be written in these tests
    )


# ── TC-M11-01〜08: adapt_epsilon メソッド ────────────────────────────


class TestAdaptEpsilon:
    """TC-M11-01 〜 TC-M11-08"""

    def test_rate_zero_returns_epsilon_max(self) -> None:
        """TC-M11-01: chat_rate=0 → epsilon_max (探索最大)。"""
        b = _bandit(epsilon_min=0.05, epsilon_max=0.30, threshold=20)
        eps = b.adapt_epsilon(0)
        assert eps == pytest.approx(0.30)

    def test_rate_at_threshold_returns_epsilon_min(self) -> None:
        """TC-M11-02: chat_rate == threshold → epsilon_min (活用最大)。"""
        b = _bandit(epsilon_min=0.05, epsilon_max=0.30, threshold=20)
        eps = b.adapt_epsilon(20)
        assert eps == pytest.approx(0.05)

    def test_rate_above_threshold_clamped_to_epsilon_min(self) -> None:
        """TC-M11-03: chat_rate > threshold → epsilon_min でクランプ。"""
        b = _bandit(epsilon_min=0.05, epsilon_max=0.30, threshold=20)
        eps = b.adapt_epsilon(100)
        assert eps == pytest.approx(0.05)

    def test_rate_negative_clamped_to_epsilon_max(self) -> None:
        """TC-M11-04: chat_rate < 0 → epsilon_max でクランプ。"""
        b = _bandit(epsilon_min=0.05, epsilon_max=0.30, threshold=20)
        eps = b.adapt_epsilon(-5)
        assert eps == pytest.approx(0.30)

    def test_midpoint_interpolation(self) -> None:
        """TC-M11-05: chat_rate = threshold/2 → (max+min)/2。"""
        b = _bandit(epsilon_min=0.10, epsilon_max=0.30, threshold=20)
        eps = b.adapt_epsilon(10)
        assert eps == pytest.approx(0.20, abs=1e-6)

    def test_adapt_epsilon_updates_internal_epsilon(self) -> None:
        """TC-M11-06: adapt_epsilon は self._epsilon を更新する。"""
        b = _bandit(epsilon_min=0.05, epsilon_max=0.30, threshold=20)
        b.adapt_epsilon(10)
        assert b._epsilon == pytest.approx(0.175, abs=1e-6)

    def test_epsilon_min_equals_epsilon_max_constant(self) -> None:
        """TC-M11-07: epsilon_min == epsilon_max → rate に関係なく一定。"""
        b = _bandit(epsilon_min=0.10, epsilon_max=0.10, threshold=20)
        for rate in [0, 5, 10, 20, 100]:
            assert b.adapt_epsilon(rate) == pytest.approx(0.10), f"rate={rate}"

    def test_result_always_in_range(self) -> None:
        """TC-M11-08: 結果は [epsilon_min, epsilon_max] の範囲内に収まる。"""
        b = _bandit(epsilon_min=0.05, epsilon_max=0.30, threshold=10)
        for rate in range(-5, 25):
            eps = b.adapt_epsilon(rate)
            assert 0.05 <= eps <= 0.30, f"rate={rate}, eps={eps}"


# ── TC-M11-09〜11: auto_adapt=True 統合 ──────────────────────────────


class TestAutoAdaptIntegration:
    """TC-M11-09 〜 TC-M11-11"""

    def test_auto_adapt_off_does_not_change_epsilon(self, tmp_path) -> None:
        """TC-M11-09: auto_adapt=False (default) では select_action が epsilon を変えない。"""
        b = ContextualBandit(
            config=_cfg(),
            epsilon=0.15,
            auto_adapt=False,
            log_path=tmp_path / "log.jsonl",
        )
        ctx = BanditContext(chat_rate_15s=20)
        b.select_action(ctx)
        assert b._epsilon == pytest.approx(0.15)

    def test_auto_adapt_on_updates_epsilon_each_call(self, tmp_path) -> None:
        """TC-M11-10: auto_adapt=True では select_action が
        chat_rate_15s に基づいて epsilon を更新。"""
        b = ContextualBandit(
            config=_cfg(epsilon_min=0.05, epsilon_max=0.30, threshold=20),
            epsilon=0.15,
            auto_adapt=True,
            log_path=tmp_path / "log.jsonl",
        )
        # chat_rate_15s=0 → epsilon_max=0.30
        ctx_low = BanditContext(chat_rate_15s=0)
        b.select_action(ctx_low)
        assert b._epsilon == pytest.approx(0.30)

        # chat_rate_15s=20 → epsilon_min=0.05
        ctx_high = BanditContext(chat_rate_15s=20)
        b.select_action(ctx_high)
        assert b._epsilon == pytest.approx(0.05)

    def test_auto_adapt_on_high_rate_exploits_more(self, tmp_path) -> None:
        """TC-M11-11: 視聴者数が多い (rate=20) でほぼ決定論的な選択になる。"""
        cfg = _cfg(epsilon_min=0.00, epsilon_max=0.00, threshold=20)
        b = ContextualBandit(
            config=cfg,
            epsilon=0.0,
            auto_adapt=True,
            log_path=tmp_path / "log.jsonl",
        )
        # Train to prefer reply_now
        b.update_action_reward("reply_now", 1.0)
        b.update_action_reward("reply_now", 1.0)

        actions = set()
        for _ in range(20):
            ctx = BanditContext(chat_rate_15s=20)
            d = b.select_action(ctx)
            actions.add(d.action)

        # With epsilon=0 (max adaptation), always greedy
        assert actions == {"reply_now"}


# ── TC-M11-12〜14: BanditConfig defaults & custom config ─────────────


class TestBanditConfigDefaults:
    """TC-M11-12 〜 TC-M11-14"""

    def test_default_config_has_epsilon_fields(self) -> None:
        """TC-M11-12: BanditConfig のデフォルト値が設定されている。"""
        cfg = BanditConfig()
        assert 0.0 < cfg.epsilon_min < cfg.epsilon_max <= 1.0
        assert cfg.viewer_rate_threshold > 0

    def test_custom_config_overrides_epsilon_params(self) -> None:
        """TC-M11-13: カスタム config でε パラメータを上書きできる。"""
        cfg = BanditConfig(epsilon_min=0.01, epsilon_max=0.50, viewer_rate_threshold=50)
        b = ContextualBandit(config=cfg)
        eps = b.adapt_epsilon(0)
        assert eps == pytest.approx(0.50)
        eps = b.adapt_epsilon(50)
        assert eps == pytest.approx(0.01)

    def test_adapt_epsilon_with_threshold_one(self) -> None:
        """TC-M11-14: threshold=1 でも safe (÷0 なし)。"""
        b = _bandit(epsilon_min=0.05, epsilon_max=0.30, threshold=1)
        assert b.adapt_epsilon(0) == pytest.approx(0.30)
        assert b.adapt_epsilon(1) == pytest.approx(0.05)
        assert b.adapt_epsilon(2) == pytest.approx(0.05)
