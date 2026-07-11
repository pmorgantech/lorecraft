"""A0.2 — the three scripting registries publish descriptors to the shared catalog.

Importing the registry modules must populate ``global_vocabulary()`` with a self-describing
:class:`VocabEntry` for every built-in condition/effect (not just a bare handler string). The
historical flag-family drift the capability-duplication check used to surface was renamed away
in Sprint 69 (`actor_has_flag`/`actor_lacks_flag`), so the catalog now reports no overlaps. See
``docs/scripting_engine_design.md`` §8.
"""

from __future__ import annotations

# Importing these modules is what registers the built-ins into the shared catalog.
from lorecraft.engine.game import command_conditions
from lorecraft.engine.scripting.vocabulary import VocabKind, global_vocabulary
from lorecraft.features.npc import dialogue_conditions, side_effects

_SIDE_EFFECTS = ("set_flags", "clear_flags", "give_item", "start_quest", "end_dialogue")
_COMMAND_CONDITIONS = (
    "requires_light",
    "not_in_combat",
    "in_combat",
    "actor_has_flag",
    "actor_lacks_flag",
    "item_in_inventory",
    "object_present",
    "npc_present",
)
_DIALOGUE_CONDITIONS = ("actor_has_flag", "actor_lacks_flag")


def test_side_effect_builtins_are_catalogued_and_wired() -> None:
    vocab = global_vocabulary()
    registry = side_effects.get_registry()
    for name in _SIDE_EFFECTS:
        entry = vocab.get(name)
        assert entry is not None, f"{name} missing from catalog"
        assert entry.kind is VocabKind.EFFECT
        assert entry.doc, f"{name} has no doc"
        assert name in registry, f"{name} handler not wired"


def test_command_condition_builtins_are_catalogued_and_wired() -> None:
    vocab = global_vocabulary()
    registry = command_conditions.get_registry()
    for name in _COMMAND_CONDITIONS:
        entry = vocab.get(name)
        assert entry is not None, f"{name} missing from catalog"
        assert entry.kind is VocabKind.CONDITION
        assert name in registry, f"{name} handler not wired"


def test_dialogue_condition_builtins_are_catalogued_and_wired() -> None:
    vocab = global_vocabulary()
    registry = dialogue_conditions.get_registry()
    for name in _DIALOGUE_CONDITIONS:
        entry = vocab.get(name)
        assert entry is not None, f"{name} missing from catalog"
        assert entry.kind is VocabKind.CONDITION
        assert name in registry, f"{name} handler not wired"


def test_flag_family_is_canonicalized_with_no_overlaps() -> None:
    """Sprint 69 killed the flag-family drift (§8.6).

    `flag_set`/`required_flags` (and the `_not`/`forbidden` variants) collapsed to the one §8.4
    canonical name per capability — `actor_has_flag` / `actor_lacks_flag` — registered on *both*
    the command and dialogue surfaces (a legal same-capability, two-surface pair via the
    catalog's idempotent registration). The old drifted names are retired, and the
    duplicate-detection self-check now reports **no** capability overlaps.
    """
    assert global_vocabulary().overlaps() == []
    for retired in ("flag_set", "flag_not_set", "required_flags", "forbidden_flags"):
        assert global_vocabulary().get(retired) is None, f"{retired} should be retired"
    for name in ("actor_has_flag", "actor_lacks_flag"):
        assert global_vocabulary().get(name) is not None
        assert name in command_conditions.get_registry(), (
            f"{name} not on command surface"
        )
        assert name in dialogue_conditions.get_registry(), (
            f"{name} not on dialogue surface"
        )
