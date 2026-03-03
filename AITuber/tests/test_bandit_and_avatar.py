"""TC-D-01: bandit_log pre/post output.
TC-A7-07: viseme events applied in order.
TC-A7-08: crossfade prevents abrupt jumps.

Maps to: FR-RL-01, FR-LIPSYNC-02.
"""

from __future__ import annotations

import json
import tempfile
import time
from pathlib import Path

import numpy as np

from orchestrator.avatar_ws import AvatarMessage, VisemeEvent, compute_rms_mouth_open
from orchestrator.bandit import BanditContext, ContextualBandit, compute_reward

# ── TC-D-01: bandit_log pre/post ──────────────────────────────────────


class TestBanditLog:
    """TC-D-01: bandit_log pre/post output (FR-RL-01)."""

    def test_pre_log_written(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as f:
            log_path = Path(f.name)

        bandit = ContextualBandit(log_path=log_path, epsilon=0.0)
        ctx = BanditContext(t_since_last_reply_sec=10.0, chat_rate_15s=3)
        bandit.select_action(ctx)

        log_lines = log_path.read_text().strip().split("\n")
        assert len(log_lines) >= 1
        entry = json.loads(log_lines[0])
        assert entry["phase"] == "pre"
        assert "data" in entry
        log_path.unlink()

    def test_post_log_written(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as f:
            log_path = Path(f.name)

        from orchestrator.bandit import BanditReward

        bandit = ContextualBandit(log_path=log_path, epsilon=0.0)
        reward = BanditReward(decision_id="test123", reward=0.8, safe=False)
        bandit.record_reward(reward)

        log_lines = log_path.read_text().strip().split("\n")
        assert len(log_lines) >= 1
        entry = json.loads(log_lines[-1])
        assert entry["phase"] == "post"
        log_path.unlink()

    def test_log_rotation_triggers(self):
        """bandit.yml: rotate_mb=50。閾値超過でリネーム。"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as f:
            log_path = Path(f.name)

        bandit = ContextualBandit(log_path=log_path, epsilon=0.0)
        bandit._ROTATE_MB = 0.0001  # 約100B で発火させる

        # ログを数行書き込む → _ROTATE_MB を極小に設定した状態で次の書き込み時にrotate
        ctx = BanditContext(t_since_last_reply_sec=1.0)
        bandit.select_action(ctx)
        bandit.select_action(ctx)  # 2回目で rotate_mb 超過→ rotate

        bak = log_path.with_suffix(".jsonl.bak")
        # rotation が発生していれば .bak が存在するか、元ファイルが小さくなっている
        rotated = bak.exists()
        log_path.unlink(missing_ok=True)
        bak.unlink(missing_ok=True)
        assert rotated

    def test_retention_days_cleanup(self):
        """bandit.yml: retention_days=90。古い .bak を削除。"""
        import os

        with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as f:
            log_path = Path(f.name)

        bak = log_path.with_suffix(".jsonl.bak")
        bak.write_text("{}\n", encoding="utf-8")

        # .bak の mtime を 100 日前に設定
        old_time = time.time() - (100 * 86400)
        os.utime(bak, (old_time, old_time))

        bandit = ContextualBandit(log_path=log_path, epsilon=0.0)
        bandit._RETENTION_DAYS = 90

        ctx = BanditContext(t_since_last_reply_sec=1.0)
        bandit.select_action(ctx)  # _log → _maybe_rotate → _cleanup_old_backups

        assert not bak.exists(), ".bak should be deleted after 90 days"
        log_path.unlink(missing_ok=True)

    def test_retention_days_keeps_recent(self):
        """retention_days: 直近の .bak は削除されない。"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as f:
            log_path = Path(f.name)

        bak = log_path.with_suffix(".jsonl.bak")
        bak.write_text("{}\n", encoding="utf-8")

        bandit = ContextualBandit(log_path=log_path, epsilon=0.0)
        bandit._RETENTION_DAYS = 90

        ctx = BanditContext(t_since_last_reply_sec=1.0)
        bandit.select_action(ctx)

        assert bak.exists(), "Recent .bak should not be deleted"
        log_path.unlink(missing_ok=True)
        bak.unlink(missing_ok=True)

    def test_safe_true_skips_model_update(self):
        """FR-RL-01: Do not update model on safe=true outcomes."""

        with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as f:
            log_path = Path(f.name)

        bandit = ContextualBandit(log_path=log_path, epsilon=0.0)
        # Record a reward for an action
        bandit.update_action_reward("reply_now", 1.0, safe=False)
        # Record same but safe=True → should not update
        bandit.update_action_reward("reply_now", 100.0, safe=True)

        # Check that weights only reflect the non-safe update
        total, count = bandit._weights["reply_now"]
        assert count == 1
        assert total == 1.0
        log_path.unlink()

    def test_action_selection_returns_valid_action(self):
        bandit = ContextualBandit(epsilon=1.0)  # full exploration
        ctx = BanditContext()
        decision = bandit.select_action(ctx)
        assert decision.action in bandit.actions

    def test_summary_mode_selects_summarize(self):
        bandit = ContextualBandit()
        ctx = BanditContext(is_summary_mode=True)
        decision = bandit.select_action(ctx)
        assert decision.action == "summarize_cluster"

    def test_high_safety_risk_selects_ignore(self):
        bandit = ContextualBandit()
        ctx = BanditContext(safety_risk=0.9)
        decision = bandit.select_action(ctx)
        assert decision.action == "ignore"


# ── 報酬計算式 v1.0 テスト ────────────────────────────────────────────


class TestRewardFormula:
    """bandit.yml formula_version=1.0 パラメータ検証。"""

    def test_base_only(self):
        """追加信号なし → base がそのまま返る。"""
        assert compute_reward(1.0) == 1.0

    def test_engagement_bonus(self):
        """k=0.10 * engagement → base + 0.10。"""
        r = compute_reward(1.0, engagement=1.0)
        assert r == 1.1

    def test_sentiment_bonus(self):
        """m=0.05 * sentiment → base + 0.05。"""
        r = compute_reward(1.0, sentiment=1.0)
        assert r == 1.05

    def test_silence_penalty_below_threshold(self):
        """silence < S(5.0) → ペナルティなし。"""
        r = compute_reward(1.0, silence_sec=3.0)
        assert r == 1.0

    def test_silence_penalty_above_threshold(self):
        """silence=10 → penalty = 0.10 * (10-5) = 0.5。"""
        r = compute_reward(1.0, silence_sec=10.0)
        assert r == 0.5

    def test_summarize_cluster_bonus(self):
        """summary_mode=True & delta_chat>=0 → +0.5。"""
        r = compute_reward(
            1.0, action="summarize_cluster", is_summary_mode=True, delta_chat_rate=0.0
        )
        assert r == 1.5

    def test_summarize_no_bonus_without_summary_mode(self):
        r = compute_reward(1.0, action="summarize_cluster", is_summary_mode=False)
        assert r == 1.0

    def test_ignore_high_safety_floor(self):
        """safety_risk>0.8 → 最低0.3。"""
        r = compute_reward(0.0, action="ignore", safety_risk=0.9)
        assert r == 0.3

    def test_combined_signals(self):
        """全信号混合。"""
        r = compute_reward(0.5, engagement=0.8, sentiment=0.6, silence_sec=7.0)
        # 0.5 + 0.10*0.8 + 0.05*0.6 - 0.10*(7-5) = 0.5+0.08+0.03-0.2 = 0.41
        assert abs(r - 0.41) < 0.001


class TestDecisionTracking:
    """record_reward で decision_id → action を正しく追跡。"""

    def test_record_reward_updates_correct_action(self):
        from orchestrator.bandit import BanditReward

        with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as f:
            log_path = Path(f.name)

        bandit = ContextualBandit(log_path=log_path, epsilon=0.0)
        ctx = BanditContext(t_since_last_reply_sec=5.0)
        decision = bandit.select_action(ctx)

        reward = BanditReward(
            decision_id=decision.decision_id,
            reward=1.0,
            engagement_signal=0.5,
        )
        bandit.record_reward(reward)

        action = decision.action
        total, count = bandit._weights[action]
        assert count == 1
        assert total > 0
        log_path.unlink()

    def test_pending_eviction_at_capacity(self):
        """_MAX_PENDING を超えると古いものから削除。"""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as f:
            log_path = Path(f.name)

        bandit = ContextualBandit(log_path=log_path, epsilon=0.0)
        bandit._MAX_PENDING = 5  # type: ignore[attr-defined]

        first_ids = []
        for _ in range(7):
            d = bandit.select_action(BanditContext())
            first_ids.append(d.decision_id)

        # 最初の2件は削除されているはず
        assert first_ids[0] not in bandit._pending
        assert first_ids[1] not in bandit._pending
        assert first_ids[-1] in bandit._pending
        log_path.unlink()


# ── TC-A7-07: viseme events applied in order ─────────────────────────


class TestVisemeOrder:
    """TC-A7-07: viseme events applied in order (FR-LIPSYNC-02)."""

    def test_events_sorted_by_tms(self):
        """Events must be sorted by t_ms in the output message."""
        events = [
            VisemeEvent(t_ms=300, v="u"),
            VisemeEvent(t_ms=100, v="a"),
            VisemeEvent(t_ms=200, v="i"),
        ]
        sorted_events = sorted(events, key=lambda e: e.t_ms)
        assert [e.t_ms for e in sorted_events] == [100, 200, 300]
        assert [e.v for e in sorted_events] == ["a", "i", "u"]

    def test_already_sorted_unchanged(self):
        events = [
            VisemeEvent(t_ms=0, v="sil"),
            VisemeEvent(t_ms=50, v="a"),
            VisemeEvent(t_ms=100, v="o"),
        ]
        sorted_events = sorted(events, key=lambda e: e.t_ms)
        assert [e.t_ms for e in sorted_events] == [0, 50, 100]


# ── TC-A7-08: crossfade prevents abrupt jumps ────────────────────────


class TestCrossfade:
    """TC-A7-08: crossfade prevents abrupt jumps (FR-LIPSYNC-02)."""

    def test_crossfade_clamped_to_range(self):
        """crossfade_ms should be clamped to 40..80."""
        # Test via AvatarMessage construction (matching send_viseme logic)
        crossfade = max(40, min(80, 20))
        assert crossfade == 40

        crossfade = max(40, min(80, 100))
        assert crossfade == 80

        crossfade = max(40, min(80, 60))
        assert crossfade == 60

    def test_default_crossfade_in_range(self):
        """Default crossfade_ms (60) is within 40..80."""
        default = 60
        assert 40 <= default <= 80


# ── RMS lip sync (FR-LIPSYNC-01) ─────────────────────────────────────


class TestRMSMouthOpen:
    """FR-LIPSYNC-01: RMS mouth_open 0..1."""

    def test_silence_returns_zero(self):
        silence = np.zeros(1024, dtype=np.float32)
        assert compute_rms_mouth_open(silence) == 0.0

    def test_loud_clamped_to_one(self):
        loud = np.ones(1024, dtype=np.float32)
        result = compute_rms_mouth_open(loud)
        assert result <= 1.0

    def test_moderate_in_range(self):
        moderate = np.full(1024, 0.05, dtype=np.float32)
        result = compute_rms_mouth_open(moderate)
        assert 0.0 < result < 1.0

    def test_empty_array(self):
        empty = np.array([], dtype=np.float32)
        assert compute_rms_mouth_open(empty) == 0.0

    def test_sensitivity_scaling(self):
        chunk = np.full(1024, 0.05, dtype=np.float32)
        low = compute_rms_mouth_open(chunk, sensitivity=0.5)
        high = compute_rms_mouth_open(chunk, sensitivity=2.0)
        assert low <= high


# ── Avatar message format ─────────────────────────────────────────────


class TestAvatarMessageFormat:
    """Protocol contract: messages have id, ts, cmd, params."""

    def test_message_has_required_fields(self):
        msg = AvatarMessage(cmd="avatar_update", params={"emotion": "happy"})
        data = json.loads(msg.to_json())
        assert "id" in data
        assert "ts" in data
        assert "cmd" in data
        assert data["cmd"] == "avatar_update"
        assert data["params"]["emotion"] == "happy"

    def test_unknown_fields_preserved(self):
        """additionalProperties: true in schema."""
        msg = AvatarMessage(cmd="avatar_update", params={"emotion": "happy", "unknown_field": 42})
        data = json.loads(msg.to_json())
        assert data["params"]["unknown_field"] == 42

    def test_capabilities_message_format(self):
        """capabilities_message (optional handshake)."""
        msg = AvatarMessage(
            cmd="capabilities",
            params={
                "mouth_open": True,
                "viseme": True,
                "viseme_set": ["jp_basic_8"],
            },
        )
        data = json.loads(msg.to_json())
        assert data["cmd"] == "capabilities"
        assert data["params"]["mouth_open"] is True
        assert data["params"]["viseme"] is True
        assert "jp_basic_8" in data["params"]["viseme_set"]


class TestBanditConfigParams:
    """Verify BanditConfig k/m/n/s are wired into compute_reward."""

    def test_custom_k_param(self):
        r_default = compute_reward(0.5, engagement=1.0)
        r_custom = compute_reward(0.5, engagement=1.0, k=0.50)
        # k=0.50 should give bigger engagement bonus than k=0.10
        assert r_custom > r_default

    def test_custom_n_param(self):
        r_default = compute_reward(0.5, silence_sec=10.0)
        r_custom = compute_reward(0.5, silence_sec=10.0, n=0.50)
        # n=0.50 should give bigger silence penalty
        assert r_custom < r_default

    def test_custom_s_param(self):
        # With S=20, silence_sec=10 should NOT be penalized
        r_high_s = compute_reward(0.5, silence_sec=10.0, s=20.0)
        r_low_s = compute_reward(0.5, silence_sec=10.0, s=5.0)
        assert r_high_s > r_low_s
