"""Tests for orchestrator.broadcast_desire.

TC-BCAST-01 to TC-BCAST-05.
Issue: #17 E-7. FR-BCAST-01.
"""

from __future__ import annotations

import pytest

from orchestrator.broadcast_desire import (
    _HIGH_DESIRE_THRESHOLD,
    _MIN_DESIRE_THRESHOLD,
    BroadcastDesireEvaluator,
    DesireState,
)


@pytest.fixture()
def bde() -> BroadcastDesireEvaluator:
    return BroadcastDesireEvaluator()


class TestBroadcastDesireEvaluator:
    def test_returns_desire_state(self, bde: BroadcastDesireEvaluator) -> None:
        """TC-BCAST-01: evaluate() returns a DesireState."""
        result = bde.evaluate(energy=0.5, content_count=2, hours_since_last=12.0)
        assert isinstance(result, DesireState)

    def test_score_in_range(self, bde: BroadcastDesireEvaluator) -> None:
        """TC-BCAST-01b: desire_score is always in [0.0, 1.0]."""
        for energy in [0.0, 0.5, 1.0]:
            for content in [0, 5, 100]:
                for hours in [0.0, 12.0, 48.0]:
                    s = bde.evaluate(energy=energy, content_count=content, hours_since_last=hours)
                    assert 0.0 <= s.desire_score <= 1.0

    def test_max_score_all_high(self, bde: BroadcastDesireEvaluator) -> None:
        """TC-BCAST-02: max energy + max content + max recency → high score."""
        s = bde.evaluate(energy=1.0, content_count=100, hours_since_last=48.0)
        assert s.desire_score >= _HIGH_DESIRE_THRESHOLD

    def test_zero_score_all_low(self, bde: BroadcastDesireEvaluator) -> None:
        """TC-BCAST-03: no energy + no content + just broadcast → low score."""
        s = bde.evaluate(energy=0.0, content_count=0, hours_since_last=0.0)
        assert s.desire_score <= _MIN_DESIRE_THRESHOLD

    def test_energy_clamp(self, bde: BroadcastDesireEvaluator) -> None:
        """TC-BCAST-04: energy > 1.0 is clamped to 1.0, < 0.0 clamped to 0.0."""
        high = bde.evaluate(energy=2.0, content_count=0, hours_since_last=0.0)
        expected = bde.evaluate(energy=1.0, content_count=0, hours_since_last=0.0)
        assert high.desire_score == expected.desire_score

        low = bde.evaluate(energy=-5.0, content_count=0, hours_since_last=0.0)
        zero = bde.evaluate(energy=0.0, content_count=0, hours_since_last=0.0)
        assert low.desire_score == zero.desire_score

    def test_should_broadcast_flag(self, bde: BroadcastDesireEvaluator) -> None:
        """TC-BCAST-05: should_broadcast True only when score >= HIGH_DESIRE_THRESHOLD."""
        high = bde.evaluate(energy=1.0, content_count=100, hours_since_last=48.0)
        assert high.should_broadcast is True

        low = bde.evaluate(energy=0.0, content_count=0, hours_since_last=0.0)
        assert low.should_broadcast is False

    def test_thresholds_accessible(self, bde: BroadcastDesireEvaluator) -> None:
        """TC-BCAST-05b: threshold properties are readable."""
        assert bde.high_threshold == _HIGH_DESIRE_THRESHOLD
        assert bde.min_threshold == _MIN_DESIRE_THRESHOLD
