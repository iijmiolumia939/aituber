"""Gesture Composer — intensity/context-aware body expression selector.

FR-E5-01: Selects gesture and expression based on emotion + intensity + intent.
Issue: #15 E-5

References:
  CoALA (Sumers et al., 2023) arXiv:2309.02427 §5 "Action Space"
  Park et al. (2023), Generative Agents, arXiv:2304.03442
"""

from __future__ import annotations

from dataclasses import dataclass

# ── Data models ──────────────────────────────────────────────────────


@dataclass
class GestureSpec:
    """Output of GestureComposer.

    FR-E5-01.

    Attributes:
        gesture: gesture key (matches behavior_policy intent or avatar_update gesture)
        expression: emotion key
        duration_hint: approximate seconds the gesture should hold (0 = default)
    """

    gesture: str
    expression: str
    duration_hint: float = 0.0


# ── Mapping tables ────────────────────────────────────────────────────

# (emotion, high_intensity) → GestureSpec
# "high" = intensity >= 0.6
_HIGH_INTENSITY_MAP: dict[str, GestureSpec] = {
    "happy": GestureSpec(gesture="cheer", expression="happy", duration_hint=2.0),
    "surprised": GestureSpec(gesture="surprised", expression="surprised", duration_hint=1.5),
    "sad": GestureSpec(gesture="sad_kick", expression="sad", duration_hint=2.5),
    "angry": GestureSpec(gesture="facepalm", expression="angry", duration_hint=1.5),
    "thinking": GestureSpec(gesture="thinking", expression="thinking", duration_hint=2.0),
    "neutral": GestureSpec(gesture="wave", expression="neutral", duration_hint=1.0),
    "panic": GestureSpec(gesture="rejected", expression="panic", duration_hint=1.5),
}

# (emotion, low_intensity) → GestureSpec
# "low" = intensity < 0.6
_LOW_INTENSITY_MAP: dict[str, GestureSpec] = {
    "happy": GestureSpec(gesture="nod", expression="happy", duration_hint=1.0),
    "surprised": GestureSpec(gesture="shrug", expression="surprised", duration_hint=1.0),
    "sad": GestureSpec(gesture="sad_idle", expression="sad", duration_hint=2.0),
    "angry": GestureSpec(gesture="shake", expression="angry", duration_hint=1.0),
    "thinking": GestureSpec(gesture="thinking", expression="thinking", duration_hint=1.5),
    "neutral": GestureSpec(gesture="none", expression="neutral", duration_hint=0.0),
    "panic": GestureSpec(gesture="sigh", expression="sad", duration_hint=1.0),
}

# Intent overrides (take priority over emotion mapping when set)
_INTENT_OVERRIDE: dict[str, GestureSpec] = {
    "question": GestureSpec(gesture="thinking", expression="thinking", duration_hint=1.5),
    "praise": GestureSpec(gesture="shy", expression="happy", duration_hint=1.5),
    "tease": GestureSpec(gesture="laugh", expression="happy", duration_hint=1.5),
    "concern": GestureSpec(gesture="sad_idle", expression="sad", duration_hint=2.0),
}

_HIGH_THRESHOLD = 0.6
_DEFAULT_GESTURE = GestureSpec(gesture="none", expression="neutral")


class GestureComposer:
    """Select an appropriate gesture+expression based on context.

    FR-E5-01: intensity-aware; same emotion may yield different gestures
    when high vs. low intensity.
    """

    def compose(
        self,
        emotion: str = "neutral",
        intensity: float = 0.5,
        intent: str | None = None,
    ) -> GestureSpec:
        """Select gesture and expression.

        Args:
            emotion: base emotion (happy/sad/surprised/angry/thinking/neutral/panic).
            intensity: 0.0 (subtle) – 1.0 (strong).
            intent: optional viewer intent hint from TomEstimator
                    (question/praise/tease/concern/neutral).

        Returns:
            GestureSpec with gesture, expression, and duration_hint.

        FR-E5-01: High intensity (>= 0.6) uses more expressive gestures.
        """
        # Intent override takes priority
        if intent and intent in _INTENT_OVERRIDE:
            spec = _INTENT_OVERRIDE[intent]
            # Blend intensity into duration
            return GestureSpec(
                gesture=spec.gesture,
                expression=emotion if emotion != "neutral" else spec.expression,
                duration_hint=spec.duration_hint * (0.5 + intensity * 0.5),
            )

        em = emotion.lower()
        if intensity >= _HIGH_THRESHOLD:
            spec = _HIGH_INTENSITY_MAP.get(em, _DEFAULT_GESTURE)
        else:
            spec = _LOW_INTENSITY_MAP.get(em, _DEFAULT_GESTURE)

        return GestureSpec(
            gesture=spec.gesture,
            expression=spec.expression,
            duration_hint=spec.duration_hint,
        )

    def compose_idle_ambient(self, idle_text: str = "") -> GestureSpec:
        """Return an ambient gesture for idle/alone moments.

        FR-E5-01: Natural ambient gestures when not being addressed.
        """
        text_lower = idle_text.lower()
        if any(w in text_lower for w in ("質問", "考え", "不思議", "なぜ", "?")):
            return GestureSpec(gesture="thinking", expression="thinking", duration_hint=3.0)
        if any(w in text_lower for w in ("楽し", "好き", "嬉し", "わーい")):
            return GestureSpec(gesture="idle_alt", expression="happy", duration_hint=2.0)
        # Default calm idle
        return GestureSpec(gesture="idle_alt", expression="neutral", duration_hint=0.0)
