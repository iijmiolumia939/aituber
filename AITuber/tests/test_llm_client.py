"""TC-LLM-01: LLM fallback template mode.

Maps to: FR-LLM-01.
"""

from __future__ import annotations

import pytest

from orchestrator.config import LLMConfig
from orchestrator.llm_client import CostTracker, LLMClient

# ── Mock backend ──────────────────────────────────────────────────────


class FailingBackend:
    """Always raises an exception."""

    def __init__(self, fail_count: int = 999):
        self._fail_count = fail_count
        self._call_count = 0

    async def chat(self, system: str, user: str) -> tuple[str, float]:
        self._call_count += 1
        if self._call_count <= self._fail_count:
            raise ConnectionError("API unavailable")
        return ("mock reply", 0.01)

    @property
    def call_count(self) -> int:
        return self._call_count


class SuccessBackend:
    """Always succeeds."""

    async def chat(self, system: str, user: str) -> tuple[str, float]:
        return (f"Reply to: {user}", 0.05)


class FailThenSucceedBackend:
    """Fails N times, then succeeds."""

    def __init__(self, fail_count: int = 1):
        self._fail_count = fail_count
        self._call_count = 0

    async def chat(self, system: str, user: str) -> tuple[str, float]:
        self._call_count += 1
        if self._call_count <= self._fail_count:
            raise ConnectionError("Temporary failure")
        return ("recovered reply", 0.01)


# ── Tests ─────────────────────────────────────────────────────────────


class TestLLMFallback:
    """TC-LLM-01: LLM fallback template mode (FR-LLM-01)."""

    @pytest.mark.asyncio
    async def test_all_retries_exhausted_gives_template(self):
        """After max_retries failures, returns template response."""
        cfg = LLMConfig(max_retries=2)
        backend = FailingBackend()
        client = LLMClient(config=cfg, backend=backend)

        result = await client.generate_reply("テスト")
        assert result.is_template is True
        assert len(result.text) > 0
        # Should have attempted max_retries + 1 total calls
        assert backend.call_count == cfg.max_retries + 1

    @pytest.mark.asyncio
    async def test_success_on_first_try(self):
        cfg = LLMConfig(max_retries=2)
        client = LLMClient(config=cfg, backend=SuccessBackend())

        result = await client.generate_reply("こんにちは")
        assert result.is_template is False
        assert "こんにちは" in result.text
        assert result.retries_used == 0

    @pytest.mark.asyncio
    async def test_success_after_retry(self):
        """Recovers after one failure."""
        cfg = LLMConfig(max_retries=2)
        backend = FailThenSucceedBackend(fail_count=1)
        client = LLMClient(config=cfg, backend=backend)

        result = await client.generate_reply("リトライテスト")
        assert result.is_template is False
        assert result.retries_used == 1

    @pytest.mark.asyncio
    async def test_template_mode_does_not_stop_speech(self):
        """Template mode returns a non-empty text (speech continues)."""
        cfg = LLMConfig(max_retries=0)
        client = LLMClient(config=cfg, backend=FailingBackend())

        result = await client.generate_reply("何か言って")
        assert result.is_template is True
        assert len(result.text) > 0  # Speech continues

    @pytest.mark.asyncio
    async def test_cost_hard_limit_triggers_template(self):
        """NFR-COST-01: Over hard limit → template mode."""
        cfg = LLMConfig(cost_hard_limit_yen_per_hour=1.0)
        client = LLMClient(config=cfg, backend=SuccessBackend())

        # Simulate spending
        client.cost_tracker.record(2.0)

        result = await client.generate_reply("コスト超過テスト")
        assert result.is_template is True


class TestCostTracker:
    """NFR-COST-01: Cost guardrail."""

    def test_under_target(self):
        ct = CostTracker(target=150.0, hard_limit=300.0)
        ct.record(50.0)
        assert ct.is_over_target() is False
        assert ct.is_over_hard_limit() is False

    def test_over_target_under_hard(self):
        ct = CostTracker(target=150.0, hard_limit=300.0)
        ct.record(200.0)
        assert ct.is_over_target() is True
        assert ct.is_over_hard_limit() is False

    def test_over_hard_limit(self):
        ct = CostTracker(target=150.0, hard_limit=300.0)
        ct.record(300.0)
        assert ct.is_over_hard_limit() is True


class TestCostTrackerTemplateRatio:
    """NFR-COST-01: テンプレート率 (ソフトリミット)。"""

    def test_under_target_ratio_zero(self):
        """spend < target → ratio = 0.0。"""
        ct = CostTracker(target=150.0, hard_limit=300.0)
        ct.record(100.0)
        assert ct.template_ratio == 0.0

    def test_at_midpoint_ratio_half(self):
        """spend = (target + hard) / 2 → ratio ≈ 0.5。"""
        ct = CostTracker(target=100.0, hard_limit=300.0)
        ct.record(200.0)
        assert ct.template_ratio == pytest.approx(0.5)

    def test_at_hard_limit_ratio_one(self):
        """spend >= hard → ratio = 1.0。"""
        ct = CostTracker(target=150.0, hard_limit=300.0)
        ct.record(300.0)
        assert ct.template_ratio == 1.0

    def test_over_hard_limit_capped_at_one(self):
        """spend > hard → ratio は 1.0 にキャッピング。"""
        ct = CostTracker(target=150.0, hard_limit=300.0)
        ct.record(500.0)
        assert ct.template_ratio == 1.0

    def test_target_equals_hard(self):
        """target == hard → target 以上なら ratio = 1.0。"""
        ct = CostTracker(target=100.0, hard_limit=100.0)
        ct.record(100.0)
        assert ct.template_ratio == 1.0


class TestSoftLimitTemplateMode:
    """NFR-COST-01: ソフトリミット超過時に確率的にテンプレート。"""

    @pytest.mark.asyncio
    async def test_soft_limit_sometimes_returns_template(self):
        """ソフトリミット超過で、一定確率でテンプレートが返る。"""
        cfg = LLMConfig(
            cost_target_yen_per_hour=10.0,
            cost_hard_limit_yen_per_hour=20.0,
        )
        client = LLMClient(config=cfg, backend=SuccessBackend())
        # spend = 19 (target=10, hard=20 → ratio = 0.9)
        client.cost_tracker.record(19.0)

        template_count = 0
        for _ in range(100):
            result = await client.generate_reply("テスト")
            if result.is_template:
                template_count += 1

        # ratio=0.9 → 100回中かなりの割合がテンプレートになるはず
        assert template_count > 20  # 最低限 20% 以上
