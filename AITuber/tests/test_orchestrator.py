"""Pipeline integration tests.

TC-SAFE-01 (integration): NG-confirmed comments never reach Bandit/LLM.
Verifies the ordering Safety → Bandit → LLM (FR-SAFE-01).

TC-PERC-01~05: _on_perception_update behavior_completed routing (L-5/R3-2/R4).
"""

from __future__ import annotations

from unittest.mock import ANY, AsyncMock, MagicMock, patch

import pytest

from orchestrator.chat_poller import ChatMessage
from orchestrator.config import AppConfig, LLMConfig
from orchestrator.episodic_store import EpisodeEntry
from orchestrator.main import Orchestrator, sanitize_display_name


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


class TestStreamRituals:
    """FR-BCAST-02: stream greeting/farewell ritual intent hooks."""

    @pytest.mark.asyncio
    async def test_queue_priority_intent_enqueues_with_seq(self):
        cfg = AppConfig(llm=LLMConfig(max_retries=0))
        orch = Orchestrator(config=cfg)

        await orch._queue_priority_intent(intent="stream_greeting", source="system", priority=0)

        item = orch._intent_queue.get_nowait()
        assert item.intent == "stream_greeting"
        assert item.source == "system"
        assert item.seq == 1

    @pytest.mark.asyncio
    async def test_stop_sends_stream_farewell_intent(self):
        cfg = AppConfig(llm=LLMConfig(max_retries=0))
        orch = Orchestrator(config=cfg)
        orch._avatar.send_avatar_intent = AsyncMock()
        orch._tts.close = AsyncMock()
        orch._avatar.disconnect = AsyncMock()
        orch._overlay.stop = AsyncMock()

        await orch.stop()

        orch._avatar.send_avatar_intent.assert_called_once_with(
            intent="stream_farewell",
            source="system",
        )


class TestViewerCountMilestoneReaction:
    """FR-VIEWCNT-01: milestone callback enqueues celebrate intent."""

    @pytest.mark.asyncio
    async def test_on_viewer_milestone_enqueues_celebration(self):
        cfg = AppConfig(llm=LLMConfig(max_retries=0))
        orch = Orchestrator(config=cfg)

        await orch._on_viewer_milestone(current=120, milestone=100)

        queued = orch._intent_queue.get_nowait()
        assert queued.intent == "celebrate_milestone"
        assert queued.source == "viewer_count"
        assert orch._peak_viewers_this_session == 120


class TestDisplayNameSanitization:
    def test_sanitize_display_name_removes_symbols(self):
        assert sanitize_display_name("<script>abc!!!") == "scriptabc"

    def test_sanitize_display_name_fallback_when_empty(self):
        assert sanitize_display_name("$$$") == "視聴者"

    def test_sanitize_display_name_truncates(self):
        assert sanitize_display_name("abcdefghijklmnopqrstuvwxyz") == "abcdefghijklmnopqrst"


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

    def test_behavior_completed_is_recorded_in_episodic_memory(self):
        """TC-PERC-06: behavior completion events are written to episodic memory metadata."""
        cfg = AppConfig()
        orch = Orchestrator(config=cfg)
        orch._episodic.append = MagicMock()  # type: ignore[method-assign]
        orch._goals.observe_behavior_result = MagicMock()  # type: ignore[method-assign]
        orch._goals.to_idle_hint = MagicMock(  # type: ignore[method-assign]
            return_value="最近は 会話と配信の流れ をもう少し深めたい"
        )
        orch._goals.get_scheduler_focus = MagicMock(  # type: ignore[method-assign]
            return_value=("会話と配信の流れ を深めたい", "social")
        )
        orch._life.set_goal_focus = MagicMock()  # type: ignore[method-assign]
        orch._world_context.state.scene_name = "yuia_home"
        orch._world_context.state.room_name = "desk_area"
        orch._world_context.state.objects_nearby = ["desk", "monitor"]
        orch._world_context.state.time_of_day = "morning"

        orch._on_perception_update(
            {"behavior_completed": "go_stream", "success": True, "reason": ""}
        )

        orch._episodic.append.assert_called_once_with(
            author="system",
            user_text="behavior_completed: go_stream",
            ai_response="success",
            importance=4,
            source_type="behavior",
            scene_name="yuia_home",
            room_name="desk_area",
            nearby_objects=["desk", "monitor"],
            activity_type="go_stream",
            outcome="success",
            time_bucket="morning",
        )
        orch._goals.observe_behavior_result.assert_called_once_with(
            behavior="go_stream",
            success=True,
            reason="",
            room_name="desk_area",
        )
        orch._life.set_goal_focus.assert_called_once_with(
            "会話と配信の流れ を深めたい",
            focus_type="social",
        )

    def test_behavior_failure_reason_is_recorded_in_episodic_memory(self):
        """TC-PERC-07: behavior failure reason is preserved in episodic memory outcome."""
        cfg = AppConfig()
        orch = Orchestrator(config=cfg)
        orch._episodic.append = MagicMock()  # type: ignore[method-assign]
        orch._goals.observe_behavior_result = MagicMock()  # type: ignore[method-assign]
        orch._goals.to_idle_hint = MagicMock(  # type: ignore[method-assign]
            return_value="今は 移動の安定性 をもう少し深めたい"
        )
        orch._goals.get_scheduler_focus = MagicMock(  # type: ignore[method-assign]
            return_value=("移動の安定性 を深めたい", "exploration")
        )
        orch._life.set_goal_focus = MagicMock()  # type: ignore[method-assign]
        orch._world_context.state.scene_name = "yuia_home"
        orch._world_context.state.room_name = "hallway"
        orch._world_context.state.objects_nearby = ["door", "plant"]
        orch._world_context.state.time_of_day = "night"

        orch._on_perception_update(
            {
                "behavior_completed": "walk_to_bed",
                "success": False,
                "reason": "locomotion_blocked",
            }
        )

        orch._episodic.append.assert_called_once_with(
            author="system",
            user_text="behavior_completed: walk_to_bed",
            ai_response="failure: locomotion_blocked",
            importance=7,
            source_type="behavior",
            scene_name="yuia_home",
            room_name="hallway",
            nearby_objects=["door", "plant"],
            activity_type="walk_to_bed",
            outcome="locomotion_blocked",
            time_bucket="night",
        )
        orch._goals.observe_behavior_result.assert_called_once_with(
            behavior="walk_to_bed",
            success=False,
            reason="locomotion_blocked",
            room_name="hallway",
        )
        orch._life.set_goal_focus.assert_called_once_with(
            "移動の安定性 を深めたい",
            focus_type="exploration",
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
            build_calls.append(kwargs)
            return fake_entry

        orch._narrative.build = fake_build  # type: ignore[method-assign]
        orch._episodic.get_recent = MagicMock(return_value=[])  # type: ignore[method-assign]
        orch._episodic.get_relevant = MagicMock(return_value=[])  # type: ignore[method-assign]
        orch._semantic.to_overview_fragment = MagicMock(  # type: ignore[method-assign]
            return_value="[FACTS]\nshader"
        )
        orch._goals.current_goal = MagicMock(return_value=MagicMock(subject="Alice"))  # type: ignore[method-assign]
        orch._goals.top_goal_values = MagicMock(return_value=["shader", "room"])  # type: ignore[method-assign]
        orch._goals.to_prompt_fragment = MagicMock(  # type: ignore[method-assign]
            return_value="[GOALS]\n今は shader をもう少し深めたい"
        )
        orch._world_context.state.scene_name = "yuia_home"
        orch._world_context.state.time_of_day = "night"
        orch._world_context.state.room_name = "desk_area"
        orch._world_context.state.objects_nearby = ["desk", "monitor"]

        sleep_count = 0

        async def fake_sleep(_n: float) -> None:
            nonlocal sleep_count
            sleep_count += 1
            if sleep_count >= 1:
                orch._running = False  # stop after first sleep (= after one build)

        with patch("orchestrator.main.asyncio.sleep", side_effect=fake_sleep):
            await orch._narrative_loop()

        assert len(build_calls) == 2
        assert orch._narrative_hint == fake_entry.narrative
        assert build_calls[1]["semantic_fragment"].startswith("[FACTS]")
        assert build_calls[1]["goal_fragment"].startswith("[GOALS]")
        orch._episodic.get_relevant.assert_called_once_with(
            "shader room",
            top_k=8,
            author="Alice",
            time_bucket="night",
            scene_name="yuia_home",
            room_name="desk_area",
            nearby_objects=["desk", "monitor"],
        )

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


class TestReplyEpisodeMetadata:
    """TC-MEM-17: conversation replies record richer episodic metadata."""

    @pytest.mark.asyncio
    async def test_reply_records_viewer_and_world_metadata(self):
        cfg = AppConfig(llm=LLMConfig(max_retries=0))
        orch = Orchestrator(config=cfg)
        orch._world_context.state.scene_name = "yuia_home"
        orch._world_context.state.room_name = "living_room"
        orch._world_context.state.objects_nearby = ["sofa", "window"]
        orch._world_context.state.time_of_day = "evening"
        orch._episodic.append = MagicMock()  # type: ignore[method-assign]

        from orchestrator.llm_client import LLMResult

        async def _stub_stream(text, *, avoidance_hint=None):
            yield LLMResult(text="こんばんは、続きを話そう。", is_template=False)

        with (
            patch.object(orch._llm, "generate_reply_stream", new=_stub_stream),
            patch.object(orch._avatar, "send_event", new_callable=AsyncMock),
            patch.object(orch._avatar, "send_update", new_callable=AsyncMock),
            patch.object(orch, "_speak", new_callable=AsyncMock),
        ):
            await orch._reply_to(_make_msg("昨日の話の続きして"))

        orch._episodic.append.assert_called_once_with(
            author="テストユーザー",
            user_text="昨日の話の続きして",
            ai_response="こんばんは、続きを話そう。",
            source_type="conversation",
            scene_name="yuia_home",
            room_name="living_room",
            nearby_objects=["sofa", "window"],
            time_bucket="evening",
            related_viewer="テストユーザー",
        )

    @pytest.mark.asyncio
    async def test_reply_observes_semantic_memory(self):
        """TC-MEM-18: reply path promotes durable facts into semantic memory."""
        cfg = AppConfig(llm=LLMConfig(max_retries=0))
        orch = Orchestrator(config=cfg)
        orch._semantic.observe_conversation = MagicMock()  # type: ignore[method-assign]

        from orchestrator.llm_client import LLMResult

        async def _stub_stream(text, *, avoidance_hint=None):
            yield LLMResult(text="shader の続きを話そう。", is_template=False)

        with (
            patch.object(orch._llm, "generate_reply_stream", new=_stub_stream),
            patch.object(orch._avatar, "send_event", new_callable=AsyncMock),
            patch.object(orch._avatar, "send_update", new_callable=AsyncMock),
            patch.object(orch, "_speak", new_callable=AsyncMock),
        ):
            await orch._reply_to(_make_msg("shader の続きを教えて"))

        orch._semantic.observe_conversation.assert_called_once_with(
            author="テストユーザー",
            user_text="shader の続きを教えて",
            ai_response="shader の続きを話そう。",
            episode_id=ANY,
        )

    @pytest.mark.asyncio
    async def test_reply_observes_goal_memory(self):
        """TC-MEM-20: reply path updates medium-horizon goal memory."""
        cfg = AppConfig(llm=LLMConfig(max_retries=0))
        orch = Orchestrator(config=cfg)
        orch._goals.observe_conversation = MagicMock()  # type: ignore[method-assign]
        orch._goals.to_idle_hint = MagicMock(return_value="今は shader をもう少し深めたい")  # type: ignore[method-assign]
        orch._goals.get_scheduler_focus = MagicMock(return_value=("shader を深めたい", "learning"))  # type: ignore[method-assign]
        orch._life.set_goal_focus = MagicMock()  # type: ignore[method-assign]

        from orchestrator.llm_client import LLMResult

        async def _stub_stream(text, *, avoidance_hint=None):
            yield LLMResult(text="shader の続きを話そう。", is_template=False)

        with (
            patch.object(orch._llm, "generate_reply_stream", new=_stub_stream),
            patch.object(orch._avatar, "send_event", new_callable=AsyncMock),
            patch.object(orch._avatar, "send_update", new_callable=AsyncMock),
            patch.object(orch, "_speak", new_callable=AsyncMock),
        ):
            await orch._reply_to(_make_msg("shader の続きを教えて"))

        orch._goals.observe_conversation.assert_called_once_with(
            author="テストユーザー",
            user_text="shader の続きを教えて",
            ai_response="shader の続きを話そう。",
        )
        orch._life.set_goal_focus.assert_called_once_with(
            "shader を深めたい",
            focus_type="learning",
        )

    @pytest.mark.asyncio
    async def test_reply_goal_fragment_uses_familiarity_score(self):
        """TC-MEM-23: reply goal prompt passes semantic familiarity into goal selection."""
        cfg = AppConfig(llm=LLMConfig(max_retries=0))
        orch = Orchestrator(config=cfg)
        orch._semantic.familiarity_score = MagicMock(return_value=1)  # type: ignore[method-assign]
        orch._episodic.to_prompt_fragment = MagicMock(return_value="")  # type: ignore[method-assign]
        orch._semantic.to_prompt_fragment = MagicMock(return_value="[FACTS]\n常連視聴者")  # type: ignore[method-assign]
        orch._goals.top_goal_values = MagicMock(return_value=["shader の続き"])  # type: ignore[method-assign]
        orch._goals.to_prompt_fragment = MagicMock(  # type: ignore[method-assign]
            return_value="[GOALS]\n今は shader の続き を拾い直したい"
        )
        orch._world_context.state.scene_name = "yuia_home"
        orch._world_context.state.time_of_day = "evening"
        orch._world_context.state.room_name = "living_room"
        orch._world_context.state.objects_nearby = ["sofa", "window"]

        from orchestrator.llm_client import LLMResult

        async def _stub_stream(text, *, avoidance_hint=None):
            yield LLMResult(text="了解です。", is_template=False)

        with (
            patch.object(orch._llm, "generate_reply_stream", new=_stub_stream),
            patch.object(orch._avatar, "send_event", new_callable=AsyncMock),
            patch.object(orch._avatar, "send_update", new_callable=AsyncMock),
            patch.object(orch, "_speak", new_callable=AsyncMock),
        ):
            await orch._reply_to(_make_msg("shader の続きを教えて"))

        orch._goals.to_prompt_fragment.assert_any_call(
            author="テストユーザー",
            query="shader の続きを教えて",
            familiarity_score=1,
        )
        orch._goals.top_goal_values.assert_any_call(
            author="テストユーザー",
            familiarity_score=1,
        )
        orch._semantic.to_prompt_fragment.assert_any_call(
            author="テストユーザー",
            query="shader の続きを教えて",
            exclude_topics=["shader の続き"],
        )
        orch._episodic.to_prompt_fragment.assert_any_call(
            "shader の続きを教えて",
            author="テストユーザー",
            time_bucket="evening",
            scene_name="yuia_home",
            room_name="living_room",
            nearby_objects=["sofa", "window"],
        )

    @pytest.mark.asyncio
    async def test_narrative_loop_excludes_current_goal_topics_from_semantic_overview(self):
        """TC-NARR-04: narrative semantic overview omits themes already represented as goals."""
        from orchestrator.narrative_builder import NarrativeEntry

        cfg = AppConfig()
        orch = Orchestrator(config=cfg)
        orch._running = True
        orch._narrative.build = MagicMock(
            return_value=NarrativeEntry(
                narrative_id="abc123",
                timestamp=0.0,
                narrative="最近は文脈が整理されている。",
                episode_count=2,
            )
        )  # type: ignore[method-assign]
        orch._episodic.get_recent = MagicMock(return_value=[])  # type: ignore[method-assign]
        orch._episodic.get_relevant = MagicMock(return_value=[])  # type: ignore[method-assign]
        orch._semantic.to_overview_fragment = MagicMock(return_value="[FACTS]\ntea")  # type: ignore[method-assign]
        orch._goals.current_goal = MagicMock(return_value=MagicMock(subject="Alice"))  # type: ignore[method-assign]
        orch._goals.top_goal_values = MagicMock(return_value=["shader の続き", "room"])  # type: ignore[method-assign]
        orch._goals.to_prompt_fragment = MagicMock(  # type: ignore[method-assign]
            return_value="[GOALS]\n今は shader の続き を拾い直したい"
        )
        orch._world_context.state.scene_name = "yuia_home"
        orch._world_context.state.objects_nearby = ["desk", "monitor"]

        sleep_count = 0

        async def fake_sleep(_n: float) -> None:
            nonlocal sleep_count
            sleep_count += 1
            if sleep_count >= 1:
                orch._running = False

        with patch("orchestrator.main.asyncio.sleep", side_effect=fake_sleep):
            await orch._narrative_loop()

        orch._semantic.to_overview_fragment.assert_called_once_with(
            exclude_topics=["shader の続き", "room"]
        )


class TestNarrativeEpisodeSelection:
    def test_select_narrative_episodes_blends_relevant_and_recent(self):
        """TC-NARR-03: narrative episode selection mixes goal-relevant recall with recency."""
        cfg = AppConfig()
        orch = Orchestrator(config=cfg)

        recent = [
            EpisodeEntry(
                episode_id="recent001",
                timestamp=1.0,
                author="Alice",
                user_text="recent",
                ai_response="recent-reply",
            )
        ]
        relevant = [
            EpisodeEntry(
                episode_id="goal001",
                timestamp=2.0,
                author="Bob",
                user_text="shader",
                ai_response="goal-reply",
            ),
            EpisodeEntry(
                episode_id="recent001",
                timestamp=1.0,
                author="Alice",
                user_text="recent",
                ai_response="recent-reply",
            ),
        ]
        orch._episodic.get_recent = MagicMock(return_value=recent)  # type: ignore[method-assign]
        orch._episodic.get_relevant = MagicMock(return_value=relevant)  # type: ignore[method-assign]

        selected = orch._select_narrative_episodes(
            "shader",
            author="Alice",
            time_bucket="evening",
            scene_name="yuia_home",
            room_name="desk_area",
            nearby_objects=["desk", "monitor"],
        )

        assert [ep.episode_id for ep in selected] == ["goal001", "recent001"]
        orch._episodic.get_relevant.assert_called_once_with(
            "shader",
            top_k=8,
            author="Alice",
            time_bucket="evening",
            scene_name="yuia_home",
            room_name="desk_area",
            nearby_objects=["desk", "monitor"],
        )

    def test_dedupe_semantic_goal_overlap_removes_redundant_topic_line(self):
        """TC-MEM-24: semantic topic lines already covered by goals are dropped."""
        semantic_fragment = (
            "[FACTS]\n"
            "テストユーザー は regular 寄りの視聴者で、会話の連続性を期待できる\n"
            "テストユーザー は shader の話題を繰り返し持ち込みやすい"
        )

        trimmed = Orchestrator._dedupe_semantic_goal_overlap(
            semantic_fragment,
            ["shader の続き"],
        )

        assert "regular" in trimmed
        assert "shader の話題" not in trimmed

    @pytest.mark.asyncio
    async def test_reply_injects_semantic_fragment_into_llm_context(self):
        """TC-MEM-19: semantic facts are combined with world and episodic context."""
        cfg = AppConfig(llm=LLMConfig(max_retries=0))
        orch = Orchestrator(config=cfg)
        orch._world_context.state.scene_name = "yuia_home"
        orch._world_context.state.room_name = "living_room"
        orch._episodic.to_prompt_fragment = MagicMock(return_value="[MEMORY]\n過去の会話")  # type: ignore[method-assign]
        orch._semantic.to_prompt_fragment = MagicMock(return_value="[FACTS]\n常連視聴者")  # type: ignore[method-assign]
        orch._goals.to_prompt_fragment = MagicMock(  # type: ignore[method-assign]
            return_value="[GOALS]\n今は shader をもう少し深めたい"
        )

        from orchestrator.llm_client import LLMResult

        async def _stub_stream(text, *, avoidance_hint=None):
            yield LLMResult(text="了解です。", is_template=False)

        with (
            patch.object(orch._llm, "generate_reply_stream", new=_stub_stream),
            patch.object(orch._llm, "set_world_context_fragment") as mock_set_ctx,
            patch.object(orch._avatar, "send_event", new_callable=AsyncMock),
            patch.object(orch._avatar, "send_update", new_callable=AsyncMock),
            patch.object(orch, "_speak", new_callable=AsyncMock),
        ):
            await orch._reply_to(_make_msg("今日のこと覚えてる？"))

        injected = mock_set_ctx.call_args.args[0]
        assert "[WORLD]" in injected
        assert "[FACTS]" in injected
        assert "[GOALS]" in injected
        assert "[MEMORY]" in injected


class TestIdleHintSelection:
    def test_select_idle_hints_prioritizes_goal_and_life(self):
        """TC-MEM-21: idle hints stay compact and prioritize current continuity."""
        cfg = AppConfig()
        orch = Orchestrator(config=cfg)
        orch._goal_hint = "今は shader の続き を拾い直したい"
        orch._life_hint = "机で考え事を続けている"
        orch._narrative_hint = "最近の会話からとても多くを学び、これからも成長していきたいです。"

        hints = orch._select_idle_hints()

        assert hints == [
            "今は shader の続き を拾い直したい",
            "机で考え事を続けている",
        ]

    @pytest.mark.asyncio
    async def test_idle_talk_loop_passes_trimmed_hints(self):
        """TC-MEM-22: idle talk injects only the selected compact hint set."""
        orch = Orchestrator(config=AppConfig())
        orch._running = True
        orch._start_time = 0.0
        orch._last_reply_time = 0.0
        orch._IDLE_TIMEOUT_SEC = 0.0
        orch._goal_hint = "今は shader の続き を拾い直したい"
        orch._life_hint = "机で考え事を続けている"
        orch._narrative_hint = "最近の会話からとても多くを学び、これからも成長していきたいです。"
        orch._idle_topics = ["ambient-topic"]

        captured_hints: list[str] = []

        async def _stub_idle(*, hints=None):
            from orchestrator.llm_client import LLMResult

            captured_hints.extend(hints or [])
            orch._running = False
            return LLMResult(text="静かに考えてみよう。", is_template=False)

        with (
            patch.object(orch._llm, "generate_idle_talk", new=_stub_idle),
            patch.object(orch._avatar, "send_update", new_callable=AsyncMock),
            patch.object(orch, "_speak", new_callable=AsyncMock),
            patch("orchestrator.main.asyncio.sleep", new=AsyncMock()),
        ):
            await orch._idle_talk_loop()

        assert captured_hints == [
            "今は shader の続き を拾い直したい",
            "机で考え事を続けている",
            "ambient-topic",
        ]
