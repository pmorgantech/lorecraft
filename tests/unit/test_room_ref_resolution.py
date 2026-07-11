"""Zone-qualified room resolution: RoomRepo.resolve_ref (Sprint 69.5).

Rooms have string ids and names but no integer ids, so `zone.room` is how a builder or
admin disambiguates rooms that share a name.
"""

from __future__ import annotations

import pytest
from sqlalchemy.engine import Engine, create_engine
from sqlmodel import Session

from lorecraft.db import create_tables
from lorecraft.engine.models.world import Room
from lorecraft.engine.repos.room_repo import RoomRepo


@pytest.fixture
def engine() -> Engine:  # type: ignore[misc]
    eng = create_engine("sqlite://")
    create_tables(game_engine=eng, audit_engine=create_engine("sqlite://"))
    with Session(eng) as session:
        session.add(
            Room(
                id="inner_vault",
                name="The Inner Vault",
                description="d",
                map_x=0,
                map_y=0,
                area_id="town",
            )
        )
        # A name deliberately shared across two zones — only zone-qualifying disambiguates.
        session.add(
            Room(
                id="town_chapel",
                name="The Chapel",
                description="d",
                map_x=1,
                map_y=0,
                area_id="town",
            )
        )
        session.add(
            Room(
                id="wild_chapel",
                name="The Chapel",
                description="d",
                map_x=2,
                map_y=0,
                area_id="wilderness",
            )
        )
        session.commit()
    return eng


def _resolve(engine: Engine, ref: str) -> str | None:
    with Session(engine) as session:
        room = RoomRepo(session).resolve_ref(ref)
        return room.id if room else None


def test_exact_id(engine: Engine) -> None:
    assert _resolve(engine, "inner_vault") == "inner_vault"


def test_bare_name_case_insensitive(engine: Engine) -> None:
    assert _resolve(engine, "the inner vault") == "inner_vault"


def test_zone_qualified_by_id(engine: Engine) -> None:
    assert _resolve(engine, "town.inner_vault") == "inner_vault"


def test_zone_qualified_by_name(engine: Engine) -> None:
    assert _resolve(engine, "wilderness.The Chapel") == "wild_chapel"


def test_ambiguous_bare_name_is_unresolved(engine: Engine) -> None:
    assert _resolve(engine, "The Chapel") is None


def test_zone_qualifier_disambiguates_shared_name(engine: Engine) -> None:
    assert _resolve(engine, "town.The Chapel") == "town_chapel"


def test_unknown_ref_is_none(engine: Engine) -> None:
    assert _resolve(engine, "nowhere") is None
    assert _resolve(engine, "town.nowhere") is None
    assert _resolve(engine, "") is None
