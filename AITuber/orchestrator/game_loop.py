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
from typing import Any

from .config import AppConfig
from .game_context_adapter import GameContextAdapter
from .llm_client import LLMClient
from .rule_engine import GameAction, RuleEngine

logger = logging.getLogger(__name__)

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

    # ── Public entry point ────────────────────────────────────────────────────

    async def run(self) -> None:
        """Long-running coroutine. Cancel this task to stop the game loop."""
        self._running = True
        logger.info("[GameLoop] Starting game loop (bridge=%s)", self._gc_cfg)
        async with asyncio.TaskGroup() as tg:
            tg.create_task(self._adapter.connect(), name="game-bridge-connect")
            tg.create_task(self._reflex_loop(), name="game-reflex-loop")
            tg.create_task(self._commentary_loop(), name="game-commentary-loop")

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
