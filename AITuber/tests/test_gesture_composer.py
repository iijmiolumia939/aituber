"""Tests for orchestrator.gesture_composer.

TC-GESTURE-01 to TC-GESTURE-08.
Issue: #15 E-5. FR-E5-01.
"""

from __future__ import annotations

import pytest

from orchestrator.gesture_composer import GestureComposer


@pytest.fixture()
def gc() -> GestureComposer:
    return GestureComposer()


class TestGestureComposerIntensity:
    def test_high_intensity_happy(self, gc: GestureComposer) -> None:
        """TC-GESTURE-01: high intensity happy → cheer."""
        spec = gc.compose(emotion="happy", intensity=0.9)
        assert spec.gesture == "cheer"
        assert spec.expression == "happy"

    def test_low_intensity_happy(self, gc: GestureComposer) -> None:
        """TC-GESTURE-01b: low intensity happy → nod."""
        spec = gc.compose(emotion="happy", intensity=0.2)
        assert spec.gesture == "nod"
        assert spec.expression == "happy"

    def test_different_gesture_for_high_vs_low(self, gc: GestureComposer) -> None:
        """TC-GESTURE-02: same emotion, different intensity → different gesture."""
        high = gc.compose(emotion="surprised", intensity=0.8)
        low = gc.compose(emotion="surprised", intensity=0.3)
        assert high.gesture != low.gesture

    def test_high_intensity_sad(self, gc: GestureComposer) -> None:
        """TC-GESTURE-03: high intensity sad → sad_kick."""
        spec = gc.compose(emotion="sad", intensity=0.7)
        assert spec.gesture == "sad_kick"

    def test_low_intensity_sad(self, gc: GestureComposer) -> None:
        """TC-GESTURE-03b: low intensity sad → sad_idle."""
        spec = gc.compose(emotion="sad", intensity=0.1)
        assert spec.gesture == "sad_idle"

    def test_high_intensity_thinking(self, gc: GestureComposer) -> None:
        """TC-GESTURE-04: thinking at any intensity → thinking gesture."""
        spec = gc.compose(emotion="thinking", intensity=0.9)
        assert spec.gesture == "thinking"

    def test_threshold_boundary(self, gc: GestureComposer) -> None:
        """TC-GESTURE-05: intensity exactly at threshold (0.6) → high."""
        high = gc.compose(emotion="happy", intensity=0.6)
        assert high.gesture == "cheer"

    def test_unknown_emotion_returns_default(self, gc: GestureComposer) -> None:
        """TC-GESTURE-06: unknown emotion → none/neutral default."""
        spec = gc.compose(emotion="confused_alien_emotion", intensity=0.5)
        assert spec.gesture == "none"
        assert spec.expression == "neutral"


class TestGestureComposerIntent:
    def test_question_intent_override(self, gc: GestureComposer) -> None:
        """TC-GESTURE-07: question intent → thinking gesture regardless of emotion."""
        spec = gc.compose(emotion="happy", intensity=0.9, intent="question")
        assert spec.gesture == "thinking"

    def test_praise_intent_override(self, gc: GestureComposer) -> None:
        """TC-GESTURE-07b: praise intent → shy gesture."""
        spec = gc.compose(emotion="neutral", intensity=0.5, intent="praise")
        assert spec.gesture == "shy"

    def test_tease_intent_override(self, gc: GestureComposer) -> None:
        """TC-GESTURE-07c: tease intent → laugh gesture."""
        spec = gc.compose(emotion="neutral", intensity=0.5, intent="tease")
        assert spec.gesture == "laugh"

    def test_concern_intent_override(self, gc: GestureComposer) -> None:
        """TC-GESTURE-07d: concern intent → sad_idle."""
        spec = gc.compose(emotion="neutral", intensity=0.5, intent="concern")
        assert spec.gesture == "sad_idle"

    def test_neutral_intent_no_override(self, gc: GestureComposer) -> None:
        """TC-GESTURE-08: neutral/absent intent uses emotion mapping."""
        spec_no_intent = gc.compose(emotion="happy", intensity=0.9, intent=None)
        spec_neutral = gc.compose(emotion="happy", intensity=0.9, intent="neutral")
        # Both should use emotion map (cheer for high happy)
        assert spec_no_intent.gesture == "cheer"
        # "neutral" intent is not in override table, so falls through to emotion map
        assert spec_neutral.gesture == "cheer"


class TestGestureComposerIdle:
    def test_idle_thinking_text(self, gc: GestureComposer) -> None:
        """TC-GESTURE-08b: idle text with question-like content → thinking."""
        spec = gc.compose_idle_ambient("なぜ空は青いのか不思議ですね")
        assert spec.gesture == "thinking"

    def test_idle_happy_text(self, gc: GestureComposer) -> None:
        """TC-GESTURE-08c: idle text with happy content → idle_alt happy."""
        spec = gc.compose_idle_ambient("今日は楽しいですね！")
        assert spec.gesture == "idle_alt"
        assert spec.expression == "happy"

    def test_idle_default(self, gc: GestureComposer) -> None:
        """TC-GESTURE-08d: empty idle text → idle_alt neutral."""
        spec = gc.compose_idle_ambient()
        assert spec.gesture == "idle_alt"
        assert spec.expression == "neutral"
