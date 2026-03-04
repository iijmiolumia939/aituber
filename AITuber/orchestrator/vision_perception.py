"""Vision Perception — GPT-4o Vision self-view analysis for YUI.A.

FR-CAM-04: Analyse avatar's self-view screenshot to produce SelfViewState.
Issue: #18 E-8. Virtual Camera + Avatar Self-Perception.

The vision_fn is injected for testability — it receives a base64 PNG and a
text prompt, and returns a string response.

References:
  OpenAI Vision API: https://platform.openai.com/docs/guides/vision
  Durante et al. (2024), Agent AI, arXiv:2401.03568 §4 "Perception"
"""

from __future__ import annotations

import logging
import re
from collections.abc import Callable
from dataclasses import dataclass

logger = logging.getLogger(__name__)

# ── Data models ───────────────────────────────────────────────────────

_VALID_FRAMINGS = {"too_close", "good", "too_far", "unknown"}


@dataclass
class SelfViewState:
    """Avatar's self-perception from a camera frame analysis.

    FR-CAM-04.

    Attributes:
        framing: "too_close" | "good" | "too_far" | "unknown"
        emotion_visible: whether the avatar's emotion expression is clearly visible
        suggestion: short suggestion for camera/pose adjustment
        raw_response: full LLM response for debugging
    """

    framing: str = "unknown"
    emotion_visible: bool = True
    suggestion: str = ""
    raw_response: str = ""


class VisionPerception:
    """Analyse YUI.A's self-view screenshot using a vision LLM.

    FR-CAM-04: Returns SelfViewState with framing, emotion_visible, suggestion.
    NFR-CAM-02: vision_fn calls should be rate-limited by the caller (max 1/10s).

    Args:
        vision_fn: callable(image_b64: str, prompt: str) → str response.
                   If None, returns a default SelfViewState without LLM.
    """

    _ANALYSIS_PROMPT = (
        "あなたはYUI.Aというアバターです。"
        "この配信画面での自分の映り方を分析してください。\n"
        "以下のJSON形式で回答してください（コードブロック不要）：\n"
        '{"framing":"too_close|good|too_far","emotion_visible":true|false,'
        '"suggestion":"改善案を一文で"}'
    )

    def __init__(
        self,
        vision_fn: Callable[[str, str], str] | None = None,
    ) -> None:
        self._vision_fn = vision_fn

    def analyze_self(self, image_b64: str) -> SelfViewState:
        """Analyse a self-view frame.

        FR-CAM-04: Returns SelfViewState parsed from LLM JSON response.
        Returns a default state silently if vision_fn is None or fails.

        Args:
            image_b64: base64-encoded PNG image string.

        Returns:
            SelfViewState with analysis results.
        """
        if not image_b64:
            return SelfViewState(framing="unknown", suggestion="No image provided")

        if self._vision_fn is None:
            return SelfViewState(
                framing="good",
                emotion_visible=True,
                suggestion="Vision API not configured",
            )

        try:
            raw = self._vision_fn(image_b64, self._ANALYSIS_PROMPT)
            return self._parse_response(raw)
        except Exception as exc:  # noqa: BLE001
            logger.warning("[VisionPerception] Analysis failed: %s", exc)
            return SelfViewState(framing="unknown", suggestion=f"Analysis error: {exc}")

    # ── Private helpers ───────────────────────────────────────────────

    @staticmethod
    def _parse_response(raw: str) -> SelfViewState:
        """Parse JSON-like LLM response into SelfViewState.

        Tolerates sloppy JSON by using regex fallback.
        """
        import json

        # Try direct JSON parse (strip whitespace/newlines)
        try:
            data = json.loads(raw.strip())
            framing = str(data.get("framing", "unknown"))
            if framing not in _VALID_FRAMINGS:
                framing = "unknown"
            return SelfViewState(
                framing=framing,
                emotion_visible=bool(data.get("emotion_visible", True)),
                suggestion=str(data.get("suggestion", "")),
                raw_response=raw,
            )
        except (json.JSONDecodeError, ValueError):
            pass

        # Regex fallback
        framing = "unknown"
        m = re.search(r'"framing"\s*:\s*"([^"]+)"', raw)
        if m and m.group(1) in _VALID_FRAMINGS:
            framing = m.group(1)

        emotion_visible = True
        m2 = re.search(r'"emotion_visible"\s*:\s*(true|false)', raw, re.IGNORECASE)
        if m2:
            emotion_visible = m2.group(1).lower() == "true"

        suggestion = ""
        m3 = re.search(r'"suggestion"\s*:\s*"([^"]+)"', raw)
        if m3:
            suggestion = m3.group(1)

        return SelfViewState(
            framing=framing,
            emotion_visible=emotion_visible,
            suggestion=suggestion,
            raw_response=raw,
        )
