"""The `harvest` active ability: data layer, depletable-node service, and the
flag-gated verb + flavor aliases (roadmap_world.md gap #2).

Mirrors `test_forage.py`'s harness for the command/service tests, adding the
zone-energy plumbing (channel config + lazy state) `harvest` draws down.
"""

from __future__ import annotations

import pytest
from sqlmodel import Session, create_engine

from lorecraft.db import create_tables
from lorecraft.engine.game.connection_manager import ConnectionManager
from lorecraft.engine.game.context import GameContext
from lorecraft.engine.game.engine import CommandEngine
from lorecraft.engine.game.events import EventBus
from lorecraft.engine.game.holders import Location
from lorecraft.engine.game.registry import CommandRegistry
from lorecraft.engine.game.rng import GameRng
from lorecraft.engine.game.rules import RuleEngine
from lorecraft.engine.game.transaction import TransactionContext
from lorecraft.engine.models.player import Player, PlayerStats
from lorecraft.engine.models.world import Item, Room
from lorecraft.engine.models.zone_energy import (
    ZoneEnergyChannelConfig,
    ZoneEnergyState,
)
from lorecraft.engine.repos.item_repo import ItemRepo
from lorecraft.engine.repos.npc_repo import NpcRepo
from lorecraft.engine.repos.player_repo import PlayerRepo
from lorecraft.engine.repos.room_repo import RoomRepo
from lorecraft.engine.repos.stack_repo import StackRepo
from lorecraft.engine.repos.zone_energy_repo import ZoneEnergyRepo
from lorecraft.engine.services.effects import EffectService
from lorecraft.engine.services.item_location import ItemLocationService
from lorecraft.engine.services.ledger import LedgerService
from lorecraft.engine.services.meters import MeterService
from lorecraft.engine.services.zone_energy import ZoneEnergyService
from lorecraft.errors import NotFoundError
from lorecraft.features.living_energy.channels import CHANNELS
from lorecraft.features.living_energy.commands import register_living_energy_commands
from lorecraft.features.living_energy.harvest import (
    HarvestDocument,
    HarvestProfile,
    HarvestRegistry,
    HarvestService,
    load_harvest_yaml,
    validate_harvest_document,
)

ROOM_ID = "vault_chamber"
ZONE = "test_zone"
CHANNEL = "emberthorn"  # a real channel from CHANNELS
YIELD_ITEM = "emberthorn_vitriol_vial"


# --------------------------------------------------------------------------- #
# H2 — data layer                                                             #
# --------------------------------------------------------------------------- #


def _profile(
    *,
    channel: str = CHANNEL,
    difficulty: int = 10,
    draw_amount: float = 8.0,
    min_harvestable: float = 4.0,
    zones: list[str] | None = None,
    yields: list[str] | None = None,
) -> HarvestProfile:
    return HarvestProfile(
        channel=channel,
        discipline="survival",
        check_key="skill.survival",
        difficulty=difficulty,
        draw_amount=draw_amount,
        min_harvestable=min_harvestable,
        yields=yields if yields is not None else [YIELD_ITEM],
        zones=zones if zones is not None else [ZONE],
    )


def test_validate_harvest_document_round_trip() -> None:
    doc = validate_harvest_document(
        {
            "version": 1,
            "profiles": [
                {
                    "channel": "lumenroot",
                    "discipline": "survival",
                    "check_key": "skill.survival",
                    "difficulty": 15,
                    "draw_amount": 8.0,
                    "min_harvestable": 10.0,
                    "yields": ["lumenroot_sap_vial"],
                    "zones": ["whisperwood"],
                }
            ],
        }
    )
    assert isinstance(doc, HarvestDocument)
    assert doc.profiles[0].channel == "lumenroot"
    assert doc.profiles[0].zones == ["whisperwood"]
    assert doc.profiles[0].required_tool is None


def test_harvest_profile_rejects_empty_and_negative() -> None:
    with pytest.raises(ValueError):
        HarvestProfile(
            channel="",
            discipline="survival",
            check_key="skill.survival",
            difficulty=10,
            draw_amount=8.0,
            min_harvestable=4.0,
        )
    with pytest.raises(ValueError):
        HarvestProfile(
            channel="lumenroot",
            discipline="survival",
            check_key="skill.survival",
            difficulty=10,
            draw_amount=-1.0,
            min_harvestable=4.0,
        )


def test_registry_rejects_unknown_channel() -> None:
    registry = HarvestRegistry()
    with pytest.raises(NotFoundError):
        registry.register(_profile(channel="not_a_channel"))


def test_registry_lookup_and_is_empty() -> None:
    registry = HarvestRegistry()
    assert registry.is_empty()
    registry.register(_profile(channel="lumenroot"))
    assert not registry.is_empty()
    assert registry.get("lumenroot") is not None
    assert registry.get("dreamveil") is None


def test_world_harvest_yaml_round_trip() -> None:
    doc = load_harvest_yaml("world_content/harvest.yaml")
    channels = {p.channel for p in doc.profiles}
    assert channels == set(CHANNELS)
    # Every profile references a real channel, so load_document does not raise.
    registry = HarvestRegistry()
    registry.load_document(doc)
    for channel in CHANNELS:
        profile = registry.get(channel)
        assert profile is not None
        assert profile.zones  # each channel is present in at least one zone


# --------------------------------------------------------------------------- #
# H3 — service                                                                 #
# --------------------------------------------------------------------------- #


def _build(
    *,
    seed: int,
    profile: HarvestProfile | None = None,
    zone: str | None = ZONE,
    survival: int = 95,
    seed_item: bool = True,
    seed_state: float | None = None,
    baseline: float = 50.0,
) -> tuple[HarvestService, GameContext, Session]:
    engine = create_engine("sqlite://")
    create_tables(game_engine=engine, audit_engine=create_engine("sqlite://"))
    session = Session(engine)
    session.add(
        Room(
            id=ROOM_ID,
            name="Vault Chamber",
            description="d",
            map_x=0,
            map_y=0,
            terrain="normal",
            zone=zone,
        )
    )
    if seed_item:
        session.add(
            Item(id=YIELD_ITEM, name="Vial of Emberthorn Vitriol", description="d")
        )
    # Channel config so ZoneEnergyService.get() can lazily seed the node.
    session.add(
        ZoneEnergyChannelConfig(
            channel=CHANNEL, baseline=baseline, max_intensity=100.0, regen_per_tick=4.0
        )
    )
    if seed_state is not None and zone is not None:
        session.add(ZoneEnergyState(zone=zone, channel=CHANNEL, intensity=seed_state))
    player = Player(
        id="player-1",
        username="tester",
        current_room_id=ROOM_ID,
        respawn_room_id=ROOM_ID,
        flags={"ability.harvest": True},
    )
    session.add(player)
    session.add(
        PlayerStats(player_id=player.id, discipline_ranks={"survival": survival})
    )
    session.commit()

    room = session.get(Room, ROOM_ID)
    assert room is not None
    ctx = GameContext(
        player=player,
        room=room,
        clock=None,
        player_repo=PlayerRepo(session),
        room_repo=RoomRepo(session),
        item_repo=ItemRepo(session),
        stack_repo=StackRepo(session),
        item_location=ItemLocationService(session),
        ledger=LedgerService(),
        rng=GameRng(seed=seed),
        session=session,
        meters=MeterService(session.get_bind(), GameRng()),
        effects=EffectService(session.get_bind(), GameRng()),
        npc_repo=NpcRepo(session),
        manager=ConnectionManager(),
        bus=EventBus(),
        audit=None,
        transaction=TransactionContext.create(actor_id=player.id, correlation_id="s1"),
        session_id="s1",
    )
    registry = HarvestRegistry()
    registry.register(profile or _profile())
    service = HarvestService(
        registry=registry, zone_energy=ZoneEnergyService(session.get_bind())
    )
    return service, ctx, session


def _carries(ctx: GameContext, item_id: str) -> bool:
    return ctx.stack_repo.quantity_of(Location("player", ctx.player.id), item_id) > 0


def _intensity(session: Session, zone: str, channel: str) -> float | None:
    state = ZoneEnergyRepo(session).find(zone, channel)
    return None if state is None else state.intensity


def test_zone_energy_injection_is_used_verbatim() -> None:
    """An injected ZoneEnergyService is reused as-is (no lazy rebuild) — the
    composition-layer wiring path that shares main.py's sweep singleton."""
    service, ctx, session = _build(seed=1)
    try:
        injected = ZoneEnergyService(session.get_bind())
        harvest = HarvestService(registry=service._registry, zone_energy=injected)
        assert harvest._zone_energy_service(ctx) is injected
    finally:
        session.close()


def test_zone_energy_lazy_fallback_builds_from_session_bind() -> None:
    """Without injection, the service type-safely narrows Session.get_bind()'s
    Engine | Connection union to a concrete Engine and still harvests."""
    for seed in range(50):
        service, ctx, session = _build(seed=seed, survival=95, baseline=50.0)
        try:
            uninjected = HarvestService(registry=service._registry)
            resolved = uninjected._zone_energy_service(ctx)
            assert isinstance(resolved, ZoneEnergyService)
            uninjected.harvest(ctx, CHANNEL)
            if any("You harvest the" in m for m in ctx.messages):
                assert _carries(ctx, YIELD_ITEM)
                return
        finally:
            session.close()
    pytest.fail("no seed produced a successful harvest in 50 tries")


def test_register_living_energy_commands_accepts_zone_energy() -> None:
    """The verb-registration seam forwards an injected ZoneEnergyService without
    error (main.py -> register_all_commands -> here threading)."""
    _service, _ctx, session = _build(seed=1)
    try:
        registry = CommandRegistry()
        register_living_energy_commands(
            registry, zone_energy=ZoneEnergyService(session.get_bind())
        )
        assert registry.get("harvest") is not None
    finally:
        session.close()


def test_harvest_success_draws_down_and_grants() -> None:
    for seed in range(50):
        service, ctx, session = _build(seed=seed, survival=95, baseline=50.0)
        try:
            service.harvest(ctx, CHANNEL)
            if any("You harvest the" in m for m in ctx.messages):
                assert _carries(ctx, YIELD_ITEM)
                # Baseline 50 drawn down by draw_amount 8.
                assert _intensity(session, ZONE, CHANNEL) == 50.0 - 8.0
                return
        finally:
            session.close()
    pytest.fail("no seed produced a successful harvest in 50 tries")


def test_harvest_skill_failure_no_draw() -> None:
    for seed in range(50):
        service, ctx, session = _build(seed=seed, survival=0)
        try:
            service.harvest(ctx, CHANNEL)
            if any("come away with nothing" in m for m in ctx.messages):
                assert not _carries(ctx, YIELD_ITEM)
                # Failure returns before the node is even read — no state row.
                assert _intensity(session, ZONE, CHANNEL) is None
                return
        finally:
            session.close()
    pytest.fail("no seed produced a failed harvest in 50 tries")


def test_harvest_exhausted_node_fails_with_no_draw() -> None:
    # Node pre-seeded below the harvestable floor (min_harvestable 4).
    for seed in range(50):
        service, ctx, session = _build(
            seed=seed,
            survival=95,
            profile=_profile(min_harvestable=4.0, draw_amount=8.0),
            seed_state=2.0,
        )
        try:
            service.harvest(ctx, CHANNEL)
            if any("is spent" in m for m in ctx.messages):
                assert not _carries(ctx, YIELD_ITEM)
                assert _intensity(session, ZONE, CHANNEL) == 2.0  # untouched
                return
        finally:
            session.close()
    pytest.fail("no seed reached the exhaustion branch in 50 tries")


def test_harvest_at_floor_reads_exhausted_no_draw() -> None:
    # Node pre-seeded exactly at the harvestable floor (min_harvestable 4).
    # Spec (roadmap_world.md gap #2): at/below the floor => exhausted, no draw.
    for seed in range(50):
        service, ctx, session = _build(
            seed=seed,
            survival=95,
            profile=_profile(min_harvestable=4.0, draw_amount=8.0),
            seed_state=4.0,
        )
        try:
            service.harvest(ctx, CHANNEL)
            if any("is spent" in m for m in ctx.messages):
                assert not _carries(ctx, YIELD_ITEM)
                assert _intensity(session, ZONE, CHANNEL) == 4.0  # untouched
                return
        finally:
            session.close()
    pytest.fail("no seed reached the at-floor exhaustion branch in 50 tries")


def test_harvest_clamped_low_grants_and_warns() -> None:
    # intensity 8 >= floor 4 (harvestable) but < draw 12, so the draw clamps to 0.
    for seed in range(50):
        service, ctx, session = _build(
            seed=seed,
            survival=95,
            profile=_profile(min_harvestable=4.0, draw_amount=12.0),
            seed_state=8.0,
        )
        try:
            service.harvest(ctx, CHANNEL)
            if any("You harvest the" in m for m in ctx.messages):
                assert _carries(ctx, YIELD_ITEM)
                assert _intensity(session, ZONE, CHANNEL) == 0.0
                assert any("last of the" in m for m in ctx.messages)
                return
        finally:
            session.close()
    pytest.fail("no seed reached the clamped-low branch in 50 tries")


def test_harvest_fail_closed_when_zone_is_none() -> None:
    service, ctx, session = _build(seed=1, zone=None)
    try:
        service.harvest(ctx, CHANNEL)
        assert any("no living energy to harvest here" in m for m in ctx.messages)
        assert not _carries(ctx, YIELD_ITEM)
    finally:
        session.close()


def test_harvest_channel_not_in_zone_fails() -> None:
    service, ctx, session = _build(seed=1, profile=_profile(zones=["some_other_zone"]))
    try:
        service.harvest(ctx, CHANNEL)
        assert any("no emberthorn to harvest in this region" in m for m in ctx.messages)
        assert not _carries(ctx, YIELD_ITEM)
    finally:
        session.close()


def test_harvest_unknown_channel_message() -> None:
    service, ctx, session = _build(seed=1)
    try:
        service.harvest(ctx, "banana")
        assert any("don't know how to harvest that" in m for m in ctx.messages)
    finally:
        session.close()


def test_harvest_item_existence_guard() -> None:
    # yields references an item id that isn't seeded → no grant, guard message.
    for seed in range(50):
        service, ctx, session = _build(
            seed=seed,
            survival=95,
            seed_item=False,
            profile=_profile(yields=["ghost_item"]),
        )
        try:
            service.harvest(ctx, CHANNEL)
            if any("slips away before you can vial it" in m for m in ctx.messages):
                assert not _carries(ctx, "ghost_item")
                # Guard runs before the draw — the node is read but not depleted.
                assert _intensity(session, ZONE, CHANNEL) == 50.0
                return
        finally:
            session.close()
    pytest.fail("no seed reached the item-existence guard in 50 tries")


# --------------------------------------------------------------------------- #
# H4 — command surface                                                         #
# --------------------------------------------------------------------------- #


def _cmd_build(
    *, seed: int, has_flag: bool
) -> tuple[CommandEngine, GameContext, Session]:
    service, ctx, session = _build(seed=seed)
    if not has_flag:
        ctx.player.flags = {}
    registry = CommandRegistry()
    register_living_energy_commands(registry, harvest=service)
    return CommandEngine(registry, RuleEngine()), ctx, session


def test_harvest_hidden_without_ability_flag() -> None:
    cmd_engine, ctx, session = _cmd_build(seed=1, has_flag=False)
    try:
        cmd_engine.handle_command("harvest emberthorn", ctx)
        assert not any("You harvest the" in m for m in ctx.messages)
        assert ctx.messages == ["You can't do that yet."]
    finally:
        session.close()


def test_harvest_verb_gate_in_definition() -> None:
    registry = CommandRegistry()
    register_living_energy_commands(registry)
    definition = registry.get("harvest")
    assert definition is not None
    assert "actor_has_flag:ability.harvest" in definition.conditions
    assert "harvest <channel>" in definition.help_text


def test_harvest_aliases_registered_with_gate_and_help() -> None:
    registry = CommandRegistry()
    register_living_energy_commands(registry)
    for alias in ("tap", "scrape", "bleed"):
        definition = registry.get(alias)
        assert definition is not None, alias
        assert "actor_has_flag:ability.harvest" in definition.conditions
        assert definition.help_text  # non-empty help


def test_harvest_dispatches_channel_from_noun() -> None:
    for seed in range(50):
        cmd_engine, ctx, session = _cmd_build(seed=seed, has_flag=True)
        try:
            cmd_engine.handle_command("harvest emberthorn", ctx)
            if any("You harvest the" in m for m in ctx.messages):
                assert _carries(ctx, YIELD_ITEM)
                return
        finally:
            session.close()
    pytest.fail("no seed dispatched a successful harvest in 50 tries")


def test_harvest_bleed_alias_prefills_emberthorn() -> None:
    for seed in range(50):
        cmd_engine, ctx, session = _cmd_build(seed=seed, has_flag=True)
        try:
            # `bleed` carries no noun but must harvest emberthorn.
            cmd_engine.handle_command("bleed", ctx)
            if any("You harvest the emberthorn" in m for m in ctx.messages):
                assert _carries(ctx, YIELD_ITEM)
                return
        finally:
            session.close()
    pytest.fail("no seed dispatched a successful bleed alias in 50 tries")


def test_harvest_without_noun_prompts() -> None:
    cmd_engine, ctx, session = _cmd_build(seed=1, has_flag=True)
    try:
        cmd_engine.handle_command("harvest", ctx)
        assert any("Harvest what?" in m for m in ctx.messages)
    finally:
        session.close()
