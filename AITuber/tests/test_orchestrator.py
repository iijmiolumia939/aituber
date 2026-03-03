"""Pipeline integration tests.

TC-SAFE-01 (integration): NG-confirmed comments never reach Bandit/LLM.
Verifies the ordering Safety → Bandit → LLM (FR-SAFE-01).
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from orchestrator.chat_poller import ChatMessage
from orchestrator.config import AppConfig, LLMConfig
from orchestrator.main import Orchestrator


def _make_msg(text: str, msg_id: str = "test_msg") -> ChatMessage:
    return ChatMessage(
        message_id=msg_id,
        author_channel_id="UC_test",
        author_display_name="テストユーザー",
        text=text,
        published_at="2025-01-01T00:00:00Z",
        received_at=1000.0,
    )


class TestSafetyBlocksPipeline:
    """TC-SAFE-01 integration: NG messages must not reach Bandit or LLM."""

    @pytest.mark.asyncio
    async def test_ng_message_never_reaches_bandit(self):
        """NG message (hate speech) → Bandit.select_action NOT called."""
        cfg = AppConfig(llm=LLMConfig(max_retries=0))
        orch = Orchestrator(config=cfg)

        with patch.object(orch._bandit, "select_action", wraps=orch._bandit.select_action) as spy:
            await orch._process_message(_make_msg("死ね"))
            spy.assert_not_called()

    @pytest.mark.asyncio
    async def test_ng_message_never_reaches_llm(self):
        """NG message (personal info) → LLM.generate_reply NOT called."""
        cfg = AppConfig(llm=LLMConfig(max_retries=0))
        orch = Orchestrator(config=cfg)

        with patch.object(orch._llm, "generate_reply", new_callable=AsyncMock) as spy:
            await orch._process_message(_make_msg("test@example.com"))
            spy.assert_not_called()

    @pytest.mark.asyncio
    async def test_ok_message_reaches_bandit(self):
        """OK message → Bandit.select_action IS called."""
        cfg = AppConfig(llm=LLMConfig(max_retries=0))
        orch = Orchestrator(config=cfg)

        with (
            patch.object(orch._bandit, "select_action", wraps=orch._bandit.select_action) as spy,
            patch.object(orch._llm, "generate_reply", new_callable=AsyncMock) as _llm_spy,
            patch.object(orch._avatar, "send_event", new_callable=AsyncMock),
            patch.object(orch._avatar, "send_update", new_callable=AsyncMock),
        ):
            from orchestrator.llm_client import LLMResult

            _llm_spy.return_value = LLMResult(text="返信です", is_template=False, retries_used=0)
            await orch._process_message(_make_msg("今日の配信楽しいね！"))
            spy.assert_called_once()

    @pytest.mark.asyncio
    async def test_self_harm_returns_template_response(self):
        """Self-harm NG → template response with 専門窓口 is used."""
        cfg = AppConfig()
        orch = Orchestrator(config=cfg)

        spoke_texts: list[str] = []

        async def capture_speak(text, msg, *, is_safety_template=False):
            spoke_texts.append(text)

        orch._speak = capture_speak  # type: ignore[assignment]
        await orch._process_message(_make_msg("自殺したい"))
        assert len(spoke_texts) == 1
        assert "専門窓口" in spoke_texts[0]


class TestPipelineOrdering:
    """Verify Safety → Bandit → LLM execution order."""

    @pytest.mark.asyncio
    async def test_ok_message_order_safety_bandit_llm(self):
        """For OK message: check_safety runs, then bandit, then LLM."""
        call_order: list[str] = []

        cfg = AppConfig(llm=LLMConfig(max_retries=0))
        orch = Orchestrator(config=cfg)

        original_check_safety = None
        import orchestrator.main as main_mod
        import orchestrator.safety as safety_mod

        original_check_safety = safety_mod.check_safety

        def tracked_check_safety(text):
            call_order.append("safety")
            return original_check_safety(text)

        original_select_action = orch._bandit.select_action

        def tracked_select_action(ctx):
            call_order.append("bandit")
            return original_select_action(ctx)

        from orchestrator.llm_client import LLMResult

        async def tracked_generate_reply(text, *, avoidance_hint=None):
            call_order.append("llm")
            return LLMResult(text="返信", is_template=False, retries_used=0)

        with (
            patch.object(main_mod, "check_safety", side_effect=tracked_check_safety),
            patch.object(orch._bandit, "select_action", side_effect=tracked_select_action),
            patch.object(orch._llm, "generate_reply", side_effect=tracked_generate_reply),
            patch.object(orch._avatar, "send_event", new_callable=AsyncMock),
            patch.object(orch._avatar, "send_update", new_callable=AsyncMock),
        ):
            # Force bandit to return reply_now (epsilon=0, set weight)
            orch._bandit.update_action_reward("reply_now", 100.0)
            orch._bandit._epsilon = 0.0
            await orch._process_message(_make_msg("こんにちは！"))

        assert call_order == ["safety", "bandit", "llm"]


class TestGrayZonePipeline:
    """GRAYメッセージはBandit/LLMに到達し、回避ヒント付きで処理される。"""

    @pytest.mark.asyncio
    async def test_gray_message_reaches_llm_with_avoidance_hint(self):
        """GRAY → LLM.generate_reply が avoidance_hint 付きで呼ばれる。"""
        cfg = AppConfig(llm=LLMConfig(max_retries=0))
        orch = Orchestrator(config=cfg)
        orch._bandit.update_action_reward("reply_now", 100.0)
        orch._bandit._epsilon = 0.0

        captured_kwargs: list[dict] = []

        from orchestrator.llm_client import LLMResult

        async def spy_generate(text, *, avoidance_hint=None):
            captured_kwargs.append({"avoidance_hint": avoidance_hint})
            return LLMResult(text="別の話題にしよう！", is_template=False, retries_used=0)

        with (
            patch.object(orch._llm, "generate_reply", side_effect=spy_generate),
            patch.object(orch._avatar, "send_event", new_callable=AsyncMock),
            patch.object(orch._avatar, "send_update", new_callable=AsyncMock),
        ):
            await orch._process_message(_make_msg("政治の話しよう"))

        assert len(captured_kwargs) == 1
        assert captured_kwargs[0]["avoidance_hint"] is not None
        assert "別の話題" in captured_kwargs[0]["avoidance_hint"]

    @pytest.mark.asyncio
    async def test_gray_message_reaches_bandit(self):
        """GRAY → Bandit.select_action は呼ばれる。"""
        cfg = AppConfig(llm=LLMConfig(max_retries=0))
        orch = Orchestrator(config=cfg)

        with patch.object(orch._bandit, "select_action", wraps=orch._bandit.select_action) as spy:
            # Banditがignore以外を選ぶ保証はないが、少なくとも呼ばれる
            await orch._process_message(_make_msg("宗教について教えて"))
            spy.assert_called_once()
