"""GameContextAdapter: WebSocket client that connects to the Minecraft bridge bot.

Emits       game_state  JSON from the bot.js side
Receives    action_cmd  JSON sent by the orchestrator

FR-GAME-01: bot.js listens on ws://127.0.0.1:31901
            orchestrator connects as client and reads game_state stream.
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

from .config import GameBridgeConfig

logger = logging.getLogger(__name__)


class GameContextAdapter:
    """Persistent WebSocket client for the game bridge.

    Usage::

        adapter = GameContextAdapter(cfg)
        await adapter.connect()      # blocks in background
        ctx = adapter.get_context_snippet()
        await adapter.send_action({"type": "move", "args": {...}})
        adapter.close()

    ``connect()`` must be called as an asyncio.Task so it keeps running in the
    background while the rest of the orchestrator operates.
    """

    def __init__(self, cfg: GameBridgeConfig) -> None:
        self._cfg = cfg
        self._state: dict[str, Any] = {}
        self._ws: Any = None  # websockets.ClientConnection
        self._running = False
        self._connected = asyncio.Event()
        self._uri = f"ws://{cfg.host}:{cfg.port}"

    # ── Public API ────────────────────────────────────────────────────────────

    async def connect(self) -> None:
        """Long-running task. Connects (with reconnection) and consumes messages."""
        import websockets  # lazy import — mirrors pattern in avatar_ws.py

        self._running = True
        while self._running:
            try:
                logger.info("[GameContextAdapter] Connecting to %s", self._uri)
                async with websockets.connect(self._uri) as ws:
                    self._ws = ws
                    self._connected.set()
                    logger.info("[GameContextAdapter] Connected to game bridge")
                    await self._consume(ws)
            except Exception as exc:
                logger.warning(
                    "[GameContextAdapter] Connection lost (%s). Retry in %.0fs.",
                    exc,
                    self._cfg.reconnect_interval_sec,
                )
            finally:
                self._ws = None
                self._connected.clear()
            if self._running:
                await asyncio.sleep(self._cfg.reconnect_interval_sec)

    def close(self) -> None:
        """Signal the adapter to stop reconnecting."""
        self._running = False

    def get_context_snippet(self) -> str:
        """Return a compact text summary of the latest game state for LLM prompt injection."""
        s = self._state
        if not s:
            return "[game: no data]"
        hp = s.get("health", "?")
        max_hp = s.get("max_health", 20)
        pos = s.get("pos", {})
        pos_str = f"({pos.get('x', '?'):.0f},{pos.get('z', '?'):.0f})" if pos else "?"
        entities = s.get("nearby_entities") or []
        hostile_count = sum(
            1 for e in entities if isinstance(e, dict) and e.get("type") == "hostile"
        )
        time_val = s.get("time")
        if time_val is not None and time_val >= 13000:
            time_label = "night"
        elif time_val is not None:
            time_label = "day"
        else:
            time_label = "?"
        return (
            f"[game: HP={hp}/{max_hp} pos={pos_str} "
            f"hostiles={hostile_count} time={time_label}]"
        )

    async def send_action(self, cmd: dict[str, Any]) -> bool:
        """Send an action command dict to the bot. Returns False if not connected."""
        if self._ws is None:
            logger.debug("[GameContextAdapter] send_action skipped — not connected")
            return False
        try:
            await self._ws.send(json.dumps(cmd))
            return True
        except Exception as exc:
            logger.warning("[GameContextAdapter] send_action failed: %s", exc)
            return False

    @property
    def state(self) -> dict[str, Any]:
        """A shallow copy of the latest game state."""
        return dict(self._state)

    @property
    def is_connected(self) -> bool:
        return self._ws is not None

    # ── Internal ──────────────────────────────────────────────────────────────

    async def _consume(self, ws: Any) -> None:
        async for raw in ws:
            try:
                msg = json.loads(raw)
            except json.JSONDecodeError:
                logger.warning("[GameContextAdapter] Non-JSON message received")
                continue
            self._on_message(msg)

    def _on_message(self, msg: dict[str, Any]) -> None:
        msg_type = msg.get("type")
        if msg_type == "game_state":
            payload = msg.get("payload") or msg
            self._state = payload
            logger.debug("[GameContextAdapter] game_state updated: %s", self.get_context_snippet())
        elif msg_type == "event":
            # Future: push events onto an internal queue for GameLoop
            logger.debug("[GameContextAdapter] game event: %s", msg.get("event"))
        else:
            logger.debug("[GameContextAdapter] Unknown message type: %s", msg_type)
