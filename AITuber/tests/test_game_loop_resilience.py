"""Tests for GameLoop crash-recovery and fallback layout behavior.

TC-GLR-01: Connected bridge switches layout to GAME once
TC-GLR-02: Disconnected bridge past grace switches to fallback scene
TC-GLR-03: Relauch triggers when disconnected and cooldown elapsed
"""

from __future__ import annotations

import time
from types import SimpleNamespace

import pytest

from orchestrator.broadcast_layout import BroadcastScene, TransitionName
from orchestrator.config import AppConfig, GameBridgeConfig
from orchestrator.game_loop import GameLoop, GameLoopEvent


class _DummyLayout:
    def __init__(self) -> None:
        self.calls: list[tuple[BroadcastScene, TransitionName | None]] = []

    async def switch_to(self, scene: BroadcastScene, *, transition=None, **_kwargs):
        self.calls.append((scene, transition))
        return True


def _make_loop(*, cfg: GameBridgeConfig, layout=None, on_event=None) -> GameLoop:
    app_cfg = AppConfig(game_bridge=cfg)
    llm = SimpleNamespace()
    tts = SimpleNamespace()
    avatar = SimpleNamespace()
    return GameLoop(app_cfg, llm, tts, avatar, layout_manager=layout, on_event=on_event)


@pytest.mark.asyncio
async def test_glr_01_connected_switches_to_game() -> None:
    cfg = GameBridgeConfig()
    layout = _DummyLayout()
    loop = _make_loop(cfg=cfg, layout=layout)

    loop._adapter._ws = object()
    await loop._sync_layout_with_connection_state()

    assert loop._in_game_scene is True
    assert layout.calls[0][0] == BroadcastScene.GAME


@pytest.mark.asyncio
async def test_glr_01b_connected_emits_event() -> None:
    cfg = GameBridgeConfig()
    layout = _DummyLayout()
    seen: list[GameLoopEvent] = []

    async def _on_event(event: GameLoopEvent) -> None:
        seen.append(event)

    loop = _make_loop(cfg=cfg, layout=layout, on_event=_on_event)

    loop._adapter._ws = object()
    await loop._sync_layout_with_connection_state()

    assert GameLoopEvent.CONNECTED in seen


@pytest.mark.asyncio
async def test_glr_02_disconnected_switches_to_fallback_after_grace() -> None:
    cfg = GameBridgeConfig(disconnect_hide_scene="opening", disconnect_grace_sec=0.1)
    layout = _DummyLayout()
    loop = _make_loop(cfg=cfg, layout=layout)

    loop._in_game_scene = True
    loop._adapter._ws = None
    loop._disconnect_started_monotonic = time.monotonic() - 1.0

    await loop._sync_layout_with_connection_state()

    assert loop._in_game_scene is False
    assert layout.calls[0][0] == BroadcastScene.OPENING


@pytest.mark.asyncio
async def test_glr_02b_disconnected_emits_event_after_grace() -> None:
    cfg = GameBridgeConfig(disconnect_hide_scene="chat", disconnect_grace_sec=0.1)
    layout = _DummyLayout()
    seen: list[GameLoopEvent] = []

    async def _on_event(event: GameLoopEvent) -> None:
        seen.append(event)

    loop = _make_loop(cfg=cfg, layout=layout, on_event=_on_event)

    loop._in_game_scene = False
    loop._adapter._ws = None
    loop._disconnect_started_monotonic = time.monotonic() - 1.0

    await loop._sync_layout_with_connection_state()

    assert seen == [GameLoopEvent.DISCONNECTED]


def test_glr_03_relaunch_when_disconnected_and_cooldown_elapsed() -> None:
    cfg = GameBridgeConfig(
        auto_launch_game=True,
        game_launch_command="dummy",
        relaunch_on_disconnect=True,
        disconnect_grace_sec=0.1,
        relaunch_cooldown_sec=0.1,
    )
    loop = _make_loop(cfg=cfg, layout=None)

    called = {"value": False}

    def _fake_launch() -> bool:
        called["value"] = True
        return True

    loop._try_auto_launch_game = _fake_launch  # type: ignore[method-assign]
    loop._adapter._ws = None
    loop._disconnect_started_monotonic = time.monotonic() - 1.0
    loop._last_relaunch_attempt_monotonic = 0.0
    loop._game_process = None

    loop._maybe_relaunch_game()

    assert called["value"] is True
