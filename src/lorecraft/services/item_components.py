"""Read/write helpers for per-instance component state.

JSON columns need a fresh dict object per mutation for SQLAlchemy's change
tracking to notice — in-place ``instance.state[k] = v`` on the existing dict
is invisible to the ORM. Every setter here reassigns ``instance.state`` as a
new dict so the column is marked dirty.
"""

from __future__ import annotations

from sqlmodel import Session

from lorecraft.models.items import ItemInstance
from lorecraft.types import JsonValue


def get_component_state(instance: ItemInstance, component: str) -> JsonValue | None:
    return instance.state.get(component)


def set_component_state(
    session: Session, instance: ItemInstance, component: str, value: JsonValue
) -> None:
    new_state = dict(instance.state)
    new_state[component] = value
    instance.state = new_state
    session.add(instance)
