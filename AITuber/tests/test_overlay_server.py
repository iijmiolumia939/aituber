"""Tests for OverlayServer and OverlayConfig.

TC-OVL-01 ~ TC-OVL-20

Coverage:
  OVL-01  OverlayConfig default host is '127.0.0.1'
  OVL-02  OverlayConfig default port is 31901
  OVL-03  OverlayConfig custom host/port applied
  OVL-04  OverlayServer.client_count is 0 initially
  OVL-05  OverlayServer._server is None initially
  OVL-06  OverlayServer uses default OverlayConfig when none provided
  OVL-07  send_chat: payload type='chat', correct author and text
  OVL-08  send_chat: id is 8-char hex string, ts is float
  OVL-09  send_chat: badge field forwarded (default empty string)
  OVL-10  send_subtitle: type='subtitle', text, duration_sec
  OVL-11  send_subtitle: default duration_sec is 10.0
  OVL-12  clear_subtitle: text='', duration_sec=0
  OVL-13  send_config: type='config', character_name, character_subtitle
  OVL-14  _broadcast to empty client set completes without error
  OVL-15  ConnectionError on ws.send removes client from _clients
  OVL-16  OSError on ws.send removes client from _clients
  OVL-17  Good client remains alive; dead client removed after error
  OVL-18  send_chat broadcasts to all connected clients
  OVL-19  client_count reflects len(_clients)
  OVL-20  Japanese text preserved (ensure_ascii=False)

SRS ref: FR-A7-01 (WS overlay), Overlay / OBS integration
"""

from __future__ import annotations

import json

import pytest

from orchestrator.overlay_server import OverlayConfig, OverlayServer

# ── Test helpers ──────────────────────────────────────────────────────────────


class _FakeWS:
    """Fake WebSocket that captures sent payloads."""

    def __init__(self) -> None:
        self.sent: list[str] = []
        self.remote_address = ("127.0.0.1", 9999)

    async def send(self, payload: str) -> None:  # noqa: ASYNC109  (sync mock OK)
        self.sent.append(payload)

    @property
    def last_message(self) -> dict:
        return json.loads(self.sent[-1])


class _DeadWS:
    """Fake WebSocket that raises on send to simulate a dropped connection."""

    def __init__(self, error_cls: type[Exception] = ConnectionError) -> None:
        self.remote_address = ("127.0.0.1", 9998)
        self._error_cls = error_cls
        self.send_count = 0

    async def send(self, _: str) -> None:
        self.send_count += 1
        raise self._error_cls("Simulated closed connection")


# ── TC-OVL-01 ~ 03: OverlayConfig ────────────────────────────────────────────


class TestOverlayConfig:
    # [TC-OVL-01] デフォルト host は '127.0.0.1'
    def test_default_host(self) -> None:
        cfg = OverlayConfig()
        assert cfg.host == "127.0.0.1"

    # [TC-OVL-02] デフォルト port は 31901
    def test_default_port(self) -> None:
        cfg = OverlayConfig()
        assert cfg.port == 31901

    # [TC-OVL-03] カスタム host / port が適用される
    def test_custom_values(self) -> None:
        cfg = OverlayConfig(host="0.0.0.0", port=12345)
        assert cfg.host == "0.0.0.0"
        assert cfg.port == 12345


# ── TC-OVL-04 ~ 06: OverlayServer 初期状態 ────────────────────────────────────


class TestOverlayServerInit:
    # [TC-OVL-04] 初期 client_count は 0
    def test_client_count_initially_zero(self) -> None:
        assert OverlayServer().client_count == 0

    # [TC-OVL-05] 初期 _server は None
    def test_server_initially_none(self) -> None:
        assert OverlayServer()._server is None

    # [TC-OVL-06] config 未指定時はデフォルト OverlayConfig が使われる
    def test_default_config_applied(self) -> None:
        server = OverlayServer()
        assert server._cfg.host == "127.0.0.1"
        assert server._cfg.port == 31901


# ── TC-OVL-07 ~ 09: send_chat ────────────────────────────────────────────────


class TestSendChat:
    @pytest.fixture()
    def server_with_client(self) -> tuple[OverlayServer, _FakeWS]:
        server = OverlayServer()
        ws = _FakeWS()
        server._clients.add(ws)
        return server, ws

    # [TC-OVL-07] type='chat', author, text が正しく含まれる
    @pytest.mark.asyncio
    async def test_chat_fields(self, server_with_client) -> None:
        server, ws = server_with_client
        await server.send_chat(author="Alice", text="Hello!")
        msg = ws.last_message
        assert msg["type"] == "chat"
        assert msg["author"] == "Alice"
        assert msg["text"] == "Hello!"

    # [TC-OVL-08] id は 8 文字の hex 文字列、 ts は float
    @pytest.mark.asyncio
    async def test_chat_id_and_ts(self, server_with_client) -> None:
        server, ws = server_with_client
        await server.send_chat(author="Bob", text="Hi")
        msg = ws.last_message
        assert isinstance(msg["id"], str)
        assert len(msg["id"]) == 8
        assert all(c in "0123456789abcdef" for c in msg["id"])
        assert isinstance(msg["ts"], float)

    # [TC-OVL-09] badge フィールドが転送される（デフォルトは空文字列）
    @pytest.mark.asyncio
    async def test_chat_badge_forwarded(self, server_with_client) -> None:
        server, ws = server_with_client
        await server.send_chat(author="Carol", text="Hey", badge="moderator")
        assert ws.last_message["badge"] == "moderator"

        # default
        ws.sent.clear()
        await server.send_chat(author="Carol", text="Hey2")
        assert ws.last_message["badge"] == ""


# ── TC-OVL-10 ~ 12: send_subtitle / clear_subtitle ───────────────────────────


class TestSendSubtitle:
    @pytest.fixture()
    def server_with_client(self) -> tuple[OverlayServer, _FakeWS]:
        server = OverlayServer()
        ws = _FakeWS()
        server._clients.add(ws)
        return server, ws

    # [TC-OVL-10] type='subtitle', text, duration_sec が正しく含まれる
    @pytest.mark.asyncio
    async def test_subtitle_fields(self, server_with_client) -> None:
        server, ws = server_with_client
        await server.send_subtitle("こんにちは", duration_sec=5.0)
        msg = ws.last_message
        assert msg["type"] == "subtitle"
        assert msg["text"] == "こんにちは"
        assert msg["duration_sec"] == pytest.approx(5.0)

    # [TC-OVL-11] デフォルト duration_sec は 10.0
    @pytest.mark.asyncio
    async def test_subtitle_default_duration(self, server_with_client) -> None:
        server, ws = server_with_client
        await server.send_subtitle("テスト")
        assert ws.last_message["duration_sec"] == pytest.approx(10.0)

    # [TC-OVL-12] clear_subtitle は text='' かつ duration_sec=0 を送信する
    @pytest.mark.asyncio
    async def test_clear_subtitle(self, server_with_client) -> None:
        server, ws = server_with_client
        await server.clear_subtitle()
        msg = ws.last_message
        assert msg["type"] == "subtitle"
        assert msg["text"] == ""
        assert msg["duration_sec"] == 0


# ── TC-OVL-13: send_config ────────────────────────────────────────────────────


class TestSendConfig:
    # [TC-OVL-13] type='config', character_name, character_subtitle が含まれる
    @pytest.mark.asyncio
    async def test_config_fields(self) -> None:
        server = OverlayServer()
        ws = _FakeWS()
        server._clients.add(ws)
        await server.send_config(character_name="Lumia", character_subtitle="AI配信者")
        msg = ws.last_message
        assert msg["type"] == "config"
        assert msg["character_name"] == "Lumia"
        assert msg["character_subtitle"] == "AI配信者"


# ── TC-OVL-14: 空クライアントへの broadcast ───────────────────────────────────


class TestBroadcastEmptyClients:
    # [TC-OVL-14] クライアントが 0 のとき _broadcast はエラーなく完了する
    @pytest.mark.asyncio
    async def test_broadcast_no_clients_no_error(self) -> None:
        server = OverlayServer()
        # Should not raise
        await server._broadcast({"type": "test"})


# ── TC-OVL-15 ~ 17: 切断クライアントの除去 ────────────────────────────────────


class TestDeadClientCleanup:
    # [TC-OVL-15] ConnectionError で送信失敗したクライアントは _clients から除去される
    @pytest.mark.asyncio
    async def test_connection_error_removes_client(self) -> None:
        server = OverlayServer()
        dead = _DeadWS(ConnectionError)
        server._clients.add(dead)
        await server._broadcast({"type": "ping"})
        assert dead not in server._clients

    # [TC-OVL-16] OSError で送信失敗したクライアントは _clients から除去される
    @pytest.mark.asyncio
    async def test_os_error_removes_client(self) -> None:
        server = OverlayServer()
        dead = _DeadWS(OSError)
        server._clients.add(dead)
        await server._broadcast({"type": "ping"})
        assert dead not in server._clients

    # [TC-OVL-17] 正常クライアントは残り、切断クライアントのみ除去される
    @pytest.mark.asyncio
    async def test_good_client_remains_dead_removed(self) -> None:
        server = OverlayServer()
        good = _FakeWS()
        dead = _DeadWS(OSError)
        server._clients.update({good, dead})

        await server._broadcast({"type": "ping"})

        assert good in server._clients
        assert dead not in server._clients
        assert len(good.sent) == 1


# ── TC-OVL-18 ~ 19: 複数クライアント / client_count ─────────────────────────


class TestMultipleClients:
    # [TC-OVL-18] send_chat は接続中の全クライアントにブロードキャストされる
    @pytest.mark.asyncio
    async def test_broadcast_reaches_all_clients(self) -> None:
        server = OverlayServer()
        ws1, ws2, ws3 = _FakeWS(), _FakeWS(), _FakeWS()
        server._clients.update({ws1, ws2, ws3})
        await server.send_chat(author="X", text="hello")
        assert len(ws1.sent) == 1
        assert len(ws2.sent) == 1
        assert len(ws3.sent) == 1

    # [TC-OVL-19] client_count は _clients の実際のサイズを反映する
    def test_client_count_reflects_clients_set(self) -> None:
        server = OverlayServer()
        assert server.client_count == 0
        ws = _FakeWS()
        server._clients.add(ws)
        assert server.client_count == 1
        server._clients.discard(ws)
        assert server.client_count == 0


# ── TC-OVL-20: プリペイロード検証 ─────────────────────────────────────────────


class TestJSONPayload:
    # [TC-OVL-20] 日本語テキストが ensure_ascii=False で正しく保持される
    @pytest.mark.asyncio
    async def test_japanese_text_preserved(self) -> None:
        server = OverlayServer()
        ws = _FakeWS()
        server._clients.add(ws)
        jp_text = "みなさん、こんにちは！"
        await server.send_subtitle(jp_text)
        raw = ws.sent[-1]
        # ensure_ascii=False: Japanese chars must appear as-is, not as \uXXXX
        assert jp_text in raw
        # Must still be valid JSON
        assert json.loads(raw)["text"] == jp_text
