"""Tests for BroadcastLayoutManager.

TC-LAYOUT-01 ~ TC-LAYOUT-14

Coverage:
  LAYOUT-01  BroadcastScene enum contains opening/chat/game/ending
  LAYOUT-02  TransitionName enum contains fade/glitch/scan/slide_left/slide_right
  LAYOUT-03  BroadcastLayoutManager.current_scene defaults to CHAT
  LAYOUT-04  switch_to calls send_transition with direction='in' first
  LAYOUT-05  switch_to calls obs_switch with configured OBS scene name
  LAYOUT-06  switch_to calls send_scene with target scene name
  LAYOUT-07  switch_to calls send_layout with mode + overlay params
  LAYOUT-08  switch_to calls send_transition with direction='out' last
  LAYOUT-09  switch_to updates current_scene after success
  LAYOUT-10  switch_to accepts str scene slug (auto-coerces to BroadcastScene)
  LAYOUT-11  switch_to returns False and logs when scene unknown
  LAYOUT-12  update_game_frame broadcasts layout event without scene switch
  LAYOUT-13  configure_scene overrides default OBS scene name
  LAYOUT-14  set_transition_duration clamps negative values to 0

SRS ref: FR-LAYOUT-01, FR-LAYOUT-02, FR-TRANS-01
"""

from __future__ import annotations

import asyncio
from unittest.mock import MagicMock

from orchestrator.broadcast_layout import (
    BroadcastLayoutManager,
    BroadcastScene,
    LayoutConfig,
    TransitionName,
)

# ── Helpers ───────────────────────────────────────────────────────────────────


def _run(coro):
    return asyncio.run(coro)


def _make_manager(
    *,
    transition_duration_ms: int = 0,
    obs_ok: bool = True,
) -> tuple[BroadcastLayoutManager, MagicMock, MagicMock, MagicMock, MagicMock, MagicMock]:
    """Return (manager, send_scene, send_layout, send_transition, obs_switch, send_bg_mode)."""
    send_scene = MagicMock()
    send_layout = MagicMock()
    send_transition = MagicMock()
    send_bg_mode = MagicMock()
    obs_switch = MagicMock(return_value=obs_ok)

    async def async_scene(*a, **kw):
        send_scene(*a, **kw)

    async def async_layout(*a, **kw):
        send_layout(*a, **kw)

    async def async_trans(*a, **kw):
        send_transition(*a, **kw)

    async def async_bg_mode(*a, **kw):
        send_bg_mode(*a, **kw)

    mgr = BroadcastLayoutManager(
        send_scene_fn=async_scene,
        send_layout_fn=async_layout,
        send_transition_fn=async_trans,
        obs_switch_fn=obs_switch,
        send_background_mode_fn=async_bg_mode,
        transition_duration_ms=transition_duration_ms,
    )
    return mgr, send_scene, send_layout, send_transition, obs_switch, send_bg_mode


# ── Enum tests ────────────────────────────────────────────────────────────────


def test_layout_01_broadcast_scene_members():
    """TC-LAYOUT-01: BroadcastScene contains all expected slugs."""
    assert set(s.value for s in BroadcastScene) == {"opening", "chat", "game", "ending"}


def test_layout_02_transition_name_members():
    """TC-LAYOUT-02: TransitionName contains all expected slugs."""
    assert set(t.value for t in TransitionName) == {
        "fade",
        "glitch",
        "scan",
        "slide_left",
        "slide_right",
    }


# ── Initial state ─────────────────────────────────────────────────────────────


def test_layout_03_default_current_scene():
    """TC-LAYOUT-03: current_scene defaults to CHAT."""
    mgr, *_ = _make_manager()
    assert mgr.current_scene == BroadcastScene.CHAT


# ── switch_to call order ─────────────────────────────────────────────────────


def test_layout_04_transition_in_called_first():
    """TC-LAYOUT-04: transition direction='in' is sent before obs_switch."""
    mgr, _, _, send_trans, obs_switch, _ = _make_manager()

    call_order = []
    send_trans.side_effect = lambda *a, **kw: call_order.append(
        "trans:" + kw.get("direction", "?")
    )
    obs_switch.side_effect = lambda _: call_order.append("obs") or True

    _run(mgr.switch_to(BroadcastScene.OPENING))

    assert call_order.index("trans:in") < call_order.index("obs")


def test_layout_05_obs_switch_called_with_obs_scene_name():
    """TC-LAYOUT-05: OBS scene name from config is forwarded to obs_switch."""
    mgr, _, _, _, obs_switch, _ = _make_manager()
    _run(mgr.switch_to(BroadcastScene.OPENING))
    obs_switch.assert_called_once_with("Opening")


def test_layout_06_send_scene_called_with_slug():
    """TC-LAYOUT-06: send_scene receives the string slug of the scene."""
    mgr, send_scene, _, _, _, _ = _make_manager()
    _run(mgr.switch_to(BroadcastScene.ENDING))
    send_scene.assert_called_once_with("ending")


def test_layout_07_send_layout_called():
    """TC-LAYOUT-07: send_layout is called with mode argument."""
    mgr, _, send_layout, _, _, _ = _make_manager()
    _run(mgr.switch_to(BroadcastScene.CHAT))
    send_layout.assert_called_once()
    args, kwargs = send_layout.call_args
    assert args[0] == "chat"


def test_layout_08_transition_out_called_last():
    """TC-LAYOUT-08: transition direction='out' is sent after send_scene."""
    mgr, send_scene, _, send_trans, _, _ = _make_manager()

    call_order = []
    send_scene.side_effect = lambda *a, **kw: call_order.append("scene")
    send_trans.side_effect = lambda *a, **kw: call_order.append(
        "trans:" + kw.get("direction", "?")
    )

    _run(mgr.switch_to(BroadcastScene.CHAT))

    assert call_order.index("scene") < call_order.index("trans:out")


def test_layout_09_current_scene_updated():
    """TC-LAYOUT-09: current_scene reflects the new scene after switch_to."""
    mgr, *_ = _make_manager()
    _run(mgr.switch_to(BroadcastScene.GAME))
    assert mgr.current_scene == BroadcastScene.GAME


def test_layout_10_switch_to_accepts_str():
    """TC-LAYOUT-10: switch_to accepts a plain string slug."""
    mgr, _, _, _, obs_switch, _ = _make_manager()
    result = _run(mgr.switch_to("ending"))
    assert result is True
    obs_switch.assert_called_once_with("Ending")


def test_layout_11_unknown_scene_returns_false():
    """TC-LAYOUT-11: switch_to returns False for unknown scene slugs."""
    mgr, _, _, send_trans, obs_switch, _ = _make_manager()
    result = _run(mgr.switch_to("unknown_scene"))
    assert result is False
    obs_switch.assert_not_called()


# ── Game frame update ────────────────────────────────────────────────────────


def test_layout_12_update_game_frame_sends_layout_only():
    """TC-LAYOUT-12: update_game_frame broadcasts layout without obs/scene calls."""
    mgr, send_scene, send_layout, _, obs_switch, _ = _make_manager()
    _run(mgr.update_game_frame(position="top-left", size="sm"))
    obs_switch.assert_not_called()
    send_scene.assert_not_called()
    send_layout.assert_called_once()
    _, kwargs = send_layout.call_args
    assert kwargs["position"] == "top-left"
    assert kwargs["size"] == "sm"


# ── configure_scene ──────────────────────────────────────────────────────────


def test_layout_13_configure_scene_overrides_obs_name():
    """TC-LAYOUT-13: configure_scene changes the OBS scene name used by switch_to."""
    mgr, _, _, _, obs_switch, _ = _make_manager()
    mgr.configure_scene(BroadcastScene.GAME, LayoutConfig(obs_scene="Minecraft"))
    _run(mgr.switch_to(BroadcastScene.GAME))
    obs_switch.assert_called_once_with("Minecraft")


# ── set_transition_duration ──────────────────────────────────────────────────


def test_layout_14_set_transition_duration_clamps_negative():
    """TC-LAYOUT-14: set_transition_duration clamps negative values to 0."""
    mgr, *_ = _make_manager()
    mgr.set_transition_duration(-100)
    assert mgr._transition_ms == 0


# ── background mode ──────────────────────────────────────────────────────────


def test_layout_15_chat_sends_transparent_bg():
    """TC-LAYOUT-15: switch_to CHAT sends background_mode=transparent."""
    mgr, _, _, _, _, send_bg = _make_manager()
    _run(mgr.switch_to(BroadcastScene.CHAT))
    send_bg.assert_called_once_with("transparent")


def test_layout_16_game_sends_transparent_bg():
    """TC-LAYOUT-16: switch_to GAME sends background_mode=transparent."""
    mgr, _, _, _, _, send_bg = _make_manager()
    _run(mgr.switch_to(BroadcastScene.GAME))
    send_bg.assert_called_once_with("transparent")


def test_layout_17_opening_sends_room_bg():
    """TC-LAYOUT-17: switch_to OPENING sends background_mode=room."""
    mgr, _, _, _, _, send_bg = _make_manager()
    _run(mgr.switch_to(BroadcastScene.OPENING))
    send_bg.assert_called_once_with("room")
