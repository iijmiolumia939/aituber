"""ViewerCountMonitor tests.

TC-VIEWCNT-01: milestones trigger exactly once.
TC-VIEWCNT-02: no milestone for None/negative counts.
"""

from __future__ import annotations

import pytest

from orchestrator.viewer_count_monitor import ViewerCountMonitor


class TestViewerCountMonitor:
    @pytest.mark.asyncio
    async def test_milestones_trigger_once(self):
        counts = iter([5, 12, 60, 60, 120])
        seen: list[int] = []

        async def _fetch() -> int | None:
            return next(counts)

        async def _on(current: int, milestone: int) -> None:
            seen.append(milestone)

        mon = ViewerCountMonitor(
            fetch_count=_fetch,
            on_milestone=_on,
            milestones=[10, 50, 100],
        )

        await mon.check_once()  # 5
        await mon.check_once()  # 12 -> 10
        await mon.check_once()  # 60 -> 50
        await mon.check_once()  # 60 -> none
        await mon.check_once()  # 120 -> 100

        assert seen == [10, 50, 100]
        assert mon.peak == 120

    @pytest.mark.asyncio
    async def test_none_or_negative_count_is_ignored(self):
        counts = iter([None, -1, 0, 10])
        seen: list[int] = []

        async def _fetch() -> int | None:
            return next(counts)

        async def _on(current: int, milestone: int) -> None:
            seen.append(milestone)

        mon = ViewerCountMonitor(
            fetch_count=_fetch,
            on_milestone=_on,
            milestones=[10],
        )

        await mon.check_once()
        await mon.check_once()
        await mon.check_once()
        await mon.check_once()

        assert seen == [10]
