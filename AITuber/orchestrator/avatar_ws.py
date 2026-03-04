"""Avatar WebSocket **server** – controls the thin Unity/Live2D renderer.

SRS refs: FR-A7-01, FR-LIPSYNC-01, FR-LIPSYNC-02.
Protocol:  protocols/avatar_ws.yml

The orchestrator runs a WS server on ws://0.0.0.0:31900 (default).
Unity (AvatarWSClient) connects as a WS client.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
import uuid
from collections.abc import Sequence
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

import numpy as np

from orchestrator.config import AvatarWSConfig
from orchestrator.ws_schema_validator import WsSchemaValidator

logger = logging.getLogger(__name__)


# ── Enums matching protocol ──────────────────────────────────────────


class Emotion(StrEnum):
    NEUTRAL = "neutral"
    HAPPY = "happy"
    THINKING = "thinking"
    SURPRISED = "surprised"
    SAD = "sad"
    ANGRY = "angry"
    PANIC = "panic"


class Gesture(StrEnum):
    NONE = "none"
    NOD = "nod"
    SHAKE = "shake"
    WAVE = "wave"
    CHEER = "cheer"
    SHRUG = "shrug"
    FACEPALM = "facepalm"
    # ── Mixamo 追加ジェスチャー ──
    SHY         = "shy"
    LAUGH       = "laugh"
    SURPRISED   = "surprised"
    REJECTED    = "rejected"
    SIGH        = "sigh"
    THANKFUL    = "thankful"
    SAD_IDLE    = "sad_idle"
    SAD_KICK    = "sad_kick"
    THINKING    = "thinking"
    IDLE_ALT    = "idle_alt"
    SIT_DOWN    = "sit_down"
    SIT_IDLE    = "sit_idle"
    SIT_LAUGH   = "sit_laugh"
    SIT_CLAP    = "sit_clap"
    SIT_POINT   = "sit_point"
    SIT_DISBELIEF = "sit_disbelief"
    SIT_KICK    = "sit_kick"


class LookTarget(StrEnum):
    CENTER = "center"
    CHAT = "chat"
    CAMERA = "camera"
    DOWN = "down"
    RANDOM = "random"


class AvatarEventType(StrEnum):
    COMMENT_READ_START = "comment_read_start"
    COMMENT_READ_END = "comment_read_end"
    TOPIC_SWITCH = "topic_switch"
    BREAK_START = "break_start"
    BREAK_END = "break_end"


# ── Data models ──────────────────────────────────────────────────────


@dataclass
class VisemeEvent:
    t_ms: int
    v: str  # e.g. "a", "i", "u", "e", "o", "sil", "m", "fv"


@dataclass
class AvatarMessage:
    """Wire format for avatar WS messages."""

    cmd: str
    params: dict[str, Any] = field(default_factory=dict)
    msg_id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    ts: str = field(default_factory=lambda: time.strftime("%Y-%m-%dT%H:%M:%S.000Z", time.gmtime()))

    def to_json(self) -> str:
        return json.dumps(
            {"id": self.msg_id, "ts": self.ts, "cmd": self.cmd, "params": self.params},
            ensure_ascii=False,
        )


# ── RMS lip sync helper (FR-LIPSYNC-01) ──────────────────────────────


def compute_rms_mouth_open(audio_chunk: np.ndarray, *, sensitivity: float = 1.0) -> float:
    """Compute mouth_open 0..1 from audio RMS.

    FR-LIPSYNC-01: During playback, update mouth_open at 30 Hz.
    """
    if audio_chunk.size == 0:
        return 0.0
    rms = float(np.sqrt(np.mean(audio_chunk.astype(np.float64) ** 2)))
    # Normalize: typical speech RMS ~0.01–0.3 for float32 audio
    normalized = min(1.0, rms * sensitivity * 5.0)
    return round(normalized, 3)


# ── WebSocket SERVER sender ──────────────────────────────────────────


class AvatarWSSender:
    """Runs a WebSocket **server** that Unity connects to.

    Architecture:
      - Python (this) = WS server on :31900
      - Unity (AvatarWSClient.cs) = WS client connecting to :31900
    """

    def __init__(self, config: AvatarWSConfig | None = None) -> None:
        self._cfg = config or AvatarWSConfig()
        self._clients: set = set()  # active websocket connections
        self._server = None
        self._lock = asyncio.Lock()
        self._ready = asyncio.Event()
        self._schema_validator = WsSchemaValidator()


    @property
    def connected(self) -> bool:
        return len(self._clients) > 0

    @property
    def client_count(self) -> int:
        return len(self._clients)

    # ── Server lifecycle ──────────────────────────────────────────

    async def start_server(self) -> None:
        """Start the WebSocket server (non-blocking)."""
        import websockets

        self._server = await websockets.serve(
            self._handle_client,
            self._cfg.host,
            self._cfg.port,
        )
        self._ready.set()
        logger.info(
            "Avatar WS server listening on ws://%s:%d",
            self._cfg.host,
            self._cfg.port,
        )

    async def _handle_client(self, websocket) -> None:
        """Handle a new client connection."""
        self._clients.add(websocket)
        remote = websocket.remote_address
        logger.info("Avatar client connected from %s", remote)

        # Send capabilities handshake
        try:
            await self._send_capabilities(websocket)
        except Exception:
            logger.debug("Capabilities handshake skipped")

        try:
            # Keep connection alive — read messages if Unity sends any
            async for _message in websocket:
                logger.debug("Received from Unity: %s", _message[:200] if _message else "")
        except Exception:
            pass
        finally:
            self._clients.discard(websocket)
            logger.info("Avatar client disconnected from %s", remote)

    async def stop_server(self) -> None:
        """Stop the server and close all client connections."""
        if self._server:
            self._server.close()
            await self._server.wait_closed()
            self._server = None
        self._clients.clear()
        self._ready.clear()

    # ── Backward-compatible aliases ───────────────────────────────

    async def connect(self) -> None:
        """Start the WS server (backward-compatible with old client API)."""
        await self.start_server()

    async def disconnect(self) -> None:
        """Stop the WS server (backward-compatible with old client API)."""
        await self.stop_server()

    # ── Send helpers ──────────────────────────────────────────────

    async def _send_capabilities(self, ws=None) -> None:
        """Send optional capabilities message to one or all clients."""
        caps_msg = AvatarMessage(
            cmd="capabilities",
            params={
                "mouth_open": True,
                "viseme": True,
                "viseme_set": ["jp_basic_8"],
            },
        )
        data = caps_msg.to_json()
        if ws is not None:
            await ws.send(data)
        else:
            await self._broadcast(data)
        logger.debug("Sent capabilities message")

    async def _broadcast(self, data: str) -> None:
        """Send data to all connected clients."""
        if not self._clients:
            return
        import websockets

        dead = set()
        async with self._lock:
            for ws in self._clients:
                try:
                    await ws.send(data)
                except (
                    websockets.exceptions.ConnectionClosed,
                    ConnectionError,
                    OSError,
                ):
                    dead.add(ws)
        self._clients -= dead

    async def _send(self, msg: AvatarMessage) -> None:
        """Broadcast a message to all connected clients.

        FR-WS-SCHEMA-01, FR-WS-SCHEMA-02: Validates against protocol schema
        before sending; logs a warning if the message is non-conformant but
        does NOT block delivery (warn-only mode).
        """
        result = self._schema_validator.validate_json(msg.to_json())
        if not result.ok:
            logger.warning(
                "WS schema validation failed (cmd=%s): [%s] %s",
                msg.cmd,
                result.error_code,
                result.message,
            )
        if not self._clients:
            logger.debug("No avatar clients connected; message dropped")
            return
        await self._broadcast(msg.to_json())

    # ── High-level commands ───────────────────────────────────────

    async def send_update(
        self,
        emotion: Emotion = Emotion.NEUTRAL,
        gesture: Gesture = Gesture.NONE,
        look_target: LookTarget = LookTarget.CAMERA,
        mouth_open: float = 0.0,
    ) -> None:
        """Send avatar_update command."""
        msg = AvatarMessage(
            cmd="avatar_update",
            params={
                "emotion": emotion.value,
                "gesture": gesture.value,
                "look_target": look_target.value,
                "mouth_open": round(max(0.0, min(1.0, mouth_open)), 3),
            },
        )
        await self._send(msg)

    async def send_event(
        self,
        event: AvatarEventType,
        intensity: float = 1.0,
    ) -> None:
        """Send avatar_event command."""
        msg = AvatarMessage(
            cmd="avatar_event",
            params={
                "event": event.value,
                "intensity": round(max(0.0, min(1.0, intensity)), 3),
            },
        )
        await self._send(msg)

    async def send_config(
        self,
        mouth_sensitivity: float = 1.0,
        blink_enabled: bool = True,
        idle_motion: str = "default",
    ) -> None:
        """Send avatar_config command."""
        msg = AvatarMessage(
            cmd="avatar_config",
            params={
                "mouth_sensitivity": mouth_sensitivity,
                "blink_enabled": blink_enabled,
                "idle_motion": idle_motion,
            },
        )
        await self._send(msg)

    async def send_reset(self) -> None:
        """Send avatar_reset command."""
        msg = AvatarMessage(cmd="avatar_reset")
        await self._send(msg)

    async def send_viseme(
        self,
        utterance_id: str,
        events: Sequence[VisemeEvent],
        *,
        viseme_set: str = "jp_basic_8",
        crossfade_ms: int = 60,
        strength: float = 1.0,
    ) -> None:
        """Send avatar_viseme command.

        FR-LIPSYNC-02: events sorted by t_ms; crossfade 40..80 recommended.
        AvatarWSConfig.viseme_audio_offset_ms を全イベントの t_ms に加算し、
        音声再生開始のバッファリング遅延に合わせてビゼームをずらす。
        """
        offset = getattr(self._cfg, "viseme_audio_offset_ms", 0)
        sorted_events = sorted(events, key=lambda e: e.t_ms)
        msg = AvatarMessage(
            cmd="avatar_viseme",
            params={
                "utterance_id": utterance_id,
                "viseme_set": viseme_set,
                "events": [{"t_ms": e.t_ms + offset, "v": e.v} for e in sorted_events],
                "crossfade_ms": max(40, min(80, crossfade_ms)),
                "strength": round(max(0.0, min(1.0, strength)), 3),
            },
        )
        await self._send(msg)

    async def run_lip_sync_loop(
        self,
        audio_chunks: asyncio.Queue[np.ndarray | None],
        *,
        sensitivity: float = 1.0,
    ) -> None:
        """Stream mouth_open updates at ~30 Hz from audio chunks.

        FR-LIPSYNC-01: RMS-based lip sync at 30 Hz.
        Send None to the queue to stop.
        """
        interval = 1.0 / self._cfg.mouth_open_hz
        while True:
            chunk = await audio_chunks.get()
            if chunk is None:
                # End of audio – close mouth
                await self.send_update(mouth_open=0.0)
                break
            mouth = compute_rms_mouth_open(chunk, sensitivity=sensitivity)
            await self.send_update(mouth_open=mouth)
            await asyncio.sleep(interval)


