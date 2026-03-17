"""Tests for GameContextAdapter (FR-GAME-01).

TC-GCA-01: get_context_snippet returns '[game: no data]' when no state
TC-GCA-02: get_context_snippet formats HP/pos/hostiles/time correctly (day)
TC-GCA-03: get_context_snippet formats night correctly
TC-GCA-04: _on_message with game_state updates internal state
TC-GCA-05: _on_message with unknown type is silently ignored
TC-GCA-06: send_action returns False when not connected
TC-GCA-07: send_action returns True and calls ws.send when connected
TC-GCA-08: close() sets _running=False
TC-GCA-09: _on_message with malformed payload is handled
TC-GCA-10: state property returns shallow copy
"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock

import pytest

from orchestrator.config import GameBridgeConfig
from orchestrator.game_context_adapter import GameContextAdapter


@pytest.fixture
def cfg() -> GameBridgeConfig:
    return GameBridgeConfig(host="127.0.0.1", port=31901)


@pytest.fixture
def adapter(cfg: GameBridgeConfig) -> GameContextAdapter:
    return GameContextAdapter(cfg)


# ── TC-GCA-01: no data ───────────────────────────────────────────────────────


def test_context_snippet_no_data(adapter: GameContextAdapter) -> None:
    """TC-GCA-01"""
    assert adapter.get_context_snippet() == "[game: no data]"


# ── TC-GCA-02: snippet with day + hostiles ───────────────────────────────────


def test_context_snippet_day(adapter: GameContextAdapter) -> None:
    """TC-GCA-02"""
    adapter._state = {
        "health": 16,
        "max_health": 20,
        "pos": {"x": 100.0, "y": 64.0, "z": -200.0},
        "nearby_entities": [
            {"type": "hostile", "distance": 5.0},
            {"type": "passive", "distance": 3.0},
        ],
        "time": 6000,
    }
    snippet = adapter.get_context_snippet()
    assert "HP=16/20" in snippet
    assert "hostiles=1" in snippet
    assert "time=day" in snippet
    assert "pos=(100,-200)" in snippet


# ── TC-GCA-03: snippet with night ────────────────────────────────────────────


def test_context_snippet_night(adapter: GameContextAdapter) -> None:
    """TC-GCA-03"""
    adapter._state = {
        "health": 20,
        "max_health": 20,
        "pos": {"x": 0.0, "y": 64.0, "z": 0.0},
        "nearby_entities": [],
        "time": 13001,
    }
    snippet = adapter.get_context_snippet()
    assert "time=night" in snippet


# ── TC-GCA-04: _on_message updates state ─────────────────────────────────────


def test_on_message_game_state_updates_state(adapter: GameContextAdapter) -> None:
    """TC-GCA-04"""
    msg = {
        "type": "game_state",
        "payload": {"health": 10, "max_health": 20, "nearby_entities": []},
    }
    adapter._on_message(msg)
    assert adapter._state["health"] == 10


# ── TC-GCA-05: unknown message type silently ignored ─────────────────────────


def test_on_message_unknown_type(adapter: GameContextAdapter) -> None:
    """TC-GCA-05"""
    adapter._on_message({"type": "something_new", "data": 42})
    assert adapter._state == {}  # state unchanged


# ── TC-GCA-06: send_action not connected ─────────────────────────────────────


@pytest.mark.asyncio
async def test_send_action_not_connected(adapter: GameContextAdapter) -> None:
    """TC-GCA-06"""
    result = await adapter.send_action({"type": "move", "args": {}})
    assert result is False


# ── TC-GCA-07: send_action connected ─────────────────────────────────────────


@pytest.mark.asyncio
async def test_send_action_connected(adapter: GameContextAdapter) -> None:
    """TC-GCA-07"""
    mock_ws = AsyncMock()
    adapter._ws = mock_ws
    cmd = {"type": "attack", "args": {"target": "nearest_hostile"}}
    result = await adapter.send_action(cmd)
    assert result is True
    mock_ws.send.assert_awaited_once_with(json.dumps(cmd))


# ── TC-GCA-08: close() stops reconnection ────────────────────────────────────


def test_close_sets_running_false(adapter: GameContextAdapter) -> None:
    """TC-GCA-08"""
    adapter._running = True
    adapter.close()
    assert adapter._running is False


# ── TC-GCA-09: _on_message without payload key ───────────────────────────────


def test_on_message_game_state_no_payload(adapter: GameContextAdapter) -> None:
    """TC-GCA-09: When payload is absent, falls back to full message dict."""
    msg = {"type": "game_state", "health": 14, "max_health": 20, "nearby_entities": []}
    adapter._on_message(msg)
    # The whole message becomes the state when payload is missing
    assert adapter._state.get("health") == 14


# ── TC-GCA-10: state property is a copy ──────────────────────────────────────


def test_state_property_is_copy(adapter: GameContextAdapter) -> None:
    """TC-GCA-10"""
    adapter._state = {"health": 20}
    s = adapter.state
    s["health"] = 0
    assert adapter._state["health"] == 20  # original unchanged
