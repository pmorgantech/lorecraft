"""A0.3 — the generated scripting reference must not drift from the catalog.

`docs/worldbuilding/scripting_api.md` is generated from the self-describing descriptors
(§8.2). This test is the CI drift-check: it re-renders the doc from the live catalog and
fails if the committed copy differs, so a registration change that forgets to regenerate the
doc is caught in CI. Also smoke-tests the `vocabulary` CLI command.
"""

from __future__ import annotations

import json
from pathlib import Path

from lorecraft.engine.scripting import catalog
from lorecraft.engine.scripting.vocabulary import VocabKind
from lorecraft.tools.world_cli import _load_scripting_vocabulary, main

_DOC = (
    Path(__file__).resolve().parents[2] / "docs" / "worldbuilding" / "scripting_api.md"
)


def test_scripting_api_doc_is_current() -> None:
    expected = catalog.render_markdown(_load_scripting_vocabulary())
    actual = _DOC.read_text(encoding="utf-8")
    assert actual == expected, (
        "docs/worldbuilding/scripting_api.md is stale — run `make scripting-docs` and commit the result."
    )


def test_rendered_doc_marks_generated() -> None:
    text = _DOC.read_text(encoding="utf-8")
    assert "GENERATED FILE" in text
    assert "make scripting-docs" in text


def test_render_json_is_valid_and_matches_catalog() -> None:
    vocab = _load_scripting_vocabulary()
    payload = json.loads(catalog.render_json(vocab))
    names = {e["name"] for e in payload["entries"]}
    assert {"set_flags", "actor_has_flag", "actor_lacks_flag"} <= names


def test_vocabulary_cli_json_runs(capsys) -> None:  # type: ignore[no-untyped-def]
    rc = main(["vocabulary", "--json"])
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["entries"], "CLI emitted an empty catalog"


def test_vocabulary_cli_category_filter(capsys) -> None:  # type: ignore[no-untyped-def]
    rc = main(["vocabulary", "--json", "--category", "combat"])
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert {e["name"] for e in payload["entries"]} == {"in_combat", "not_in_combat"}


def test_loader_enables_features_without_crashing() -> None:
    """The generator wires (enables) every discovered feature, not just imports it.

    Enable-time ``register_fn``s run against a doc-generation ``AppState`` stand-in;
    this asserts none of the currently-registered features blow up during that wiring
    (the stub carries enough surface — a populated ``ServiceContainer`` — for all of
    them). A non-empty catalog is the smoke signal that wiring completed.
    """
    vocab = _load_scripting_vocabulary()
    assert len(vocab) > 0
    # Idempotent: enabling twice in the same process must not raise (VocabularyError on
    # a same-capability re-register is a no-op — see Vocabulary.register).
    assert len(_load_scripting_vocabulary()) == len(vocab)


def test_enable_time_reputation_vocab_is_catalogued() -> None:
    """Reputation's vocab registers at *enable* time (inside its ``register_fn``), not
    module import, so it only reaches the catalog because the generator now enables
    features. Guards the part-(b) ``register_spec`` migration."""
    vocab = _load_scripting_vocabulary()

    condition = vocab.get("actor_reputation_at_least")
    assert condition is not None, "reputation condition missing from catalog"
    assert condition.kind is VocabKind.CONDITION
    assert condition.category == "reputation"

    effect = vocab.get("adjust_reputation")
    assert effect is not None, "adjust_reputation missing from catalog"
    assert effect.kind is VocabKind.EFFECT

    # Two authoring surfaces, one canonical capability — no accidental duplicate.
    assert vocab.overlaps() == []
