"""Tide-gated exits: YAML-declared, tide-driven Exit writes (Sprint 54.3).

The data-driven half of the celestial feature: `world_content/celestial.yaml`
declares which exits the tide opens (the hunts/marks content-file pattern —
no room ids in code), and a `TIDE_CHANGED` handler writes the **one
authoritative `Exit` state** per the §3.9 one-owner rule — movement stays
unchanged, a causeway "reveals" by unlocking and "drowns" by re-locking.
`sync_tide_gates` also runs once at startup so gates match the clock the
world wakes up to, not the last tide *transition*.
"""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path

import yaml
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.engine import Engine
from sqlmodel import Session

from lorecraft.engine.clock.celestial import TIDES, tide_for_hour
from lorecraft.engine.game.events import Event, EventBus, GameEvent
from lorecraft.engine.repos.room_repo import RoomRepo

CELESTIAL_SCHEMA_VERSION = 1


class TideGate(BaseModel):
    """One exit the tide controls: open (unlocked) only at `open_at` tide."""

    room: str
    direction: str
    open_at: str = "low"

    @field_validator("open_at")
    @classmethod
    def _open_at_known(cls, value: str) -> str:
        if value not in TIDES:
            raise ValueError(f"open_at must be one of {TIDES}, got {value!r}")
        return value


class CelestialDocument(BaseModel):
    version: int = CELESTIAL_SCHEMA_VERSION
    tide_gates: list[TideGate] = Field(default_factory=list)


def validate_celestial_document(data: object) -> CelestialDocument:
    return CelestialDocument.model_validate(data)


def load_celestial_yaml(path: str | Path) -> CelestialDocument:
    text = Path(path).read_text()
    return validate_celestial_document(yaml.safe_load(text) or {})


def lint_celestial(
    document: CelestialDocument,
    *,
    known_exits: Iterable[tuple[str, str]],
) -> list[str]:
    """Content-lint: every tide gate must name a real room exit.

    `known_exits` is (room_id, direction) pairs from world content — both are
    statically known here, so the whole reference is checked (unlike
    `open_timed_passage`, whose room is only known at runtime).
    """
    exits = set(known_exits)
    problems: list[str] = []
    for gate in document.tide_gates:
        if (gate.room, gate.direction) not in exits:
            problems.append(
                f"tide gate {gate.room!r} {gate.direction!r}: no such exit in world content"
            )
    return problems


class CelestialContentRegistry:
    def __init__(self) -> None:
        self._tide_gates: list[TideGate] = []

    def load_document(self, document: CelestialDocument) -> None:
        self._tide_gates = list(document.tide_gates)

    def tide_gates(self) -> list[TideGate]:
        return list(self._tide_gates)

    def clear(self) -> None:
        self._tide_gates.clear()


_registry = CelestialContentRegistry()


def get_content_registry() -> CelestialContentRegistry:
    return _registry


def sync_tide_gates(
    session: Session, hour: int, registry: CelestialContentRegistry | None = None
) -> int:
    """Write every declared tide gate's Exit to match the tide at `hour`.

    Returns how many exits changed. Never commits — the caller owns the txn.
    """
    gates = (registry or _registry).tide_gates()
    if not gates:
        return 0
    tide = tide_for_hour(hour)
    room_repo = RoomRepo(session)
    changed = 0
    for gate in gates:
        exit_ = room_repo.exit(gate.room, gate.direction)
        if exit_ is None:
            continue
        should_lock = tide != gate.open_at
        if exit_.locked != should_lock:
            exit_.locked = should_lock
            session.add(exit_)
            changed += 1
    return changed


def register_tide_gate_handlers(
    bus: EventBus,
    game_engine: Engine,
    registry: CelestialContentRegistry | None = None,
) -> None:
    """Drive the declared tide gates from `TIDE_CHANGED` (weather-handler
    pattern: own session, own commit — the clock runner's context has no
    game session of its own)."""

    def on_tide_changed(event: Event, ctx: object) -> None:
        del ctx
        hour = event.payload.get("hour")
        if not isinstance(hour, int):
            return
        with Session(game_engine) as session:
            if sync_tide_gates(session, hour, registry):
                session.commit()

    bus.on(GameEvent.TIDE_CHANGED, on_tide_changed)
