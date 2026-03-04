"""Tests for orchestrator.tom_estimator.

TC-TOM-01 to TC-TOM-08.
Issue: #13 E-3 Theory of Mind. FR-E3-01.
"""

from __future__ import annotations

import pytest

from orchestrator.tom_estimator import TomEstimate, TomEstimator


@pytest.fixture()
def est() -> TomEstimator:
    return TomEstimator()


class TestTomEstimatorIntent:
    def test_question_mark(self, est: TomEstimator) -> None:
        """TC-TOM-01: '?' triggers question intent."""
        r = est.estimate("今日の配信どうでしたか？")
        assert r.intent == "question"

    def test_question_word(self, est: TomEstimator) -> None:
        """TC-TOM-01b: 'なに' triggers question intent."""
        r = est.estimate("なにしてるの")
        assert r.intent == "question"

    def test_what_english(self, est: TomEstimator) -> None:
        """TC-TOM-01c: English 'what' triggers question intent."""
        r = est.estimate("what are you doing")
        assert r.intent == "question"

    def test_praise(self, est: TomEstimator) -> None:
        """TC-TOM-02: praise keywords trigger praise intent."""
        r = est.estimate("かわいい！ありがとうございます")
        assert r.intent == "praise"

    def test_tease(self, est: TomEstimator) -> None:
        """TC-TOM-03: tease keywords trigger tease intent."""
        r = est.estimate("www　草生えた")
        assert r.intent == "tease"

    def test_concern(self, est: TomEstimator) -> None:
        """TC-TOM-04: concern keywords trigger concern intent."""
        est.estimate("大丈夫ですか？心配してます")  # question takes priority (? present)
        # concern takes lower priority than question — test without question mark
        r2 = est.estimate("大丈夫 心配しています")
        assert r2.intent == "concern"

    def test_neutral(self, est: TomEstimator) -> None:
        """TC-TOM-05: unclassifiable text is neutral."""
        r = est.estimate("えーと")
        assert r.intent == "neutral"


class TestTomEstimatorSentiment:
    def test_positive(self, est: TomEstimator) -> None:
        """TC-TOM-05b: positive keywords yield positive sentiment."""
        r = est.estimate("最高！楽しい！")
        assert r.sentiment == "positive"

    def test_negative(self, est: TomEstimator) -> None:
        """TC-TOM-06: negative keywords yield negative sentiment."""
        r = est.estimate("sad ほんとつまらない")
        assert r.sentiment == "negative"

    def test_neutral_sentiment(self, est: TomEstimator) -> None:
        """TC-TOM-06b: no polarity keywords → neutral sentiment."""
        r = est.estimate("こんにちは")
        assert r.sentiment == "neutral"


class TestTomEstimatorFamiliarity:
    def test_newcomer(self, est: TomEstimator) -> None:
        """TC-TOM-07: 0 past episodes → newcomer."""
        r = est.estimate("こんにちは", episode_count=0)
        assert r.familiarity == "newcomer"

    def test_regular(self, est: TomEstimator) -> None:
        """TC-TOM-07b: 5 past episodes → regular."""
        r = est.estimate("こんにちは", episode_count=5)
        assert r.familiarity == "regular"

    def test_superchatter(self, est: TomEstimator) -> None:
        """TC-TOM-08: 20 past episodes → superchatter."""
        r = est.estimate("こんにちは", episode_count=20)
        assert r.familiarity == "superchatter"


class TestTomEstimatorPromptFragment:
    def test_fragment_structure(self, est: TomEstimator) -> None:
        """TC-TOM-08b: to_prompt_fragment produces [TOM] block."""
        estimate = TomEstimate(
            intent="question",
            sentiment="positive",
            familiarity="newcomer",
            knowledge_assumed="YUI.A が何者かを知らない可能性が高い",
        )
        frag = est.to_prompt_fragment(estimate)
        assert frag.startswith("[TOM]")
        assert "question" in frag
        assert "positive" in frag
        assert "newcomer" in frag
