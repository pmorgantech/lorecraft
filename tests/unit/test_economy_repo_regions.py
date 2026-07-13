"""Unit tests for EconomyRepo.all_regions() (Sprint 76.1)."""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from sqlmodel import Session, create_engine

from lorecraft.db import create_tables
from lorecraft.features.economy.models import RegionPricing
from lorecraft.features.economy.repo import EconomyRepo


@pytest.fixture
def session() -> Iterator[Session]:
    engine = create_engine("sqlite://")
    create_tables(game_engine=engine, audit_engine=create_engine("sqlite://"))
    with Session(engine) as sess:
        yield sess


def test_all_regions_empty_when_none_seeded(session: Session) -> None:
    assert EconomyRepo(session).all_regions() == []


def test_all_regions_returns_all_rows_zone_ordered(session: Session) -> None:
    session.add(RegionPricing(zone="whisperwood", region_mult=1.2, bias={}))
    session.add(RegionPricing(zone="cogsworth", region_mult=0.9, bias={"gem": 2.0}))
    session.add(RegionPricing(zone="port_veridian", region_mult=1.0, bias={}))
    session.commit()

    regions = EconomyRepo(session).all_regions()

    assert [r.zone for r in regions] == ["cogsworth", "port_veridian", "whisperwood"]
    cogsworth = regions[0]
    assert cogsworth.region_mult == 0.9
    assert cogsworth.bias == {"gem": 2.0}
