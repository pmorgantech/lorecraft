from lorecraft.engine.game.events import Event, EventBus, GameEvent


def test_event_bus_runs_handlers_by_priority() -> None:
    bus = EventBus()
    calls: list[str] = []

    bus.on(GameEvent.PLAYER_MOVED, lambda event, ctx: calls.append("low"), priority=0)
    bus.on(GameEvent.PLAYER_MOVED, lambda event, ctx: calls.append("high"), priority=10)

    bus.emit(Event(GameEvent.PLAYER_MOVED, {"room_id": "square"}), ctx=None)

    assert calls == ["high", "low"]


def test_event_bus_isolates_handler_exceptions() -> None:
    bus = EventBus()
    calls: list[str] = []

    def broken(event, ctx):
        raise RuntimeError("boom")

    bus.on(GameEvent.ITEM_TAKEN, broken)
    bus.on(GameEvent.ITEM_TAKEN, lambda event, ctx: calls.append("ok"))

    results = bus.emit(Event(GameEvent.ITEM_TAKEN), ctx=None)

    assert [result.ok for result in results] == [False, True]
    assert calls == ["ok"]


def test_event_bus_identifies_work_events() -> None:
    bus = EventBus()

    assert bus.is_work_event(GameEvent.NPC_MOVE_DUE) is True
    assert bus.is_work_event(GameEvent.PLAYER_MOVED) is False


def test_event_bus_reports_handler_count() -> None:
    bus = EventBus()

    bus.on(GameEvent.PLAYER_MOVED, lambda event, ctx: None)

    assert bus.handler_count(GameEvent.PLAYER_MOVED) == 1
    assert bus.handler_count(GameEvent.ITEM_TAKEN) == 0


def test_event_bus_records_handler_duration() -> None:
    bus = EventBus()
    bus.on(GameEvent.PLAYER_MOVED, lambda event, ctx: None)

    results = bus.emit(Event(GameEvent.PLAYER_MOVED), ctx=None)

    assert len(results) == 1
    assert results[0].duration_ms >= 0.0


def test_event_bus_records_handler_duration_even_on_error() -> None:
    bus = EventBus()

    def broken(event, ctx):
        raise RuntimeError("boom")

    bus.on(GameEvent.ITEM_TAKEN, broken)

    results = bus.emit(Event(GameEvent.ITEM_TAKEN), ctx=None)

    assert results[0].ok is False
    assert results[0].duration_ms >= 0.0
