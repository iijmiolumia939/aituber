"""メモリ監視モジュール (NFR-RES-02).

RSS メモリ使用量を定期的にサンプリングし、
60 分あたりの増加量 (MB) を追跡する。
目標: rss_growth_mb_over_60min <= 300.
"""

from __future__ import annotations

import logging
import time
from collections import deque
from dataclasses import dataclass

logger = logging.getLogger(__name__)

_NFR_RES_02_LIMIT_MB = 300


@dataclass
class MemorySample:
    """1 件の RSS サンプル。"""

    ts: float  # monotonic
    rss_mb: float


class MemoryTracker:
    """NFR-RES-02: RSS メモリ増加量の追跡。

    定期的に ``sample()`` を呼び出し、60 分間の RSS 増加量を算出する。
    閾値超過時はログ警告を出力する。
    """

    def __init__(
        self,
        limit_mb: float = _NFR_RES_02_LIMIT_MB,
        window_sec: float = 3600.0,
    ) -> None:
        self._limit_mb = limit_mb
        self._window_sec = window_sec
        self._samples: deque[MemorySample] = deque()

    def sample(self, rss_mb: float | None = None, now: float | None = None) -> float:
        """RSS サンプルを記録し、現在の 60 分増加量 (MB) を返す。

        *rss_mb* を省略すると ``psutil`` から自動取得する。
        """
        now = now if now is not None else time.monotonic()
        if rss_mb is None:
            rss_mb = _get_rss_mb()

        self._samples.append(MemorySample(ts=now, rss_mb=rss_mb))
        self._prune(now)

        growth = self.growth_mb
        if growth > self._limit_mb:
            logger.warning(
                "NFR-RES-02 violation: RSS growth=%.1f MB over %.0fs (limit=%d MB)",
                growth,
                self._window_sec,
                self._limit_mb,
            )
        return growth

    @property
    def growth_mb(self) -> float:
        """窓内の RSS 増加量 (MB)。サンプル不足なら 0.0。"""
        if len(self._samples) < 2:
            return 0.0
        return self._samples[-1].rss_mb - self._samples[0].rss_mb

    @property
    def current_rss_mb(self) -> float:
        """最新の RSS (MB)。サンプルなしなら 0.0。"""
        if not self._samples:
            return 0.0
        return self._samples[-1].rss_mb

    @property
    def sample_count(self) -> int:
        return len(self._samples)

    def _prune(self, now: float) -> None:
        cutoff = now - self._window_sec
        while self._samples and self._samples[0].ts < cutoff:
            self._samples.popleft()


def _get_rss_mb() -> float:
    """現在プロセスの RSS を MB で取得。psutil がなければ 0.0。"""
    try:
        import psutil

        return psutil.Process().memory_info().rss / (1024 * 1024)
    except ImportError:
        logger.debug("psutil not installed; RSS monitoring unavailable")
        return 0.0
    except Exception:
        logger.warning("Failed to get RSS info")
        return 0.0
