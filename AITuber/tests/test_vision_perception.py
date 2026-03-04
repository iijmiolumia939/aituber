"""Tests for orchestrator.vision_perception.

TC-CAM-06 to TC-CAM-10.
Issue: #18 E-8. FR-CAM-04. NFR-CAM-02.
"""

from __future__ import annotations

import json

from orchestrator.vision_perception import SelfViewState, VisionPerception


def _make_vp(response: str | None = None) -> VisionPerception:
    if response is None:
        return VisionPerception(vision_fn=None)
    return VisionPerception(vision_fn=lambda _img, _prompt: response)


class TestVisionPerceptionDefault:
    def test_no_vision_fn_returns_good_framing(self) -> None:
        """TC-CAM-06: No vision_fn → default SelfViewState with framing=good."""
        vp = _make_vp(response=None)
        result = vp.analyze_self("abc123")
        assert isinstance(result, SelfViewState)
        assert result.framing == "good"

    def test_empty_image_returns_state(self) -> None:
        """TC-CAM-06b: Empty image_b64 returns SelfViewState without calling fn."""
        called = []

        def fn(img, prompt):
            called.append(img)
            return "{}"

        vp = VisionPerception(vision_fn=fn)
        result = vp.analyze_self("")
        assert isinstance(result, SelfViewState)
        assert len(called) == 0  # not called for empty image


class TestVisionPerceptionParsing:
    def test_valid_json_response_parsed(self) -> None:
        """TC-CAM-07: Valid JSON response is correctly parsed."""
        resp = json.dumps(
            {
                "framing": "good",
                "emotion_visible": True,
                "suggestion": "問題ありません",
            }
        )
        vp = _make_vp(response=resp)
        result = vp.analyze_self("img_b64_data")
        assert result.framing == "good"
        assert result.emotion_visible is True
        assert result.suggestion == "問題ありません"

    def test_too_close_framing(self) -> None:
        """TC-CAM-07b: too_close framing parsed correctly."""
        resp = '{"framing":"too_close","emotion_visible":true,"suggestion":"引いてください"}'
        vp = _make_vp(response=resp)
        result = vp.analyze_self("data")
        assert result.framing == "too_close"

    def test_too_far_framing(self) -> None:
        """TC-CAM-07c: too_far framing parsed correctly."""
        resp = '{"framing":"too_far","emotion_visible":false,"suggestion":"アップにして"}'
        vp = _make_vp(response=resp)
        result = vp.analyze_self("data")
        assert result.framing == "too_far"
        assert result.emotion_visible is False

    def test_invalid_framing_becomes_unknown(self) -> None:
        """TC-CAM-08: Unknown framing values become 'unknown'."""
        resp = '{"framing":"weirdvalue","emotion_visible":true,"suggestion":""}'
        vp = _make_vp(response=resp)
        result = vp.analyze_self("data")
        assert result.framing == "unknown"

    def test_malformed_json_regex_fallback(self) -> None:
        """TC-CAM-08b: Malformed JSON falls back to regex parsing."""
        resp = 'Analysis: framing is "good", emotion_visible: true, suggestion: "OK"'
        vp = _make_vp(response=resp)
        result = vp.analyze_self("data")
        # Regex won't find perfect match, but should not raise
        assert isinstance(result, SelfViewState)

    def test_raw_response_stored(self) -> None:
        """TC-CAM-09: raw_response field stores the original LLM response."""
        resp = '{"framing":"good","emotion_visible":true,"suggestion":"test"}'
        vp = _make_vp(response=resp)
        result = vp.analyze_self("data")
        assert result.raw_response == resp

    def test_vision_fn_called_with_image_and_prompt(self) -> None:
        """TC-CAM-10: vision_fn receives the image and a non-empty prompt."""
        received = {}

        def fn(img: str, prompt: str) -> str:
            received["img"] = img
            received["prompt"] = prompt
            return '{"framing":"good","emotion_visible":true,"suggestion":""}'

        vp = VisionPerception(vision_fn=fn)
        vp.analyze_self("myimage_b64")
        assert received["img"] == "myimage_b64"
        assert len(received["prompt"]) > 20

    def test_vision_fn_exception_returns_unknown(self) -> None:
        """TC-CAM-10b: vision_fn raising exception → framing=unknown, no re-raise."""

        def fn(img, prompt):
            raise RuntimeError("API down")

        vp = VisionPerception(vision_fn=fn)
        result = vp.analyze_self("data")
        assert result.framing == "unknown"
