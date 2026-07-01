"""Pytest fixtures for item-name disambiguation tests.

Production worlds define the Key Gallery in ``world_content/world.yaml``.
This module is for tests only — never import it from ``src/lorecraft/``.
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlmodel import Session, select

from lorecraft.models.world import Exit, Item, Room, RoomItem

DISAMBIG_ROOM_ID = "key_gallery"


@dataclass(frozen=True)
class GalleryExitLink:
    """Optional exit wiring when a test seeds the gallery beside another room."""

    parent_room_id: str
    to_gallery: str
    from_gallery: str


STARTER_WORLD_GALLERY_LINK = GalleryExitLink(
    parent_room_id="blacksmith_forge",
    to_gallery="north",
    from_gallery="south",
)


@dataclass(frozen=True)
class SimilarItemSpec:
    id: str
    name: str
    description: str
    takeable: bool = True


SIMILAR_ITEM_SPECS: tuple[SimilarItemSpec, ...] = (
    SimilarItemSpec("red_key", "Red Key", "A small key painted crimson."),
    SimilarItemSpec("iron_key", "Iron Key", "A plain iron key, unadorned."),
    SimilarItemSpec(
        "rusty_iron_key",
        "Rusty Iron Key",
        "An iron key thick with orange rust.",
    ),
    SimilarItemSpec("steel_key", "Steel Key", "A bright steel key, recently cut."),
    SimilarItemSpec("cage_key", "Cage Key", "A delicate key for a cage latch."),
    SimilarItemSpec(
        "cage_lock",
        "Cage Lock",
        "A small brass lock still mounted on a cage hasp.",
    ),
    SimilarItemSpec(
        "rusty_iron_sword",
        "Rusty Iron Sword",
        "A short sword eaten through with rust.",
    ),
    SimilarItemSpec("red_rose", "Red Rose", "A silk rose, unnaturally perfect."),
)


def similar_item_entities() -> list[tuple[str, str, list[str]]]:
    """Parser/inventory candidate tuples: (id, name, aliases)."""
    return [(spec.id, spec.name, []) for spec in SIMILAR_ITEM_SPECS]


def seed_similar_items(session: Session) -> None:
    """Insert item definitions if they are not already present."""
    for spec in SIMILAR_ITEM_SPECS:
        if session.get(Item, spec.id) is None:
            session.add(
                Item(
                    id=spec.id,
                    name=spec.name,
                    description=spec.description,
                    takeable=spec.takeable,
                )
            )


def seed_disambig_gallery(
    session: Session,
    *,
    room_id: str = DISAMBIG_ROOM_ID,
    link: GalleryExitLink | None = None,
) -> Room:
    """Create the gallery room, its items, and optional exits described by *link*."""
    seed_similar_items(session)

    room = session.get(Room, room_id)
    if room is None:
        room = Room(
            id=room_id,
            name="Locksmith's Gallery",
            description=(
                "Pegboards and shallow trays display a confusing spread of keys, "
                "locks, blades, and curios — many names differ by only a word or two."
            ),
            map_x=1,
            map_y=-1,
        )
        session.add(room)

    for spec in SIMILAR_ITEM_SPECS:
        existing = session.exec(
            select(RoomItem).where(
                RoomItem.room_id == room_id,
                RoomItem.item_id == spec.id,
            )
        ).first()
        if existing is None:
            session.add(RoomItem(room_id=room_id, item_id=spec.id, quantity=1))

    if link is not None:
        parent = session.get(Room, link.parent_room_id)
        if parent is not None:
            has_exit = session.exec(
                select(Exit).where(
                    Exit.room_id == link.parent_room_id,
                    Exit.direction == link.to_gallery,
                    Exit.target_room_id == room_id,
                )
            ).first()
            if has_exit is None:
                session.add(
                    Exit(
                        room_id=link.parent_room_id,
                        direction=link.to_gallery,
                        target_room_id=room_id,
                    )
                )
            has_return = session.exec(
                select(Exit).where(
                    Exit.room_id == room_id,
                    Exit.direction == link.from_gallery,
                    Exit.target_room_id == link.parent_room_id,
                )
            ).first()
            if has_return is None:
                session.add(
                    Exit(
                        room_id=room_id,
                        direction=link.from_gallery,
                        target_room_id=link.parent_room_id,
                    )
                )

    return room
