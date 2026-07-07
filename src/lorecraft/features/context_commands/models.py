"""Context-attached commands: bindings, registry, loader, content-lint (Sprint 55).

An object-scoped verb declared in world content on an item or NPC
(`context_commands: {pull: {...}}`). At startup every item/NPC is scanned into
an in-memory `ContextCommandRegistry` of `ContextBinding`s; the dispatcher
(`commands.py`) registers one gated command per distinct verb. The verb's
`gate` (`object_present:<id>` / `npc_present:<id>`, Sprint 55.1) makes it
available — and, via the help-availability filter, only *listed* — when its
object is at hand. Actions fire through the shared side-effect registry
(`features/npc/side_effects.py`), so context verbs compose the same effects
dialogue and mechanisms use — no new effect machinery.
"""

from __future__ import annotations

from collections.abc import Iterable, Iterator
from dataclasses import dataclass

from sqlmodel import Session, select

from lorecraft.engine.models.world import NPC, Item
from lorecraft.types import JsonObject

# owner_type -> the Sprint 55.1 presence condition that gates the verb.
_GATE_CONDITION = {"item": "object_present", "npc": "npc_present"}


@dataclass(frozen=True)
class ContextBinding:
    """One (object, verb) pairing resolved from content."""

    verb: str
    owner_type: str  # "item" | "npc"
    owner_id: str
    aliases: tuple[str, ...]
    help: str
    say: str
    side_effects: JsonObject
    requires: str | None

    @property
    def gate(self) -> str:
        """The presence condition string this binding is available under."""
        return f"{_GATE_CONDITION[self.owner_type]}:{self.owner_id}"


def _bindings_from(
    owner_type: str, owner_id: str, context_commands: object
) -> Iterator[ContextBinding]:
    if not isinstance(context_commands, dict):
        return
    for verb, spec in context_commands.items():
        if not isinstance(verb, str) or not isinstance(spec, dict):
            continue
        aliases = spec.get("aliases") or []
        side_effects = spec.get("side_effects") or {}
        requires = spec.get("requires")
        yield ContextBinding(
            verb=verb,
            owner_type=owner_type,
            owner_id=owner_id,
            aliases=tuple(a for a in aliases if isinstance(a, str)),
            help=str(spec.get("help", "")),
            say=str(spec.get("say", "")),
            side_effects=dict(side_effects) if isinstance(side_effects, dict) else {},
            requires=requires if isinstance(requires, str) else None,
        )


class ContextCommandRegistry:
    """Distinct context verbs, each with the list of objects that declare it.

    A verb (e.g. `pull`) may be declared by several objects — the dispatcher
    resolves *which* present object fires at runtime.
    """

    def __init__(self) -> None:
        self._by_verb: dict[str, list[ContextBinding]] = {}

    def register(self, binding: ContextBinding) -> None:
        self._by_verb.setdefault(binding.verb, []).append(binding)

    def load_from_session(self, session: Session) -> None:
        """Scan every item + NPC for declared context commands."""
        for item in session.exec(select(Item)).all():
            for binding in _bindings_from("item", item.id, item.context_commands):
                self.register(binding)
        for npc in session.exec(select(NPC)).all():
            for binding in _bindings_from("npc", npc.id, npc.context_commands):
                self.register(binding)

    def verbs(self) -> list[str]:
        return list(self._by_verb.keys())

    def bindings_for(self, verb: str) -> list[ContextBinding]:
        return list(self._by_verb.get(verb, []))

    def all_bindings(self) -> list[ContextBinding]:
        return [b for bindings in self._by_verb.values() for b in bindings]

    def clear(self) -> None:
        self._by_verb.clear()


def lint_context_commands(
    bindings: Iterable[ContextBinding], *, known_side_effects: object
) -> list[str]:
    """Content-lint: every context command's side-effect keys must resolve to a
    registered handler. `known_side_effects` is anything supporting ``in`` (the
    side-effect registry) — the same fail-fast contract as hunt/mark linting.
    """
    problems: list[str] = []
    for binding in bindings:
        for effect_name in binding.side_effects:
            if effect_name not in known_side_effects:  # type: ignore[operator]
                problems.append(
                    f"context command {binding.verb!r} on {binding.owner_type} "
                    f"{binding.owner_id!r}: unknown side effect {effect_name!r}"
                )
    return problems


_registry = ContextCommandRegistry()


def get_registry() -> ContextCommandRegistry:
    return _registry
