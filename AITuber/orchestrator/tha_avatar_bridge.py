"""THA4 Avatar Bridge — Emotion/Gesture/Viseme を 45 次元ポーズベクターに変換.

Issue #85: THA アバターブリッジモジュール
Issue #89: 感情→THA 表情マッピング
SRS refs: FR-A7-01 (avatar control), FR-LIPSYNC-01.

THA4 の 45 パラメータ仕様 (PoseParameters):
  EYEBROW 0-11, EYE 12-23, IRIS_MORPH 24-25,
  MOUTH 26-36, IRIS_ROTATION 37-38, FACE_ROTATION 39-41,
  BODY_ROTATION 42-43, BREATHING 44.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import yaml

from orchestrator.avatar_ws import Emotion, Gesture

logger = logging.getLogger(__name__)

# ── THA4 パラメータインデックス定義 (45 params) ──────────────────

# fmt: off
PARAM_INDEX: dict[str, int] = {
    # EYEBROW (0-11)
    "eyebrow_troubled_left":  0,  "eyebrow_troubled_right":  1,
    "eyebrow_angry_left":     2,  "eyebrow_angry_right":     3,
    "eyebrow_lowered_left":   4,  "eyebrow_lowered_right":   5,
    "eyebrow_raised_left":    6,  "eyebrow_raised_right":    7,
    "eyebrow_happy_left":     8,  "eyebrow_happy_right":     9,
    "eyebrow_serious_left":  10,  "eyebrow_serious_right":  11,
    # EYE (12-23)
    "eye_wink_left":         12,  "eye_wink_right":         13,
    "eye_happy_wink_left":   14,  "eye_happy_wink_right":   15,
    "eye_surprised_left":    16,  "eye_surprised_right":    17,
    "eye_relaxed_left":      18,  "eye_relaxed_right":      19,
    "eye_unimpressed_left":  20,  "eye_unimpressed_right":  21,
    "eye_raised_lower_eyelid_left":  22,  "eye_raised_lower_eyelid_right":  23,
    # IRIS_MORPH (24-25)
    "iris_small_left":       24,  "iris_small_right":       25,
    # MOUTH (26-36)
    "mouth_aaa":             26,
    "mouth_iii":             27,
    "mouth_uuu":             28,
    "mouth_eee":             29,
    "mouth_ooo":             30,
    "mouth_delta":           31,
    "mouth_lowered_corner_left":  32,  "mouth_lowered_corner_right":  33,
    "mouth_raised_corner_left":   34,  "mouth_raised_corner_right":   35,
    "mouth_smirk":           36,
    # IRIS_ROTATION (37-38)
    "iris_rotation_x":       37,
    "iris_rotation_y":       38,
    # FACE_ROTATION (39-41)
    "head_x":                39,
    "head_y":                40,
    "neck_z":                41,
    # BODY_ROTATION (42-43)
    "body_y":                42,
    "body_z":                43,
    # BREATHING (44)
    "breathing":             44,
}
# fmt: on

POSE_DIM = 45
_DEFAULT_MOUTH_AAA = 1.0  # THA4 のデフォルト: mouth_aaa=1.0 (閉口)

# 左右対称パラメータ: サフィックスなし名 → (_left, _right)
_SYMMETRIC_PARAMS: dict[str, tuple[str, str]] = {}
_seen_bases: set[str] = set()
for name in PARAM_INDEX:
    if name.endswith("_left"):
        base = name.removesuffix("_left")
        right = f"{base}_right"
        if right in PARAM_INDEX:
            _SYMMETRIC_PARAMS[base] = (name, right)


def _make_default_pose() -> list[float]:
    """45 次元のデフォルトポーズベクター (THA4 基準)."""
    pose = [0.0] * POSE_DIM
    pose[PARAM_INDEX["mouth_aaa"]] = _DEFAULT_MOUTH_AAA
    return pose


class THAAvatarBridge:
    """Orchestrator の Emotion/Gesture/Viseme を THA4 ポーズベクターに変換.

    Parameters
    ----------
    config_path : Path | str
        ``tha_emotion_map.yml`` のパス。
    """

    def __init__(self, config_path: Path | str | None = None) -> None:
        if config_path is None:
            config_path = Path(__file__).resolve().parent.parent / "config" / "tha_emotion_map.yml"
        self._config_path = Path(config_path)
        self._emotion_map: dict[str, dict[str, float]] = {}
        self._viseme_map: dict[str, dict[str, float]] = {}
        self._gesture_map: dict[str, dict[str, float]] = {}
        self._load_config()

    # ── Public API ────────────────────────────────────────────────

    def emotion_to_pose(self, emotion: Emotion | str) -> list[float]:
        """Emotion enum をポーズベクターに変換."""
        pose = _make_default_pose()
        emotion_key = str(emotion).lower()
        params = self._emotion_map.get(emotion_key, {})
        self._apply_params(pose, params)
        return pose

    def viseme_to_pose(self, viseme: str, intensity: float = 1.0) -> list[float]:
        """Viseme ラベル (a/i/u/e/o/sil/m/fv) をポーズベクターに変換.

        Parameters
        ----------
        viseme : str
            Viseme ラベル。
        intensity : float
            0.0–1.0 の強度。RMS ベースの口の開き具合に使用。
        """
        pose = _make_default_pose()
        params = self._viseme_map.get(viseme.lower(), {})
        scaled = {k: v * max(0.0, min(1.0, intensity)) for k, v in params.items()}
        self._apply_params(pose, scaled)
        return pose

    def gesture_to_pose(self, gesture: Gesture | str) -> list[float]:
        """Gesture enum をポーズベクターに変換."""
        pose = _make_default_pose()
        gesture_key = str(gesture).lower()
        params = self._gesture_map.get(gesture_key, {})
        self._apply_params(pose, params)
        return pose

    def compose_pose(
        self,
        emotion: Emotion | str = Emotion.NEUTRAL,
        viseme: str = "sil",
        viseme_intensity: float = 1.0,
        gesture: Gesture | str = Gesture.NONE,
        breathing: float = 0.5,
    ) -> list[float]:
        """感情・口形・ジェスチャー・呼吸を合成して最終ポーズベクターを生成.

        合成戦略:
          1. 感情をベースに適用
          2. viseme は mouth 系パラメータ (26-36) を上書き
          3. gesture は body/head 系をブレンド
          4. breathing は最後に設定
        """
        pose = _make_default_pose()

        # 1. 感情ベース
        emotion_params = self._emotion_map.get(str(emotion).lower(), {})
        self._apply_params(pose, emotion_params)

        # 2. Viseme で mouth 系を上書き
        viseme_params = self._viseme_map.get(viseme.lower(), {})
        intensity = max(0.0, min(1.0, viseme_intensity))
        for k, v in viseme_params.items():
            if k.startswith("mouth_"):
                self._set_param(pose, k, v * intensity)

        # 3. Gesture をブレンド (body/head 系のみ加算)
        gesture_params = self._gesture_map.get(str(gesture).lower(), {})
        for k, v in gesture_params.items():
            if k.startswith("_"):
                continue  # _animation 等のメタデータをスキップ
            idx = self._resolve_index(k)
            if idx is not None:
                pose[idx] = max(-1.0, min(1.0, pose[idx] + v))

        # 4. 呼吸
        pose[PARAM_INDEX["breathing"]] = max(0.0, min(1.0, breathing))

        return pose

    # ── Internal ──────────────────────────────────────────────────

    def _load_config(self) -> None:
        """YAML マッピング定義を読み込み."""
        if not self._config_path.exists():
            logger.warning(
                "THA emotion map not found: %s — using empty mapping. "
                "Fix: create config/tha_emotion_map.yml",
                self._config_path,
            )
            return

        with open(self._config_path, encoding="utf-8") as f:
            data: dict[str, Any] = yaml.safe_load(f) or {}

        # 感情マッピング (トップレベル, visemes/gestures 以外)
        reserved = {"visemes", "gestures"}
        for key, params in data.items():
            if key in reserved or not isinstance(params, dict):
                continue
            self._emotion_map[key] = {
                k: float(v) for k, v in params.items() if not str(k).startswith("_")
            }

        # Viseme マッピング
        visemes_raw = data.get("visemes", {})
        if isinstance(visemes_raw, dict):
            for label, params in visemes_raw.items():
                if isinstance(params, dict):
                    self._viseme_map[str(label)] = {
                        k: float(v) for k, v in params.items() if not str(k).startswith("_")
                    }

        # Gesture マッピング
        gestures_raw = data.get("gestures", {})
        if isinstance(gestures_raw, dict):
            for label, params in gestures_raw.items():
                if isinstance(params, dict):
                    self._gesture_map[str(label)] = {
                        k: float(v) for k, v in params.items() if not str(k).startswith("_")
                    }

        logger.info(
            "THA emotion map loaded: %d emotions, %d visemes, %d gestures",
            len(self._emotion_map),
            len(self._viseme_map),
            len(self._gesture_map),
        )

    def _apply_params(self, pose: list[float], params: dict[str, float]) -> None:
        """パラメータ辞書をポーズベクターに適用 (左右対称展開あり)."""
        for name, value in params.items():
            self._set_param(pose, name, value)

    def _set_param(self, pose: list[float], name: str, value: float) -> None:
        """単一パラメータを設定。左右対称名は両側に展開."""
        idx = self._resolve_index(name)
        if idx is not None:
            pose[idx] = value
            return
        # 左右対称展開
        if name in _SYMMETRIC_PARAMS:
            left_name, right_name = _SYMMETRIC_PARAMS[name]
            pose[PARAM_INDEX[left_name]] = value
            pose[PARAM_INDEX[right_name]] = value
            return
        logger.debug("Unknown THA param: %s — skipped", name)

    @staticmethod
    def _resolve_index(name: str) -> int | None:
        """パラメータ名 → インデックス。見つからなければ None."""
        return PARAM_INDEX.get(name)
