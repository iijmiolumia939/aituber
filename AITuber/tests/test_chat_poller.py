"""TC-A3-01: pollingIntervalMillis respected (mock API + injectable clock).
TC-A3-02: seen_set TTL and cap.
TC-A3-03: summary mode triggers.

Maps to: FR-A3-01, FR-A3-02, FR-A3-03, NFR-RES-02.
"""

from __future__ import annotations

import pytest

from orchestrator.chat_poller import AuthorTracker, RateTracker, SeenSet, YouTubeChatPoller, _clamp
from orchestrator.config import SeenSetConfig, YouTubeConfig

# ── Helpers: mock YouTube API ─────────────────────────────────────────


def _make_item(
    msg_id: str,
    text: str = "hello",
    author: str = "user1",
    *,
    message_type: str = "textMessageEvent",
    amount_micros: int = 0,
    amount_display: str = "",
) -> dict:
    """Build a single YouTube LiveChatMessages.list item."""
    snippet: dict[str, object] = {
        "displayMessage": text,
        "publishedAt": "2025-01-01T00:00:00Z",
        "type": message_type,
    }
    if amount_micros > 0 or amount_display:
        snippet["superChatDetails"] = {
            "amountMicros": amount_micros,
            "amountDisplayString": amount_display,
        }
    return {
        "id": msg_id,
        "snippet": snippet,
        "authorDetails": {
            "channelId": f"UC_{author}",
            "displayName": author,
        },
    }


def _mock_api_factory(responses: list[dict]):
    """Return a factory that yields a mock client returning *responses* in order."""
    call_idx = {"n": 0}

    class _MockRequest:
        def __init__(self, resp: dict) -> None:
            self._resp = resp

        def execute(self) -> dict:
            return self._resp

    class _MockLiveChat:
        def list(self, **_kw):
            idx = call_idx["n"]
            call_idx["n"] += 1
            return _MockRequest(responses[idx])

    class _MockClient:
        def liveChatMessages(self):  # noqa: N802
            return _MockLiveChat()

    def factory():
        return _MockClient()

    return factory


def _failing_api_factory(fail_count: int, then_response: dict):
    """Factory that raises *fail_count* times, then returns *then_response*."""
    call_idx = {"n": 0}

    class _FailRequest:
        def execute(self):
            raise ConnectionError("API transient error")

    class _OkRequest:
        def execute(self):
            return then_response

    class _MockLiveChat:
        def list(self, **_kw):
            call_idx["n"] += 1
            if call_idx["n"] <= fail_count:
                return _FailRequest()
            return _OkRequest()

    class _MockClient:
        def liveChatMessages(self):  # noqa: N802
            return _MockLiveChat()

    def factory():
        return _MockClient()

    return factory


# ── TC-A3-01: pollingIntervalMillis clamping ──────────────────────────


class TestPollingIntervalClamping:
    """TC-A3-01: pollingIntervalMillis respected (clamp logic)."""

    def test_clamp_within_range(self):
        assert _clamp(5000, 3000, 30000) == 5000

    def test_clamp_below_minimum(self):
        """API returns very short interval → clamped to minimum."""
        assert _clamp(500, 3000, 30000) == 3000

    def test_clamp_above_maximum(self):
        """API returns very long interval → clamped to maximum."""
        assert _clamp(60000, 3000, 30000) == 30000

    def test_clamp_at_boundary(self):
        assert _clamp(3000, 3000, 30000) == 3000
        assert _clamp(30000, 3000, 30000) == 30000


# ── TC-A3-01: mock API poller integration ─────────────────────────────


class TestPollerMockAPI:
    """TC-A3-01: pollingIntervalMillis respected (mock_youtube_api + injectable_clock)."""

    @pytest.mark.asyncio
    async def test_poll_once_returns_messages_and_interval(self):
        """Basic poll returns new messages and clamped interval."""
        resp = {
            "items": [_make_item("m1", "こんにちは")],
            "pollingIntervalMillis": 5000,
        }
        cfg = YouTubeConfig(live_chat_id="LC_TEST")
        clock_time = [1000.0]
        poller = YouTubeChatPoller(
            cfg,
            api_client_factory=_mock_api_factory([resp]),
            clock=lambda: clock_time[0],
        )
        msgs, interval_ms = await poller.poll_once()
        assert len(msgs) == 1
        assert msgs[0].text == "こんにちは"
        assert msgs[0].message_id == "m1"
        assert interval_ms == 5000

    @pytest.mark.asyncio
    async def test_polling_interval_clamped_from_api(self):
        """API-returned pollingIntervalMillis is clamped to [3000, 30000]."""
        resp_low = {
            "items": [],
            "pollingIntervalMillis": 500,
        }
        resp_high = {
            "items": [],
            "pollingIntervalMillis": 99999,
        }
        cfg = YouTubeConfig(live_chat_id="LC_TEST")
        poller = YouTubeChatPoller(
            cfg,
            api_client_factory=_mock_api_factory([resp_low, resp_high]),
        )
        _, interval1 = await poller.poll_once()
        assert interval1 == 3000  # clamped up

        _, interval2 = await poller.poll_once()
        assert interval2 == 30000  # clamped down

    @pytest.mark.asyncio
    async def test_dedup_across_polls(self):
        """Duplicate message IDs across polls are filtered out."""
        resp1 = {
            "items": [_make_item("m1"), _make_item("m2")],
            "pollingIntervalMillis": 5000,
        }
        resp2 = {
            "items": [_make_item("m1"), _make_item("m3")],
            "pollingIntervalMillis": 5000,
        }
        cfg = YouTubeConfig(live_chat_id="LC_TEST")
        poller = YouTubeChatPoller(
            cfg,
            api_client_factory=_mock_api_factory([resp1, resp2]),
        )
        msgs1, _ = await poller.poll_once()
        assert {m.message_id for m in msgs1} == {"m1", "m2"}

        msgs2, _ = await poller.poll_once()
        # m1 is duplicate → filtered out
        assert {m.message_id for m in msgs2} == {"m3"}

    @pytest.mark.asyncio
    async def test_injectable_clock_used_for_received_at(self):
        """Injectable clock controls received_at on ChatMessage."""
        resp = {
            "items": [_make_item("m1")],
            "pollingIntervalMillis": 5000,
        }
        fixed_time = 42.0
        cfg = YouTubeConfig(live_chat_id="LC_TEST")
        poller = YouTubeChatPoller(
            cfg,
            api_client_factory=_mock_api_factory([resp]),
            clock=lambda: fixed_time,
        )
        msgs, _ = await poller.poll_once()
        assert msgs[0].received_at == 42.0

    @pytest.mark.asyncio
    async def test_summary_mode_activates_on_burst(self):
        """FR-A3-03: >=10 messages in 15s window → summary_mode=True."""
        items = [_make_item(f"m{i}") for i in range(12)]
        resp = {
            "items": items,
            "pollingIntervalMillis": 5000,
        }
        cfg = YouTubeConfig(live_chat_id="LC_TEST")
        clock_time = [1000.0]
        poller = YouTubeChatPoller(
            cfg,
            api_client_factory=_mock_api_factory([resp]),
            clock=lambda: clock_time[0],
        )
        assert poller.summary_mode is False
        await poller.poll_once()
        assert poller.summary_mode is True

    @pytest.mark.asyncio
    async def test_retry_with_backoff_succeeds(self):
        """FR-A3-01: Bounded retries with exponential backoff."""
        ok_resp = {
            "items": [_make_item("m1", "復旧")],
            "pollingIntervalMillis": 5000,
        }
        cfg = YouTubeConfig(
            live_chat_id="LC_TEST",
            max_retries=3,
            backoff_base_sec=0.001,  # fast for test
        )
        poller = YouTubeChatPoller(
            cfg,
            api_client_factory=_failing_api_factory(2, ok_resp),
        )
        msgs, interval_ms = await poller.poll_once()
        assert len(msgs) == 1
        assert msgs[0].text == "復旧"

    @pytest.mark.asyncio
    async def test_retry_exhausted_raises(self):
        """FR-A3-01: After max_retries, error is raised."""
        cfg = YouTubeConfig(
            live_chat_id="LC_TEST",
            max_retries=2,
            backoff_base_sec=0.001,
        )
        poller = YouTubeChatPoller(
            cfg,
            api_client_factory=_failing_api_factory(
                10, {"items": [], "pollingIntervalMillis": 5000}
            ),
        )
        with pytest.raises(ConnectionError):
            await poller.poll_once()

    @pytest.mark.asyncio
    async def test_no_client_returns_empty(self):
        """No api_client_factory → returns empty with 5000ms interval."""
        cfg = YouTubeConfig(live_chat_id="LC_TEST")
        poller = YouTubeChatPoller(cfg)
        msgs, interval_ms = await poller.poll_once()
        assert msgs == []
        assert interval_ms == 5000

    @pytest.mark.asyncio
    async def test_superchat_metadata_is_parsed(self):
        """FR-SPCHA-01: paid message type and amount fields are preserved."""
        resp = {
            "items": [
                _make_item(
                    "m_paid",
                    text="いつもありがとう",
                    author="supporter",
                    message_type="liveChatPaidMessageEvent",
                    amount_micros=5_000_000_000,
                    amount_display="¥5000",
                )
            ],
            "pollingIntervalMillis": 5000,
        }
        cfg = YouTubeConfig(live_chat_id="LC_TEST")
        poller = YouTubeChatPoller(
            cfg,
            api_client_factory=_mock_api_factory([resp]),
        )

        msgs, _ = await poller.poll_once()
        assert len(msgs) == 1
        assert msgs[0].message_type == "liveChatPaidMessageEvent"
        assert msgs[0].amount_micros == 5_000_000_000
        assert msgs[0].amount_display == "¥5000"


# ── TC-A3-02: seen_set TTL and cap ──────────────────────────────────


class TestSeenSet:
    """TC-A3-02: seen_set TTL and cap (FR-A3-02, NFR-RES-02)."""

    def test_dedup_new_item(self):
        ss = SeenSet()
        assert ss.add("msg1") is True
        assert ss.add("msg1") is False

    def test_ttl_eviction(self):
        """Items older than TTL are evicted."""
        cfg = SeenSetConfig(ttl_seconds=10, max_capacity=100)
        ss = SeenSet(cfg)
        base = 1000.0
        ss.add("old", now=base)
        # 11 seconds later, old item should be evicted
        assert ss.add("old", now=base + 11) is True

    def test_ttl_not_evicted_within_window(self):
        cfg = SeenSetConfig(ttl_seconds=10, max_capacity=100)
        ss = SeenSet(cfg)
        base = 1000.0
        ss.add("recent", now=base)
        # 5 seconds later, still within TTL
        assert ss.add("recent", now=base + 5) is False

    def test_capacity_eviction(self):
        """Exceeding cap evicts oldest entries."""
        cfg = SeenSetConfig(ttl_seconds=3600, max_capacity=5)
        ss = SeenSet(cfg)
        base = 1000.0
        for i in range(6):
            ss.add(f"msg{i}", now=base + i)
        # Oldest (msg0) should have been evicted
        assert len(ss) == 5
        assert "msg0" not in ss
        assert "msg5" in ss

    def test_capacity_at_limit(self):
        """At exactly the cap, no eviction needed."""
        cfg = SeenSetConfig(ttl_seconds=3600, max_capacity=5)
        ss = SeenSet(cfg)
        for i in range(5):
            ss.add(f"msg{i}")
        assert len(ss) == 5

    def test_large_capacity_bound(self):
        """Default cap is 100_000."""
        ss = SeenSet()
        assert ss.capacity == 100_000

    def test_default_ttl(self):
        """Default TTL is 30 minutes."""
        ss = SeenSet()
        assert ss.ttl == 30 * 60


# ── TC-A3-03: summary mode triggers ─────────────────────────────────


class TestSummaryMode:
    """TC-A3-03: summary mode triggers (FR-A3-03)."""

    def test_rate_below_threshold(self):
        rt = RateTracker(window_sec=15.0)
        base = 1000.0
        for i in range(9):
            rt.record(now=base + i)
        assert rt.rate(now=base + 14) < 10

    def test_rate_at_threshold(self):
        rt = RateTracker(window_sec=15.0)
        base = 1000.0
        for i in range(10):
            rt.record(now=base + i)
        assert rt.rate(now=base + 14) >= 10

    def test_rate_decays_over_time(self):
        rt = RateTracker(window_sec=15.0)
        base = 1000.0
        for i in range(20):
            rt.record(now=base + i)
        # At base + 30, only messages from base+16..base+30 remain
        assert rt.rate(now=base + 30) < 10

    def test_empty_rate(self):
        rt = RateTracker()
        assert rt.rate() == 0


class TestAuthorTracker:
    """bandit.yml: unique_authors_60s tracking."""

    def test_unique_count_single_author(self):
        at = AuthorTracker(window_sec=60.0)
        at.record("UC_alice", now=1.0)
        at.record("UC_alice", now=2.0)
        assert at.unique_count(now=3.0) == 1

    def test_unique_count_multiple_authors(self):
        at = AuthorTracker(window_sec=60.0)
        at.record("UC_alice", now=1.0)
        at.record("UC_bob", now=2.0)
        at.record("UC_charlie", now=3.0)
        assert at.unique_count(now=4.0) == 3

    def test_window_prunes_old_authors(self):
        at = AuthorTracker(window_sec=10.0)
        at.record("UC_alice", now=1.0)
        at.record("UC_bob", now=5.0)
        # At t=15, alice (t=1) is outside window (10s), bob (t=5) is inside
        assert at.unique_count(now=15.0) == 1

    def test_empty_returns_zero(self):
        at = AuthorTracker()
        assert at.unique_count() == 0
