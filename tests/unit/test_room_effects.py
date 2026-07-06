"""Sprint 39 timed room effects — the passage_open gate + occupant auras.

Exercises both §3.9 mechanics end-to-end: a room-state effect that writes the
authoritative `Exit` state (opened on apply, restored by the expiry sweep), and
an occupant aura read through the §3.5 modifier resolver.
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from sqlmodel import Session, create_engine

from lorecraft.db import create_tables
from lorecraft.engine.game.effects import EffectDef
from lorecraft.engine.game.effects import get_registry as get_effect_registry
from lorecraft.engine.game.events import Event, EventBus, GameEvent
from lorecraft.engine.game.modifiers import Modifier, resolve_for
from lorecraft.engine.game.rng import GameRng
from lorecraft.engine.models.player import Player
from lorecraft.engine.models.world import Exit, Room
from lorecraft.engine.repos.room_repo import RoomRepo
from lorecraft.engine.services.effects import EffectService
from lorecraft.features.exploration.room_effects import PASSAGE_OPEN_KEY
from lorecraft.features.exploration.room_effects import (
    register as register_room_effects,
)
from lorecraft.features.npc.side_effects import get_registry as get_side_effect_registry


def _engine():
    engine = create_engine("sqlite://")
    create_tables(game_engine=engine, audit_engine=create_engine("sqlite://"))
    return engine


def _add_exit(session: Session, room_id: str, direction: str, *, locked: bool) -> None:
    session.add(Room(id=room_id, name=room_id, description="", map_x=0, map_y=0))
    session.add(Room(id="beyond", name="Beyond", description="", map_x=0, map_y=1))
    session.add(
        Exit(
            room_id=room_id,
            direction=direction,
            target_room_id="beyond",
            locked=locked,
        )
    )
    session.commit()


def _sweep(bus: EventBus, epoch: float) -> None:
    bus.emit(Event(GameEvent.TIME_ADVANCED, {"current_epoch": epoch}), ctx=None)


def test_register_is_idempotent_and_wires_both_registries() -> None:
    register_room_effects()
    register_room_effects()  # second call must not raise or double-register
    assert PASSAGE_OPEN_KEY in get_effect_registry()
    assert "open_timed_passage" in get_side_effect_registry()


class TestPassageOpenGate:
    def test_apply_opens_the_exit_and_expiry_relocks_it(self) -> None:
        register_room_effects()
        engine = _engine()
        bus = EventBus()
        service = EffectService(engine, GameRng())
        service.register(bus)

        with Session(engine) as session:
            _add_exit(session, "vault", "north", locked=True)
            service.apply(
                session,
                "room",
                "vault",
                PASSAGE_OPEN_KEY,
                duration_ticks=10.0,
                payload={"direction": "north"},
                clock_epoch=0.0,
            )
            session.commit()
            opened = RoomRepo(session).exit("vault", "north")
            assert opened is not None and opened.locked is False

        _sweep(bus, 20.0)  # past expiry

        with Session(engine) as session:
            relocked = RoomRepo(session).exit("vault", "north")
            assert relocked is not None and relocked.locked is True

    def test_expiry_restores_a_normally_open_exit_unchanged(self) -> None:
        # on_expire restores the *prior* state — a normally-open exit stays open.
        register_room_effects()
        engine = _engine()
        bus = EventBus()
        service = EffectService(engine, GameRng())
        service.register(bus)

        with Session(engine) as session:
            _add_exit(session, "cave", "east", locked=False)
            service.apply(
                session,
                "room",
                "cave",
                PASSAGE_OPEN_KEY,
                duration_ticks=10.0,
                payload={"direction": "east"},
                clock_epoch=0.0,
            )
            session.commit()

        _sweep(bus, 20.0)

        with Session(engine) as session:
            exit_ = RoomRepo(session).exit("cave", "east")
            assert exit_ is not None and exit_.locked is False


class TestOccupantAura:
    @pytest.fixture
    def chill_zone_effect(self) -> Iterator[None]:
        registry = get_effect_registry()
        registry.register(
            EffectDef(
                key="chill_zone",
                modifiers=lambda effect: [
                    Modifier("skill.athletics", "add", -2.0, f"aura:{effect.id}")
                ],
            )
        )
        yield
        registry._defs.pop("chill_zone", None)  # type: ignore[attr-defined]

    def test_aura_modifies_occupant_and_lifts_on_leave(
        self, chill_zone_effect: None
    ) -> None:
        engine = _engine()
        service = EffectService(engine, GameRng())

        with Session(engine) as session:
            session.add(
                Room(id="tundra", name="Tundra", description="", map_x=0, map_y=0)
            )
            session.add(
                Room(id="lodge", name="Lodge", description="", map_x=1, map_y=0)
            )
            session.add(
                Player(
                    id="p1",
                    username="u",
                    current_room_id="tundra",
                    respawn_room_id="tundra",
                )
            )
            service.apply(
                session,
                "room",
                "tundra",
                "chill_zone",
                duration_ticks=None,
                clock_epoch=0.0,
            )
            session.commit()

            # Standing in the tundra, the aura debuffs athletics (10 - 2).
            assert resolve_for(session, "player", "p1", "skill.athletics", 10.0) == 8.0

            # Walking to the lodge lifts it — no per-player state to unwind.
            player = session.get(Player, "p1")
            assert player is not None
            player.current_room_id = "lodge"
            session.add(player)
            session.commit()
            assert resolve_for(session, "player", "p1", "skill.athletics", 10.0) == 10.0
