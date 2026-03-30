"""Tests for WsSchemaValidator.

SRS refs: FR-WS-SCHEMA-01, FR-WS-SCHEMA-02.
TC-M9-01 〜 TC-M9-15
"""

from __future__ import annotations

import json

import pytest

from orchestrator.ws_schema_validator import (
    KNOWN_CMDS,
    WsSchemaValidator,
    WsValidationResult,
)


@pytest.fixture()
def validator() -> WsSchemaValidator:
    return WsSchemaValidator()


# ── Helpers ───────────────────────────────────────────────────────────


def _avatar_update(**kwargs) -> dict:
    base = {
        "cmd": "avatar_update",
        "params": {
            "emotion": "neutral",
            "gesture": "none",
            "look_target": "camera",
            "mouth_open": 0.0,
        },
    }
    base["params"].update(kwargs)
    return base


def _avatar_event(**kwargs) -> dict:
    base = {
        "cmd": "avatar_event",
        "params": {"event": "comment_read_start", "intensity": 1.0},
    }
    base["params"].update(kwargs)
    return base


def _avatar_config(**kwargs) -> dict:
    base = {
        "cmd": "avatar_config",
        "params": {
            "mouth_sensitivity": 1.0,
            "blink_enabled": True,
            "idle_motion": "default",
        },
    }
    base["params"].update(kwargs)
    return base


def _avatar_viseme(**kwargs) -> dict:
    base = {
        "cmd": "avatar_viseme",
        "params": {
            "utterance_id": "utt-001",
            "viseme_set": "jp_basic_8",
            "events": [{"t_ms": 0, "v": "a"}, {"t_ms": 100, "v": "sil"}],
            "crossfade_ms": 60,
            "strength": 1.0,
        },
    }
    base["params"].update(kwargs)
    return base


# ── WsValidationResult unit tests ────────────────────────────────────


class TestWsValidationResult:
    def test_valid_factory(self) -> None:
        r = WsValidationResult.valid()
        assert r.ok is True
        assert r.error_code is None
        assert r.message == ""

    def test_error_factory(self) -> None:
        r = WsValidationResult.error("MISSING_CMD", "no cmd")
        assert r.ok is False
        assert r.error_code == "MISSING_CMD"
        assert "cmd" in r.message


# ── TC-M9-01: avatar_update 正常系 ───────────────────────────────────


class TestAvatarUpdate:
    """TC-M9-01 〜 TC-M9-04"""

    def test_valid(self, validator: WsSchemaValidator) -> None:
        """TC-M9-01: avatar_update 正常系"""
        result = validator.validate(_avatar_update())
        assert result.ok

    def test_all_emotions(self, validator: WsSchemaValidator) -> None:
        for emotion in ["neutral", "happy", "thinking", "surprised", "sad", "angry", "panic"]:
            result = validator.validate(_avatar_update(emotion=emotion))
            assert result.ok, f"emotion={emotion} should be valid"

    def test_invalid_emotion(self, validator: WsSchemaValidator) -> None:
        """TC-M9-02: emotion 不正値 → INVALID_PARAM_VALUE"""
        result = validator.validate(_avatar_update(emotion="angry_bird"))
        assert not result.ok
        assert result.error_code == "INVALID_PARAM_VALUE"

    def test_mouth_open_out_of_range(self, validator: WsSchemaValidator) -> None:
        """TC-M9-03: mouth_open 範囲外 → INVALID_PARAM_VALUE"""
        result = validator.validate(_avatar_update(mouth_open=1.5))
        assert not result.ok
        assert result.error_code == "INVALID_PARAM_VALUE"

    def test_mouth_open_negative(self, validator: WsSchemaValidator) -> None:
        result = validator.validate(_avatar_update(mouth_open=-0.1))
        assert not result.ok
        assert result.error_code == "INVALID_PARAM_VALUE"

    def test_missing_gesture(self, validator: WsSchemaValidator) -> None:
        """TC-M9-04: gesture 欠損 → MISSING_PARAM"""
        msg = _avatar_update()
        del msg["params"]["gesture"]
        result = validator.validate(msg)
        assert not result.ok
        assert result.error_code == "MISSING_PARAM"

    def test_invalid_look_target(self, validator: WsSchemaValidator) -> None:
        result = validator.validate(_avatar_update(look_target="sideways"))
        assert not result.ok
        assert result.error_code == "INVALID_PARAM_VALUE"

    def test_extended_gesture(self, validator: WsSchemaValidator) -> None:
        """Mixamo 拡張ジェスチャーも valid"""
        for g in ["shy", "laugh", "sit_down", "sit_idle", "sit_clap"]:
            result = validator.validate(_avatar_update(gesture=g))
            assert result.ok, f"gesture={g} should be valid"

    def test_mouth_open_boundary_values(self, validator: WsSchemaValidator) -> None:
        assert validator.validate(_avatar_update(mouth_open=0.0)).ok
        assert validator.validate(_avatar_update(mouth_open=1.0)).ok


# ── TC-M9-05 / TC-M9-06: avatar_event ───────────────────────────────


class TestAvatarEvent:
    """TC-M9-05, TC-M9-06"""

    def test_valid(self, validator: WsSchemaValidator) -> None:
        """TC-M9-05: avatar_event 正常系"""
        result = validator.validate(_avatar_event())
        assert result.ok

    def test_invalid_event(self, validator: WsSchemaValidator) -> None:
        """TC-M9-06: event 不正値 → INVALID_PARAM_VALUE"""
        result = validator.validate(_avatar_event(event="unknown_event"))
        assert not result.ok
        assert result.error_code == "INVALID_PARAM_VALUE"

    def test_all_events(self, validator: WsSchemaValidator) -> None:
        events = [
            "comment_read_start",
            "comment_read_end",
            "topic_switch",
            "break_start",
            "break_end",
        ]
        for ev in events:
            assert validator.validate(_avatar_event(event=ev)).ok

    def test_intensity_out_of_range(self, validator: WsSchemaValidator) -> None:
        result = validator.validate(_avatar_event(intensity=2.0))
        assert not result.ok
        assert result.error_code == "INVALID_PARAM_VALUE"


# ── TC-M9-07: avatar_config ──────────────────────────────────────────


class TestAvatarConfig:
    """TC-M9-07"""

    def test_valid(self, validator: WsSchemaValidator) -> None:
        """TC-M9-07: avatar_config 正常系"""
        result = validator.validate(_avatar_config())
        assert result.ok

    def test_missing_blink_enabled(self, validator: WsSchemaValidator) -> None:
        msg = _avatar_config()
        del msg["params"]["blink_enabled"]
        result = validator.validate(msg)
        assert not result.ok
        assert result.error_code == "MISSING_PARAM"

    def test_blink_enabled_not_bool(self, validator: WsSchemaValidator) -> None:
        result = validator.validate(_avatar_config(blink_enabled="yes"))
        assert not result.ok
        assert result.error_code == "INVALID_PARAM_VALUE"

    def test_mouth_sensitivity_not_numeric(self, validator: WsSchemaValidator) -> None:
        result = validator.validate(_avatar_config(mouth_sensitivity="fast"))
        assert not result.ok
        assert result.error_code == "INVALID_PARAM_VALUE"


# ── TC-M9-08: avatar_reset ───────────────────────────────────────────


class TestAvatarReset:
    """TC-M9-08"""

    def test_valid_with_empty_params(self, validator: WsSchemaValidator) -> None:
        """TC-M9-08: avatar_reset 正常系"""
        result = validator.validate({"cmd": "avatar_reset", "params": {}})
        assert result.ok

    def test_valid_without_params_key(self, validator: WsSchemaValidator) -> None:
        """avatar_reset: params キーなしでも valid"""
        result = validator.validate({"cmd": "avatar_reset"})
        assert result.ok


# ── TC-M9-09 / TC-M9-10: avatar_viseme ──────────────────────────────


class TestAvatarViseme:
    """TC-M9-09, TC-M9-10"""

    def test_valid(self, validator: WsSchemaValidator) -> None:
        """TC-M9-09: avatar_viseme 正常系"""
        result = validator.validate(_avatar_viseme())
        assert result.ok

    def test_invalid_viseme_value(self, validator: WsSchemaValidator) -> None:
        """TC-M9-10: events[].v 不正値 → INVALID_PARAM_VALUE"""
        msg = _avatar_viseme()
        msg["params"]["events"] = [{"t_ms": 0, "v": "x_unknown"}]
        result = validator.validate(msg)
        assert not result.ok
        assert result.error_code == "INVALID_PARAM_VALUE"

    def test_unknown_viseme_set(self, validator: WsSchemaValidator) -> None:
        result = validator.validate(_avatar_viseme(viseme_set="en_us"))
        assert not result.ok
        assert result.error_code == "INVALID_PARAM_VALUE"

    def test_missing_events(self, validator: WsSchemaValidator) -> None:
        msg = _avatar_viseme()
        del msg["params"]["events"]
        result = validator.validate(msg)
        assert not result.ok
        assert result.error_code == "MISSING_PARAM"

    def test_event_missing_t_ms(self, validator: WsSchemaValidator) -> None:
        msg = _avatar_viseme()
        msg["params"]["events"] = [{"v": "a"}]
        result = validator.validate(msg)
        assert not result.ok
        assert result.error_code == "INVALID_PARAM_VALUE"

    def test_crossfade_ms_not_int(self, validator: WsSchemaValidator) -> None:
        msg = _avatar_viseme()
        msg["params"]["crossfade_ms"] = 60.5
        result = validator.validate(msg)
        assert not result.ok
        assert result.error_code == "INVALID_PARAM_VALUE"

    def test_all_jp_basic_8_visemes(self, validator: WsSchemaValidator) -> None:
        for v in ["sil", "a", "i", "u", "e", "o", "m", "fv"]:
            msg = _avatar_viseme()
            msg["params"]["events"] = [{"t_ms": 0, "v": v}]
            assert validator.validate(msg).ok, f"viseme '{v}' should be valid"


# ── TC-M9-11: room_change ────────────────────────────────────────────


class TestRoomChange:
    """TC-M9-11"""

    def test_valid(self, validator: WsSchemaValidator) -> None:
        """TC-M9-11: room_change 正常系"""
        result = validator.validate({"cmd": "room_change", "params": {"room_id": "alchemist"}})
        assert result.ok

    def test_missing_room_id(self, validator: WsSchemaValidator) -> None:
        result = validator.validate({"cmd": "room_change", "params": {}})
        assert not result.ok
        assert result.error_code == "MISSING_PARAM"


# ── TC-M9-12 / TC-M9-13: cmd field errors ────────────────────────────


class TestCmdErrors:
    """TC-M9-12, TC-M9-13"""

    def test_missing_cmd(self, validator: WsSchemaValidator) -> None:
        """TC-M9-12: MISSING_CMD"""
        result = validator.validate({"params": {}})
        assert not result.ok
        assert result.error_code == "MISSING_CMD"

    def test_unknown_cmd(self, validator: WsSchemaValidator) -> None:
        """TC-M9-13: UNKNOWN_CMD"""
        result = validator.validate({"cmd": "avatar_fly", "params": {}})
        assert not result.ok
        assert result.error_code == "UNKNOWN_CMD"

    def test_not_a_dict(self, validator: WsSchemaValidator) -> None:
        result = validator.validate("not a dict")  # type: ignore[arg-type]
        assert not result.ok
        assert result.error_code == "INVALID_MSG"

    def test_params_not_dict(self, validator: WsSchemaValidator) -> None:
        result = validator.validate({"cmd": "avatar_reset", "params": "bad"})
        assert not result.ok
        assert result.error_code == "INVALID_PARAM_VALUE"


# ── TC-M9-14 / TC-M9-15: validate_json ──────────────────────────────


class TestValidateJson:
    """TC-M9-14, TC-M9-15"""

    def test_valid_json(self, validator: WsSchemaValidator) -> None:
        """TC-M9-14: validate_json 正常 JSON"""
        raw = json.dumps({"cmd": "avatar_reset", "params": {}})
        result = validator.validate_json(raw)
        assert result.ok

    def test_invalid_json(self, validator: WsSchemaValidator) -> None:
        """TC-M9-15: validate_json 不正 JSON → INVALID_JSON"""
        result = validator.validate_json("{not valid json")
        assert not result.ok
        assert result.error_code == "INVALID_JSON"

    def test_validate_json_full_avatar_update(self, validator: WsSchemaValidator) -> None:
        raw = json.dumps(
            {
                "cmd": "avatar_update",
                "params": {
                    "emotion": "happy",
                    "gesture": "wave",
                    "look_target": "chat",
                    "mouth_open": 0.5,
                },
            }
        )
        assert validator.validate_json(raw).ok

    def test_validate_json_with_extra_fields(self, validator: WsSchemaValidator) -> None:
        """id/ts 等の common_fields があっても valid"""
        raw = json.dumps(
            {
                "id": "abc123",
                "ts": "2026-01-01T00:00:00.000Z",
                "cmd": "avatar_reset",
                "params": {},
            }
        )
        assert validator.validate_json(raw).ok


# ── KNOWN_CMDS coverage ──────────────────────────────────────────────


class TestKnownCmds:
    def test_known_cmds_complete(self) -> None:
        """KNOWN_CMDS should cover all protocol commands."""
        expected = {
            "avatar_update",
            "avatar_event",
            "avatar_config",
            "avatar_reset",
            "avatar_viseme",
            "avatar_intent",
            "capabilities",
            "room_change",
            "zone_change",
            "behavior_start",
            "appearance_update",
            "set_background_mode",  # FR-BCAST-BG-01
            "a2f_audio",
            "a2f_chunk",
            "a2f_stream_close",
            "a2g_chunk",
            "a2g_stream_close",
            "game_action",  # FR-GAME-01
        }
        assert expected == set(KNOWN_CMDS)

    def test_zone_change_valid(self, validator: WsSchemaValidator) -> None:
        result = validator.validate({"cmd": "zone_change", "params": {"zone_id": "pc_area"}})
        assert result.ok

    def test_zone_change_missing_zone_id(self, validator: WsSchemaValidator) -> None:
        result = validator.validate({"cmd": "zone_change", "params": {}})
        assert not result.ok

    # ── a2g_chunk / a2g_stream_close (FR-GESTURE-AUTO-01) ─────────────

    def test_a2g_chunk_valid(self, validator: WsSchemaValidator) -> None:
        result = validator.validate(
            {
                "cmd": "a2g_chunk",
                "params": {
                    "pcm_b64": "AAAA",
                    "format": "int16",
                    "sample_rate": 16000,
                    "is_first": False,
                },
            }
        )
        assert result.ok

    def test_a2g_chunk_missing_pcm_b64(self, validator: WsSchemaValidator) -> None:
        result = validator.validate({"cmd": "a2g_chunk", "params": {}})
        assert not result.ok
        assert result.error_code == "MISSING_PARAM"

    def test_a2g_chunk_invalid_format(self, validator: WsSchemaValidator) -> None:
        result = validator.validate(
            {
                "cmd": "a2g_chunk",
                "params": {"pcm_b64": "AAAA", "format": "mp3"},
            }
        )
        assert not result.ok

    def test_a2g_stream_close_valid(self, validator: WsSchemaValidator) -> None:
        result = validator.validate({"cmd": "a2g_stream_close", "params": {}})
        assert result.ok

    def test_capabilities_is_valid(self, validator: WsSchemaValidator) -> None:
        result = validator.validate(
            {
                "cmd": "capabilities",
                "params": {"mouth_open": True, "viseme": True, "viseme_set": ["jp_basic_8"]},
            }
        )
        assert result.ok

    def test_capabilities_empty_params_is_valid(self, validator: WsSchemaValidator) -> None:
        """capabilities: all fields optional"""
        result = validator.validate({"cmd": "capabilities", "params": {}})
        assert result.ok

    # ── appearance_update (FR-SHADER-02) ───────────────────────────────

    def test_appearance_update_shader_mode_scss(self, validator: WsSchemaValidator) -> None:
        """TC-APPEARANCE-01: appearance_update shader_mode=scss 正常系"""
        result = validator.validate(
            {"cmd": "appearance_update", "params": {"shader_mode": "scss"}}
        )
        assert result.ok

    def test_appearance_update_all_shader_modes(self, validator: WsSchemaValidator) -> None:
        """TC-APPEARANCE-02: 全shader_mode 正常系.

        Covers toon/lit/scss/crt/sketch/watercolor/wireframe/manga.
        """
        for mode in (
            "toon",
            "lit",
            "scss",
            "crt",
            "sketch",
            "watercolor",
            "wireframe",
            "manga",
        ):
            result = validator.validate(
                {"cmd": "appearance_update", "params": {"shader_mode": mode}}
            )
            assert result.ok, f"Expected ok for shader_mode={mode}"

    def test_appearance_update_invalid_shader_mode(self, validator: WsSchemaValidator) -> None:
        """TC-APPEARANCE-03: 未知の shader_mode → INVALID_PARAM_VALUE"""
        result = validator.validate(
            {"cmd": "appearance_update", "params": {"shader_mode": "mtoon"}}
        )
        assert not result.ok
        assert result.error_code == "INVALID_PARAM_VALUE"

    def test_appearance_update_no_fields(self, validator: WsSchemaValidator) -> None:
        """TC-APPEARANCE-04: パラメータが一つもない → MISSING_PARAM"""
        result = validator.validate({"cmd": "appearance_update", "params": {}})
        assert not result.ok
        assert result.error_code == "MISSING_PARAM"

    def test_appearance_update_costume_and_hair(self, validator: WsSchemaValidator) -> None:
        """TC-APPEARANCE-05: costume + hair のみも OK (shader_mode なし)"""
        result = validator.validate(
            {"cmd": "appearance_update", "params": {"costume": "casual", "hair": "ponytail"}}
        )
        assert result.ok

    # ── set_background_mode (FR-BCAST-BG-01) ───────────────────────────

    def test_set_background_mode_transparent(self, validator: WsSchemaValidator) -> None:
        """set_background_mode mode=transparent 正常系"""
        result = validator.validate(
            {"cmd": "set_background_mode", "params": {"mode": "transparent"}}
        )
        assert result.ok

    def test_set_background_mode_room(self, validator: WsSchemaValidator) -> None:
        """set_background_mode mode=room 正常系"""
        result = validator.validate({"cmd": "set_background_mode", "params": {"mode": "room"}})
        assert result.ok

    def test_set_background_mode_invalid(self, validator: WsSchemaValidator) -> None:
        """set_background_mode 不正値 → INVALID_PARAM_VALUE"""
        result = validator.validate({"cmd": "set_background_mode", "params": {"mode": "blue"}})
        assert not result.ok
        assert result.error_code == "INVALID_PARAM_VALUE"

    def test_set_background_mode_missing(self, validator: WsSchemaValidator) -> None:
        """set_background_mode mode 欠損 → MISSING_PARAM"""
        result = validator.validate({"cmd": "set_background_mode", "params": {}})
        assert not result.ok
        assert result.error_code == "MISSING_PARAM"
