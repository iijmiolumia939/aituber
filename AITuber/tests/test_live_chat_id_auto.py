"""TC-CHATID-AUTO-01 ~ TC-CHATID-AUTO-05: LIVE_CHAT_ID 自動取得テスト.

FR-CHATID-AUTO-01: YOUTUBE_LIVE_CHAT_ID が未設定の場合、
liveBroadcasts.list API で自動検出する。
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from orchestrator.chat_poller import fetch_active_live_chat_id
from orchestrator.config import YouTubeConfig

# ── Helper factories ──────────────────────────────────────────────────


def _make_broadcast_response(chat_id: str) -> dict:
    """liveBroadcasts.list レスポンスのモック（1件のアクティブ配信）。"""
    return {
        "items": [
            {
                "id": "broadcast_001",
                "snippet": {
                    "title": "Test Stream",
                    "liveChatId": chat_id,
                },
            }
        ]
    }


def _empty_response() -> dict:
    """アクティブ配信なしのレスポンス。"""
    return {"items": []}


def _service_factory_returning(chat_id: str | None):
    """OAuth サービスをモックする factory を返す。"""
    class _MockRequest:
        def execute(self) -> dict:
            if chat_id:
                return _make_broadcast_response(chat_id)
            return _empty_response()

    class _MockBroadcasts:
        def list(self, **_kw):
            return _MockRequest()

    class _MockService:
        def liveBroadcasts(self):  # noqa: N802
            return _MockBroadcasts()

    def factory():
        return _MockService()

    return factory


def _service_factory_raising(exc: Exception):
    """OAuth サービスが例外を raise するモック。"""
    def factory():
        raise exc

    return factory


# ── TC-CHATID-AUTO-01: OAuth パスで chat_id を取得 ────────────────────


@pytest.mark.asyncio
async def test_fetch_active_live_chat_id_oauth_success():
    """TC-CHATID-AUTO-01: OAuth サービスがアクティブ配信の liveChatId を返す。"""
    cfg = YouTubeConfig(api_key="", live_chat_id="")
    expected_id = "Cq1abcXYZ"

    result = await fetch_active_live_chat_id(
        cfg,
        _service_factory=_service_factory_returning(expected_id),
    )

    assert result == expected_id


# ── TC-CHATID-AUTO-02: アクティブ配信なし → None を返す ───────────────


@pytest.mark.asyncio
async def test_fetch_active_live_chat_id_no_active_broadcast():
    """TC-CHATID-AUTO-02: アクティブ配信がない場合は None を返す。"""
    cfg = YouTubeConfig(api_key="", live_chat_id="")

    result = await fetch_active_live_chat_id(
        cfg,
        _service_factory=_service_factory_returning(None),
    )

    assert result is None


# ── TC-CHATID-AUTO-03: OAuth 失敗 → API key fallback ─────────────────


@pytest.mark.asyncio
async def test_fetch_active_live_chat_id_oauth_error_uses_apikey_fallback():
    """TC-CHATID-AUTO-03: OAuth エラー時、APIキー+channelId にフォールバックする。"""
    expected_id = "ChatId_from_apikey"
    cfg = YouTubeConfig(
        api_key="MY_API_KEY",
        channel_id="UC_my_channel",
        live_chat_id="",
    )

    # httpx fallback をモック
    mock_response = MagicMock()
    mock_response.json.return_value = _make_broadcast_response(expected_id)
    mock_response.raise_for_status = MagicMock()

    with patch("httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client.get.return_value = mock_response
        mock_client_cls.return_value.__aenter__.return_value = mock_client

        result = await fetch_active_live_chat_id(
            cfg,
            _service_factory=_service_factory_raising(RuntimeError("OAuth failed")),
        )

    assert result == expected_id


# ── TC-CHATID-AUTO-04: API key + channel_id のみで取得 ────────────────


@pytest.mark.asyncio
async def test_fetch_active_live_chat_id_apikey_path_no_oauth():
    """TC-CHATID-AUTO-04: OAuth token ファイルが存在しない場合、API key パスで取得できる。"""
    expected_id = "ChatId_apikey_only"
    cfg = YouTubeConfig(
        api_key="VALID_KEY",
        channel_id="UC_channel",
        live_chat_id="",
    )

    mock_response = MagicMock()
    mock_response.json.return_value = _make_broadcast_response(expected_id)
    mock_response.raise_for_status = MagicMock()

    with patch("os.path.exists", return_value=False), \
         patch("httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client.get.return_value = mock_response
        mock_client_cls.return_value.__aenter__.return_value = mock_client

        result = await fetch_active_live_chat_id(cfg)

    assert result == expected_id


# ── TC-CHATID-AUTO-05: 資格情報なし → None ───────────────────────────


@pytest.mark.asyncio
async def test_fetch_active_live_chat_id_no_credentials_returns_none():
    """TC-CHATID-AUTO-05: 認証情報もなく API キー・channel_id も未設定なら None。"""
    cfg = YouTubeConfig(api_key="", channel_id="", live_chat_id="")

    with patch("os.path.exists", return_value=False):
        result = await fetch_active_live_chat_id(cfg)

    assert result is None


# ── TC-CHATID-AUTO-06: YouTubeConfig.channel_id フィールド確認 ────────


def test_youtube_config_has_channel_id_field():
    """TC-CHATID-AUTO-06: YouTubeConfig に channel_id フィールドが追加されている。"""
    cfg = YouTubeConfig(channel_id="UC_test")
    assert cfg.channel_id == "UC_test"


def test_youtube_config_broadcast_wait_interval_default():
    """TC-CHATID-AUTO-07: broadcast_wait_interval_sec のデフォルト値は 15.0。"""
    cfg = YouTubeConfig()
    assert cfg.broadcast_wait_interval_sec == 15.0


# ── TC-CHATID-AUTO-08: Orchestrator が live_chat_id を自動解決して poller を更新 ──


@pytest.mark.asyncio
async def test_orchestrator_resolve_live_chat_id_updates_poller():
    """TC-CHATID-AUTO-08: Orchestrator._resolve_live_chat_id が cfg と poller を更新する。"""
    from orchestrator.config import AppConfig
    from orchestrator.main import Orchestrator

    expected_id = "resolved_chat_id"

    # Orchestrator を最小化して初期化（YouTube / TTS / WS の実通信なし）
    cfg = AppConfig(youtube=YouTubeConfig(live_chat_id="", api_key="key"))

    with patch("orchestrator.main.load_character") as mock_load_char:
        mock_char = MagicMock()
        mock_char.voice.tts_backend = "voicevox"
        mock_char.voice.tts_port = None
        mock_char.voice.speaker_id = 1
        mock_char.voice.sbv2_model_id = 0
        mock_char.voice.sbv2_style = "Neutral"
        mock_char.idle_topics = []
        mock_char.name = "test"
        mock_load_char.return_value = mock_char

        orch = Orchestrator(config=cfg)
    orch._running = True  # start() が設定する値を再現

    # fetch_active_live_chat_id をモックして即座に resolved_id を返す
    with patch(
        "orchestrator.main.fetch_active_live_chat_id",
        new=AsyncMock(return_value=expected_id),
    ):
        await orch._resolve_live_chat_id()

    assert orch._cfg.youtube.live_chat_id == expected_id
    assert orch._poller._cfg.live_chat_id == expected_id


# ── TC-CHATID-AUTO-09: 配信未開始 → リトライして取得 ─────────────────


@pytest.mark.asyncio
async def test_orchestrator_resolve_retries_until_found():
    """TC-CHATID-AUTO-09: 配信未開始（None）の後、2回目に chat_id が取得できる。"""
    from orchestrator.config import AppConfig
    from orchestrator.main import Orchestrator

    cfg = AppConfig(
        youtube=YouTubeConfig(
            live_chat_id="",
            api_key="key",
            broadcast_wait_interval_sec=0.0,  # テスト高速化
        )
    )

    with patch("orchestrator.main.load_character") as mock_load_char:
        mock_char = MagicMock()
        mock_char.voice.tts_backend = "voicevox"
        mock_char.voice.tts_port = None
        mock_char.voice.speaker_id = 1
        mock_char.voice.sbv2_model_id = 0
        mock_char.voice.sbv2_style = "Neutral"
        mock_char.idle_topics = []
        mock_char.name = "test"
        mock_load_char.return_value = mock_char

        orch = Orchestrator(config=cfg)
    orch._running = True  # start() が設定する値を再現

    # 1回目は None、2回目に chat_id を返す
    side_effects = [None, "found_chat_id"]
    with patch(
        "orchestrator.main.fetch_active_live_chat_id",
        new=AsyncMock(side_effect=side_effects),
    ):
        await orch._resolve_live_chat_id()

    assert orch._cfg.youtube.live_chat_id == "found_chat_id"
