"""イベントバス: Orchestrator → Dashboard のデータ通知。

各コンポーネントが emit() でイベントを発行し、
Dashboard が subscribe() で受信してリアルタイム表示する。
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any


class EventType(Enum):
    """ダッシュボードに通知するイベント種別。"""

    # コメント系
    COMMENT_RECEIVED = auto()
    COMMENT_FILTERED = auto()  # Safety NG

    # LLM系
    LLM_REQUEST_START = auto()
    LLM_RESPONSE = auto()
    LLM_TEMPLATE_FALLBACK = auto()

    # TTS系
    TTS_START = auto()
    TTS_COMPLETE = auto()
    TTS_ERROR = auto()

    # アイドルトーク
    IDLE_TALK = auto()

    # システム
    SYSTEM_STATUS = auto()
    COST_UPDATE = auto()
    LATENCY_UPDATE = auto()
    LOG = auto()


@dataclass
class DashboardEvent:
    """ダッシュボードイベント。"""

    type: EventType
    timestamp: float = field(default_factory=time.time)
    data: dict[str, Any] = field(default_factory=dict)


# コールバック型
EventCallback = Callable[[DashboardEvent], Any]


class EventBus:
    """シンプルな非同期イベントバス。"""

    def __init__(self) -> None:
        self._subscribers: list[EventCallback] = []
        self._queue: asyncio.Queue[DashboardEvent] = asyncio.Queue(maxsize=1000)

    def subscribe(self, callback: EventCallback) -> None:
        """イベント受信コールバックを登録。"""
        self._subscribers.append(callback)

    def unsubscribe(self, callback: EventCallback) -> None:
        """コールバックを解除。"""
        self._subscribers = [s for s in self._subscribers if s is not callback]

    def emit(self, event: DashboardEvent) -> None:
        """イベントを発行（非同期コールバック呼び出し）。"""
        for cb in self._subscribers:
            try:
                result = cb(event)
                # awaitableならタスクとして投げる
                if asyncio.iscoroutine(result):
                    try:
                        loop = asyncio.get_running_loop()
                        loop.create_task(result)
                    except RuntimeError:
                        pass
            except Exception:
                pass  # Dashboard がクラッシュしても本体に影響しない

    def emit_simple(self, event_type: EventType, **data: Any) -> None:
        """簡易イベント発行。"""
        self.emit(DashboardEvent(type=event_type, data=data))


# グローバルシングルトン
_bus: EventBus | None = None


def get_event_bus() -> EventBus:
    """グローバルイベントバスを取得。"""
    global _bus
    if _bus is None:
        _bus = EventBus()
    return _bus
