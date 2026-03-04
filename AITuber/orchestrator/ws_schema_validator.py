"""WebSocket message schema validator for Avatar WS protocol.

SRS refs: FR-WS-SCHEMA-01, FR-WS-SCHEMA-02.
Protocol:  protocols/avatar_ws.yml

FR-WS-SCHEMA-01: All messages must contain a 'cmd' field from the known command set.
FR-WS-SCHEMA-02: All required params must be present with correct types and value ranges.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

# ── Allowed value sets (mirrors avatar_ws.yml + Gesture enum in avatar_ws.py) ──

_EMOTIONS: frozenset[str] = frozenset(
    ["neutral", "happy", "thinking", "surprised", "sad", "angry", "panic"]
)

_GESTURES: frozenset[str] = frozenset(
    [
        "none", "nod", "shake", "wave", "cheer", "shrug", "facepalm",
        # Mixamo extended gestures (Gesture enum)
        "shy", "laugh", "surprised", "rejected", "sigh", "thankful",
        "sad_idle", "sad_kick", "thinking", "idle_alt",
        "sit_down", "sit_idle", "sit_laugh", "sit_clap",
        "sit_point", "sit_disbelief", "sit_kick",
    ]
)

_LOOK_TARGETS: frozenset[str] = frozenset(
    ["center", "chat", "camera", "down", "random"]
)

_AVATAR_EVENTS: frozenset[str] = frozenset(
    ["comment_read_start", "comment_read_end", "topic_switch", "break_start", "break_end"]
)

_VISEME_SETS: frozenset[str] = frozenset(["jp_basic_8"])

_JP_BASIC_8: frozenset[str] = frozenset(["sil", "a", "i", "u", "e", "o", "m", "fv"])

KNOWN_CMDS: frozenset[str] = frozenset(
    [
        "avatar_update",
        "avatar_event",
        "avatar_config",
        "avatar_reset",
        "avatar_viseme",
        "capabilities",
        "room_change",
    ]
)


# ── Result type ───────────────────────────────────────────────────────


@dataclass(frozen=True)
class WsValidationResult:
    """Immutable result from a schema validation check.

    Attributes:
        ok: True if validation passed.
        error_code: Short machine-readable identifier (None when ok=True).
        message: Human-readable description of the error (empty when ok=True).
    """

    ok: bool
    error_code: str | None = None
    message: str = ""

    @classmethod
    def valid(cls) -> WsValidationResult:
        """Return a passing result."""
        return cls(ok=True)

    @classmethod
    def error(cls, code: str, msg: str) -> WsValidationResult:
        """Return a failing result with code and human-readable message."""
        return cls(ok=False, error_code=code, message=msg)


# ── Low-level field checkers ──────────────────────────────────────────


def _check_range_01(params: dict, key: str) -> WsValidationResult | None:
    """Return error result if ``params[key]`` is missing or outside 0..1."""
    val = params.get(key)
    if val is None:
        return WsValidationResult.error("MISSING_PARAM", f"'{key}' is required")
    if not isinstance(val, (int, float)) or isinstance(val, bool):
        return WsValidationResult.error(
            "INVALID_PARAM_VALUE", f"'{key}' must be numeric, got {type(val).__name__}"
        )
    if not (0.0 <= float(val) <= 1.0):
        return WsValidationResult.error(
            "INVALID_PARAM_VALUE", f"'{key}' must be in 0..1, got {val}"
        )
    return None


def _check_enum(params: dict, key: str, allowed: frozenset[str]) -> WsValidationResult | None:
    """Return error result if ``params[key]`` is missing or not in ``allowed``."""
    val = params.get(key)
    if val is None:
        return WsValidationResult.error("MISSING_PARAM", f"'{key}' is required")
    if val not in allowed:
        return WsValidationResult.error(
            "INVALID_PARAM_VALUE", f"'{key}' value '{val}' not in allowed set"
        )
    return None


def _check_required_str(params: dict, key: str) -> WsValidationResult | None:
    """Return error result if ``params[key]`` is missing or not a string."""
    val = params.get(key)
    if val is None:
        return WsValidationResult.error("MISSING_PARAM", f"'{key}' is required")
    if not isinstance(val, str):
        return WsValidationResult.error(
            "INVALID_PARAM_VALUE", f"'{key}' must be a string, got {type(val).__name__}"
        )
    return None


# ── Per-command validators ────────────────────────────────────────────


def _validate_avatar_update(params: dict) -> WsValidationResult:
    for check in [
        _check_enum(params, "emotion", _EMOTIONS),
        _check_enum(params, "gesture", _GESTURES),
        _check_enum(params, "look_target", _LOOK_TARGETS),
        _check_range_01(params, "mouth_open"),
    ]:
        if check is not None:
            return check
    return WsValidationResult.valid()


def _validate_avatar_event(params: dict) -> WsValidationResult:
    for check in [
        _check_enum(params, "event", _AVATAR_EVENTS),
        _check_range_01(params, "intensity"),
    ]:
        if check is not None:
            return check
    return WsValidationResult.valid()


def _validate_avatar_config(params: dict) -> WsValidationResult:
    check = _check_required_str(params, "idle_motion")
    if check is not None:
        return check
    val = params.get("mouth_sensitivity")
    if val is None:
        return WsValidationResult.error("MISSING_PARAM", "'mouth_sensitivity' is required")
    if not isinstance(val, (int, float)) or isinstance(val, bool):
        return WsValidationResult.error(
            "INVALID_PARAM_VALUE", "'mouth_sensitivity' must be numeric"
        )
    val = params.get("blink_enabled")
    if val is None:
        return WsValidationResult.error("MISSING_PARAM", "'blink_enabled' is required")
    if not isinstance(val, bool):
        return WsValidationResult.error(
            "INVALID_PARAM_VALUE", "'blink_enabled' must be bool"
        )
    return WsValidationResult.valid()


def _validate_avatar_reset(params: dict) -> WsValidationResult:  # noqa: ARG001
    return WsValidationResult.valid()


def _validate_avatar_viseme(params: dict) -> WsValidationResult:
    for check in [
        _check_required_str(params, "utterance_id"),
        _check_enum(params, "viseme_set", _VISEME_SETS),
    ]:
        if check is not None:
            return check

    events = params.get("events")
    if events is None:
        return WsValidationResult.error("MISSING_PARAM", "'events' is required")
    if not isinstance(events, list):
        return WsValidationResult.error("INVALID_PARAM_VALUE", "'events' must be a list")

    for i, evt in enumerate(events):
        if not isinstance(evt, dict):
            return WsValidationResult.error(
                "INVALID_PARAM_VALUE", f"events[{i}] must be a dict"
            )
        if "t_ms" not in evt or not isinstance(evt["t_ms"], int) or isinstance(evt["t_ms"], bool):
            return WsValidationResult.error(
                "INVALID_PARAM_VALUE", f"events[{i}].t_ms must be int"
            )
        if "v" not in evt or evt["v"] not in _JP_BASIC_8:
            return WsValidationResult.error(
                "INVALID_PARAM_VALUE",
                f"events[{i}].v must be a jp_basic_8 viseme, got '{evt.get('v')}'",
            )

    cfms = params.get("crossfade_ms")
    if cfms is None:
        return WsValidationResult.error("MISSING_PARAM", "'crossfade_ms' is required")
    if not isinstance(cfms, int) or isinstance(cfms, bool):
        return WsValidationResult.error("INVALID_PARAM_VALUE", "'crossfade_ms' must be int")

    check = _check_range_01(params, "strength")
    if check is not None:
        return check

    return WsValidationResult.valid()


def _validate_capabilities(params: dict) -> WsValidationResult:  # noqa: ARG001
    # All capabilities fields are optional per spec
    return WsValidationResult.valid()


def _validate_room_change(params: dict) -> WsValidationResult:
    check = _check_required_str(params, "room_id")
    return check if check is not None else WsValidationResult.valid()


_CMD_VALIDATORS: dict[str, Any] = {
    "avatar_update": _validate_avatar_update,
    "avatar_event": _validate_avatar_event,
    "avatar_config": _validate_avatar_config,
    "avatar_reset": _validate_avatar_reset,
    "avatar_viseme": _validate_avatar_viseme,
    "capabilities": _validate_capabilities,
    "room_change": _validate_room_change,
}


# ── Public validator class ────────────────────────────────────────────


class WsSchemaValidator:
    """Validates Avatar WebSocket messages against the protocol schema.

    FR-WS-SCHEMA-01: All messages must have a 'cmd' from the known command set.
    FR-WS-SCHEMA-02: All required params must be present with correct types/values.

    Example::

        v = WsSchemaValidator()
        result = v.validate_json('{"cmd":"avatar_reset","params":{}}')
        assert result.ok
    """

    def validate(self, msg: dict[str, Any]) -> WsValidationResult:
        """Validate a parsed message dict.

        Args:
            msg: Parsed JSON message dict.

        Returns:
            WsValidationResult with ok=True on success, or error code+message.
        """
        if not isinstance(msg, dict):
            return WsValidationResult.error("INVALID_MSG", "Message must be a dict")

        cmd = msg.get("cmd")
        if cmd is None:
            return WsValidationResult.error(
                "MISSING_CMD", "Message missing required 'cmd' field"
            )

        if cmd not in KNOWN_CMDS:
            return WsValidationResult.error("UNKNOWN_CMD", f"Unknown cmd '{cmd}'")

        params = msg.get("params", {})
        if not isinstance(params, dict):
            return WsValidationResult.error(
                "INVALID_PARAM_VALUE", "'params' must be a dict"
            )

        return _CMD_VALIDATORS[cmd](params)

    def validate_json(self, raw: str) -> WsValidationResult:
        """Validate a raw JSON string.

        FR-WS-SCHEMA-01, FR-WS-SCHEMA-02.

        Args:
            raw: Raw JSON string to validate.

        Returns:
            WsValidationResult; error_code=INVALID_JSON if not parseable.
        """
        try:
            msg = json.loads(raw)
        except json.JSONDecodeError as exc:
            return WsValidationResult.error("INVALID_JSON", f"JSON parse error: {exc}")
        return self.validate(msg)
