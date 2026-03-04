"""イベントバスのテスト。"""

from __future__ import annotations

from orchestrator.event_bus import DashboardEvent, EventBus, EventType, get_event_bus


class TestEventType:
    """EventType enum のテスト。"""

    def test_all_types_defined(self) -> None:
        expected = {
            "COMMENT_RECEIVED",
            "COMMENT_FILTERED",
            "LLM_REQUEST_START",
            "LLM_RESPONSE",
            "LLM_TEMPLATE_FALLBACK",
            "TTS_START",
            "TTS_COMPLETE",
            "TTS_ERROR",
            "IDLE_TALK",
            "SYSTEM_STATUS",
            "COST_UPDATE",
            "LATENCY_UPDATE",
            "LOG",
        }
        actual = {e.name for e in EventType}
        assert expected.issubset(actual)


class TestDashboardEvent:
    """DashboardEvent データクラスのテスト。"""

    def test_default_timestamp(self) -> None:
        ev = DashboardEvent(type=EventType.LOG)
        assert ev.timestamp > 0
        assert ev.data == {}

    def test_custom_data(self) -> None:
        ev = DashboardEvent(type=EventType.COST_UPDATE, data={"cost": 1.5})
        assert ev.data["cost"] == 1.5


class TestEventBus:
    """EventBus の subscribe / emit / emit_simple テスト。"""

    def test_subscribe_and_emit(self) -> None:
        bus = EventBus()
        received: list[DashboardEvent] = []
        bus.subscribe(received.append)

        bus.emit_simple(EventType.LOG, message="hello")
        assert len(received) == 1
        assert received[0].type == EventType.LOG
        assert received[0].data["message"] == "hello"

    def test_multiple_subscribers(self) -> None:
        bus = EventBus()
        a: list[DashboardEvent] = []
        b: list[DashboardEvent] = []
        bus.subscribe(a.append)
        bus.subscribe(b.append)

        bus.emit_simple(EventType.TTS_START, text="test")
        assert len(a) == 1
        assert len(b) == 1

    def test_unsubscribe(self) -> None:
        bus = EventBus()
        received: list[DashboardEvent] = []
        cb = received.append
        bus.subscribe(cb)
        bus.unsubscribe(cb)

        bus.emit_simple(EventType.LOG, message="gone")
        assert len(received) == 0

    def test_emit_with_event_object(self) -> None:
        bus = EventBus()
        received: list[DashboardEvent] = []
        bus.subscribe(received.append)

        ev = DashboardEvent(
            type=EventType.COMMENT_RECEIVED,
            data={"author": "alice", "text": "hi"},
        )
        bus.emit(ev)
        assert len(received) == 1
        assert received[0].data["author"] == "alice"

    def test_subscriber_exception_does_not_crash(self) -> None:
        bus = EventBus()

        def bad_cb(event: DashboardEvent) -> None:
            raise RuntimeError("intentional")

        good: list[DashboardEvent] = []
        bus.subscribe(bad_cb)
        bus.subscribe(good.append)

        bus.emit_simple(EventType.LOG, message="ok")
        # good subscriber still receives the event
        assert len(good) == 1

    def test_emit_simple_creates_event(self) -> None:
        bus = EventBus()
        received: list[DashboardEvent] = []
        bus.subscribe(received.append)

        bus.emit_simple(EventType.IDLE_TALK, text="zzz", cost=0.01)
        ev = received[0]
        assert ev.type == EventType.IDLE_TALK
        assert ev.data["text"] == "zzz"
        assert ev.data["cost"] == 0.01
        assert ev.timestamp > 0


class TestGetEventBus:
    """get_event_bus シングルトンのテスト。"""

    def test_returns_same_instance(self) -> None:
        bus1 = get_event_bus()
        bus2 = get_event_bus()
        assert bus1 is bus2

    def test_is_event_bus(self) -> None:
        bus = get_event_bus()
        assert isinstance(bus, EventBus)
