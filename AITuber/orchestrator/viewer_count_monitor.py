"""Viewer count milestone monitor.

FR-VIEWCNT-01: periodically fetch concurrent viewers and trigger milestone hooks.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable, Sequence

logger = logging.getLogger(__name__)

FetchCountFn = Callable[[], Awaitable[int | None]]
MilestoneFn = Callable[[int, int], Awaitable[None]]


class ViewerCountMonitor:
    """Track concurrent viewer milestones for reaction intents."""

    DEFAULT_MILESTONES: tuple[int, ...] = (10, 50, 100, 200, 500, 1000, 5000)

    def __init__(
        self,
        *,
        fetch_count: FetchCountFn,
        on_milestone: MilestoneFn,
        milestones: Sequence[int] | None = None,
    ) -> None:
        self._fetch_count = fetch_count
        self._on_milestone = on_milestone
        self._milestones = tuple(sorted(milestones or self.DEFAULT_MILESTONES))
        self._achieved: set[int] = set()
        self._peak: int = 0

    @property
    def peak(self) -> int:
        return self._peak

    async def check_once(self) -> list[int]:
        """Fetch current count and emit newly reached milestones."""
        current = await self._fetch_count()
        if current is None or current < 0:
            return []

        if current > self._peak:
            self._peak = current

        reached: list[int] = []
        for milestone in self._milestones:
            if milestone in self._achieved:
                continue
            if current >= milestone:
                self._achieved.add(milestone)
                reached.append(milestone)

        for milestone in reached:
            try:
                await self._on_milestone(current, milestone)
            except Exception as exc:  # noqa: BLE001
                logger.warning("Viewer milestone callback failed (%s): %s", milestone, exc)

        return reached

    async def poll_loop(self, *, interval_sec: float, is_running: Callable[[], bool]) -> None:
        """Periodic polling loop."""
        while is_running():
            await self.check_once()
            await asyncio.sleep(interval_sec)
