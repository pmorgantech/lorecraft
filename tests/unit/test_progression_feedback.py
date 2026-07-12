"""Unit tests for the Tier 2 level-up feedback (Sprint 73.9).

`narrate_level_up` turns a `RewardOutcome`'s level-up into the three player-facing
effects — a LEVEL feed line, a PLAYER_LEVELED_UP event, and a Stats-pane push —
while the Tier 1 leveling mechanism stays IO-free.
"""

from __future__ import annotations

from sqlmodel import Session, create_engine

from lorecraft.db import create_tables
from lorecraft.engine.game.connection_manager import ConnectionManager
from lorecraft.engine.game.context import GameContext
from lorecraft.engine.game.events import EventBus, GameEvent
from lorecraft.engine.game.leveling import LevelUpResult
from lorecraft.engine.game.message_types import MessageType
from lorecraft.engine.game.rng import GameRng
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
from lorecraft.features.progression.feedback import STATS_UPDATE_KEY, narrate_level_up
from lorecraft.features.progression.models import ProgressionConfig
from lorecraft.features.progression.rewards import RewardOutcome, apply_rewards


def _engine():
    e = create_engine("sqlite://")
    create_tables(game_engine=e, audit_engine=create_engine("sqlite://"))
    return e


def _seed(session: Session, *, config: ProgressionConfig | None = None) -> Player:
    session.add(
        Room(id="tavern", name="Tavern", description="A warm room.", map_x=0, map_y=0)
    )
    player = Player(
        id="p1", username="hero", current_room_id="tavern", respawn_room_id="tavern"
    )
    session.add(player)
    session.add(PlayerStats(player_id="p1", level=1, xp=0, xp_to_next=100))
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


def test_narrate_level_up_emits_message_event_and_stats_push() -> None:
    with Session(_engine()) as session:
        player = _seed(session, config=_config(base=100))
        ctx = _ctx(session, player)
        outcome = apply_rewards(ctx, {"xp": 100})  # exactly one level
        assert outcome.level_up is not None and outcome.level_up.leveled_up

        narrate_level_up(ctx, outcome)

        # Feed line tagged with the dedicated LEVEL type.
        level_msgs = [m for m in ctx.messages if m.type == MessageType.LEVEL]
        assert level_msgs == ["You reach level 2!"]

        # PLAYER_LEVELED_UP queued with the transition payload.
        events = [
            e for e in ctx.pending_events if e.type == GameEvent.PLAYER_LEVELED_UP
        ]
        assert len(events) == 1
        assert events[0].payload == {
            "player_id": "p1",
            "old_level": 1,
            "new_level": 2,
            "levels_gained": 1,
        }

        # Stats-pane push carries the fresh Score numbers, incl. the payout's
        # skill points (skill_points_per_level=1 -> 1 unspent point).
        assert ctx.updates[STATS_UPDATE_KEY] == {
            "level": 2,
            "xp": 0,
            "xp_to_next": 100,
            "skill_points": 1,
        }


def test_narrate_level_up_noop_when_no_level_up_present() -> None:
    with Session(_engine()) as session:
        player = _seed(session)
        ctx = _ctx(session, player)

        narrate_level_up(ctx, RewardOutcome(xp_granted=40, level_up=None))

        assert ctx.messages == []
        assert ctx.pending_events == []
        assert STATS_UPDATE_KEY not in ctx.updates


def test_narrate_level_up_noop_when_xp_gained_but_no_threshold_crossed() -> None:
    with Session(_engine()) as session:
        player = _seed(session)
        ctx = _ctx(session, player)
        outcome = RewardOutcome(
            xp_granted=40,
            level_up=LevelUpResult(
                leveled_up=False, old_level=1, new_level=1, levels_gained=0
            ),
        )

        narrate_level_up(ctx, outcome)

        assert ctx.messages == []
        assert ctx.pending_events == []
        assert STATS_UPDATE_KEY not in ctx.updates
