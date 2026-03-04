"""E2E dry-run tests for pre-broadcast sanity check.

TC-E2E-01 : VOICEVOX HTTP :50021 — /speakers 応答確認
TC-E2E-02 : VOICEVOX speaker_id=47 (ナースロボ＿タイプＴ) 存在確認
TC-E2E-03 : Overlay WS :31901 — 接続＋chat イベント送信確認
TC-E2E-04 : yuia キャラクター設定確認 (speaker_id=47, yui.a name)  ← always-green
TC-E2E-05 : Unity WS :31900 — 接続確認
TC-E2E-06 : Unity WS :31900 — avatar_update コマンド往復確認
TC-E2E-07 : Overlay WS :31901 — subtitle イベント送信確認

サービス依存テスト (TC-E2E-01〜03, 05〜07) はサービス未起動時に自動スキップ → CI 常時グリーン。
手動配信前ドライランとして実行: pytest tests/test_e2e_dryrun.py -v -m e2e

FR-E2E-01: 配信前に全コンポーネントが疎通していることを確認できる。
"""

import asyncio
import json
import socket

import pytest
import pytest_asyncio  # noqa: F401 (ensures asyncio_mode=auto)

# ---------------------------------------------------------------------------
# Service availability helpers
# ---------------------------------------------------------------------------

VOICEVOX_URL = "http://127.0.0.1:50021"
OVERLAY_WS_URL = "ws://127.0.0.1:31901"
UNITY_WS_URL = "ws://127.0.0.1:31900"


def _tcp_reachable(host: str, port: int, timeout: float = 1.0) -> bool:
    """Return True if a TCP connection to host:port can be established."""
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def _voicevox_available() -> bool:
    return _tcp_reachable("127.0.0.1", 50021)


def _overlay_available() -> bool:
    return _tcp_reachable("127.0.0.1", 31901)


def _unity_ws_available() -> bool:
    return _tcp_reachable("127.0.0.1", 31900)


# ---------------------------------------------------------------------------
# TC-E2E-01 : VOICEVOX HTTP /speakers 応答
# ---------------------------------------------------------------------------

@pytest.mark.e2e
@pytest.mark.skipif(not _voicevox_available(), reason="VOICEVOX not running on :50021")
async def test_voicevox_speakers_endpoint():
    """TC-E2E-01: VOICEVOX /speakers が 200 を返す。"""
    import aiohttp

    async with aiohttp.ClientSession() as session:
        async with session.get(f"{VOICEVOX_URL}/speakers", timeout=aiohttp.ClientTimeout(total=5)) as resp:
            assert resp.status == 200, f"/speakers returned {resp.status}"
            speakers = await resp.json()
            assert isinstance(speakers, list) and len(speakers) > 0, "Empty speakers list"


# ---------------------------------------------------------------------------
# TC-E2E-02 : speaker_id=47 存在確認
# ---------------------------------------------------------------------------

@pytest.mark.e2e
@pytest.mark.skipif(not _voicevox_available(), reason="VOICEVOX not running on :50021")
async def test_voicevox_speaker_47_exists():
    """TC-E2E-02: speaker_id=47 (ナースロボ＿タイプＴ) が /speakers に含まれる。"""
    import aiohttp

    async with aiohttp.ClientSession() as session:
        async with session.get(f"{VOICEVOX_URL}/speakers", timeout=aiohttp.ClientTimeout(total=5)) as resp:
            speakers = await resp.json()

    # Flatten all style ids
    all_ids = {
        style["id"]
        for speaker in speakers
        for style in speaker.get("styles", [])
    }
    assert 47 in all_ids, (
        f"speaker_id=47 not found in VOICEVOX. available style ids (sample): {sorted(all_ids)[:20]}"
    )


# ---------------------------------------------------------------------------
# TC-E2E-03 : Overlay WS :31901 — chat イベント送信
# ---------------------------------------------------------------------------

@pytest.mark.e2e
@pytest.mark.skipif(not _overlay_available(), reason="Overlay WS not running on :31901")
async def test_overlay_chat_event():
    """TC-E2E-03: Overlay WS :31901 に chat イベントを送信できる。"""
    import websockets

    async with websockets.connect(OVERLAY_WS_URL, open_timeout=3) as ws:
        event = json.dumps({"type": "chat", "payload": {"user": "DrRun", "message": "E2E check"}})
        await ws.send(event)
        # overlay_server は broadcast のみでエコーしないため送信成功で OK
    # Connection closed cleanly == pass


# ---------------------------------------------------------------------------
# TC-E2E-04 : yuia 設定確認 (サービス不要 — always green)
# ---------------------------------------------------------------------------

@pytest.mark.e2e
def test_yuia_character_config():
    """TC-E2E-04: yuia.yml から speaker_id=47 と名前 YUI.A が読み込める。"""
    import sys
    import os

    # Ensure orchestrator package is importable
    orchestrator_root = os.path.join(os.path.dirname(__file__), "..")
    if orchestrator_root not in sys.path:
        sys.path.insert(0, orchestrator_root)

    from orchestrator.character import load_character

    char = load_character("yuia")
    assert char.voice.speaker_id == 47, f"Expected voice.speaker_id=47, got {char.voice.speaker_id}"
    assert "yui" in char.name.lower() or "YUI" in char.name, (
        f"Expected 'YUI' in character name, got '{char.name}'"
    )
    assert len(char.idle_topics) >= 5, f"Expected >=5 idle_topics, got {len(char.idle_topics)}"
    assert char.system_prompt, "system_prompt must not be empty"


# ---------------------------------------------------------------------------
# TC-E2E-05 : Unity WS :31900 — 接続確認
# ---------------------------------------------------------------------------

@pytest.mark.e2e
@pytest.mark.skipif(not _unity_ws_available(), reason="Unity WS not running on :31900")
async def test_unity_ws_connect():
    """TC-E2E-05: Unity WS :31900 に接続できる。"""
    import websockets

    async with websockets.connect(UNITY_WS_URL, open_timeout=5) as ws:
        assert ws.open, "WebSocket connection to Unity :31900 not open"


# ---------------------------------------------------------------------------
# TC-E2E-06 : Unity WS :31900 — avatar_update 往路送信
# ---------------------------------------------------------------------------

@pytest.mark.e2e
@pytest.mark.skipif(not _unity_ws_available(), reason="Unity WS not running on :31900")
async def test_unity_ws_avatar_update():
    """TC-E2E-06: Unity WS に avatar_update を送信してもエラーにならない。"""
    import websockets

    async with websockets.connect(UNITY_WS_URL, open_timeout=5) as ws:
        payload = json.dumps({
            "type": "avatar_update",
            "payload": {
                "emotion": "joy",
                "gesture": "nod",
                "mouth_open": 0.0,
                "look_target": "camera",
            },
        })
        await ws.send(payload)
        # Wait briefly for any immediate error response
        try:
            response = await asyncio.wait_for(ws.recv(), timeout=2.0)
            data = json.loads(response)
            # If Unity sends back an error, test fails
            assert data.get("type") != "error", f"Unity returned error: {data}"
        except asyncio.TimeoutError:
            pass  # No response in 2s is acceptable (thin client)


# ---------------------------------------------------------------------------
# TC-E2E-07 : Overlay WS :31901 — subtitle イベント送信
# ---------------------------------------------------------------------------

@pytest.mark.e2e
@pytest.mark.skipif(not _overlay_available(), reason="Overlay WS not running on :31901")
async def test_overlay_subtitle_event():
    """TC-E2E-07: Overlay WS :31901 に subtitle イベントを送信できる。"""
    import websockets

    async with websockets.connect(OVERLAY_WS_URL, open_timeout=3) as ws:
        event = json.dumps({
            "type": "subtitle",
            "payload": {"text": "E2E ドライラン確認中…", "speaker": "YUI.A"},
        })
        await ws.send(event)
    # Clean close == pass
