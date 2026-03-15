"""MessagePack binary WS transport tests.

TC-MSGPACK-01~05 / FR-PERF-01 / Issue #61
"""

from __future__ import annotations

import json

# ── TC-MSGPACK-01: msgpack is importable ─────────────────────────────────────


def test_msgpack_importable():
    """TC-MSGPACK-01: msgpack library must be installed and importable."""
    import msgpack  # noqa: PLC0415

    assert msgpack.__version__


# ── TC-MSGPACK-02: msgpack encodes smaller than JSON ─────────────────────────


def test_msgpack_smaller_than_json():
    """TC-MSGPACK-02: msgpack payload must be smaller than equivalent JSON."""
    import msgpack  # noqa: PLC0415

    from orchestrator.avatar_ws import AvatarMessage

    msg = AvatarMessage(
        cmd="avatar_update",
        params={
            "emotion": "happy",
            "gesture": "nod",
            "look_target": "camera",
            "mouth_open": 0.5,
        },
    )
    json_bytes = msg.to_json().encode("utf-8")
    pack_bytes = msgpack.packb(json.loads(msg.to_json()), use_bin_type=True)
    assert len(pack_bytes) < len(
        json_bytes
    ), f"msgpack ({len(pack_bytes)}) should be < json ({len(json_bytes)})"


# ── TC-MSGPACK-03: round-trip pack/unpack equals source dict ─────────────────


def test_msgpack_roundtrip():
    """TC-MSGPACK-03: msgpack pack → unpack must reproduce the original dict."""
    import msgpack  # noqa: PLC0415

    from orchestrator.avatar_ws import AvatarMessage

    msg = AvatarMessage(
        cmd="blend_shapes",
        params={"shapes": {"browDown_L": 0.8, "mouthSmile_L": 0.3}},
    )
    src = json.loads(msg.to_json())
    packed = msgpack.packb(src, use_bin_type=True)
    unpacked = msgpack.unpackb(packed, raw=False)
    assert unpacked == src


# ── TC-MSGPACK-04: USE_MSGPACK=1 sets _use_msgpack flag ─────────────────────


def test_sender_flag_enabled(monkeypatch):
    """TC-MSGPACK-04: AvatarWSSender._use_msgpack is True when USE_MSGPACK=1."""
    monkeypatch.setenv("USE_MSGPACK", "1")
    from orchestrator.avatar_ws import AvatarWSSender  # noqa: PLC0415

    sender = AvatarWSSender()
    assert sender._use_msgpack is True


# ── TC-MSGPACK-05: USE_MSGPACK=0 keeps _use_msgpack False ────────────────────


def test_sender_flag_disabled(monkeypatch):
    """TC-MSGPACK-05: AvatarWSSender._use_msgpack is False when USE_MSGPACK=0."""
    monkeypatch.setenv("USE_MSGPACK", "0")
    from orchestrator.avatar_ws import AvatarWSSender  # noqa: PLC0415

    sender = AvatarWSSender()
    assert sender._use_msgpack is False


# ── TC-MSGPACK-06: default (no env var) enables msgpack ─────────────────────


def test_sender_flag_default(monkeypatch):
    """TC-MSGPACK-06: AvatarWSSender._use_msgpack is True by default (FR-PERF-01)."""
    monkeypatch.delenv("USE_MSGPACK", raising=False)
    from orchestrator.avatar_ws import AvatarWSSender  # noqa: PLC0415

    sender = AvatarWSSender()
    assert sender._use_msgpack is True
