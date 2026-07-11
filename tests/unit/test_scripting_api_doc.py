"""A0.3 — the generated scripting reference must not drift from the catalog.

`docs/scripting_api.md` is generated from the self-describing descriptors (§8.2). This test is
the CI drift-check: it re-renders the doc from the live catalog and fails if the committed copy
differs, so a registration change that forgets to regenerate the doc is caught in CI. Also
smoke-tests the `vocabulary` CLI command.
"""

from __future__ import annotations

import json
from pathlib import Path

from lorecraft.engine.scripting import catalog
from lorecraft.tools.world_cli import _load_scripting_vocabulary, main

_DOC = Path(__file__).resolve().parents[2] / "docs" / "scripting_api.md"


def test_scripting_api_doc_is_current() -> None:
    expected = catalog.render_markdown(_load_scripting_vocabulary())
    actual = _DOC.read_text(encoding="utf-8")
    assert actual == expected, (
        "docs/scripting_api.md is stale — run `make scripting-docs` and commit the result."
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
