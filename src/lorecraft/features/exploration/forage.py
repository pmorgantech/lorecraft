"""Forage: the `forage` active-utility verb + its data-driven yield table (Sprint 74.5).

`forage` is the reference *active ability* (flavor A) unlocked by the skill tree:
its command registers with `conditions=[..., actor_has_flag:ability.forage]`, so it
is invisible and unusable — hidden from `help` too — until the node is bought.

The verb itself is generic mechanism: in an outdoor room it rolls a `survival`
skill check and, on success, yields a consumable drawn from a *content-authored*
forage table (`world_content/forage.yaml`), keyed by terrain with a `*` fallback.
No item ids are hardcoded here — which items a terrain yields is world content.
"""

from __future__ import annotations

from pathlib import Path

import yaml
from pydantic import BaseModel, Field, field_validator

from lorecraft.engine.game.checks import skill_check
from lorecraft.engine.game.context import GameContext
from lorecraft.engine.game.holders import Location
from lorecraft.engine.game.message_types import MessageType
from lorecraft.engine.game.modifiers import get_registry as get_modifier_registry
from lorecraft.features.skills.service import SkillService

FORAGE_SCHEMA_VERSION = 1

# Any-terrain fallback key. Entries under "*" are foragable in every outdoor room.
WILDCARD_TERRAIN = "*"

# A middling check — forage is meant to usually pay off outdoors, but not always.
FORAGE_DIFFICULTY = 15

_SURVIVAL_SKILL = "survival"


class ForageEntry(BaseModel):
    terrain: str
    items: list[str] = Field(default_factory=list)

    @field_validator("terrain")
    @classmethod
    def _terrain_non_empty(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("forage entry terrain must be non-empty")
        return value


class ForageDocument(BaseModel):
    version: int = FORAGE_SCHEMA_VERSION
    entries: list[ForageEntry] = Field(default_factory=list)


def validate_forage_document(data: object) -> ForageDocument:
    return ForageDocument.model_validate(data)


def load_forage_yaml(path: str | Path) -> ForageDocument:
    text = Path(path).read_text(encoding="utf-8")
    return validate_forage_document(yaml.safe_load(text) or {})


class ForageRegistry:
    """Terrain -> foragable item ids, with a `*` wildcard for any outdoor terrain."""

    def __init__(self) -> None:
        self._by_terrain: dict[str, list[str]] = {}

    def register(self, entry: ForageEntry) -> None:
        bucket = self._by_terrain.setdefault(entry.terrain, [])
        bucket.extend(entry.items)

    def load_document(self, document: ForageDocument) -> None:
        for entry in document.entries:
            self.register(entry)

    def items_for(self, terrain: str) -> list[str]:
        """Item ids foragable in `terrain`: its own entries plus the wildcard set."""
        return [
            *self._by_terrain.get(terrain, []),
            *self._by_terrain.get(WILDCARD_TERRAIN, []),
        ]

    def clear(self) -> None:
        self._by_terrain.clear()


_registry = ForageRegistry()


def get_registry() -> ForageRegistry:
    return _registry


class ForageService:
    """Handles the `forage` verb: a survival check for a consumable outdoors."""

    def __init__(
        self,
        registry: ForageRegistry | None = None,
        skills: SkillService | None = None,
    ) -> None:
        self._registry = registry or get_registry()
        self._skills = skills or SkillService()

    def forage(self, ctx: GameContext) -> None:
        if ctx.room.indoor:
            ctx.say(
                "There's nothing to forage indoors. Try the open air.",
                MessageType.WARNING,
            )
            return

        base = self._skills.get_level(ctx.session, ctx.player.id, _SURVIVAL_SKILL)
        modifiers = get_modifier_registry().collect(
            ctx.session, "player", ctx.player.id
        )
        result = skill_check(
            ctx.rng,
            base=base,
            difficulty=FORAGE_DIFFICULTY,
            modifiers=modifiers,
            key=f"skill.{_SURVIVAL_SKILL}",
        )

        self._skills.record_use(ctx.session, ctx.rng, ctx.player.id, _SURVIVAL_SKILL)

        if not result.success:
            ctx.say("You forage the area but turn up nothing edible.")
            return

        # Yield a foragable item that actually exists in the world. Which items
        # a terrain offers is content (forage.yaml); this only picks among them.
        candidates = [
            item_id
            for item_id in self._registry.items_for(ctx.room.terrain)
            if ctx.item_repo.get(item_id) is not None
        ]
        if not candidates:
            ctx.say("You forage the area but turn up nothing edible.")
            return

        item_id = ctx.rng.choice(candidates)
        item = ctx.item_repo.get(item_id)
        assert item is not None
        ctx.item_location.spawn(item_id, Location("player", ctx.player.id))
        ctx.say(f"You forage and find {item.name}.", MessageType.HINT)
        ctx.tell_room(f"{ctx.player.username} forages the area.")
