"""Import-direction enforcement for the Tier 1/Tier 2/web split.

The tier refactor (docs/tier_split_refactor.md) physically separates the engine
(Tier 1, ``lorecraft.engine``), optional features (Tier 2,
``lorecraft.features``), and the web delivery hosts (``lorecraft.webui.player`` /
``lorecraft.webui``). The whole point is enforceable direction:

* ``engine/`` must not import ``features/`` or any web host — it runs headless.
* ``features/`` must not import a web host — features are game mechanics, not
  presentation. (A feature's optional ``presentation.py`` is imported *by* the
  host, never the reverse.)

These tests parse every module's imports with ``ast`` (catching lazy in-function
imports too, not just top-level ones) and fail with the exact offending
``file: imported-module`` pairs, so a regression names itself.
"""

from __future__ import annotations

import ast
from collections.abc import Iterator
from pathlib import Path

SRC_ROOT = Path(__file__).resolve().parents[2] / "src" / "lorecraft"

# Web host packages. ``web`` is the current player/admin frontend; ``webui`` is
# its post-refactor home (step 10). Both are forbidden imports for engine/features.
WEB_PREFIXES = ("lorecraft.webui.player", "lorecraft.webui")
FEATURES_PREFIX = "lorecraft.features"


def _imported_modules(path: Path) -> set[str]:
    """Every dotted module name imported by ``path`` (any import statement)."""
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            modules.add(node.module)
    return modules


def _py_files(package: str) -> Iterator[Path]:
    yield from (SRC_ROOT / package).rglob("*.py")


def _violations(package: str, forbidden: tuple[str, ...]) -> list[str]:
    bad: list[str] = []
    for path in _py_files(package):
        for module in _imported_modules(path):
            if any(module == p or module.startswith(p + ".") for p in forbidden):
                rel = path.relative_to(SRC_ROOT.parent.parent)
                bad.append(f"{rel} -> {module}")
    return bad


def test_engine_does_not_import_features_or_web() -> None:
    violations = _violations("engine", (FEATURES_PREFIX, *WEB_PREFIXES))
    assert not violations, (
        "engine/ (Tier 1) must not import features/ or a web host; found:\n  "
        + "\n  ".join(sorted(violations))
    )


def test_features_do_not_import_web() -> None:
    violations = _violations("features", WEB_PREFIXES)
    assert not violations, (
        "features/ (Tier 2) must not import a web host; found:\n  "
        + "\n  ".join(sorted(violations))
    )
