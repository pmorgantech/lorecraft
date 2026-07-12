"""Unit tests for the Tier 2 reward interpreter (Sprint 73.5 + 73.7 payout)."""

from __future__ import annotations

from sqlmodel import Session, create_engine

from lorecraft.db import create_tables
from lorecraft.engine.game.connection_manager import ConnectionManager
from lorecraft.engine.game.context import GameContext
from lorecraft.engine.game.events import EventBus
from lorecraft.engine.game.holders import Location
from lorecraft.engine.game.rng import GameRng
from lorecraft.engine.game.transaction import TransactionContext
from lorecraft.engine.models.player import Player, PlayerStats
from lorecraft.engine.models.world import Item, Room
from lorecraft.engine.repos.item_repo import ItemRepo
from lorecraft.engine.repos.npc_repo import NpcRepo
from lorecraft.engine.repos.player_repo import PlayerRepo
from lorecraft.engine.repos.room_repo import RoomRepo
from lorecraft.engine.repos.stack_repo import StackRepo
from lorecraft.engine.services.effects import EffectService
from lorecraft.engine.services.item_location import ItemLocationService
from lorecraft.engine.services.ledger import LedgerService
from lorecraft.engine.services.meters import MeterService
from lorecraft.features.progression.models import ProgressionConfig
from lorecraft.features.progression.rewards import apply_rewards


def _engine():
    e = create_engine("sqlite://")
    create_tables(game_engine=e, audit_engine=create_engine("sqlite://"))
    return e


def _seed(
    session: Session,
    *,
    config: ProgressionConfig | None = None,
    with_stats: bool = True,
) -> Player:
    session.add(
        Room(id="tavern", name="Tavern", description="A warm room.", map_x=0, map_y=0)
    )
    player = Player(
        id="p1",
        username="hero",
        current_room_id="tavern",
        respawn_room_id="tavern",
    )
    session.add(player)
    if with_stats:
        session.add(PlayerStats(player_id="p1", level=1, xp=0, xp_to_next=100))
    session.add(Item(id="gem", name="a shining gem", description="It sparkles."))
    if config is not None:
        session.add(config)
    session.commit()
    return player


def _ctx(session: Session, player: Player) -> GameContext:
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
        transaction=TransactionContext.create(actor_id=player.id, correlation_id="s"),
        session_id="s",
    )


def _config(**overrides: int) -> ProgressionConfig:
    values = {
        "base": 100,
        "step": 0,
        "coins_per_level": 25,
        "skill_points_per_level": 1,
    }
    values.update(overrides)
    return ProgressionConfig(**values)


def test_items_reward_spawns_to_player() -> None:
    with Session(_engine()) as session:
        player = _seed(session)
        ctx = _ctx(session, player)

        outcome = apply_rewards(ctx, {"items": ["gem"]})

        assert outcome.items_spawned == ("gem",)
        assert ctx.stack_repo.quantity_of(Location("player", "p1"), "gem") == 1


def test_items_reward_skips_unknown_and_already_carried() -> None:
    with Session(_engine()) as session:
        player = _seed(session)
        ctx = _ctx(session, player)
        apply_rewards(ctx, {"items": ["gem"]})

        outcome = apply_rewards(ctx, {"items": ["gem", "does-not-exist"]})

        assert outcome.items_spawned == ()  # already carried + unknown -> nothing new
        assert ctx.stack_repo.quantity_of(Location("player", "p1"), "gem") == 1


def test_items_reward_skips_and_warns_on_non_list_value(caplog) -> None:
    # A malformed `items` value (not a list) is tolerated — skipped, not raised —
    # but logs a warning so a content-authoring typo isn't silently swallowed.
    import logging

    with Session(_engine()) as session:
        player = _seed(session)
        ctx = _ctx(session, player)

        with caplog.at_level(logging.WARNING):
            outcome = apply_rewards(ctx, {"items": "gem"})

        assert outcome.items_spawned == ()
        assert any("items" in r.message for r in caplog.records)


def test_coins_reward_credits_ledger() -> None:
    with Session(_engine()) as session:
        player = _seed(session)
        ctx = _ctx(session, player)

        outcome = apply_rewards(ctx, {"coins": 40})

        assert outcome.coins_granted == 40
        assert ctx.ledger.balance_of(session, "player", "p1") == 40


def test_money_alias_is_tolerated_as_coins() -> None:
    with Session(_engine()) as session:
        player = _seed(session)
        ctx = _ctx(session, player)

        outcome = apply_rewards(ctx, {"money": 15})

        assert outcome.coins_granted == 15
        assert ctx.ledger.balance_of(session, "player", "p1") == 15


def test_skill_points_reward_applies_stat_delta() -> None:
    with Session(_engine()) as session:
        player = _seed(session)
        ctx = _ctx(session, player)

        outcome = apply_rewards(ctx, {"skill_points": 3})

        assert outcome.stat_deltas_applied == {"skill_points": 3}
        assert PlayerRepo(session).stats("p1").skill_points == 3  # type: ignore[union-attr]


def test_xp_reward_awards_without_leveling_below_threshold() -> None:
    with Session(_engine()) as session:
        player = _seed(session, config=_config(base=100))
        ctx = _ctx(session, player)

        outcome = apply_rewards(ctx, {"xp": 40})

        assert outcome.xp_granted == 40
        assert outcome.level_up is not None
        assert outcome.level_up.levels_gained == 0
        stats = PlayerRepo(session).stats("p1")
        assert stats is not None and stats.xp == 40 and stats.level == 1


def test_xp_reward_without_config_banks_raw_xp() -> None:
    with Session(_engine()) as session:
        player = _seed(session, config=None)
        ctx = _ctx(session, player)

        outcome = apply_rewards(ctx, {"xp": 40})

        assert outcome.xp_granted == 40
        assert outcome.level_up is None  # no curve -> no leveling
        stats = PlayerRepo(session).stats("p1")
        assert stats is not None and stats.xp == 40 and stats.level == 1


def test_combined_bundle_grants_every_key() -> None:
    with Session(_engine()) as session:
        player = _seed(session, config=_config(base=100))
        ctx = _ctx(session, player)

        outcome = apply_rewards(
            ctx,
            {"items": ["gem"], "xp": 40, "coins": 10, "skill_points": 2},
        )

        assert outcome.items_spawned == ("gem",)
        assert outcome.coins_granted == 10
        assert outcome.xp_granted == 40
        assert outcome.stat_deltas_applied == {"skill_points": 2}
        assert ctx.stack_repo.quantity_of(Location("player", "p1"), "gem") == 1
        assert ctx.ledger.balance_of(session, "player", "p1") == 10
        stats = PlayerRepo(session).stats("p1")
        assert stats is not None and stats.xp == 40 and stats.skill_points == 2


def test_level_up_credits_configured_payout() -> None:
    # base=100, step=0 -> each level costs 100. 250 xp crosses two levels.
    with Session(_engine()) as session:
        player = _seed(
            session,
            config=_config(base=100, coins_per_level=25, skill_points_per_level=1),
        )
        ctx = _ctx(session, player)

        outcome = apply_rewards(ctx, {"xp": 250})

        assert outcome.level_up is not None
        assert outcome.level_up.levels_gained == 2
        assert outcome.level_up.new_level == 3
        # Payout folded into the reported totals: 2 levels * (25 coins, 1 sp).
        assert outcome.coins_granted == 50
        assert outcome.stat_deltas_applied == {"skill_points": 2}
        assert ctx.ledger.balance_of(session, "player", "p1") == 50
        stats = PlayerRepo(session).stats("p1")
        assert stats is not None and stats.skill_points == 2 and stats.level == 3


def test_changing_config_changes_level_up_payout() -> None:
    with Session(_engine()) as session:
        player = _seed(
            session,
            config=_config(base=100, coins_per_level=100, skill_points_per_level=5),
        )
        ctx = _ctx(session, player)

        outcome = apply_rewards(ctx, {"xp": 100})  # exactly one level

        assert outcome.level_up is not None and outcome.level_up.levels_gained == 1
        assert outcome.coins_granted == 100
        assert outcome.stat_deltas_applied == {"skill_points": 5}


def test_level_up_payout_adds_to_explicit_skill_points() -> None:
    # An explicit skill_points reward and the level-up payout both apply.
    with Session(_engine()) as session:
        player = _seed(
            session,
            config=_config(base=100, coins_per_level=10, skill_points_per_level=1),
        )
        ctx = _ctx(session, player)

        outcome = apply_rewards(ctx, {"xp": 100, "skill_points": 3})

        # 1 level payout (1 sp) + explicit 3 sp = 4.
        assert outcome.stat_deltas_applied == {"skill_points": 4}
        stats = PlayerRepo(session).stats("p1")
        assert stats is not None and stats.skill_points == 4
