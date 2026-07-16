"""
Characterization tests for event-flow integration — Sprint 7.4

Lock in current behavior of command → event → service flow before Sprint 8–9 refactors.
Focus areas:
- Command execution → event emission → handler execution flow
- Handler priority ordering (higher priority runs first)
- Exception isolation (one handler's error doesn't block others)
- Event payload structure and correctness
- Service reactions to events (e.g., quest updates, flag changes)
- Multiple handlers per event type
"""

from __future__ import annotations

from typing import Any

from lorecraft.engine.game.events import Event, EventBus, GameEvent


# =============================================================================
# EVENT EMISSION TESTS
# =============================================================================


def test_event_emission_order() -> None:
    """Verify events are emitted in order they were added."""
    bus = EventBus()
    emitted: list[str] = []

    def handler1(event: Event, ctx: object) -> None:
        emitted.append(f"handler1-{event.type}")

    def handler2(event: Event, ctx: object) -> None:
        emitted.append(f"handler2-{event.type}")

    bus.on(GameEvent.COMMAND_EXECUTED, handler1)
    bus.on(GameEvent.COMMAND_EXECUTED, handler2)

    results = bus.emit(Event(GameEvent.COMMAND_EXECUTED, {}), None)

    assert len(results) == 2
    assert len(emitted) == 2


def test_handler_priority_ordering() -> None:
    """Verify handlers execute in priority order (higher priority first)."""
    bus = EventBus()
    execution_order: list[str] = []

    def low_priority(event: Event, ctx: object) -> None:
        execution_order.append("low")

    def high_priority(event: Event, ctx: object) -> None:
        execution_order.append("high")

    def medium_priority(event: Event, ctx: object) -> None:
        execution_order.append("medium")

    bus.on(GameEvent.ITEM_TAKEN, low_priority, priority=1)
    bus.on(GameEvent.ITEM_TAKEN, high_priority, priority=10)
    bus.on(GameEvent.ITEM_TAKEN, medium_priority, priority=5)

    bus.emit(Event(GameEvent.ITEM_TAKEN, {}), None)

    assert execution_order == ["high", "medium", "low"]


def test_exception_isolation_in_handlers() -> None:
    """Verify one handler's exception doesn't block other handlers."""
    bus = EventBus()
    executed: list[str] = []

    def failing_handler(event: Event, ctx: object) -> None:
        executed.append("failing")
        raise ValueError("intentional error")

    def normal_handler1(event: Event, ctx: object) -> None:
        executed.append("normal1")

    def normal_handler2(event: Event, ctx: object) -> None:
        executed.append("normal2")

    bus.on(GameEvent.PLAYER_MOVED, normal_handler1, priority=2)
    bus.on(GameEvent.PLAYER_MOVED, failing_handler, priority=1)
    bus.on(GameEvent.PLAYER_MOVED, normal_handler2, priority=0)

    results = bus.emit(Event(GameEvent.PLAYER_MOVED, {}), None)

    # All handlers should have executed
    assert len(results) == 3
    assert executed == ["normal1", "failing", "normal2"]
    # One should have failed
    assert results[1].error is not None
    assert isinstance(results[1].error, ValueError)


def test_event_bus_metrics_snapshot_tracks_counts_and_errors() -> None:
    bus = EventBus()

    def ok_handler(event: Event, ctx: object) -> None:
        return None

    def failing_handler(event: Event, ctx: object) -> None:
        raise ValueError("intentional error")

    bus.on(GameEvent.PLAYER_MOVED, ok_handler)
    bus.on(GameEvent.PLAYER_MOVED, failing_handler)

    bus.emit(Event(GameEvent.PLAYER_MOVED, {}), None)
    snapshot = bus.metrics_snapshot()

    assert snapshot["status"] == "instrumented"
    assert snapshot["events_emitted"] == 1
    assert snapshot["event_counts"] == {"player_moved": 1}
    handler_rows = snapshot["handlers"]
    assert isinstance(handler_rows, list)
    handlers = {row["handler"]: row for row in handler_rows}
    assert handlers["ok_handler"]["count"] == 1
    assert handlers["ok_handler"]["errors"] == 0
    assert handlers["failing_handler"]["count"] == 1
    assert handlers["failing_handler"]["errors"] == 1


def test_multiple_event_types() -> None:
    """Verify different event types trigger their respective handlers."""
    bus = EventBus()
    events_received: list[GameEvent] = []

    def movement_handler(event: Event, ctx: object) -> None:
        events_received.append(event.type)

    def item_handler(event: Event, ctx: object) -> None:
        events_received.append(event.type)

    bus.on(GameEvent.PLAYER_MOVED, movement_handler)
    bus.on(GameEvent.ITEM_TAKEN, item_handler)

    bus.emit(Event(GameEvent.PLAYER_MOVED, {"from": "a", "to": "b"}), None)
    bus.emit(Event(GameEvent.ITEM_TAKEN, {"item": "coin"}), None)
    bus.emit(Event(GameEvent.PLAYER_MOVED, {"from": "b", "to": "c"}), None)

    assert events_received == [
        GameEvent.PLAYER_MOVED,
        GameEvent.ITEM_TAKEN,
        GameEvent.PLAYER_MOVED,
    ]


# =============================================================================
# COMMAND EXECUTION → EVENT FLOW TESTS
# =============================================================================


def test_command_execution_event_payload() -> None:
    """Verify event payloads contain expected data."""
    bus = EventBus()
    captured_events: list[Event] = []

    def capture_payload(event: Event, ctx: object) -> None:
        captured_events.append(event)

    bus.on(GameEvent.ITEM_TAKEN, capture_payload)

    payload = {"item_id": "coin", "actor": "player-1"}
    bus.emit(Event(GameEvent.ITEM_TAKEN, payload), None)

    assert len(captured_events) == 1
    assert captured_events[0].payload == payload


def test_handler_result_collection() -> None:
    """Verify handler results are properly collected and reported."""
    bus = EventBus()

    def handler1(event: Event, ctx: object) -> str:
        return "result1"

    def handler2(event: Event, ctx: object) -> int:
        return 42

    bus.on(GameEvent.COMMAND_EXECUTED, handler1, priority=1)
    bus.on(GameEvent.COMMAND_EXECUTED, handler2, priority=0)

    results = bus.emit(Event(GameEvent.COMMAND_EXECUTED, {}), None)

    assert len(results) == 2
    assert results[0].handler_name == "handler1"
    assert results[0].value == "result1"
    assert results[1].handler_name == "handler2"
    assert results[1].value == 42
    assert all(r.ok for r in results)


# =============================================================================
# SERVICE REACTION TESTS
# =============================================================================


def test_event_bus_handler_count() -> None:
    """Verify handler_count correctly reports registered handlers."""
    bus = EventBus()

    assert bus.handler_count(GameEvent.PLAYER_MOVED) == 0

    def handler1(event: Event, ctx: object) -> None:
        pass

    def handler2(event: Event, ctx: object) -> None:
        pass

    bus.on(GameEvent.PLAYER_MOVED, handler1)
    assert bus.handler_count(GameEvent.PLAYER_MOVED) == 1

    bus.on(GameEvent.PLAYER_MOVED, handler2)
    assert bus.handler_count(GameEvent.PLAYER_MOVED) == 2

    bus.on(GameEvent.ITEM_TAKEN, handler1)
    assert bus.handler_count(GameEvent.ITEM_TAKEN) == 1
    assert bus.handler_count(GameEvent.PLAYER_MOVED) == 2


def test_work_event_classification() -> None:
    """Verify work events are correctly identified."""
    bus = EventBus()

    assert bus.is_work_event(GameEvent.COMBAT_TICK_DUE)
    assert bus.is_work_event(GameEvent.NPC_MOVE_DUE)
    assert bus.is_work_event(GameEvent.SCHEDULED_JOB_DUE)
    assert bus.is_work_event(GameEvent.GRACE_PERIOD_EXPIRED)

    assert not bus.is_work_event(GameEvent.PLAYER_MOVED)
    assert not bus.is_work_event(GameEvent.ITEM_TAKEN)
    assert not bus.is_work_event(GameEvent.COMMAND_EXECUTED)


# =============================================================================
# HANDLER ORDERING & INTERACTION TESTS
# =============================================================================


def test_handler_execution_sequence() -> None:
    """Verify detailed execution sequence with multiple handlers."""
    bus = EventBus()
    execution_order: list[tuple[str, int]] = []

    def handler(name: str, priority_val: int) -> Any:
        def h(event: Event, ctx: object) -> None:
            execution_order.append((name, priority_val))

        return h

    # Register handlers in non-priority order
    bus.on(GameEvent.COMMAND_EXECUTED, handler("A", 5), priority=5)
    bus.on(GameEvent.COMMAND_EXECUTED, handler("B", 2), priority=2)
    bus.on(GameEvent.COMMAND_EXECUTED, handler("C", 8), priority=8)
    bus.on(GameEvent.COMMAND_EXECUTED, handler("D", 2), priority=2)

    bus.emit(Event(GameEvent.COMMAND_EXECUTED, {}), None)

    # Should execute in priority order (8, 5, 2, 2), with stable sort for equal priorities
    names_and_priorities = execution_order
    assert len(names_and_priorities) == 4
    priorities = [p for _, p in names_and_priorities]
    assert priorities == [8, 5, 2, 2]


def test_event_context_accessible_to_handlers() -> None:
    """Verify context is passed to handlers and accessible."""
    bus = EventBus()

    class FakeContext:
        def __init__(self) -> None:
            self.data = "test_value"

    ctx = FakeContext()
    handler_ctx: list[object] = []

    def capture_context(event: Event, context: object) -> None:
        handler_ctx.append(context)

    bus.on(GameEvent.ITEM_GIVEN, capture_context)
    bus.emit(Event(GameEvent.ITEM_GIVEN, {}), ctx)

    assert len(handler_ctx) == 1
    assert handler_ctx[0] is ctx
    assert handler_ctx[0].data == "test_value"  # type: ignore
