"""Tests for the scripting-vocabulary governance layer (engine/scripting/vocabulary.py).

Covers the three jobs the descriptors exist for: registration with exact-name collision
detection, capability-signature duplication detection, and serialization for the generated
catalog. See docs/scripting_engine_design.md §8.
"""

from __future__ import annotations

import pytest

from lorecraft.engine.scripting.vocabulary import (
    CapabilitySig,
    ParamSpec,
    Subject,
    VocabEntry,
    Vocabulary,
    VocabKind,
    VocabularyError,
)


def _condition(
    name: str,
    *,
    subject: Subject = Subject.ACTOR,
    domain: str = "reputation",
    attribute: str = "standing",
    op: str = "at_least",
    category: str = "social",
    params: tuple[ParamSpec, ...] = (),
) -> VocabEntry:
    return VocabEntry(
        name=name,
        kind=VocabKind.CONDITION,
        subject=subject,
        category=category,
        doc=f"{name} test entry",
        capability=CapabilitySig(subject, domain, attribute, op),
        params=params,
    )


def test_register_and_get_roundtrip() -> None:
    vocab = Vocabulary()
    entry = vocab.register(_condition("actor_reputation_at_least"))
    assert vocab.get("actor_reputation_at_least") is entry
    assert "actor_reputation_at_least" in vocab
    assert len(vocab) == 1


def test_get_unknown_returns_none() -> None:
    assert Vocabulary().get("nope") is None


def test_name_reused_for_different_capability_is_hard_error() -> None:
    vocab = Vocabulary()
    vocab.register(_condition("actor_reputation_at_least"))
    # Same name, *different* capability (op differs) — the collision we reject.
    with pytest.raises(VocabularyError, match="already registered"):
        vocab.register(_condition("actor_reputation_at_least", op="below"))


def test_same_capability_reregistration_is_idempotent() -> None:
    """One canonical predicate on two surfaces / a re-enabled feature = a no-op."""
    vocab = Vocabulary()
    first = vocab.register(_condition("actor_reputation_at_least"))
    again = vocab.register(
        _condition("actor_reputation_at_least")
    )  # identical capability
    assert again is first
    assert len(vocab) == 1


def test_overlaps_detects_capability_synonyms() -> None:
    """Two differently-named entries with one capability signature = a duplicate."""
    vocab = Vocabulary()
    vocab.register(_condition("actor_reputation_at_least"))
    # `min_reputation` is the historical synonym — different name, same capability.
    vocab.register(_condition("min_reputation"))

    overlaps = vocab.overlaps()
    assert len(overlaps) == 1
    names = [entry.name for entry in overlaps[0]]
    assert names == ["actor_reputation_at_least", "min_reputation"]  # sorted


def test_no_overlap_for_distinct_capabilities() -> None:
    vocab = Vocabulary()
    vocab.register(_condition("actor_reputation_at_least", op="at_least"))
    vocab.register(_condition("actor_reputation_below", op="below"))
    vocab.register(
        _condition("actor_has_flag", domain="flags", attribute="<flag>", op="has")
    )
    assert vocab.overlaps() == []


def test_all_sorted_by_category_then_name() -> None:
    vocab = Vocabulary()
    vocab.register(_condition("z_social", category="social"))
    vocab.register(
        _condition("a_clock", category="world_clock", domain="clock", op="is")
    )
    vocab.register(_condition("a_social", category="social", op="below"))
    assert [e.name for e in vocab.all()] == ["a_social", "z_social", "a_clock"]


def test_by_category_groups() -> None:
    vocab = Vocabulary()
    vocab.register(_condition("actor_reputation_at_least", category="social"))
    vocab.register(
        _condition("world_season_is", category="world_clock", domain="clock", op="is")
    )
    grouped = vocab.by_category()
    assert set(grouped) == {"social", "world_clock"}
    assert [e.name for e in grouped["social"]] == ["actor_reputation_at_least"]


def test_to_json_shape_is_catalog_ready() -> None:
    vocab = Vocabulary()
    vocab.register(
        _condition(
            "actor_reputation_at_least",
            params=(ParamSpec("faction", "faction"), ParamSpec("value", "int")),
        )
    )
    payload = vocab.to_json()
    assert list(payload) == ["entries"]
    entries = payload["entries"]
    assert isinstance(entries, list)
    entry = entries[0]
    assert isinstance(entry, dict)
    assert entry["name"] == "actor_reputation_at_least"
    assert entry["kind"] == "condition"
    assert entry["subject"] == "actor"
    assert entry["capability"] == {
        "subject": "actor",
        "domain": "reputation",
        "attribute": "standing",
        "op": "at_least",
    }
    assert entry["params"] == [
        {"name": "faction", "type": "faction", "required": True, "doc": ""},
        {"name": "value", "type": "int", "required": True, "doc": ""},
    ]


def test_capability_sig_str_is_stable() -> None:
    sig = CapabilitySig(Subject.ACTOR, "reputation", "standing", "at_least")
    assert str(sig) == "actor:reputation:standing:at_least"
