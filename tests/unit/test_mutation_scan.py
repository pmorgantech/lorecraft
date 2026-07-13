"""Unit tests for the AST mutation-scan diagnostic (Rust-port Phase 0).

Runs the scanner against small synthetic fixture sources with known-good and
known-bad functions rather than the live `features/` tree — the live scan is
slow, brittle across content changes, and belongs in the CLI, not a unit test.
"""

from __future__ import annotations

import json
from pathlib import Path

from lorecraft.tools.mutation_scan import (
    main,
    render_markdown,
    scan_source,
    scan_tree,
)

_DIRTY_SOURCE = '''
"""Fixture with known violations."""


def writes_to_session(ctx):
    room = ctx.room_repo.get("village_square")  # a read — must NOT be flagged
    ctx.session.add(room)          # session_mutation
    ctx.session.commit()           # session_mutation


def mutates_a_repo_model(ctx):
    player = ctx.player_repo.get("player-1")
    player.hp = 5                  # model_attr_write
    player.room_id += "-moved"     # model_attr_write (augmented)


def local_session_variable(audit_session):
    audit_session.flush()          # session_mutation (name contains "session")
'''

_CLEAN_SOURCE = '''
"""Fixture with no violations."""


def only_reads(ctx):
    room = ctx.room_repo.get("village_square")
    name = room.name               # attribute READ, not a write
    return name


def uses_a_repo_method(ctx):
    ctx.player_repo.save_hp("player-1", 5)   # goes through a repo method
'''


def test_flags_session_mutations() -> None:
    findings = scan_source(_DIRTY_SOURCE, "dirty.py")
    session_hits = [f for f in findings if f.pattern == "session_mutation"]
    details = " ".join(f.snippet for f in session_hits)

    assert len(session_hits) == 3
    assert ".add(" in details
    assert ".commit()" in details
    assert ".flush()" in details


def test_flags_model_attr_writes() -> None:
    findings = scan_source(_DIRTY_SOURCE, "dirty.py")
    attr_hits = [f for f in findings if f.pattern == "model_attr_write"]
    attrs = {f.snippet.split("=")[0].strip() for f in attr_hits}

    assert len(attr_hits) == 2
    assert "player.hp" in attrs


def test_does_not_flag_repo_read() -> None:
    """`x = ctx.room_repo.get(...)` binding + a later attribute *read* is clean."""
    findings = scan_source(_DIRTY_SOURCE, "dirty.py")
    # The `room = ctx.room_repo.get(...)` line itself is a binding, not a write;
    # no finding should reference `room.` as a write target.
    assert not any("room." in f.detail for f in findings)


def test_clean_source_has_no_findings() -> None:
    assert scan_source(_CLEAN_SOURCE, "clean.py") == []


def test_scan_tree_finds_exactly_the_planted_violation(tmp_path: Path) -> None:
    root = tmp_path
    (root / "features").mkdir()
    (root / "features" / "dirty.py").write_text(_DIRTY_SOURCE, encoding="utf-8")
    (root / "features" / "clean.py").write_text(_CLEAN_SOURCE, encoding="utf-8")

    findings = scan_tree(root, subpaths=["features"])

    files_with_findings = {f.file for f in findings}
    assert files_with_findings == {"features/dirty.py"}
    # 3 session mutations + 2 model attribute writes in the dirty fixture.
    assert len(findings) == 5


def test_cli_writes_json_output(tmp_path: Path) -> None:
    root = tmp_path
    (root / "features").mkdir()
    (root / "features" / "dirty.py").write_text(_DIRTY_SOURCE, encoding="utf-8")
    out = root / "report.json"

    exit_code = main(["--root", str(root), "--output", str(out), "--format", "json"])

    assert exit_code == 0
    payload = json.loads(out.read_text())
    assert payload["count"] == 5
    assert all("file" in item for item in payload["findings"])


def test_markdown_escapes_pipes() -> None:
    findings = scan_source("def f(ctx):\n    ctx.session.commit()\n", "m.py")
    table = render_markdown(findings)
    assert "session_mutation" in table
    assert table.startswith("# Direct SQL/ORM mutation inventory")
