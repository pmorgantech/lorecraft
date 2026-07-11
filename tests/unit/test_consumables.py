"""Consumable items — the eat/drink/quaff mechanism.

Covers the one-shot effect dispatcher (heal + apply_effect), the category gate,
single-unit destruction, and command-level routing of eat/drink/quaff.
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from sqlmodel import Session, create_engine

from lorecraft.db import create_tables
from lorecraft.engine.game.connection_manager import ConnectionManager
from lorecraft.engine.game.context import GameContext
from lorecraft.engine.game.events import EventBus
from lorecraft.engine.game.holders import Location
from lorecraft.engine.game.meters import MeterDef
from lorecraft.engine.game.meters import get_registry as get_meter_registry
from lorecraft.engine.game.modifiers import resolve_for
from lorecraft.engine.game.registry import CommandRegistry
from lorecraft.engine.game.rng import GameRng
from lorecraft.engine.game.transaction import TransactionContext
from lorecraft.engine.models.player import Player, PlayerStats
from lorecraft.engine.models.world import Item, Room
from lorecraft.engine.repos.item_repo import ItemRepo
from lorecraft.engine.repos.meter_repo import MeterRepo
from lorecraft.engine.repos.npc_repo import NpcRepo
from lorecraft.engine.repos.player_repo import PlayerRepo
from lorecraft.engine.repos.room_repo import RoomRepo
from lorecraft.engine.repos.stack_repo import StackRepo
from lorecraft.engine.services.effects import EffectService
from lorecraft.engine.services.item_location import ItemLocationService
from lorecraft.engine.services.ledger import LedgerService
from lorecraft.engine.services.meters import MeterService
from lorecraft.features.consumables.buffs import FORTIFIED_KEY
from lorecraft.features.consumables.buffs import register as register_buffs
from lorecraft.features.consumables.commands import register_consumable_commands
from lorecraft.features.consumables.effects import apply_consumable_effects
from lorecraft.features.consumables.service import ConsumableService


@pytest.fixture
def meter_defs() -> Iterator[None]:
    """Register the hp + fatigue meters (start empty, so a heal shows a gain)."""
    registry = get_meter_registry()
    registry.register(
        MeterDef(key="hp", base_maximum=lambda et, eid, s: 100.0, start_full=False)
    )
    registry.register(
        MeterDef(key="fatigue", base_maximum=lambda et, eid, s: 100.0, start_full=False)
    )
    yield
    registry._defs.pop("hp", None)  # type: ignore[attr-defined]
    registry._defs.pop("fatigue", None)  # type: ignore[attr-defined]


def _engine():
    engine = create_engine("sqlite://")
    create_tables(game_engine=engine, audit_engine=create_engine("sqlite://"))
    return engine


def _seed(session: Session, *items: Item) -> Player:
    session.add(Room(id="tavern", name="Tavern", description="Warm.", map_x=0, map_y=0))
    player = Player(
        id="p1", username="petem", current_room_id="tavern", respawn_room_id="tavern"
    )
    session.add(player)
    session.add(PlayerStats(player_id="p1"))
    for item in items:
        session.add(item)
    session.commit()
    return player


def _give(session: Session, item_id: str, *, quantity: int = 1) -> None:
    ItemLocationService(session).spawn(item_id, Location("player", "p1"), quantity)
    session.commit()


def _build_context(session: Session, player: Player) -> GameContext:
    room = session.get(Room, player.current_room_id)
    assert room is not None
    return GameContext(
        player=player,
        room=room,
        clock=None,
        player_repo=PlayerRepo(session),
        room_repo=RoomRepo(session),
        item_repo=ItemRepo(session),
        stack_repo=StackRepo(session),
        item_location=ItemLocationService(session),
        ledger=LedgerService(),
        rng=GameRng(),
        session=session,
        meters=MeterService(session.get_bind(), GameRng()),
        effects=EffectService(session.get_bind(), GameRng()),
        npc_repo=NpcRepo(session),
        manager=ConnectionManager(),
        bus=EventBus(),
        audit=None,
        transaction=TransactionContext.create(actor_id="p1", correlation_id="s1"),
        session_id="s1",
    )


def _food(item_id: str, name: str, effects=None) -> Item:
    return Item(
        id=item_id, name=name, description="x", category="food", effects=effects or []
    )


def _drink(item_id: str, name: str, effects=None) -> Item:
    return Item(
        id=item_id, name=name, description="x", category="drink", effects=effects or []
    )


def _carried_quantity(session: Session, item_id: str) -> int:
    return sum(
        stack.quantity
        for stack in StackRepo(session).stacks_for_owner("player", "p1")
        if stack.item_id == item_id
    )


class TestHealDescriptor:
    def test_heal_hp_adjusts_the_meter(self, meter_defs: None) -> None:
        engine = _engine()
        with Session(engine) as session:
            player = _seed(
                session,
                _drink(
                    "tonic",
                    "Healing Tonic",
                    [{"type": "heal", "meter": "hp", "amount": 35}],
                ),
            )
            _give(session, "tonic")
            ctx = _build_context(session, player)

            ConsumableService().drink("tonic", ctx)
            session.commit()

            meter = MeterRepo(session).find("player", "p1", "hp")
            assert meter is not None and meter.current == 35.0
        assert "You recover 35 hp." in ctx.messages

    def test_heal_targets_generic_meter_key_fatigue(self, meter_defs: None) -> None:
        engine = _engine()
        with Session(engine) as session:
            player = _seed(
                session,
                _drink(
                    "cordial",
                    "Stamina Restorative",
                    [
                        {
                            "type": "heal",
                            "meter": "fatigue",
                            "amount": 40,
                            "message": "A second wind fills you.",
                        }
                    ],
                ),
            )
            _give(session, "cordial")
            ctx = _build_context(session, player)

            ConsumableService().drink("cordial", ctx)
            session.commit()

            meter = MeterRepo(session).find("player", "p1", "fatigue")
            assert meter is not None and meter.current == 40.0
        assert "A second wind fills you." in ctx.messages


class TestApplyEffectDescriptor:
    def test_apply_effect_registers_an_active_effect(self, meter_defs: None) -> None:
        register_buffs()
        engine = _engine()
        with Session(engine) as session:
            player = _seed(
                session,
                _drink(
                    "vigor",
                    "Draught of Vigor",
                    [
                        {
                            "type": "apply_effect",
                            "effect_key": FORTIFIED_KEY,
                            "duration_ticks": 40,
                            "payload": {"amount": 2},
                        }
                    ],
                ),
            )
            _give(session, "vigor")
            ctx = _build_context(session, player)

            ConsumableService().drink("vigor", ctx)
            session.commit()

            active = EffectService(engine, GameRng()).active_for(
                session, "player", "p1"
            )
            assert [e.effect_key for e in active] == [FORTIFIED_KEY]
            # The buff surfaces through the shared modifier resolver.
            assert resolve_for(session, "player", "p1", "stat.strength", 10.0) == 12.0


class TestCategoryGate:
    def test_eating_a_drink_is_rejected_and_keeps_the_item(
        self, meter_defs: None
    ) -> None:
        engine = _engine()
        with Session(engine) as session:
            player = _seed(session, _drink("ale", "Tankard of Ale"))
            _give(session, "ale")
            ctx = _build_context(session, player)

            ConsumableService().eat("ale", ctx)
            session.commit()

            assert _carried_quantity(session, "ale") == 1
        assert "You can't eat that." in ctx.messages

    def test_drinking_food_is_rejected(self, meter_defs: None) -> None:
        engine = _engine()
        with Session(engine) as session:
            player = _seed(session, _food("loaf", "Crusty Loaf"))
            _give(session, "loaf")
            ctx = _build_context(session, player)

            ConsumableService().drink("loaf", ctx)
            session.commit()

            assert _carried_quantity(session, "loaf") == 1
        assert "You can't drink that." in ctx.messages


class TestDestruction:
    def test_consuming_removes_exactly_one_unit(self, meter_defs: None) -> None:
        engine = _engine()
        with Session(engine) as session:
            player = _seed(session, _food("loaf", "Crusty Loaf"))
            _give(session, "loaf", quantity=2)
            ctx = _build_context(session, player)

            ConsumableService().eat("loaf", ctx)
            session.commit()

            assert _carried_quantity(session, "loaf") == 1
        assert "You eat the Crusty Loaf." in ctx.messages
        assert "petem eats the Crusty Loaf." in ctx.room_messages

    def test_effect_free_food_is_still_consumed(self, meter_defs: None) -> None:
        engine = _engine()
        with Session(engine) as session:
            player = _seed(session, _food("apple", "Apple"))
            _give(session, "apple")
            ctx = _build_context(session, player)

            ConsumableService().eat("apple", ctx)
            session.commit()

            assert _carried_quantity(session, "apple") == 0

    def test_consuming_something_you_lack_is_a_no_op(self, meter_defs: None) -> None:
        engine = _engine()
        with Session(engine) as session:
            player = _seed(session, _food("loaf", "Crusty Loaf"))
            ctx = _build_context(session, player)

            ConsumableService().eat("loaf", ctx)

        assert "You don't have that." in ctx.messages


class TestCommands:
    def test_eat_drink_quaff_route_to_service(self, meter_defs: None) -> None:
        registry = CommandRegistry()
        register_consumable_commands(registry, ConsumableService())
        for verb in ("eat", "drink", "quaff"):
            assert registry.get(verb) is not None

        engine = _engine()
        with Session(engine) as session:
            player = _seed(
                session,
                _drink(
                    "water",
                    "Flask of Water",
                    [{"type": "heal", "meter": "hp", "amount": 5}],
                ),
            )
            _give(session, "water")
            ctx = _build_context(session, player)

            quaff = registry.get("quaff")
            assert quaff is not None
            quaff.handler("water", ctx)
            session.commit()

            assert _carried_quantity(session, "water") == 0
        assert "You drink the Flask of Water." in ctx.messages


def test_apply_consumable_effects_ignores_unknown_descriptor(
    meter_defs: None,
) -> None:
    """An unrecognised descriptor type is skipped (content-lint's concern), not
    a runtime error — the dispatcher stays general."""
    engine = _engine()
    with Session(engine) as session:
        player = _seed(session, _food("odd", "Odd Snack", [{"type": "teleport"}]))
        ctx = _build_context(session, player)
        apply_consumable_effects(session.get(Item, "odd"), ctx)  # type: ignore[arg-type]
    assert ctx.messages == []
