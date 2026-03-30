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
import os
import time
import uuid
from collections.abc import Callable, Sequence
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
    SHY = "shy"
    LAUGH = "laugh"
    SURPRISED = "surprised"
    REJECTED = "rejected"
    SIGH = "sigh"
    THANKFUL = "thankful"
    SAD_IDLE = "sad_idle"
    SAD_KICK = "sad_kick"
    THINKING = "thinking"
    IDLE_ALT = "idle_alt"
    SIT_DOWN = "sit_down"
    SIT_IDLE = "sit_idle"
    SIT_LAUGH = "sit_laugh"
    SIT_CLAP = "sit_clap"
    SIT_POINT = "sit_point"
    SIT_DISBELIEF = "sit_disbelief"
    SIT_KICK = "sit_kick"
    # ── M4: stand-up gestures (behavior_policy M4) ──
    BOW = "bow"
    CLAP = "clap"
    THUMBS_UP = "thumbs_up"
    POINT_FORWARD = "point_forward"
    SPIN = "spin"
    # ── M19: daily life Sims-like gestures (FR-LIFE-01) ──
    WALK = "walk"
    SIT_READ = "sit_read"
    SIT_EAT = "sit_eat"
    SIT_WRITE = "sit_write"
    SLEEP_IDLE = "sleep_idle"
    STRETCH = "stretch"


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
        # FR-PERF-01 / Issue #61: binary msgpack transport (default ON)
        # Set USE_MSGPACK=0 to disable.
        self._use_msgpack: bool = os.environ.get("USE_MSGPACK", "1") == "1"
        # FR-E4-01: incoming message handlers keyed by message type
        self._incoming_handlers: dict[str, Callable[[dict], None]] = {}

    # ── Incoming message dispatch (FR-E4-01) ──────────────────────

    def register_incoming_handler(self, msg_type: str, handler: Callable[[dict], None]) -> None:
        """Register a handler for incoming Unity→Python messages of *msg_type*.

        FR-E4-01: Used to hook ``perception_update`` (and future types) from Unity.
        The *handler* is called synchronously with the decoded JSON dict.
        """
        self._incoming_handlers[msg_type] = handler
        logger.debug("Registered incoming handler for type=%s", msg_type)

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
                # FR-E4-01: dispatch typed incoming messages
                self._dispatch_incoming(_message)
        except Exception:
            pass
        finally:
            self._clients.discard(websocket)
            logger.info("Avatar client disconnected from %s", remote)

    def _dispatch_incoming(self, raw: str) -> None:
        """Parse incoming message and call registered handler if any.

        FR-E4-01: Boundary validation – parse here, trust inside handlers.
        """
        try:
            msg = json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            logger.warning("Received non-JSON message from Unity; ignoring")
            return
        msg_type = msg.get("type", "")
        handler = self._incoming_handlers.get(msg_type)
        if handler is not None:
            try:
                handler(msg)
            except Exception:  # noqa: BLE001
                logger.warning("Incoming handler error for type=%s", msg_type, exc_info=True)
        else:
            logger.debug("No handler for incoming type=%s", msg_type)

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
        """Send text data to all connected clients."""
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

    async def _broadcast_binary(self, data: bytes) -> None:
        """Send raw binary data to all connected clients (FR-PERF-01 / Issue #61)."""
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
        if self._use_msgpack:
            try:
                import msgpack  # noqa: PLC0415

                raw = msgpack.packb(json.loads(msg.to_json()), use_bin_type=True)
                await self._broadcast_binary(raw)
                return
            except ImportError:
                logger.warning("msgpack not installed; falling back to JSON text (FR-PERF-01)")
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

    async def send_room_change(self, room_id: str) -> None:
        """Send room_change command to Unity RoomManager.

        FR-LIFE-01: Used by LifeScheduler to move avatar between rooms
        (e.g. to alchemist room for TINKER activity).
        FR-ROOM-01: room_id must match a registered RoomDefinition.roomId.
        """
        msg = AvatarMessage(
            cmd="room_change",
            params={"room_id": room_id},
        )
        await self._send(msg)

    async def send_background_mode(self, mode: str) -> None:
        """Send set_background_mode command to Unity TransparentBackgroundController.

        FR-BCAST-BG-01: Switch between room environment and transparent chroma-key.

        Args:
            mode: "room" (3D room visible) or "transparent" (chroma-key green bg).
        """
        msg = AvatarMessage(
            cmd="set_background_mode",
            params={"mode": mode},
        )
        await self._send(msg)

    async def send_zone_change(self, zone_id: str) -> None:
        """Send zone_change command to Unity RoomManager.

        FR-ZONE-01: Moves the avatar to a named zone within the current room
        (e.g. pc_area, sleep_area, relax_area in Sci-Fi Living Room).
        zone_id must match a RoomDefinition.zones[].zoneId value.
        """
        msg = AvatarMessage(
            cmd="zone_change",
            params={"zone_id": zone_id},
        )
        await self._send(msg)

    async def send_behavior_start(self, behavior: str) -> None:
        """Send behavior_start command to Unity BehaviorSequenceRunner.

        FR-BEHAVIOR-SEQ-01: Triggers a named behavior sequence (e.g. "go_stream",
        "go_sleep").  The sequence owns movement + gesture for its duration;
        the orchestrator must not send conflicting avatar_update gestures while
        it is running.
        """
        msg = AvatarMessage(
            cmd="behavior_start",
            params={"behavior": behavior},
        )
        await self._send(msg)

    async def send_avatar_intent(
        self,
        intent: str,
        *,
        source: str = "life",
        fallback: str = "none",
        context_json: str = "",
    ) -> None:
        """Send avatar_intent command to Unity ActionDispatcher.

        Routes through ActionDispatcher → BehaviorPolicyLoader → action.
        Unrecognised intents are recorded as GapEntries for the Growth system,
        enabling ReflectionRunner to autonomously expand the policy.

        FR-BEHAVIOR-SEQ-01, FR-LIFE-01: used by _life_loop to route ALL life
        activities via the intent pipeline instead of direct behavior_start,
        closing the Perception-Memory-Action loop (Issue #44).
        """
        params: dict[str, Any] = {"intent": intent, "source": source}
        if fallback and fallback != "none":
            params["fallback"] = fallback
        if context_json:
            params["context_json"] = context_json
        msg = AvatarMessage(cmd="avatar_intent", params=params)
        await self._send(msg)

    async def send_appearance_update(
        self,
        shader_mode: str | None = None,
        costume: str | None = None,
        hair: str | None = None,
    ) -> None:
        """Send appearance_update command to Unity AppearanceController.

        FR-SHADER-02: shader_mode — one of:
          - "toon"       → AITuber/CyberpunkToon (default)
          - "lit"        → Universal Render Pipeline/Lit (PBR)
          - "scss"       → Silent's Cel Shading (Built-in RP only — non-functional in URP)
          - "crt"        → AITuber/RetroAvatarCRT (レトロ CRT スキャンライン)
          - "sketch"     → AITuber/CrosshatchSketch (クロスハッチ鉛筆)
          - "watercolor" → AITuber/WatercolorAvatar (水彩)
          - "wireframe"  → AITuber/WireframeSolid (ワイヤーフレーム + ソリッド)
          - "manga"      → AITuber/MangaPanel (漫画パネル Unlit)
        FR-APPEARANCE-01: costume preset ID (e.g. "default", "casual", "formal", "pajama")
        FR-APPEARANCE-02: hair preset ID (e.g. "default", "ponytail", "short")

        Omit arguments (or pass None) to leave the corresponding attribute unchanged.
        """
        params: dict = {}
        if shader_mode is not None:
            params["shader_mode"] = shader_mode
        if costume is not None:
            params["costume"] = costume
        if hair is not None:
            params["hair"] = hair
        if not params:
            return  # Nothing to change
        msg = AvatarMessage(cmd="appearance_update", params=params)
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

    async def send_a2f_audio(
        self,
        pcm_int16: np.ndarray,
        *,
        sample_rate: int = 24000,
    ) -> None:
        """Send a2f_audio command with full-utterance PCM for Audio2Face-3D neural lip sync.

        FR-LIPSYNC-01: Resamples *pcm_int16* from *sample_rate* to 16 kHz (A2F requirement),
        base64-encodes it, and sends via WebSocket so Unity's Audio2FaceLipSync can drive
        blendshapes.

        Args:
            pcm_int16: int16 mono PCM array at *sample_rate*.
            sample_rate: originating sample rate (VOICEVOX=24000, SBERT-VITS2=44100).
        """
        import base64

        a2f_sr = 16000
        if sample_rate != a2f_sr:
            # Simple linear (polyphase) downsample via numpy slicing for integer ratios,
            # or scipy if available; fall back to naive decimation otherwise.
            try:
                from math import gcd

                from scipy.signal import resample_poly  # type: ignore[import-untyped]

                g = gcd(a2f_sr, sample_rate)
                up, down = a2f_sr // g, sample_rate // g
                pcm_f = pcm_int16.astype(np.float32)
                resampled_f = resample_poly(pcm_f, up, down).astype(np.float32)
                pcm_int16 = np.clip(resampled_f, -32768, 32767).astype(np.int16)
            except ImportError:
                # Naive decimation (acceptable quality for speech)
                ratio = sample_rate / a2f_sr
                indices = np.round(np.arange(0, len(pcm_int16), ratio)).astype(np.int64)
                indices = indices[indices < len(pcm_int16)]
                pcm_int16 = pcm_int16[indices]

        pcm_b64 = base64.b64encode(pcm_int16.tobytes()).decode("ascii")
        msg = AvatarMessage(
            cmd="a2f_audio",
            params={
                "pcm_b64": pcm_b64,
                "format": "int16",
                "sample_rate": a2f_sr,
            },
        )
        await self._send(msg)

    async def send_a2f_chunk(
        self,
        pcm_chunk: np.ndarray,
        *,
        sample_rate: int = 24000,
        is_first: bool = False,
    ) -> None:
        """Send a2f_chunk command for streaming Audio2Face-3D lip sync.

        FR-LIPSYNC-01: Sends a single audio chunk as it arrives from TTS so that
        A2F mouth movement is synchronised with audio playback rather than starting
        only after the entire utterance has been synthesised.

        Args:
            pcm_chunk: int16 mono PCM chunk at *sample_rate*.
            sample_rate: originating sample rate (VOICEVOX=24000).
            is_first: True for the first chunk of a new utterance (resets plugin state).
        """
        import base64

        a2f_sr = 16000
        if sample_rate != a2f_sr:
            try:
                from math import gcd

                from scipy.signal import resample_poly  # type: ignore[import-untyped]

                g = gcd(a2f_sr, sample_rate)
                up, down = a2f_sr // g, sample_rate // g
                pcm_f = pcm_chunk.astype(np.float32)
                resampled_f = resample_poly(pcm_f, up, down).astype(np.float32)
                pcm_chunk = np.clip(resampled_f, -32768, 32767).astype(np.int16)
            except ImportError:
                ratio = sample_rate / a2f_sr
                indices = np.round(np.arange(0, len(pcm_chunk), ratio)).astype(np.int64)
                indices = indices[indices < len(pcm_chunk)]
                pcm_chunk = pcm_chunk[indices]

        pcm_b64 = base64.b64encode(pcm_chunk.tobytes()).decode("ascii")
        msg = AvatarMessage(
            cmd="a2f_chunk",
            params={
                "pcm_b64": pcm_b64,
                "format": "int16",
                "sample_rate": a2f_sr,
                "is_first": is_first,
            },
        )
        await self._send(msg)

    async def send_a2f_stream_close(self) -> None:
        """Send a2f_stream_close to signal the end of a streaming utterance.

        FR-LIPSYNC-01: Triggers Audio2FaceLipSync.CloseStream() on the Unity side,
        finalising the blendshape animation for the current utterance.
        """
        msg = AvatarMessage(cmd="a2f_stream_close", params={})
        await self._send(msg)

    async def send_a2g_chunk(
        self,
        pcm_chunk: np.ndarray,
        *,
        sample_rate: int = 24000,
        is_first: bool = False,
    ) -> None:
        """Send a2g_chunk for Option A Audio2Gesture neural upper-body gesture generation.

        FR-GESTURE-AUTO-01: Mirrors send_a2f_chunk; the same audio is routed to the
        Audio2Gesture plugin so body gestures stay in sync with speech.  When
        A2GPlugin.dll is absent Unity silently ignores the command.

        Args:
            pcm_chunk: int16 mono PCM chunk at *sample_rate*.
            sample_rate: originating sample rate (VOICEVOX=24000).
            is_first: True for the first chunk of a new utterance.
        """
        import base64

        a2g_sr = 16000
        if sample_rate != a2g_sr:
            try:
                from math import gcd

                from scipy.signal import resample_poly  # type: ignore[import-untyped]

                g = gcd(a2g_sr, sample_rate)
                up, down = a2g_sr // g, sample_rate // g
                pcm_f = pcm_chunk.astype(np.float32)
                resampled_f = resample_poly(pcm_f, up, down).astype(np.float32)
                pcm_chunk = np.clip(resampled_f, -32768, 32767).astype(np.int16)
            except ImportError:
                ratio = sample_rate / a2g_sr
                indices = np.round(np.arange(0, len(pcm_chunk), ratio)).astype(np.int64)
                indices = indices[indices < len(pcm_chunk)]
                pcm_chunk = pcm_chunk[indices]

        pcm_b64 = base64.b64encode(pcm_chunk.tobytes()).decode("ascii")
        msg = AvatarMessage(
            cmd="a2g_chunk",
            params={
                "pcm_b64": pcm_b64,
                "format": "int16",
                "sample_rate": a2g_sr,
                "is_first": is_first,
            },
        )
        await self._send(msg)

    async def send_a2g_stream_close(self) -> None:
        """Send a2g_stream_close to signal end of streaming for Audio2Gesture.

        FR-GESTURE-AUTO-01: Triggers Audio2GestureController.CloseStream() on the
        Unity side, finalising the gesture animation for the current utterance.
        """
        msg = AvatarMessage(cmd="a2g_stream_close", params={})
        await self._send(msg)

    async def send_a2e_emotion(
        self,
        scores: list[float],
        label: str,
    ) -> None:
        """Send a2e_emotion command with Audio2Emotion ONNX inference result.

        FR-A2E-01: Sends the 10-dim A2F emotion vector and dominant label so Unity
        EmotionController can drive face blendshapes and Audio2GestureController
        can adjust gesture intensity based on detected emotion.

        Args:
            scores: 10-dim A2F emotion vector (float values 0..1).
            label: dominant emotion label ("neutral"|"happy"|"angry"|"sad"|"fear"|"disgust").
        """
        msg = AvatarMessage(
            cmd="a2e_emotion",
            params={
                "scores": [round(float(s), 4) for s in scores],
                "label": label,
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
