"""Composition-layer wiring for the scripting engine.

Bridges the Tier-1 :class:`~lorecraft.engine.scripting.triggers.TriggerService` to the live
world and feature registries — which the engine may not import — so it lives here alongside
``main.py`` rather than in ``engine/``. Called once at startup after the world is bootstrapped.
"""

from __future__ import annotations

import logging

from sqlmodel import Session, select

from lorecraft.engine.game.events import EventBus
from lorecraft.engine.models.world import NPC, Room
from lorecraft.engine.scripting.triggers import (
    ENTITY_NPC,
    ENTITY_ROOM,
    Trigger,
    TriggerService,
    parse_trigger,
)
from lorecraft.engine.scripting.vocabulary import global_vocabulary
from lorecraft.features.npc import dialogue_conditions, side_effects

log = logging.getLogger(__name__)


def load_triggers(session: Session) -> list[Trigger]:
    """Parse every room/NPC ``triggers:`` block from the DB (fail-closed via the validator)."""
    vocab = global_vocabulary()
    triggers: list[Trigger] = []
    for room in session.exec(select(Room)).all():
        for raw in room.triggers:
            triggers.append(parse_trigger(ENTITY_ROOM, room.id, raw, vocab=vocab))
    for npc in session.exec(select(NPC)).all():
        for raw in npc.triggers:
            triggers.append(parse_trigger(ENTITY_NPC, npc.id, raw, vocab=vocab))
    return triggers


def build_trigger_service(session: Session, bus: EventBus) -> TriggerService:
    """Load triggers from the world DB, wire the real registries, and bind to the bus.

    The returned service stays alive via the bus (its handler is a bound method); callers need
    not hold it. A malformed trigger raises ``TriggerLoadError`` here — fail-closed at startup —
    rather than silently never firing in game.
    """
    triggers = load_triggers(session)
    service = TriggerService(
        when=dialogue_conditions.get_registry(),
        do=side_effects.get_registry(),
    )
    service.load(triggers)
    service.register(bus)
    log.info("trigger_service_loaded count=%d", len(triggers))
    return service
