"""Priority intent queue tests.

TC-PRIO-01: IntentItem ordering — priority takes precedence over seq.
TC-PRIO-02: IntentItem ordering — seq breaks priority tie (FIFO within same priority).
TC-PRIO-03: _intent_dispatcher dispatches immediately when _is_replying=False.
TC-PRIO-04: _intent_dispatcher defers (re-queues) when _is_replying=True.
TC-PRIO-05: _reply_to sets _is_replying=True during execution, clears on completion.
TC-PRIO-06: _idle_talk_loop skips LLM when _is_replying=True or reply_queue non-empty.

FR-INTENT-PRIORITY-01.
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from orchestrator.config import AppConfig, LLMConfig
from orchestrator.main import (
    PRIORITY_IDLE,
    PRIORITY_INTERACTIVE,
    PRIORITY_LIFE,
    IntentItem,
    Orchestrator,
)


def _make_orch() -> Orchestrator:
    cfg = AppConfig(llm=LLMConfig(max_retries=0))
    return Orchestrator(config=cfg)


# ── TC-PRIO-01/02: IntentItem ordering ───────────────────────────────────────


class TestIntentItemOrdering:
    """TC-PRIO-01, TC-PRIO-02: IntentItem comparison semantics."""

    def test_lower_priority_number_sorts_first(self):
        """TC-PRIO-01: LIFE(1) < IDLE(2) — dispatched first in PriorityQueue."""
        life = IntentItem(priority=PRIORITY_LIFE, seq=0, intent="life_ponder", source="life")
        idle = IntentItem(priority=PRIORITY_IDLE, seq=0, intent="idle_talk", source="idle")
        assert life < idle

    def test_seq_breaks_priority_tie(self):
        """TC-PRIO-02: Equal priority → earlier seq dispatched first (FIFO)."""
        first = IntentItem(priority=PRIORITY_LIFE, seq=0, intent="life_ponder", source="life")
        second = IntentItem(priority=PRIORITY_LIFE, seq=1, intent="life_stream", source="life")
        assert first < second

    def test_priority_constants_ordering(self):
        """INTERACTIVE(0) < LIFE(1) < IDLE(2)."""
        assert PRIORITY_INTERACTIVE < PRIORITY_LIFE < PRIORITY_IDLE

    def test_intent_and_source_fields_not_compared(self):
        """intent/source fields are excluded from ordering (compare=False)."""
        a = IntentItem(priority=PRIORITY_LIFE, seq=5, intent="aaa", source="x")
        b = IntentItem(priority=PRIORITY_LIFE, seq=5, intent="zzz", source="y")
        assert not (a < b) and not (b < a)  # equal

    def test_priority_queue_dequeues_in_priority_order(self):
        """asyncio.PriorityQueue respects IntentItem ordering."""
        q: asyncio.PriorityQueue[IntentItem] = asyncio.PriorityQueue()
        idle = IntentItem(priority=PRIORITY_IDLE, seq=0, intent="idle_talk", source="idle")
        life = IntentItem(priority=PRIORITY_LIFE, seq=1, intent="life_ponder", source="life")
        # put idle first, then life — life should come out first
        q.put_nowait(idle)
        q.put_nowait(life)
        assert q.get_nowait() is life   # PRIORITY_LIFE(1) < PRIORITY_IDLE(2)
        assert q.get_nowait() is idle


# ── TC-PRIO-03/04: _intent_dispatcher ────────────────────────────────────────


class TestIntentDispatcher:
    """TC-PRIO-03, TC-PRIO-04: _intent_dispatcher routing."""

    @pytest.mark.asyncio
    async def test_dispatches_immediately_when_not_replying(self):
        """TC-PRIO-03: intent is dispatched without delay when _is_replying=False."""
        orch = _make_orch()
        orch._avatar = MagicMock()
        orch._avatar.send_avatar_intent = AsyncMock()
        orch._avatar.send_room_change = AsyncMock()

        orch._is_replying = False
        orch._running = True

        item = IntentItem(
            priority=PRIORITY_LIFE, seq=0, intent="life_ponder", source="life"
        )
        await orch._intent_queue.put(item)

        async def _stop_after_dispatch() -> None:
            await asyncio.sleep(0.3)
            orch._running = False

        await asyncio.gather(orch._intent_dispatcher(), _stop_after_dispatch())

        orch._avatar.send_avatar_intent.assert_called_once_with(
            intent="life_ponder", source="life"
        )

    @pytest.mark.asyncio
    async def test_dispatches_room_change_before_intent(self):
        """TC-PRIO-03 (room): send_room_change is called before send_avatar_intent."""
        orch = _make_orch()
        orch._avatar = MagicMock()
        call_order: list[str] = []
        orch._avatar.send_room_change = AsyncMock(
            side_effect=lambda room_id: call_order.append("room")
        )
        orch._avatar.send_avatar_intent = AsyncMock(
            side_effect=lambda **kw: call_order.append("intent")
        )

        orch._is_replying = False
        orch._running = True

        item = IntentItem(
            priority=PRIORITY_LIFE, seq=0, intent="life_sleep", source="life", room_id="bedroom"
        )
        await orch._intent_queue.put(item)

        async def _stop() -> None:
            await asyncio.sleep(0.3)
            orch._running = False

        await asyncio.gather(orch._intent_dispatcher(), _stop())

        assert call_order == ["room", "intent"]

    @pytest.mark.asyncio
    async def test_defers_intent_when_replying(self):
        """TC-PRIO-04: item is re-queued and NOT dispatched while _is_replying=True."""
        orch = _make_orch()
        orch._avatar = MagicMock()
        orch._avatar.send_avatar_intent = AsyncMock()
        orch._avatar.send_room_change = AsyncMock()

        orch._is_replying = True
        orch._running = True

        item = IntentItem(
            priority=PRIORITY_LIFE, seq=0, intent="life_ponder", source="life"
        )
        await orch._intent_queue.put(item)

        async def _stop_quickly() -> None:
            await asyncio.sleep(0.8)
            # stop without clearing _is_replying so dispatcher never dispatches
            orch._running = False

        await asyncio.gather(orch._intent_dispatcher(), _stop_quickly())

        orch._avatar.send_avatar_intent.assert_not_called()


# ── TC-PRIO-05: _reply_to flag management ────────────────────────────────────


class TestReplyToIsReplyingFlag:
    """TC-PRIO-05: _is_replying lifecycle in _reply_to."""

    @pytest.mark.asyncio
    async def test_is_replying_true_during_speak(self):
        """TC-PRIO-05a: _is_replying is True while _speak is executing."""
        from orchestrator.chat_poller import ChatMessage
        from orchestrator.llm_client import LLMResult

        orch = _make_orch()
        flag_during_speak: list[bool] = []

        async def _stub_stream(text, *, avoidance_hint=None):
            yield LLMResult(text="テスト返信", is_template=False)

        async def _stub_speak(text, msg, *, is_safety_template=False):
            flag_during_speak.append(orch._is_replying)

        orch._speak = _stub_speak  # type: ignore[assignment]

        msg = ChatMessage(
            message_id="m1",
            text="こんにちは",
            author_display_name="テスト",
            author_channel_id="UC_test",
            published_at="2025-01-01T00:00:00Z",
        )

        with (
            patch.object(orch._llm, "generate_reply_stream", new=_stub_stream),
            patch.object(orch._avatar, "send_event", new_callable=AsyncMock),
            patch.object(orch._avatar, "send_update", new_callable=AsyncMock),
        ):
            await orch._reply_to(msg)

        assert flag_during_speak, "_speak was never called"
        assert all(flag_during_speak), "_is_replying must be True while speaking"

    @pytest.mark.asyncio
    async def test_is_replying_cleared_after_reply(self):
        """TC-PRIO-05b: _is_replying is False after _reply_to completes."""
        from orchestrator.chat_poller import ChatMessage
        from orchestrator.llm_client import LLMResult

        orch = _make_orch()

        async def _stub_stream(text, *, avoidance_hint=None):
            yield LLMResult(text="テスト返信", is_template=False)

        async def _stub_speak(text, msg, *, is_safety_template=False):
            pass

        orch._speak = _stub_speak  # type: ignore[assignment]

        msg = ChatMessage(
            message_id="m2",
            text="元気?",
            author_display_name="テスト",
            author_channel_id="UC_test",
            published_at="2025-01-01T00:00:00Z",
        )

        with (
            patch.object(orch._llm, "generate_reply_stream", new=_stub_stream),
            patch.object(orch._avatar, "send_event", new_callable=AsyncMock),
            patch.object(orch._avatar, "send_update", new_callable=AsyncMock),
        ):
            await orch._reply_to(msg)

        assert not orch._is_replying, "_is_replying must be False after _reply_to"


# ── TC-PRIO-06: _idle_talk_loop gate ─────────────────────────────────────────


class TestIdleTalkLoopPriorityGate:
    """TC-PRIO-06: _idle_talk_loop skips when blocked by INTERACTIVE priority."""

    @pytest.mark.asyncio
    async def test_skips_llm_when_is_replying(self):
        """TC-PRIO-06a: LLM is NOT called when _is_replying=True."""
        orch = _make_orch()
        orch._is_replying = True
        orch._start_time = 0.0
        orch._last_reply_time = 0.0  # guarantee elapsed > timeout
        orch._IDLE_TIMEOUT_SEC = 0.0

        llm_called = False

        async def _stub_idle(**kwargs):
            nonlocal llm_called
            llm_called = True
            from orchestrator.llm_client import LLMResult
            return LLMResult(text="x", is_template=False)

        orch._llm.generate_idle_talk = _stub_idle  # type: ignore[assignment]

        orch._running = True
        sleep_calls = 0
        _real_sleep = asyncio.sleep  # save before patch

        async def _fast_sleep(sec: float) -> None:
            nonlocal sleep_calls
            sleep_calls += 1
            if sleep_calls >= 2:
                orch._running = False
            await _real_sleep(0)

        with patch("asyncio.sleep", side_effect=_fast_sleep):
            await orch._idle_talk_loop()

        assert not llm_called, "LLM must NOT be called when _is_replying=True"

    @pytest.mark.asyncio
    async def test_skips_llm_when_reply_queue_non_empty(self):
        """TC-PRIO-06b: LLM is NOT called when _reply_queue has pending messages."""
        from orchestrator.chat_poller import ChatMessage

        orch = _make_orch()
        orch._is_replying = False
        orch._start_time = 0.0
        orch._last_reply_time = 0.0
        orch._IDLE_TIMEOUT_SEC = 0.0

        # Enqueue a pending user message
        msg = ChatMessage(
            message_id="pending",
            text="test",
            author_display_name="User",
            author_channel_id="UC_test",
            published_at="2025-01-01T00:00:00Z",
        )
        await orch._reply_queue.put(msg)

        llm_called = False

        async def _stub_idle(**kwargs):
            nonlocal llm_called
            llm_called = True
            from orchestrator.llm_client import LLMResult
            return LLMResult(text="x", is_template=False)

        orch._llm.generate_idle_talk = _stub_idle  # type: ignore[assignment]

        orch._running = True
        sleep_calls = 0
        _real_sleep = asyncio.sleep  # save before patch

        async def _fast_sleep(sec: float) -> None:
            nonlocal sleep_calls
            sleep_calls += 1
            if sleep_calls >= 2:
                orch._running = False
            await _real_sleep(0)

        with patch("asyncio.sleep", side_effect=_fast_sleep):
            await orch._idle_talk_loop()

        assert not llm_called, "LLM must NOT be called when reply_queue is non-empty"
