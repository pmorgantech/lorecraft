"""Cross-language protocol-version drift check.

Asserts the checked-in Rust `schema/version.json` agrees with the Python
`PROTOCOL_VERSION`. Skips (rather than fails) when the Rust tree is absent, so the
Python-only test environments still pass; in the contracts worktree the file is
present and the parity is enforced.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from lorecraft.protocol.version import PROTOCOL_VERSION


def _schema_path() -> Path | None:
    # tests/unit/ -> repo root is two parents up.
    repo_root = Path(__file__).resolve().parents[2]
    candidate = (
        repo_root / "rust" / "crates" / "lorecraft-protocol" / "schema" / "version.json"
    )
    return candidate if candidate.is_file() else None


def test_rust_schema_version_matches_python_constant() -> None:
    path = _schema_path()
    if path is None:
        pytest.skip("rust/ protocol schema not present in this checkout")
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["protocol_version"] == PROTOCOL_VERSION
