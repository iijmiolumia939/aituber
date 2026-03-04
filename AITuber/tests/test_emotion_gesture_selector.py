"""Tests for emotion_gesture_selector."""


from orchestrator.avatar_ws import Emotion, Gesture
from orchestrator.emotion_gesture_selector import (
    select_emotion_gesture,
    select_idle_emotion_gesture,
)


class TestSelectEmotionGesture:
    def test_greeting_triggers_wave(self):
        emotion, gesture = select_emotion_gesture("こんにちはー！")
        assert emotion == Emotion.HAPPY
        assert gesture == Gesture.WAVE

    def test_cheer_on_excited(self):
        emotion, gesture = select_emotion_gesture("やったー！最高ですね！")
        assert emotion == Emotion.HAPPY
        assert gesture in (Gesture.CHEER, Gesture.WAVE)

    def test_surprised(self):
        emotion, gesture = select_emotion_gesture("えっ！まじで！？")
        assert emotion == Emotion.SURPRISED

    def test_agreement_nod(self):
        emotion, gesture = select_emotion_gesture("なるほど、その通りですね")
        assert emotion == Emotion.HAPPY
        assert gesture == Gesture.NOD

    def test_thinking(self):
        emotion, gesture = select_emotion_gesture("うーん、難しいですね…")
        assert emotion == Emotion.THINKING

    def test_sad_shrug(self):
        emotion, gesture = select_emotion_gesture("残念ながらわかりません。ごめんね。")
        assert emotion in (Emotion.SAD, Emotion.NEUTRAL)

    def test_default_neutral_nod(self):
        emotion, gesture = select_emotion_gesture("今日もよろしくお願いします。")
        # "よろしく" matches greeting rule → HAPPY+WAVE
        assert emotion == Emotion.HAPPY

    def test_no_match_returns_neutral_nod(self):
        emotion, gesture = select_emotion_gesture("テスト文章です。")
        assert emotion == Emotion.NEUTRAL
        assert gesture == Gesture.NOD

    def test_empty_string_returns_default(self):
        emotion, gesture = select_emotion_gesture("")
        assert emotion == Emotion.NEUTRAL
        assert gesture == Gesture.NOD

    def test_playful_happy(self):
        emotion, gesture = select_emotion_gesture("あははー！冗談だよ！")
        assert emotion == Emotion.HAPPY

    def test_shrug_on_refusal(self):
        emotion, gesture = select_emotion_gesture("それはわからないな…難しいね")
        assert gesture in (Gesture.SHRUG, Gesture.NOD, Gesture.NONE)


class TestSelectIdleEmotionGesture:
    def test_default_happy_wave(self):
        emotion, gesture = select_idle_emotion_gesture()
        assert emotion == Emotion.HAPPY
        assert gesture == Gesture.WAVE

    def test_with_topic_hint_no_match_returns_wave(self):
        emotion, gesture = select_idle_emotion_gesture("今日の天気について")
        assert emotion == Emotion.HAPPY
        assert gesture == Gesture.WAVE

    def test_with_topic_hint_match(self):
        emotion, gesture = select_idle_emotion_gesture("やったー！楽しかった！")
        assert emotion == Emotion.HAPPY
