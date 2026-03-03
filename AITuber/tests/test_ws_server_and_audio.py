"""Tests for avatar_ws.py WS server and audio_player.py.

Validates:
- B1: AvatarWSSender runs as server, Unity connects as client
- B2: audio_player drains queue gracefully when sounddevice unavailable
- I4: QuotaExceededError in chat_poller
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, patch

import numpy as np
import pytest

from orchestrator.avatar_ws import AvatarWSSender, Emotion, Gesture
from orchestrator.config import AvatarWSConfig

# ── B1: WS Server tests ──────────────────────────────────────────────


class TestAvatarWSServer:
    """AvatarWSSender runs as a WS server."""

    @pytest.mark.asyncio
    async def test_start_and_stop_server(self):
        """Server starts on a free port and stops cleanly."""
        cfg = AvatarWSConfig(host="127.0.0.1", port=0)  # port=0 → OS picks free
        sender = AvatarWSSender(cfg)

        # Use a fixed port for test
        cfg_fixed = AvatarWSConfig(host="127.0.0.1", port=39100)
        sender = AvatarWSSender(cfg_fixed)
        await sender.start_server()
        assert sender._server is not None
        assert sender._ready.is_set()
        await sender.stop_server()
        assert sender._server is None

    @pytest.mark.asyncio
    async def test_send_without_clients_does_not_raise(self):
        """Sending with no connected clients just logs debug, no error."""
        cfg = AvatarWSConfig(host="127.0.0.1", port=39101)
        sender = AvatarWSSender(cfg)
        await sender.start_server()

        # Should not raise
        await sender.send_update(emotion=Emotion.HAPPY)
        await sender.send_reset()

        await sender.stop_server()

    @pytest.mark.asyncio
    async def test_connected_property(self):
        """connected is False when no clients."""
        sender = AvatarWSSender()
        assert sender.connected is False
        assert sender.client_count == 0

    @pytest.mark.asyncio
    async def test_client_connects_and_receives(self):
        """A WS client can connect to the server and receive messages."""
        import websockets

        cfg = AvatarWSConfig(host="127.0.0.1", port=39102)
        sender = AvatarWSSender(cfg)
        await sender.start_server()

        # Connect a client
        ws = await websockets.connect("ws://127.0.0.1:39102")
        await asyncio.sleep(0.1)  # let server register client

        assert sender.connected
        assert sender.client_count == 1

        # Receive capabilities handshake
        caps = await asyncio.wait_for(ws.recv(), timeout=2.0)
        import json

        data = json.loads(caps)
        assert data["cmd"] == "capabilities"

        # Send an update
        await sender.send_update(emotion=Emotion.HAPPY, gesture=Gesture.NOD)
        msg = await asyncio.wait_for(ws.recv(), timeout=2.0)
        parsed = json.loads(msg)
        assert parsed["cmd"] == "avatar_update"
        assert parsed["params"]["emotion"] == "happy"

        await ws.close()
        await asyncio.sleep(0.1)
        await sender.stop_server()

    @pytest.mark.asyncio
    async def test_backward_compat_connect_disconnect(self):
        """connect() and disconnect() aliases work."""
        cfg = AvatarWSConfig(host="127.0.0.1", port=39103)
        sender = AvatarWSSender(cfg)
        await sender.connect()
        assert sender._server is not None
        await sender.disconnect()
        assert sender._server is None


# ── B2: Audio player tests ───────────────────────────────────────────


class TestAudioPlayer:
    """audio_player.py graceful degradation."""

    @pytest.mark.asyncio
    async def test_drains_queue_when_sounddevice_missing(self):
        """When sounddevice is not available, just drains the queue."""
        from orchestrator.audio_player import play_audio_chunks

        q: asyncio.Queue = asyncio.Queue()
        q.put_nowait(np.zeros(100, dtype=np.int16))
        q.put_nowait(None)

        # Patch _get_sd to return None (simulating missing sounddevice)
        with patch("orchestrator.audio_player._get_sd", return_value=None):
            await play_audio_chunks(q)
        # Should complete without error

    @pytest.mark.asyncio
    async def test_plays_with_mock_sounddevice(self):
        """With a mock sounddevice, chunks are written to the stream."""
        from orchestrator.audio_player import play_audio_chunks

        written_chunks = []

        class MockStream:
            def start(self):
                pass

            def stop(self):
                pass

            def close(self):
                pass

            def write(self, data):
                written_chunks.append(data)

        class MockSD:
            def OutputStream(self, **kwargs):  # noqa: N802
                return MockStream()

        q: asyncio.Queue = asyncio.Queue()
        q.put_nowait(np.zeros(100, dtype=np.int16))
        q.put_nowait(np.ones(50, dtype=np.int16))
        q.put_nowait(None)

        with patch("orchestrator.audio_player._get_sd", return_value=MockSD()):
            await play_audio_chunks(q)

        assert len(written_chunks) == 2


# ── I4: QuotaExceededError tests ─────────────────────────────────────


class TestQuotaExceeded:
    """YouTube 429 / quota handling."""

    def test_quota_exceeded_error_class(self):
        from orchestrator.chat_poller import QuotaExceededError

        err = QuotaExceededError("rate limited")
        assert str(err) == "rate limited"
        assert isinstance(err, Exception)

    @pytest.mark.asyncio
    async def test_poll_once_handles_429(self):
        """When _do_list raises QuotaExceededError, poll_once returns empty + long wait."""
        from orchestrator.chat_poller import QuotaExceededError, YouTubeChatPoller
        from orchestrator.config import YouTubeConfig

        cfg = YouTubeConfig(api_key="test", live_chat_id="test_chat")
        poller = YouTubeChatPoller(cfg, api_client_factory=lambda: AsyncMock())

        with patch.object(poller, "_do_list", side_effect=QuotaExceededError("429")):
            messages, interval_ms = await poller.poll_once()
            assert messages == []
            assert interval_ms == 60000
