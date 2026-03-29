"""Tests for orchestrator.tha_avatar_bridge.

Issue #85: THA アバターブリッジ
Issue #89: 感情→THA 表情マッピング
TC-THA-BRIDGE-01 to TC-THA-BRIDGE-10.
"""

from __future__ import annotations

import pytest

from orchestrator.avatar_ws import Emotion, Gesture
from orchestrator.tha_avatar_bridge import (
    PARAM_INDEX,
    POSE_DIM,
    THAAvatarBridge,
    _make_default_pose,
)


@pytest.fixture()
def bridge(tmp_path):
    """YAML 付きブリッジ。実際の config/tha_emotion_map.yml を使用."""
    from pathlib import Path

    config_path = Path(__file__).resolve().parent.parent / "config" / "tha_emotion_map.yml"
    if config_path.exists():
        return THAAvatarBridge(config_path)
    # CI 用フォールバック: minimal YAML
    minimal = tmp_path / "map.yml"
    minimal.write_text(
        "happy:\n  eyebrow_happy: 0.7\n"
        "visemes:\n  a:\n    mouth_aaa: 1.0\n"
        "gestures:\n  nod:\n    head_x: 0.15\n",
        encoding="utf-8",
    )
    return THAAvatarBridge(minimal)


class TestDefaultPose:
    """TC-THA-BRIDGE-01: デフォルトポーズベクターの検証."""

    def test_dimension(self):
        pose = _make_default_pose()
        assert len(pose) == POSE_DIM == 45

    def test_mouth_aaa_default(self):
        pose = _make_default_pose()
        assert pose[PARAM_INDEX["mouth_aaa"]] == 1.0

    def test_others_zero(self):
        pose = _make_default_pose()
        for name, idx in PARAM_INDEX.items():
            if name == "mouth_aaa":
                continue
            assert pose[idx] == 0.0, f"{name} should be 0.0"


class TestEmotionToPose:
    """TC-THA-BRIDGE-02: 感情→ポーズ変換."""

    def test_happy_sets_eyebrow(self, bridge: THAAvatarBridge):
        pose = bridge.emotion_to_pose(Emotion.HAPPY)
        assert pose[PARAM_INDEX["eyebrow_happy_left"]] > 0.0
        assert pose[PARAM_INDEX["eyebrow_happy_right"]] > 0.0

    def test_neutral_is_close_to_default(self, bridge: THAAvatarBridge):
        pose = bridge.emotion_to_pose(Emotion.NEUTRAL)
        default = _make_default_pose()
        # neutral は breathing のみ変わるかもしれないが、大きな差はない
        diff = sum(abs(a - b) for a, b in zip(pose, default, strict=True))
        assert diff < 5.0

    def test_all_emotions_produce_valid_vectors(self, bridge: THAAvatarBridge):
        """TC-THA-BRIDGE-03: 全感情が 45 次元を返す."""
        for emotion in Emotion:
            pose = bridge.emotion_to_pose(emotion)
            assert len(pose) == POSE_DIM

    def test_string_emotion_accepted(self, bridge: THAAvatarBridge):
        pose = bridge.emotion_to_pose("happy")
        assert len(pose) == POSE_DIM

    def test_unknown_emotion_returns_default(self, bridge: THAAvatarBridge):
        pose = bridge.emotion_to_pose("nonexistent")
        default = _make_default_pose()
        assert pose == default


class TestVisemeToPose:
    """TC-THA-BRIDGE-04: Viseme→ポーズ変換."""

    def test_viseme_a(self, bridge: THAAvatarBridge):
        pose = bridge.viseme_to_pose("a", intensity=1.0)
        assert pose[PARAM_INDEX["mouth_aaa"]] == 1.0

    def test_viseme_sil_closes_mouth(self, bridge: THAAvatarBridge):
        pose = bridge.viseme_to_pose("sil", intensity=1.0)
        assert pose[PARAM_INDEX["mouth_aaa"]] == 0.0

    def test_intensity_scaling(self, bridge: THAAvatarBridge):
        full = bridge.viseme_to_pose("a", intensity=1.0)
        half = bridge.viseme_to_pose("a", intensity=0.5)
        # mouth_aaa: full=1.0, half=0.5
        assert full[PARAM_INDEX["mouth_aaa"]] >= half[PARAM_INDEX["mouth_aaa"]]

    def test_intensity_clamped(self, bridge: THAAvatarBridge):
        """TC-THA-BRIDGE-05: intensity > 1.0 はクランプされる."""
        pose = bridge.viseme_to_pose("a", intensity=2.0)
        assert pose[PARAM_INDEX["mouth_aaa"]] <= 1.0

    def test_all_visemes_produce_valid(self, bridge: THAAvatarBridge):
        for v in ["a", "i", "u", "e", "o", "sil", "m", "fv"]:
            pose = bridge.viseme_to_pose(v)
            assert len(pose) == POSE_DIM


class TestGestureToPose:
    """TC-THA-BRIDGE-06: ジェスチャー→ポーズ変換."""

    def test_nod_uses_head_x(self, bridge: THAAvatarBridge):
        pose = bridge.gesture_to_pose(Gesture.NOD)
        assert pose[PARAM_INDEX["head_x"]] != 0.0

    def test_none_gesture_returns_default_like(self, bridge: THAAvatarBridge):
        pose = bridge.gesture_to_pose(Gesture.NONE)
        default = _make_default_pose()
        assert pose == default

    def test_string_gesture_accepted(self, bridge: THAAvatarBridge):
        pose = bridge.gesture_to_pose("bow")
        assert len(pose) == POSE_DIM


class TestComposePose:
    """TC-THA-BRIDGE-07: 合成ポーズ."""

    def test_compose_returns_correct_dim(self, bridge: THAAvatarBridge):
        pose = bridge.compose_pose(
            emotion=Emotion.HAPPY,
            viseme="a",
            viseme_intensity=0.8,
            gesture=Gesture.NOD,
            breathing=0.6,
        )
        assert len(pose) == POSE_DIM

    def test_breathing_set(self, bridge: THAAvatarBridge):
        """TC-THA-BRIDGE-08: breathing パラメータが反映される."""
        pose = bridge.compose_pose(breathing=0.7)
        assert pose[PARAM_INDEX["breathing"]] == pytest.approx(0.7)

    def test_viseme_overrides_emotion_mouth(self, bridge: THAAvatarBridge):
        """TC-THA-BRIDGE-09: viseme が感情の mouth 設定を上書き."""
        pose = bridge.compose_pose(
            emotion=Emotion.HAPPY,
            viseme="a",
            viseme_intensity=1.0,
        )
        # viseme "a" → mouth_aaa=1.0 (感情の mouth 設定に関わらず)
        assert pose[PARAM_INDEX["mouth_aaa"]] == 1.0

    def test_gesture_blends_with_emotion(self, bridge: THAAvatarBridge):
        """TC-THA-BRIDGE-10: gesture が感情とブレンドされる."""
        emotion_only = bridge.compose_pose(emotion=Emotion.HAPPY, gesture=Gesture.NONE)
        with_gesture = bridge.compose_pose(emotion=Emotion.HAPPY, gesture=Gesture.NOD)
        # head_x が変わるはず
        assert emotion_only[PARAM_INDEX["head_x"]] != with_gesture[PARAM_INDEX["head_x"]]


class TestParamIndex:
    """TC-THA-BRIDGE-PARAM: パラメータインデックスの整合性."""

    def test_all_indices_in_range(self):
        for name, idx in PARAM_INDEX.items():
            assert 0 <= idx < POSE_DIM, f"{name} index {idx} out of range"

    def test_no_duplicate_indices(self):
        indices = list(PARAM_INDEX.values())
        assert len(indices) == len(set(indices)), "Duplicate indices found"

    def test_all_45_slots_covered(self):
        """全 45 スロットがマッピングされている."""
        covered = set(PARAM_INDEX.values())
        assert covered == set(range(POSE_DIM))


class TestMissingConfig:
    """YAML が見つからない場合の安全なフォールバック."""

    def test_missing_yaml_returns_defaults(self, tmp_path):
        bridge = THAAvatarBridge(tmp_path / "nonexistent.yml")
        pose = bridge.compose_pose(emotion=Emotion.HAPPY)
        assert len(pose) == POSE_DIM
        assert pose[PARAM_INDEX["breathing"]] == 0.5  # compose default
