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
import time
import uuid
from dataclasses import dataclass
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
    port: int = 31901


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
    ) -> None:
        """Broadcast config (character info) to overlay clients."""
        await self._broadcast(
            {
                "type": "config",
                "character_name": character_name,
                "character_subtitle": character_subtitle,
            }
        )

    async def clear_subtitle(self) -> None:
        """Clear the subtitle display."""
        await self._broadcast({"type": "subtitle", "text": "", "duration_sec": 0})
