"""A0.2 — the three scripting registries publish descriptors to the shared catalog.

Importing the registry modules must populate ``global_vocabulary()`` with a self-describing
:class:`VocabEntry` for every built-in condition/effect (not just a bare handler string), and
the capability-signature duplication check must surface the historical flag-family drift that
A0.5 will rename away. See ``docs/scripting_engine_design.md`` §8.
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
    "flag_set",
    "flag_not_set",
    "item_in_inventory",
    "object_present",
    "npc_present",
)
_DIALOGUE_CONDITIONS = ("required_flags", "forbidden_flags")


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


def test_catalog_detects_the_flag_family_drift() -> None:
    """The self-check surfaces exactly the two known synonym pairs A0.5 will rename.

    `flag_set` (command) and `required_flags` (dialogue) both mean "actor has flag"; likewise
    `flag_not_set`/`forbidden_flags`. These share a capability signature under different names —
    the drift ``docs/scripting_engine_design.md`` §8.6 exists to kill.
    """
    groups = {tuple(e.name for e in group) for group in global_vocabulary().overlaps()}
    assert ("flag_set", "required_flags") in groups
    assert ("flag_not_set", "forbidden_flags") in groups
    # And no *other* accidental duplicates among the migrated built-ins.
    assert len(groups) == 2
