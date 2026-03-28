"""Broadcast Layout Manager — AI-controlled dynamic layout switching.

FR-LAYOUT-01: Switch between chat/game/opening/ending scenes.
FR-LAYOUT-02: Coordinate overlay layout update + OBS scene switch + transition.
FR-TRANS-01:  Play named transition animation around every scene change.

State machine:
  any → (transition in) → scene switch → (transition out) → any

Layout modes:
  opening  — Full-screen loop animation shown before the stream starts.
  chat     — Standard Unity world + overlays (header / chat / subtitle).
  game     — Slim mode: game capture fills screen, avatar appears as a corner
             window with only subtitle overlay visible.
  ending   — Full-screen loop animation shown after the stream ends.

Each mode maps to:
  - An OBS scene name (configurable, defaults provided).
  - An overlay ``scene`` event sent to all browser sources.
  - Optional ``layout`` parameters forwarded to game_frame.html.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable, Coroutine
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

logger = logging.getLogger(__name__)


# ── Enums ─────────────────────────────────────────────────────────────


class BroadcastScene(StrEnum):
    """Logical scene / layout mode.  FR-LAYOUT-01."""

    OPENING = "opening"
    CHAT = "chat"
    GAME = "game"
    ENDING = "ending"


class TransitionName(StrEnum):
    """Named transition animations.  FR-TRANS-01."""

    FADE = "fade"
    GLITCH = "glitch"
    SCAN = "scan"
    SLIDE_LEFT = "slide_left"
    SLIDE_RIGHT = "slide_right"


# ── Config ────────────────────────────────────────────────────────────


@dataclass
class LayoutConfig:
    """Per-scene OBS scene name and optional overlay parameters.

    FR-LAYOUT-01.
    """

    obs_scene: str
    overlay_params: dict[str, Any] = field(default_factory=dict)


_DEFAULT_LAYOUT: dict[BroadcastScene, LayoutConfig] = {
    BroadcastScene.OPENING: LayoutConfig(obs_scene="Opening"),
    BroadcastScene.CHAT: LayoutConfig(obs_scene="Chat_Main"),
    BroadcastScene.GAME: LayoutConfig(
        obs_scene="Game_Main",
        overlay_params={"position": "bottom-right", "size": "md"},
    ),
    BroadcastScene.ENDING: LayoutConfig(obs_scene="Ending"),
}


@dataclass
class GameFramePosition:
    """Position + size for the game_frame corner avatar overlay.

    FR-LAYOUT-02.
    """

    position: str = "bottom-right"  # top-left | top-right | bottom-left | bottom-right
    size: str = "md"  # sm (240px) | md (320px) | lg (400px)


# ── Async type aliases ────────────────────────────────────────────────

_OverlayFn = Callable[..., Coroutine[Any, Any, None]]
_ObsSwitchFn = Callable[[str], bool]


# ── Manager ───────────────────────────────────────────────────────────


class BroadcastLayoutManager:
    """Orchestrate overlay events + OBS scene switch + transitions.

    FR-LAYOUT-01, FR-LAYOUT-02, FR-TRANS-01.

    All external calls are injected as callables so the class is fully
    testable without a live OBS or OverlayServer.

    Args:
        scene_configs: per-scene OBS scene name + overlay params.
            Defaults to ``_DEFAULT_LAYOUT``.
        send_scene_fn: async callable(scene: str) that sends the ``scene``
            overlay event.
        send_layout_fn: async callable(mode: str, **kwargs) for overlay layout.
        send_transition_fn: async callable(name: str, direction: str) for
            transition overlay.
        obs_switch_fn: sync callable(obs_scene_name: str) → bool for OBS scene
            switch.  Pass ``OBSCameraController.switch_to_scene`` here.
        transition_duration_ms: milliseconds to wait between transition-in and
            transition-out (time for OBS to switch scene).  Default 600 ms.
        default_transition: transition name used when caller does not specify.
    """

    def __init__(
        self,
        *,
        scene_configs: dict[BroadcastScene, LayoutConfig] | None = None,
        send_scene_fn: _OverlayFn | None = None,
        send_layout_fn: _OverlayFn | None = None,
        send_transition_fn: _OverlayFn | None = None,
        obs_switch_fn: _ObsSwitchFn | None = None,
        transition_duration_ms: int = 600,
        default_transition: TransitionName = TransitionName.FADE,
    ) -> None:
        self._configs = scene_configs or _DEFAULT_LAYOUT
        self._send_scene = send_scene_fn or _noop_async
        self._send_layout = send_layout_fn or _noop_async
        self._send_transition = send_transition_fn or _noop_async
        self._obs_switch = obs_switch_fn or (lambda _: True)
        self._transition_ms = transition_duration_ms
        self._default_transition = default_transition
        self._current_scene: BroadcastScene = BroadcastScene.CHAT
        self._game_frame = GameFramePosition()

    # ── Public API ─────────────────────────────────────────────────────

    @property
    def current_scene(self) -> BroadcastScene:
        return self._current_scene

    @property
    def game_frame(self) -> GameFramePosition:
        return self._game_frame

    async def switch_to(
        self,
        scene: BroadcastScene | str,
        *,
        transition: TransitionName | str | None = None,
        game_position: str | None = None,
        game_size: str | None = None,
    ) -> bool:
        """Switch to a scene with optional transition animation.

        FR-LAYOUT-01, FR-TRANS-01.

        Sequence:
          1. send transition "in" to overlay
          2. wait transition_duration_ms
          3. switch OBS scene
          4. send overlay scene + layout events
          5. send transition "out" to overlay

        Args:
            scene: target scene (BroadcastScene or string slug).
            transition: named transition; None uses default_transition.
            game_position: override game frame position when switching to game.
            game_size: override game frame size when switching to game.

        Returns:
            True if OBS switch succeeded (or no OBS client).
        """
        if isinstance(scene, str):
            try:
                scene = BroadcastScene(scene)
            except ValueError:
                logger.warning("[Layout] Unknown scene slug: %r", scene)
                return False

        trans = TransitionName(transition) if transition else self._default_transition
        cfg = self._configs.get(scene)
        if cfg is None:
            logger.warning("[Layout] No config for scene=%s", scene)
            return False

        logger.info("[Layout] switch %s → %s via transition=%s", self._current_scene, scene, trans)

        # Step 1: transition in
        await self._send_transition(trans, direction="in")
        await asyncio.sleep(self._transition_ms / 1000.0)

        # Step 2: OBS scene switch
        obs_ok = self._obs_switch(cfg.obs_scene)
        if not obs_ok:
            logger.warning("[Layout] OBS switch to %s failed", cfg.obs_scene)

        # Step 3: overlay scene event
        await self._send_scene(scene.value)

        # Step 4: overlay layout event (always send, even for non-game scenes)
        params = dict(cfg.overlay_params)
        if scene == BroadcastScene.GAME:
            if game_position:
                params["position"] = game_position
                self._game_frame.position = game_position
            if game_size:
                params["size"] = game_size
                self._game_frame.size = game_size
        await self._send_layout(scene.value, **params)

        # Step 5: transition out
        await self._send_transition(trans, direction="out")

        self._current_scene = scene
        return obs_ok

    async def update_game_frame(
        self,
        *,
        position: str | None = None,
        size: str | None = None,
    ) -> None:
        """Dynamically reposition / resize the game avatar frame overlay.

        FR-LAYOUT-02: AI calls this without triggering a full scene switch.
        """
        if position:
            self._game_frame.position = position
        if size:
            self._game_frame.size = size
        await self._send_layout(
            BroadcastScene.GAME.value,
            position=self._game_frame.position,
            size=self._game_frame.size,
        )
        logger.info(
            "[Layout] game_frame updated position=%s size=%s",
            self._game_frame.position,
            self._game_frame.size,
        )

    def set_transition_duration(self, ms: int) -> None:
        """Adjust the pause between transition-in and OBS scene switch.

        FR-TRANS-01: Let callers tune the timing to match the stinger length.
        """
        self._transition_ms = max(0, ms)

    def configure_scene(self, scene: BroadcastScene, config: LayoutConfig) -> None:
        """Override OBS scene name / overlay params for a given scene.

        Useful for different stream types (Minecraft vs. other games) that
        map to different OBS scenes.
        """
        self._configs[scene] = config


# ── Helpers ───────────────────────────────────────────────────────────


async def _noop_async(*_args: Any, **_kwargs: Any) -> None:
    pass
