"""Tests for orchestrator.camera_context.

TC-CAM-11 to TC-CAM-15.
Issue: #18 E-8. FR-CAM-05.
"""

from __future__ import annotations

import pytest

from orchestrator.camera_context import CameraContext
from orchestrator.vision_perception import SelfViewState


@pytest.fixture()
def ctx() -> CameraContext:
    return CameraContext(active_camera="A", available_cameras=["A", "B", "C"])


class TestCameraContextFragment:
    def test_prompt_fragment_contains_camera_name(self, ctx: CameraContext) -> None:
        """TC-CAM-11: to_prompt_fragment includes active camera name."""
        frag = ctx.to_prompt_fragment()
        assert "[CAMERA]" in frag
        assert "A" in frag

    def test_prompt_fragment_contains_available_cameras(self, ctx: CameraContext) -> None:
        """TC-CAM-11b: fragment lists all available cameras."""
        frag = ctx.to_prompt_fragment()
        assert "B" in frag
        assert "C" in frag

    def test_prompt_fragment_good_framing(self, ctx: CameraContext) -> None:
        """TC-CAM-12: good framing produces positive framing description."""
        ctx.update("A", self_view=SelfViewState(framing="good", emotion_visible=True))
        frag = ctx.to_prompt_fragment()
        assert "良好" in frag

    def test_prompt_fragment_too_close(self, ctx: CameraContext) -> None:
        """TC-CAM-12b: too_close framing described in fragment."""
        ctx.update("A", self_view=SelfViewState(framing="too_close", emotion_visible=True))
        frag = ctx.to_prompt_fragment()
        assert "大きく" in frag

    def test_prompt_fragment_too_far(self, ctx: CameraContext) -> None:
        """TC-CAM-12c: too_far framing described in fragment."""
        ctx.update("A", self_view=SelfViewState(framing="too_far", emotion_visible=True))
        frag = ctx.to_prompt_fragment()
        assert "引き" in frag

    def test_update_camera(self, ctx: CameraContext) -> None:
        """TC-CAM-13: update() changes active_camera."""
        ctx.update("B")
        assert ctx.active_camera == "B"
        frag = ctx.to_prompt_fragment()
        assert "B" in frag

    def test_update_self_view(self, ctx: CameraContext) -> None:
        """TC-CAM-13b: update() with self_view updates last_self_view."""
        sv = SelfViewState(framing="too_far", emotion_visible=False, suggestion="近づいて")
        ctx.update("C", self_view=sv)
        assert ctx.last_self_view.framing == "too_far"
        frag = ctx.to_prompt_fragment()
        assert "近づいて" in frag

    def test_emotion_visible_false_in_fragment(self, ctx: CameraContext) -> None:
        """TC-CAM-14: emotion_visible=False generates warning text."""
        ctx.update("A", self_view=SelfViewState(framing="good", emotion_visible=False))
        frag = ctx.to_prompt_fragment()
        assert "見えにくい" in frag

    def test_emotion_visible_true_in_fragment(self, ctx: CameraContext) -> None:
        """TC-CAM-14b: emotion_visible=True generates positive text."""
        ctx.update("A", self_view=SelfViewState(framing="good", emotion_visible=True))
        frag = ctx.to_prompt_fragment()
        assert "明確" in frag

    def test_update_available_cameras(self, ctx: CameraContext) -> None:
        """TC-CAM-15: update() can replace available_cameras list."""
        ctx.update("X", available_cameras=["X", "Y"])
        assert ctx.available_cameras == ["X", "Y"]
        frag = ctx.to_prompt_fragment()
        assert "X" in frag
        assert "Y" in frag
