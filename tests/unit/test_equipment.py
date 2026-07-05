"""Tests for equipment (wear/remove/wield/unwield/equipment), encumbrance,
and equipment-derived modifiers/traits (Sprint 23.1-23.2)."""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from sqlmodel import Session, create_engine

from lorecraft.commands import register_all_commands
from lorecraft.db import create_tables
from lorecraft.game.connection_manager import ConnectionManager
from lorecraft.engine.game.context import GameContext
from lorecraft.features.encumbrance.rules import (
    carry_base,
    encumbrance_band,
    resolve_carry_capacity,
    total_carried_weight,
)
from lorecraft.engine.game.engine import CommandEngine
from lorecraft.engine.game.events import EventBus
from lorecraft.engine.game.holders import Location
from lorecraft.features.items.rules import register_item_rules
from lorecraft.engine.game.modifiers import resolve_for
from lorecraft.engine.game.registry import CommandRegistry
from lorecraft.engine.game.rng import GameRng
from lorecraft.engine.game.rules import RuleEngine
from lorecraft.engine.game.transaction import TransactionContext
from lorecraft.engine.models.player import Player, PlayerStats
from lorecraft.engine.models.world import Room
from lorecraft.engine.repos.item_repo import ItemRepo
from lorecraft.engine.repos.npc_repo import NpcRepo
from lorecraft.engine.repos.player_repo import PlayerRepo
from lorecraft.engine.repos.room_repo import RoomRepo
from lorecraft.engine.repos.stack_repo import StackRepo
from lorecraft.engine.services.effects import EffectService
from lorecraft.engine.services.item_location import ItemLocationService
from lorecraft.engine.services.ledger import LedgerService
from lorecraft.engine.services.meters import MeterService
from lorecraft.world.loader import import_world
from lorecraft.world.validator import ItemData, RoomData, WorldDocument
from lorecraft.features.traits.sources import register as _register_traits
from lorecraft.features.item_components.components import (
    register as _register_item_components,
)
from lorecraft.features.equipment.sources import register as _register_equipment_source
from lorecraft.features.equipment.validators import (
    register as _register_equipment_validators,
)

# Traits, standard components, and equipment sources/validators used to register
# as import side effects; they now register via their feature register()s.
_register_traits()
_register_item_components()
_register_equipment_source()
_register_equipment_validators()

ROOM_ID = "room-1"


def _seed_items(session: Session) -> None:
    document = WorldDocument(
        rooms=[
            RoomData(id=ROOM_ID, name="Room One", description="d", map_x=0, map_y=0)
        ],
        items=[
            ItemData(
                id="iron_helm",
                name="iron helm",
                description="A sturdy helm.",
                slot="head",
                wearable=True,
                weight=2.0,
                effects=[{"type": "stat_bonus", "stat": "vitality", "amount": 3}],
            ),
            ItemData(
                id="ruby_ring",
                name="ruby ring",
                description="A shiny ring.",
                slot="finger",
                wearable=True,
                weight=0.1,
                effects=[{"type": "grant_trait", "trait": "lucky"}],
            ),
            ItemData(
                id="sapphire_ring",
                name="sapphire ring",
                description="Another ring.",
                slot="finger",
                wearable=True,
                weight=0.1,
            ),
            ItemData(
                id="short_sword",
                name="short sword",
                description="A blade.",
                slot="main_hand",
                wearable=False,
                weight=3.0,
            ),
            ItemData(
                id="backpack",
                name="backpack",
                description="Extra storage.",
                slot="back",
                wearable=True,
                weight=1.0,
                capacity=40.0,
                effects=[{"type": "carry_bonus", "amount": 40}],
            ),
            ItemData(
                id="boulder",
                name="boulder",
                description="Extremely heavy.",
                weight=1000.0,
            ),
            ItemData(
                id="lantern",
                name="brass lantern",
                description="A lantern.",
                slot="off_hand",
                wearable=False,
                weight=1.0,
                light=3,
                max_durability=10,
            ),
        ],
    )
    import_world(document, session)


def _build_engine_and_ctx() -> tuple[CommandEngine, GameContext, Session]:
    engine = create_engine("sqlite://")
    create_tables(game_engine=engine, audit_engine=create_engine("sqlite://"))
    session = Session(engine)
    _seed_items(session)
    player = Player(
        id="player-1",
        username="tester",
        current_room_id=ROOM_ID,
        respawn_room_id=ROOM_ID,
    )
    session.add(player)
    session.add(PlayerStats(player_id=player.id))
    session.commit()

    room = session.get(Room, ROOM_ID)
    assert room is not None
    item_location = ItemLocationService(session)
    ctx = GameContext(
        player=player,
        room=room,
        clock=None,
        player_repo=PlayerRepo(session),
        room_repo=RoomRepo(session),
        item_repo=ItemRepo(session),
        stack_repo=StackRepo(session),
        item_location=item_location,
        ledger=LedgerService(),
        rng=GameRng(),
        session=session,
        meters=MeterService(session.get_bind(), GameRng()),
        effects=EffectService(session.get_bind(), GameRng()),
        npc_repo=NpcRepo(session),
        manager=ConnectionManager(),
        bus=EventBus(),
        audit=None,
        transaction=TransactionContext.create(
            actor_id=player.id, correlation_id="session-1"
        ),
        session_id="session-1",
    )
    registry = CommandRegistry()
    register_all_commands(registry)
    rules = RuleEngine()
    register_item_rules(rules)
    return CommandEngine(registry, rules), ctx, session


@pytest.fixture
def built() -> Iterator[tuple[CommandEngine, GameContext, Session]]:
    cmd_engine, ctx, session = _build_engine_and_ctx()
    yield cmd_engine, ctx, session
    session.close()


def _carry(ctx: GameContext, item_id: str, quantity: int = 1) -> None:
    ctx.item_location.spawn(item_id, Location("player", ctx.player.id), quantity)
    ctx.session.commit()


class TestWearRemove:
    def test_wear_moves_item_to_slot(
        self, built: tuple[CommandEngine, GameContext, Session]
    ) -> None:
        cmd_engine, ctx, session = built
        _carry(ctx, "iron_helm")

        cmd_engine.handle_command("wear iron helm", ctx)

        assert ctx.messages == ["You wear the iron helm."]
        stacks = ctx.stack_repo.stacks_for_owner("player", ctx.player.id)
        assert any(s.slot == "head" for s in stacks)

    def test_wear_occupied_slot_reports_conflict(
        self, built: tuple[CommandEngine, GameContext, Session]
    ) -> None:
        cmd_engine, ctx, _session = built
        _carry(ctx, "iron_helm", 2)

        cmd_engine.handle_command("wear iron helm", ctx)
        ctx.messages.clear()
        cmd_engine.handle_command("wear iron helm", ctx)

        assert ctx.messages == ["Slot 'head' is already occupied"]

    def test_wear_non_wearable_item_rejected(
        self, built: tuple[CommandEngine, GameContext, Session]
    ) -> None:
        cmd_engine, ctx, _session = built
        _carry(ctx, "short_sword")

        cmd_engine.handle_command("wear short sword", ctx)

        assert ctx.messages == ["You can't wear the short sword."]

    def test_remove_moves_item_back_to_loose(
        self, built: tuple[CommandEngine, GameContext, Session]
    ) -> None:
        cmd_engine, ctx, _session = built
        _carry(ctx, "iron_helm")
        cmd_engine.handle_command("wear iron helm", ctx)
        ctx.messages.clear()

        cmd_engine.handle_command("remove iron helm", ctx)

        assert ctx.messages == ["You remove the iron helm."]
        stacks = ctx.stack_repo.stacks_for_owner("player", ctx.player.id)
        assert any(s.slot is None for s in stacks)

    def test_ring_wears_into_free_finger_slot(
        self, built: tuple[CommandEngine, GameContext, Session]
    ) -> None:
        cmd_engine, ctx, _session = built
        _carry(ctx, "ruby_ring")
        _carry(ctx, "sapphire_ring")

        cmd_engine.handle_command("wear ruby ring", ctx)
        cmd_engine.handle_command("wear sapphire ring", ctx)

        stacks = ctx.stack_repo.stacks_for_owner("player", ctx.player.id)
        slots = {s.slot for s in stacks if s.slot is not None}
        assert slots == {"finger_l", "finger_r"}


class TestWieldUnwield:
    def test_wield_equips_to_main_hand(
        self, built: tuple[CommandEngine, GameContext, Session]
    ) -> None:
        cmd_engine, ctx, _session = built
        _carry(ctx, "short_sword")

        cmd_engine.handle_command("wield short sword", ctx)

        assert ctx.messages == ["You wield the short sword."]
        stacks = ctx.stack_repo.stacks_for_owner("player", ctx.player.id)
        assert any(s.slot == "main_hand" for s in stacks)

    def test_wield_wearable_item_rejected(
        self, built: tuple[CommandEngine, GameContext, Session]
    ) -> None:
        cmd_engine, ctx, _session = built
        _carry(ctx, "iron_helm")

        cmd_engine.handle_command("wield iron helm", ctx)

        assert ctx.messages == ["You can't wield the iron helm."]

    def test_unwield_returns_to_loose(
        self, built: tuple[CommandEngine, GameContext, Session]
    ) -> None:
        cmd_engine, ctx, _session = built
        _carry(ctx, "short_sword")
        cmd_engine.handle_command("wield short sword", ctx)
        ctx.messages.clear()

        cmd_engine.handle_command("unwield short sword", ctx)

        assert ctx.messages == ["You unwield the short sword."]


class TestEquipmentListing:
    def test_equipment_command_lists_slots(
        self, built: tuple[CommandEngine, GameContext, Session]
    ) -> None:
        cmd_engine, ctx, _session = built
        _carry(ctx, "iron_helm")
        cmd_engine.handle_command("wear iron helm", ctx)
        ctx.messages.clear()

        cmd_engine.handle_command("equipment", ctx)

        assert any("iron helm" in m for m in ctx.messages)

    def test_equipment_command_empty(
        self, built: tuple[CommandEngine, GameContext, Session]
    ) -> None:
        cmd_engine, ctx, _session = built

        cmd_engine.handle_command("equipment", ctx)

        assert ctx.messages == ["You aren't wearing or wielding anything."]


class TestEquipmentModifiersAndTraits:
    def test_equipped_item_contributes_stat_modifier(
        self, built: tuple[CommandEngine, GameContext, Session]
    ) -> None:
        cmd_engine, ctx, session = built
        _carry(ctx, "iron_helm")
        cmd_engine.handle_command("wear iron helm", ctx)

        resolved = resolve_for(
            session, "player", ctx.player.id, "stat.vitality", base=10
        )

        assert resolved == 13

    def test_equipped_item_grants_trait(
        self, built: tuple[CommandEngine, GameContext, Session]
    ) -> None:
        import lorecraft.engine.game.traits as traits_module

        cmd_engine, ctx, session = built
        _carry(ctx, "ruby_ring")
        cmd_engine.handle_command("wear ruby ring", ctx)

        names = traits_module.get_registry().traits_for(
            session, "player", ctx.player.id
        )

        assert "lucky" in names

    def test_unequipping_removes_modifier(
        self, built: tuple[CommandEngine, GameContext, Session]
    ) -> None:
        cmd_engine, ctx, session = built
        _carry(ctx, "iron_helm")
        cmd_engine.handle_command("wear iron helm", ctx)
        cmd_engine.handle_command("remove iron helm", ctx)

        resolved = resolve_for(
            session, "player", ctx.player.id, "stat.vitality", base=10
        )

        assert resolved == 10

    def test_carry_bonus_extends_capacity(
        self, built: tuple[CommandEngine, GameContext, Session]
    ) -> None:
        cmd_engine, ctx, session = built
        base_capacity = resolve_carry_capacity(session, ctx.player.id, 10)

        _carry(ctx, "backpack")
        cmd_engine.handle_command("wear backpack", ctx)

        bonus_capacity = resolve_carry_capacity(session, ctx.player.id, 10)

        assert bonus_capacity == base_capacity + 40


class TestEncumbrance:
    def test_carry_base_scales_with_strength(self) -> None:
        assert carry_base(10) == 80.0
        assert carry_base(20) == 120.0

    def test_encumbrance_band_thresholds(self) -> None:
        assert encumbrance_band(50, 100) == "unburdened"
        assert encumbrance_band(120, 100) == "burdened"
        assert encumbrance_band(160, 100) == "overloaded"

    def test_total_carried_weight_sums_stacks(
        self, built: tuple[CommandEngine, GameContext, Session]
    ) -> None:
        _cmd_engine, ctx, session = built
        _carry(ctx, "iron_helm")

        weight = total_carried_weight(session, ctx.player.id)

        assert weight == 2.0

    def test_take_blocked_when_overloaded(
        self, built: tuple[CommandEngine, GameContext, Session]
    ) -> None:
        cmd_engine, ctx, _session = built
        ctx.item_location.spawn("boulder", Location("room", ROOM_ID))
        ctx.session.commit()

        cmd_engine.handle_command("take boulder", ctx)

        assert ctx.messages == ["You can't carry any more weight."]
        stacks = ctx.stack_repo.stacks_for_owner("player", ctx.player.id)
        assert not stacks


class TestBoundItemRule:
    def test_bound_item_cannot_be_dropped(
        self, built: tuple[CommandEngine, GameContext, Session]
    ) -> None:
        from lorecraft.engine.models.world import Item

        cmd_engine, ctx, session = built
        session.add(
            Item(
                id="heirloom", name="heirloom", description="Family relic.", bound=True
            )
        )
        session.commit()
        ctx.item_location.spawn("heirloom", Location("player", ctx.player.id))
        session.commit()

        cmd_engine.handle_command("drop heirloom", ctx)

        assert ctx.messages == ["The heirloom is bound to you and can't be let go."]
        stacks = ctx.stack_repo.stacks_for_owner("player", ctx.player.id)
        assert any(s.slot is None for s in stacks)
