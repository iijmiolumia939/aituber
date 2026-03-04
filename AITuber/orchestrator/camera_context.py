"""Camera Context — injects active camera state into orchestrator LLM context.

FR-CAM-05: Formats camera information as a [CAMERA] prompt block for the LLM.
Issue: #18 E-8. Virtual Camera + Avatar Self-Perception.

References:
  Park et al. (2023), Generative Agents, arXiv:2304.03442 §3 "Memory"
"""

from __future__ import annotations

from dataclasses import dataclass, field

from orchestrator.vision_perception import SelfViewState

# Framing descriptions for natural-language injection
_FRAMING_DESCRIPTIONS: dict[str, str] = {
    "too_close": "顔が大きく映りすぎています",
    "good": "フレーミングは良好です",
    "too_far": "引きすぎていて小さく映っています",
    "unknown": "フレーミングは不明です",
}


@dataclass
class CameraContext:
    """Snapshot of camera state for LLM context injection.

    FR-CAM-05.

    Attributes:
        active_camera: current active camera name ("A" | "B" | "C" | ...)
        available_cameras:  list of all available camera names
        last_self_view: most recent SelfViewState analysis result
    """

    active_camera: str = "A"
    available_cameras: list[str] = field(default_factory=lambda: ["A", "B", "C"])
    last_self_view: SelfViewState = field(default_factory=SelfViewState)

    def update(
        self,
        active_camera: str,
        available_cameras: list[str] | None = None,
        self_view: SelfViewState | None = None,
    ) -> None:
        """Update camera state.

        FR-CAM-05: Call this when camera switches or self-view re-analysed.
        """
        self.active_camera = active_camera
        if available_cameras is not None:
            self.available_cameras = list(available_cameras)
        if self_view is not None:
            self.last_self_view = self_view

    def to_prompt_fragment(self) -> str:
        """Convert to a [CAMERA] block for LLM system prompt injection.

        FR-CAM-05: Returns empty string if camera context is uninitialised.
        """
        framing_desc = _FRAMING_DESCRIPTIONS.get(
            self.last_self_view.framing, _FRAMING_DESCRIPTIONS["unknown"]
        )
        visible_str = (
            "感情表現が明確に見えています"
            if self.last_self_view.emotion_visible
            else "感情表現が見えにくい状態です"
        )
        suggestion = self.last_self_view.suggestion

        parts = [
            "[CAMERA]",
            f"現在のカメラ: {self.active_camera}",
            f"利用可能なカメラ: {', '.join(self.available_cameras)}",
            f"フレーミング: {framing_desc}",
            f"視聴者への映り: {visible_str}",
        ]
        if suggestion:
            parts.append(f"改善案: {suggestion}")

        return "\n".join(parts)
