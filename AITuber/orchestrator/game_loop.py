"""GameLoop: game-streaming loop that drives commentary, reflex actions, and LLM strategy.

FR-GAME-01: GameBridge WebSocket protocol (port 31901)
FR-GAME-02: Reflex (<50 ms) vs Strategy (LLM, 1-3 s) action split
FR-GAME-03: Event-driven commentary + periodic interval TTS
FR-GAME-04: (OBS scene switch — stub, wired when obs_client is available)
FR-GAME-05: Minecraft/Mineflayer Phase 1

Usage::

    loop = GameLoop(cfg, llm_client, tts_client, avatar_ws)
    await loop.run()          # long-running; cancel to stop
"""

from __future__ import annotations

import asyncio
import logging
import os
import shlex
import subprocess
import time
from collections.abc import Awaitable, Callable
from enum import StrEnum
from typing import Any

from .broadcast_layout import BroadcastLayoutManager, BroadcastScene, TransitionName
from .config import AppConfig
from .game_context_adapter import GameContextAdapter
from .llm_client import LLMClient
from .rule_engine import GameAction, RuleEngine

logger = logging.getLogger(__name__)


class GameLoopEvent(StrEnum):
    """High-level state changes emitted by GameLoop.

    FR-GAME-06: publish bridge/crash lifecycle events for avatar reactions.
    """

    CONNECTED = "connected"
    DISCONNECTED = "disconnected"
    RELAUNCH_STARTED = "relaunch_started"
    RELAUNCH_FAILED = "relaunch_failed"


# Build a single-turn commentary prompt from the current game context
_COMMENTARY_SYSTEM = (
    "You are {name}, an energetic AITuber who is live-streaming Minecraft. "
    "Keep commentary short (1–2 sentences), lively, and in Japanese. "
    "Use the provided game-state snippet to make it contextual."
)

_COMMENTARY_USER = (
    "Current game context: {context}\n\n"
    "Give a brief live commentary about what's happening right now."
)


class GameLoop:
    """Orchestrates the game-streaming behaviour.

    Responsibilities:

    * Spawns ``GameContextAdapter.connect()`` as a background task.
    * Runs the reflex loop: evaluates ``RuleEngine.evaluate()`` every tick and
      executes the returned action immediately via ``GameContextAdapter.send_action()``.
    * Runs the commentary loop: every ``commentary_interval_sec`` seconds, prompts
      the LLM with the current game context and speaks the result via TTS + AvatarWS.
    """

    _REFLEX_TICK_SEC = 0.1  # 10 Hz reflex tick — well under 50 ms budget

    def __init__(
        self,
        cfg: AppConfig,
        llm_client: LLMClient,
        tts_client: Any,
        avatar_ws: Any,
        character_name: str = "AITuber",
        layout_manager: BroadcastLayoutManager | None = None,
        on_event: Callable[[GameLoopEvent], Awaitable[None]] | None = None,
    ) -> None:
        self._cfg = cfg
        self._gc_cfg = cfg.game_bridge
        self._llm = llm_client
        self._tts = tts_client
        self._avatar = avatar_ws
        self._character_name = character_name
        self._adapter = GameContextAdapter(self._gc_cfg)
        self._rule_engine = RuleEngine()
        self._running = False
        self._layout = layout_manager
        self._on_event = on_event
        self._in_game_scene = False
        self._game_process: subprocess.Popen | None = None
        self._disconnect_started_monotonic: float | None = None
        self._disconnect_alerted = False
        self._last_relaunch_attempt_monotonic: float = 0.0

    # ── Public entry point ────────────────────────────────────────────────────

    async def run(self) -> None:
        """Long-running coroutine. Cancel this task to stop the game loop."""
        self._running = True
        self._try_auto_launch_game()
        logger.info("[GameLoop] Starting game loop (bridge=%s)", self._gc_cfg)
        async with asyncio.TaskGroup() as tg:
            tg.create_task(self._adapter.connect(), name="game-bridge-connect")
            tg.create_task(self._reflex_loop(), name="game-reflex-loop")
            tg.create_task(self._commentary_loop(), name="game-commentary-loop")
            tg.create_task(self._health_loop(), name="game-health-loop")

    # ── Sub-loops ─────────────────────────────────────────────────────────────

    async def _reflex_loop(self) -> None:
        """FR-GAME-02: run RuleEngine every tick and send any triggered action."""
        while True:
            if self._adapter.is_connected:
                state = self._adapter.state
                action = self._rule_engine.evaluate(state)
                if action is not None:
                    await self._dispatch_action(action)
            await asyncio.sleep(self._REFLEX_TICK_SEC)

    async def _health_loop(self) -> None:
        """FR-LAYOUT-05: monitor bridge health and recover from game crashes.

        Behaviour:
          - bridge connected   -> switch to GAME layout if needed
          - bridge disconnected -> after grace period, switch to hide layout
          - optional auto relaunch with cooldown when game process exited
        """
        while True:
            await self._sync_layout_with_connection_state()
            self._maybe_relaunch_game()
            await asyncio.sleep(1.0)

    async def _sync_layout_with_connection_state(self) -> None:
        """FR-LAYOUT-01: Move OBS/overlay layout based on game-bridge connectivity."""
        connected = self._adapter.is_connected

        if self._layout is None:
            if connected:
                self._disconnect_started_monotonic = None
                self._disconnect_alerted = False
            return

        if connected and not self._in_game_scene:
            self._disconnect_started_monotonic = None
            self._disconnect_alerted = False
            ok = await self._layout.switch_to(
                BroadcastScene.GAME,
                transition=TransitionName.GLITCH,
            )
            if ok:
                self._in_game_scene = True
            await self._emit_event(GameLoopEvent.CONNECTED)
            return

        if connected:
            self._disconnect_started_monotonic = None
            self._disconnect_alerted = False
            return

        now = time.monotonic()
        if self._disconnect_started_monotonic is None:
            self._disconnect_started_monotonic = now
            return

        if (now - self._disconnect_started_monotonic) < max(
            0.0, self._gc_cfg.disconnect_grace_sec
        ):
            return

        if not self._disconnect_alerted:
            await self._emit_event(GameLoopEvent.DISCONNECTED)
            self._disconnect_alerted = True

        if self._in_game_scene:
            hide_scene = self._resolve_hide_scene()
            transition = (
                TransitionName.SCAN
                if hide_scene == BroadcastScene.OPENING
                else TransitionName.FADE
            )
            ok = await self._layout.switch_to(hide_scene, transition=transition)
            if ok:
                self._in_game_scene = False
                logger.warning(
                    "[GameLoop] Bridge disconnected; switched to fallback scene=%s",
                    hide_scene,
                )

    def _resolve_hide_scene(self) -> BroadcastScene:
        """Resolve fallback scene when game is unavailable.

        FR-LAYOUT-06: hide gameplay feed safely while recovering from crash.
        """
        raw = self._gc_cfg.disconnect_hide_scene.strip().lower()
        try:
            return BroadcastScene(raw)
        except ValueError:
            logger.warning(
                "[GameLoop] Invalid GAME_DISCONNECT_HIDE_SCENE=%r; fallback to chat",
                raw,
            )
            return BroadcastScene.CHAT

    async def _commentary_loop(self) -> None:
        """FR-GAME-03: periodic LLM commentary at configured interval."""
        # Brief startup delay so the adapter can establish initial connection
        await asyncio.sleep(5.0)
        while True:
            interval = self._gc_cfg.commentary_interval_sec
            await asyncio.sleep(interval)
            if not self._adapter.is_connected:
                continue
            await self._generate_commentary()

    # ── Action dispatch ───────────────────────────────────────────────────────

    async def _dispatch_action(self, action: GameAction) -> None:
        """Send a reflex or strategy action to the game via the adapter."""
        success = await self._adapter.send_action(action.to_dict())
        if success:
            logger.debug("[GameLoop] Action dispatched: %s", action)
        else:
            logger.warning("[GameLoop] Failed to dispatch action %s", action)

    # ── Commentary generation ─────────────────────────────────────────────────

    async def _generate_commentary(self) -> None:
        """Ask the LLM for live commentary and send it to TTS + AvatarWS."""
        context = self._adapter.get_context_snippet()
        system_prompt = _COMMENTARY_SYSTEM.format(name=self._character_name)
        user_prompt = _COMMENTARY_USER.format(context=context)
        try:
            result = await self._llm.generate_reply(
                system=system_prompt,
                user=user_prompt,
            )
            text = result.text if hasattr(result, "text") else str(result)
            if not text:
                return
            logger.info("[GameLoop] Commentary: %s", text)
            await self._speak(text)
        except Exception:
            logger.exception("[GameLoop] Commentary LLM call failed")

    async def _speak(self, text: str) -> None:
        """Send text to TTS and stream audio/lipsync to AvatarWS."""
        if self._tts is None or self._avatar is None:
            return
        try:
            tts_result = await self._tts.synthesize(text)
            if tts_result is None:
                return
            # FR-GAME-03: drive lipsync + audio playback
            from .audio_player import play_audio_chunks

            await play_audio_chunks(tts_result, self._avatar)
        except Exception:
            logger.exception("[GameLoop] TTS/speak failed for game commentary")

    def _try_auto_launch_game(self) -> bool:
        """FR-LAYOUT-03: Optionally auto-launch game process before bridge connect."""
        if not self._gc_cfg.auto_launch_game:
            return False

        command = self._gc_cfg.game_launch_command.strip()
        if not command:
            logger.warning("[GameLoop] GAME_AUTO_LAUNCH=1 but GAME_LAUNCH_COMMAND is empty")
            return False

        try:
            # On Windows, allow shell=True so users can pass `start "" "...exe"`.
            self._game_process = subprocess.Popen(
                command if os.name == "nt" else shlex.split(command),
                shell=(os.name == "nt"),
            )
            logger.info("[GameLoop] Auto-launched game command: %s", command)
            return True
        except Exception:
            logger.exception("[GameLoop] Failed to auto-launch game command: %s", command)
            return False

    def _maybe_relaunch_game(self) -> None:
        """FR-LAYOUT-05: Relaunch game when disconnected and process exited."""
        if not self._gc_cfg.auto_launch_game:
            return
        if not self._gc_cfg.relaunch_on_disconnect:
            return
        if self._adapter.is_connected:
            return
        if self._disconnect_started_monotonic is None:
            return

        now = time.monotonic()
        if (now - self._disconnect_started_monotonic) < max(
            0.0, self._gc_cfg.disconnect_grace_sec
        ):
            return

        if (now - self._last_relaunch_attempt_monotonic) < max(
            1.0, self._gc_cfg.relaunch_cooldown_sec
        ):
            return

        if self._game_process is not None and self._game_process.poll() is None:
            # Process is still alive; bridge may reconnect soon.
            return

        self._last_relaunch_attempt_monotonic = now
        self._emit_event_nowait(GameLoopEvent.RELAUNCH_STARTED)
        relaunched = self._try_auto_launch_game()
        if relaunched:
            logger.warning("[GameLoop] Game relaunched after disconnect")
        else:
            self._emit_event_nowait(GameLoopEvent.RELAUNCH_FAILED)

    async def _emit_event(self, event: GameLoopEvent) -> None:
        """Emit GameLoop state changes to Orchestrator (best-effort)."""
        if self._on_event is None:
            return
        try:
            await self._on_event(event)
        except Exception:
            logger.exception("[GameLoop] on_event callback failed: %s", event)

    def _emit_event_nowait(self, event: GameLoopEvent) -> None:
        """Fire-and-forget wrapper used by sync code paths."""
        if self._on_event is None:
            return
        try:
            loop = asyncio.get_running_loop()
            loop.create_task(self._emit_event(event))
        except RuntimeError:
            logger.warning("[GameLoop] No running loop for event=%s", event)
