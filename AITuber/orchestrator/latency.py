"""レイテンシ計測モジュール (NFR-LAT-01).

コメント受信 → 音声再生開始 の P95 レイテンシを計測。
目標: P95 < 4.0 秒。
"""

from __future__ import annotations

import bisect
import logging
import time
from collections import deque
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class LatencyRecord:
    """1件のレイテンシ記録。"""

    message_id: str
    received_at: float  # monotonic
    speech_start_at: float = 0.0
    latency_sec: float = 0.0


class LatencyTracker:
    """NFR-LAT-01: P95 レイテンシ追跡。

    直近 *window_size* 件のレイテンシを保持し、
    P50 / P95 / P99 をリアルタイムで算出する。
    """

    def __init__(self, window_size: int = 200) -> None:
        self._window_size = window_size
        self._records: deque[LatencyRecord] = deque(maxlen=window_size)
        self._sorted_latencies: list[float] = []

    def start(self, message_id: str, received_at: float | None = None) -> None:
        """コメント受信時刻を記録。"""
        now = received_at if received_at is not None else time.monotonic()
        rec = LatencyRecord(message_id=message_id, received_at=now)
        self._records.append(rec)

    def finish(self, message_id: str, speech_start_at: float | None = None) -> float:
        """音声再生開始時刻を記録し、レイテンシ(秒)を返す。

        該当する message_id が見つからない場合は -1.0。
        """
        now = speech_start_at if speech_start_at is not None else time.monotonic()
        for rec in reversed(self._records):
            if rec.message_id == message_id and rec.speech_start_at == 0.0:
                rec.speech_start_at = now
                rec.latency_sec = now - rec.received_at
                bisect.insort(self._sorted_latencies, rec.latency_sec)
                # 窓を超えたら古い値を除去
                self._trim_sorted()
                if rec.latency_sec > 4.0:
                    logger.warning(
                        "NFR-LAT-01 violation: %s latency=%.2fs (target < 4.0s)",
                        message_id,
                        rec.latency_sec,
                    )
                return rec.latency_sec
        return -1.0

    def percentile(self, p: float) -> float:
        """レイテンシの P*p* パーセンタイル (0–100)。データ不足なら 0.0。"""
        completed = [r.latency_sec for r in self._records if r.latency_sec > 0]
        if not completed:
            return 0.0
        completed.sort()
        idx = int(len(completed) * p / 100.0)
        idx = min(idx, len(completed) - 1)
        return completed[idx]

    @property
    def p50(self) -> float:
        return self.percentile(50)

    @property
    def p95(self) -> float:
        return self.percentile(95)

    @property
    def p99(self) -> float:
        return self.percentile(99)

    @property
    def count(self) -> int:
        return sum(1 for r in self._records if r.latency_sec > 0)

    def _trim_sorted(self) -> None:
        """_sorted_latencies を窓サイズに収める。"""
        completed = [r.latency_sec for r in self._records if r.latency_sec > 0]
        if len(self._sorted_latencies) > len(completed) + 10:
            self._sorted_latencies = sorted(completed)
