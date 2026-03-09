"""Pipeline integration tests.

TC-SAFE-01 (integration): NG-confirmed comments never reach Bandit/LLM.
Verifies the ordering Safety → Bandit → LLM (FR-SAFE-01).

TC-PERC-01~05: _on_perception_update behavior_completed routing (L-5/R3-2/R4).
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

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
        """NG message (personal info) → LLM.generate_reply_stream NOT called."""
        cfg = AppConfig(llm=LLMConfig(max_retries=0))
        orch = Orchestrator(config=cfg)
        was_called = False

        async def _spy_stream(text, *, avoidance_hint=None):
            nonlocal was_called
            was_called = True
            yield  # pragma: no cover

        with patch.object(orch._llm, "generate_reply_stream", new=_spy_stream):
            await orch._process_message(_make_msg("test@example.com"))

        assert not was_called, "generate_reply_stream must not be called for NG messages"

    @pytest.mark.asyncio
    async def test_ok_message_reaches_bandit(self):
        """OK message → Bandit.select_action IS called."""
        cfg = AppConfig(llm=LLMConfig(max_retries=0))
        orch = Orchestrator(config=cfg)

        from orchestrator.llm_client import LLMResult

        async def _stub_stream(text, *, avoidance_hint=None):
            yield LLMResult(text="返信です", is_template=False)

        with (
            patch.object(orch._bandit, "select_action", wraps=orch._bandit.select_action) as spy,
            patch.object(orch._llm, "generate_reply_stream", new=_stub_stream),
            patch.object(orch._avatar, "send_event", new_callable=AsyncMock),
            patch.object(orch._avatar, "send_update", new_callable=AsyncMock),
        ):
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

        async def tracked_generate_reply_stream(text, *, avoidance_hint=None):
            call_order.append("llm")
            yield LLMResult(text="返信", is_template=False)

        with (
            patch.object(main_mod, "check_safety", side_effect=tracked_check_safety),
            patch.object(orch._bandit, "select_action", side_effect=tracked_select_action),
            patch.object(orch._llm, "generate_reply_stream", new=tracked_generate_reply_stream),
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

        async def spy_generate_stream(text, *, avoidance_hint=None):
            captured_kwargs.append({"avoidance_hint": avoidance_hint})
            yield LLMResult(text="別の話題にしよう！", is_template=False)

        with (
            patch.object(orch._llm, "generate_reply_stream", new=spy_generate_stream),
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


class TestLifeLoopOnAirSkip:
    """TC-LIFE-01: ON_AIR中はlife_loopがavatar_updateを送らない。

    FR-LIFE-01, FR-BCAST-01.
    """

    @pytest.mark.asyncio
    async def test_life_loop_skips_avatar_update_when_on_air(self):
        """FR-LIFE-01: _is_live=True時にavatar_updateをスキップする。"""
        cfg = AppConfig()
        orch = Orchestrator(config=cfg)
        orch._running = True  # start() を呼ばずに直接テスト
        orch._is_live = True  # ON_AIR 状態

        sleep_count = 0

        async def fake_sleep(_n: float) -> None:
            nonlocal sleep_count
            sleep_count += 1
            if sleep_count >= 2:
                orch._running = False

        with (
            patch.object(orch._avatar, "send_update", new_callable=AsyncMock) as mock_update,
            patch("orchestrator.main.asyncio.sleep", side_effect=fake_sleep),
        ):
            await orch._life_loop()

        # ON_AIR中はavatar_updateを送らない
        mock_update.assert_not_called()

    @pytest.mark.asyncio
    async def test_life_loop_sends_update_when_not_on_air(self):
        """FR-LIFE-01: _is_live=False時はintent queueにpushする (FR-INTENT-PRIORITY-01).

        全アクティビティが _intent_queue 経由で _intent_dispatcher に渡るよう変更。
        PONDER → IntentItem(intent="life_ponder", source="life") がキューに積まれる。
        """
        from orchestrator.life_activity import ActivityType, LifeActivity
        from orchestrator.main import PRIORITY_LIFE

        cfg = AppConfig()
        orch = Orchestrator(config=cfg)
        orch._running = True
        orch._is_live = False

        fake_activity = LifeActivity(
            activity_type=ActivityType.PONDER,
            gesture="thinking",
            emotion="thinking",
            duration_sec=60.0,
        )
        orch._life.tick = lambda **_kw: fake_activity  # type: ignore[method-assign]

        sleep_count = 0

        async def fake_sleep(_n: float) -> None:
            nonlocal sleep_count
            sleep_count += 1
            if sleep_count >= 1:
                orch._running = False  # stop after first sleep at loop bottom

        with patch("orchestrator.main.asyncio.sleep", side_effect=fake_sleep):
            await orch._life_loop()

        assert not orch._intent_queue.empty(), "intent must be queued"
        item = orch._intent_queue.get_nowait()
        assert item.intent == "life_ponder"
        assert item.source == "life"
        assert item.priority == PRIORITY_LIFE

    @pytest.mark.asyncio
    async def test_life_loop_sends_intent_for_locomotion_activity(self):
        """FR-LIFE-01/FR-BEHAVIOR-SEQ-01: 歩行系もintent queue経由 (FR-INTENT-PRIORITY-01).

        SLEEP → IntentItem(intent="life_sleep", source="life") がキューに積まれる。
        _intent_dispatcher が ActionDispatcher → BehaviorPolicy 経由で実行する。
        """
        from orchestrator.life_activity import ActivityType, LifeActivity

        cfg = AppConfig()
        orch = Orchestrator(config=cfg)
        orch._running = True
        orch._is_live = False

        fake_activity = LifeActivity(
            activity_type=ActivityType.SLEEP,
            gesture="sleep_idle",
            emotion="sleepy",
            duration_sec=360.0,
        )
        orch._life.tick = lambda **_kw: fake_activity  # type: ignore[method-assign]

        sleep_count = 0

        async def fake_sleep(_n: float) -> None:
            nonlocal sleep_count
            sleep_count += 1
            if sleep_count >= 1:
                orch._running = False

        with patch("orchestrator.main.asyncio.sleep", side_effect=fake_sleep):
            await orch._life_loop()

        assert not orch._intent_queue.empty(), "intent must be queued"
        item = orch._intent_queue.get_nowait()
        assert item.intent == "life_sleep"
        assert item.source == "life"


class TestOnPerceptionUpdateBehaviorCompleted:
    """TC-PERC-01/02/03: _on_perception_update skips WorldContext on behavior_completed.

    L-5 / Issue #50, R3-2: gap_category must reflect reason field, not hardcoded.
    """

    def test_behavior_completed_success_no_world_context_update(self, caplog):
        """TC-PERC-01: success=True → info log, WorldContext NOT updated."""
        import logging

        cfg = AppConfig()
        orch = Orchestrator(config=cfg)
        orch._world_context.update = MagicMock()  # type: ignore[method-assign]

        with caplog.at_level(logging.INFO, logger="orchestrator.main"):
            orch._on_perception_update({"behavior_completed": "morning_routine", "success": True})

        orch._world_context.update.assert_not_called()
        assert "behavior=morning_routine" in caplog.text
        assert "success=True" in caplog.text

    def test_behavior_completed_failure_locomotion_blocked(self, caplog):
        """TC-PERC-02: success=False, reason='locomotion_blocked'
        → gap_category=locomotion_blocked."""
        import logging

        cfg = AppConfig()
        orch = Orchestrator(config=cfg)
        orch._world_context.update = MagicMock()  # type: ignore[method-assign]

        with caplog.at_level(logging.WARNING, logger="orchestrator.main"):
            orch._on_perception_update(
                {
                    "behavior_completed": "walk_to_desk",
                    "success": False,
                    "reason": "locomotion_blocked",
                }
            )

        orch._world_context.update.assert_not_called()
        assert "gap_category=locomotion_blocked" in caplog.text

    def test_behavior_completed_failure_interrupted_not_locomotion_blocked(self, caplog):
        """TC-PERC-03: success=False, reason='interrupted' → gap_category=interrupted (R3-2 fix).

        Regression: must NOT emit gap_category=locomotion_blocked for interrupts.
        """
        import logging

        cfg = AppConfig()
        orch = Orchestrator(config=cfg)
        orch._world_context.update = MagicMock()  # type: ignore[method-assign]

        with caplog.at_level(logging.WARNING, logger="orchestrator.main"):
            orch._on_perception_update(
                {
                    "behavior_completed": "morning_routine",
                    "success": False,
                    "reason": "interrupted",
                }
            )

        orch._world_context.update.assert_not_called()
        assert "gap_category=interrupted" in caplog.text
        assert "gap_category=locomotion_blocked" not in caplog.text

    def test_behavior_completed_failure_empty_reason_uses_unknown(self, caplog):
        """TC-PERC-05: success=False, reason='' → gap_category=unknown (R4 empty-reason fallback).

        Verifies `gap_cat = reason if reason else "unknown"` produces "unknown" for empty string.
        """
        import logging

        cfg = AppConfig()
        orch = Orchestrator(config=cfg)
        orch._world_context.update = MagicMock()  # type: ignore[method-assign]

        with caplog.at_level(logging.WARNING, logger="orchestrator.main"):
            orch._on_perception_update(
                {"behavior_completed": "go_sleep", "success": False, "reason": ""}
            )

        orch._world_context.update.assert_not_called()
        assert "gap_category=unknown" in caplog.text

    def test_non_behavior_completed_updates_world_context(self):
        """TC-PERC-04: normal perception_update (no behavior_completed) → WorldContext updated."""
        cfg = AppConfig()
        orch = Orchestrator(config=cfg)
        orch._world_context.update = MagicMock()  # type: ignore[method-assign]

        orch._on_perception_update({"current_zone": "desk_area", "time_of_day": "morning"})

        orch._world_context.update.assert_called_once_with(
            {"current_zone": "desk_area", "time_of_day": "morning"}
        )


class TestNarrativeLoop:
    """TC-NARR-01/02: _narrative_loop が定期的に NarrativeBuilder を呼び出す。

    FR-E6-01, NFR-GROWTH-01.
    """

    @pytest.mark.asyncio
    async def test_narrative_loop_builds_and_injects_hint(self):
        """FR-E6-01: _narrative_loop が build() を呼び narrative_hint を更新。"""
        from orchestrator.narrative_builder import NarrativeEntry

        cfg = AppConfig()
        orch = Orchestrator(config=cfg)
        orch._running = True

        fake_entry = NarrativeEntry(
            narrative_id="abc123",
            timestamp=0.0,
            narrative="最近の会話からとても多くを学びました。",
            episode_count=5,
        )

        build_calls: list = []

        def fake_build(episodes, **kwargs):
            build_calls.append(episodes)
            return fake_entry

        orch._narrative.build = fake_build  # type: ignore[method-assign]
        orch._episodic.get_recent = MagicMock(return_value=[])  # type: ignore[method-assign]

        sleep_count = 0

        async def fake_sleep(_n: float) -> None:
            nonlocal sleep_count
            sleep_count += 1
            if sleep_count >= 1:
                orch._running = False  # stop after first sleep (= after one build)

        with patch("orchestrator.main.asyncio.sleep", side_effect=fake_sleep):
            await orch._narrative_loop()

        assert len(build_calls) == 1
        assert orch._narrative_hint == fake_entry.narrative

    @pytest.mark.asyncio
    async def test_narrative_loop_does_not_raise_on_build_error(self):
        """FR-E6-01: build() 例外でもループがクラッシュしない。"""
        cfg = AppConfig()
        orch = Orchestrator(config=cfg)
        orch._running = True

        error_count = [0]

        def fake_build(episodes, **kwargs):
            error_count[0] += 1
            raise RuntimeError("LLM timeout")

        orch._narrative.build = fake_build  # type: ignore[method-assign]

        sleep_count = 0

        async def fake_sleep(_n: float) -> None:
            nonlocal sleep_count
            sleep_count += 1
            if sleep_count >= 1:
                orch._running = False

        with patch("orchestrator.main.asyncio.sleep", side_effect=fake_sleep):
            await orch._narrative_loop()  # should not raise

        assert error_count[0] == 1
        assert orch._narrative_hint == ""  # unchanged on error

