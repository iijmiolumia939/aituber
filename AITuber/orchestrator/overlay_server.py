"""Overlay WebSocket server for OBS Browser Sources.

Runs a lightweight WS server on :31901 that broadcasts overlay events
(chat messages, subtitles, config) to connected HTML overlay clients.

Architecture:
  - Python Orchestrator → OverlayServer (this) → OBS Browser Sources (HTML/JS)
  - Separate from the Avatar WS on :31900 (which talks to Unity)
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import time
import uuid
from dataclasses import dataclass, field
from typing import Any

try:
    from websockets.exceptions import ConnectionClosed as _WsConnectionClosed
except ImportError:  # websockets not installed (test env without it)
    _WsConnectionClosed = None  # type: ignore[assignment,misc]

logger = logging.getLogger(__name__)


@dataclass
class OverlayConfig:
    """Configuration for the overlay WS server."""

    host: str = "127.0.0.1"
    port: int = field(default_factory=lambda: int(os.environ.get("OVERLAY_WS_PORT", "31902")))


class OverlayServer:
    """WebSocket server that broadcasts overlay events to OBS browser sources."""

    def __init__(self, config: OverlayConfig | None = None) -> None:
        self._cfg = config or OverlayConfig()
        self._clients: set = set()
        self._server = None
        self._lock = asyncio.Lock()

    @property
    def client_count(self) -> int:
        return len(self._clients)

    # ── Server lifecycle ──────────────────────────────────────────

    async def start(self) -> None:
        """Start the overlay WS server."""
        import websockets

        self._server = await websockets.serve(
            self._handle_client,
            self._cfg.host,
            self._cfg.port,
        )
        logger.info(
            "Overlay WS server listening on ws://%s:%d",
            self._cfg.host,
            self._cfg.port,
        )

    async def _handle_client(self, websocket) -> None:
        """Handle a new browser source connection."""
        self._clients.add(websocket)
        remote = websocket.remote_address
        logger.info("Overlay client connected from %s", remote)
        try:
            async for _message in websocket:
                pass  # Browser sources don't send messages
        except Exception:
            pass
        finally:
            self._clients.discard(websocket)
            logger.debug("Overlay client disconnected from %s", remote)

    async def stop(self) -> None:
        """Stop the server."""
        if self._server:
            self._server.close()
            await self._server.wait_closed()
            self._server = None
        self._clients.clear()

    # ── Broadcast ─────────────────────────────────────────────────

    async def _broadcast(self, data: dict[str, Any]) -> None:
        """Send JSON data to all connected overlay clients."""
        if not self._clients:
            return

        payload = json.dumps(data, ensure_ascii=False)
        _dead_exc: tuple[type[Exception], ...] = (ConnectionError, OSError)
        if _WsConnectionClosed is not None:
            _dead_exc = (_WsConnectionClosed, ConnectionError, OSError)

        dead = set()
        async with self._lock:
            for ws in self._clients:
                try:
                    await ws.send(payload)
                except _dead_exc:  # type: ignore[misc]
                    dead.add(ws)
        self._clients -= dead

    # ── High-level overlay events ─────────────────────────────────

    async def send_chat(self, *, author: str, text: str, badge: str = "") -> None:
        """Broadcast a chat message to overlay clients."""
        await self._broadcast(
            {
                "type": "chat",
                "id": uuid.uuid4().hex[:8],
                "ts": time.time(),
                "author": author,
                "text": text,
                "badge": badge,
            }
        )

    async def send_subtitle(self, text: str, *, duration_sec: float = 10.0) -> None:
        """Broadcast subtitle (current speech) to overlay clients."""
        await self._broadcast(
            {
                "type": "subtitle",
                "text": text,
                "duration_sec": duration_sec,
            }
        )

    async def send_config(
        self,
        *,
        character_name: str = "",
        character_subtitle: str = "",
        viewer_count: int | None = None,
        subscriber_count: int | None = None,
    ) -> None:
        """Broadcast config (character info) to overlay clients."""
        payload: dict[str, Any] = {
            "type": "config",
            "character_name": character_name,
            "character_subtitle": character_subtitle,
        }
        if viewer_count is not None:
            payload["viewer_count"] = viewer_count
        if subscriber_count is not None:
            payload["subscriber_count"] = subscriber_count
        await self._broadcast(payload)

    async def clear_subtitle(self) -> None:
        """Clear the subtitle display."""
        await self._broadcast({"type": "subtitle", "text": "", "duration_sec": 0})

    async def send_scene(self, scene: str) -> None:
        """Broadcast scene change (opening | chat | game | ending).

        FR-LAYOUT-01: All overlay HTML sources listen to this event and
        show/hide themselves accordingly.
        """
        await self._broadcast({"type": "scene", "scene": scene})

    async def send_layout(self, mode: str, **kwargs: Any) -> None:
        """Broadcast dynamic layout parameters.

        FR-LAYOUT-02: Allows AI to reconfigure overlay geometry at runtime.

        Args:
            mode: layout mode slug (e.g. "chat", "game", "opening", "ending").
            **kwargs: arbitrary layout parameters forwarded as-is to clients
                      (e.g. position="bottom-right", size="md").
        """
        await self._broadcast({"type": "layout", "mode": mode, **kwargs})

    async def send_transition(self, name: str = "fade", *, direction: str = "in") -> None:
        """Trigger a named transition animation on the transition overlay.

        FR-TRANS-01: transition.html receives this event and plays the
        corresponding animation (fade | glitch | scan | slide_left | slide_right).

        Args:
            name: transition name.
            direction: "in" (to black / cover) or "out" (reveal).
        """
        await self._broadcast({"type": "transition", "name": name, "direction": direction})

    # ── THA avatar events (Issue #87) ─────────────────────────────

    async def send_tha_frame(self, base64_png: str) -> None:
        """Broadcast a THA rendered frame to the tha_avatar overlay.

        FR-A7-01: THA レンダラーが生成した PNG を base64 で送信。
        tha_avatar.html がこれを受信してアバター画像を更新。
        """
        await self._broadcast({"type": "tha_frame", "data": base64_png})

    async def send_tha_frame_binary(self, png_bytes: bytes) -> None:
        """Broadcast a THA rendered frame as raw binary to all clients.

        高帯域・低レイテンシ版。base64 エンコード不要で tha_avatar.html が
        ArrayBuffer として直接受信。
        """
        if not self._clients:
            return

        _dead_exc: tuple[type[Exception], ...] = (ConnectionError, OSError)
        if _WsConnectionClosed is not None:
            _dead_exc = (_WsConnectionClosed, ConnectionError, OSError)

        dead: set = set()
        async with self._lock:
            for ws in self._clients:
                try:
                    await ws.send(png_bytes)
                except _dead_exc:  # type: ignore[misc]
                    dead.add(ws)
        self._clients -= dead

    async def send_tha_state(self, *, speaking: bool = False) -> None:
        """Broadcast THA avatar speaking state.

        tha_avatar.html がアイドル / 話し中のアニメーションを切り替え。
        """
        await self._broadcast({"type": "tha_state", "speaking": speaking})

    async def send_background(
        self,
        *,
        image: str = "",
        room: bool = False,
        time_period: str = "",
    ) -> None:
        """Broadcast background configuration to background.html overlay.

        Args:
            image: 背景画像 URL or base64。空文字でデフォルトグラデーション。
            room: 窓枠風フレーム表示。
            time_period: "morning" | "afternoon" | "evening" | "night"。
        """
        payload: dict[str, Any] = {"type": "background"}
        if image:
            payload["image"] = image
        payload["room"] = room
        if time_period:
            payload["time"] = time_period
        await self._broadcast(payload)

    async def send_menu(self, items: list[dict[str, Any]]) -> None:
        """Broadcast menu items to tha_broadcast.html overlay.

        Args:
            items: メニュー項目 e.g. [{"text": "ゲームプレイ", "done": True}]
        """
        await self._broadcast({"type": "menu", "items": items})

    async def send_info(self, panel: int, *, title: str = "", content: str = "") -> None:
        """Broadcast info panel content to tha_broadcast.html overlay.

        Args:
            panel: 1 or 2 (左 or 右の情報パネル)
            title: パネルタイトル
            content: パネル内容テキスト
        """
        await self._broadcast(
            {
                "type": "info",
                "panel": panel,
                "title": title,
                "content": content,
            }
        )
