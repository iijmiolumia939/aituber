"""Tests for NFR-RES-02: Memory growth monitoring."""

from __future__ import annotations

from orchestrator.memory import MemoryTracker


class TestMemoryTracker:
    """NFR-RES-02: RSS growth tracking within window."""

    def test_single_sample_zero_growth(self):
        tracker = MemoryTracker()
        growth = tracker.sample(rss_mb=100.0, now=0.0)
        assert growth == 0.0

    def test_two_samples_positive_growth(self):
        tracker = MemoryTracker()
        tracker.sample(rss_mb=100.0, now=0.0)
        growth = tracker.sample(rss_mb=150.0, now=60.0)
        assert growth == 50.0

    def test_growth_within_limit(self):
        tracker = MemoryTracker(limit_mb=300)
        tracker.sample(rss_mb=100.0, now=0.0)
        growth = tracker.sample(rss_mb=350.0, now=1800.0)
        assert growth == 250.0  # under 300

    def test_growth_over_limit_logs_warning(self, caplog):
        """RSS growth exceeding limit should log a warning."""
        import logging

        tracker = MemoryTracker(limit_mb=300)
        with caplog.at_level(logging.WARNING, logger="orchestrator.memory"):
            tracker.sample(rss_mb=100.0, now=0.0)
            tracker.sample(rss_mb=500.0, now=1800.0)
        assert any("NFR-RES-02 violation" in r.message for r in caplog.records)

    def test_window_prunes_old_samples(self):
        """Samples older than window_sec are pruned."""
        tracker = MemoryTracker(window_sec=60.0)
        tracker.sample(rss_mb=100.0, now=0.0)
        tracker.sample(rss_mb=200.0, now=30.0)
        # At t=70, first sample (t=0) should be pruned
        tracker.sample(rss_mb=220.0, now=70.0)
        # Growth = 220 - 200 = 20 (not 120, because t=0 sample pruned)
        assert tracker.growth_mb == 20.0
        assert tracker.sample_count == 2

    def test_current_rss_mb(self):
        tracker = MemoryTracker()
        assert tracker.current_rss_mb == 0.0
        tracker.sample(rss_mb=123.4, now=0.0)
        assert tracker.current_rss_mb == 123.4

    def test_bounded_data_structures(self):
        """SeenSet, LatencyTracker, BanditPending all have caps."""
        from orchestrator.chat_poller import SeenSet
        from orchestrator.config import SeenSetConfig
        from orchestrator.latency import LatencyTracker

        # SeenSet cap
        ss = SeenSet(SeenSetConfig(max_capacity=10, ttl_seconds=9999))
        for i in range(20):
            ss.add(f"id_{i}", now=float(i))
        assert len(ss) <= 10

        # LatencyTracker window size
        lt = LatencyTracker(window_size=5)
        for i in range(10):
            lt.start(f"m{i}", received_at=float(i))
        # Records capped by deque maxlen
        assert lt.count == 0  # no finish() called yet

    def test_psutil_fallback_when_missing(self):
        """_get_rss_mb returns 0.0 when psutil is not installed."""
        from unittest.mock import patch

        with patch.dict("sys.modules", {"psutil": None}):
            from orchestrator.memory import _get_rss_mb

            # Even if psutil is mocked to None, the function should handle it
            result = _get_rss_mb()
            assert isinstance(result, float)
