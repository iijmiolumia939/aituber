"""NFR-LAT-01: レイテンシ計測テスト。

P95 < 4.0s を検証するためのユニットテスト。
"""

from __future__ import annotations

import pytest

from orchestrator.latency import LatencyTracker


class TestLatencyTracker:
    """LatencyTracker の基本動作検証。"""

    def test_single_record(self) -> None:
        """1件のレイテンシが正しく計測される。"""
        lt = LatencyTracker()
        lt.start("m1", received_at=100.0)
        lat = lt.finish("m1", speech_start_at=102.5)
        assert lat == pytest.approx(2.5)
        assert lt.count == 1

    def test_p95_under_target(self) -> None:
        """全件が4秒未満なら P95 も 4 未満。"""
        lt = LatencyTracker()
        for i in range(100):
            mid = f"m{i}"
            lt.start(mid, received_at=float(i * 10))
            lt.finish(mid, speech_start_at=float(i * 10 + 2.0))
        assert lt.p95 < 4.0

    def test_p95_violation_detected(self) -> None:
        """5% 超の件数が 4 秒超なら P95 ≥ 4。"""
        lt = LatencyTracker()
        # 90件: 1秒, 10件: 5秒 → P95 index=95 → 5秒
        for i in range(90):
            mid = f"m{i}"
            lt.start(mid, received_at=float(i * 10))
            lt.finish(mid, speech_start_at=float(i * 10 + 1.0))
        for i in range(90, 100):
            mid = f"m{i}"
            lt.start(mid, received_at=float(i * 10))
            lt.finish(mid, speech_start_at=float(i * 10 + 5.0))
        assert lt.p95 >= 4.0

    def test_unknown_message_returns_negative(self) -> None:
        """存在しない message_id で finish → -1.0。"""
        lt = LatencyTracker()
        assert lt.finish("unknown") == -1.0

    def test_percentile_empty(self) -> None:
        """データ無しなら percentile = 0.0。"""
        lt = LatencyTracker()
        assert lt.p50 == 0.0
        assert lt.p95 == 0.0
        assert lt.p99 == 0.0

    def test_window_size_limits_data(self) -> None:
        """window_size を超えたら古いデータが捨てられる。"""
        lt = LatencyTracker(window_size=10)
        for i in range(20):
            mid = f"m{i}"
            lt.start(mid, received_at=float(i))
            lt.finish(mid, speech_start_at=float(i + 1))
        assert lt.count == 10  # window_size

    def test_p50(self) -> None:
        """P50 が中央値付近であること。"""
        lt = LatencyTracker()
        for i in range(100):
            mid = f"m{i}"
            lt.start(mid, received_at=0.0)
            # 0.01, 0.02, ..., 1.00
            lt.finish(mid, speech_start_at=float(i + 1) * 0.01)
        # P50: 50番目付近 → 0.50–0.51
        assert 0.4 < lt.p50 < 0.6

    def test_finish_only_once(self) -> None:
        """同一 message_id で 2 回 finish しても 1 回だけ計上。"""
        lt = LatencyTracker()
        lt.start("m1", received_at=100.0)
        lat1 = lt.finish("m1", speech_start_at=103.0)
        lat2 = lt.finish("m1", speech_start_at=105.0)
        assert lat1 == pytest.approx(3.0)
        assert lat2 == -1.0  # 2回目は見つからない
        assert lt.count == 1


class TestLatencyWarning:
    """4秒超で WARNING ログが出ることを検証。"""

    def test_warning_on_violation(self, caplog: pytest.LogCaptureFixture) -> None:
        lt = LatencyTracker()
        lt.start("slow", received_at=0.0)
        with caplog.at_level("WARNING", logger="orchestrator.latency"):
            lt.finish("slow", speech_start_at=5.0)
        assert "NFR-LAT-01 violation" in caplog.text

    def test_no_warning_under_target(self, caplog: pytest.LogCaptureFixture) -> None:
        lt = LatencyTracker()
        lt.start("fast", received_at=0.0)
        with caplog.at_level("WARNING", logger="orchestrator.latency"):
            lt.finish("fast", speech_start_at=3.0)
        assert "NFR-LAT-01 violation" not in caplog.text
