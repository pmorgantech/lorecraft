"""Shared repo-root path resolution for repo-tracked content YAML files."""

from __future__ import annotations

from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[3]


def resolve_repo_path(path: str) -> Path:
    """Resolve a path relative to the repo root when it isn't already a real file."""
    candidate = Path(path)
    if candidate.is_file():
        return candidate
    repo_relative = _REPO_ROOT / path
    if repo_relative.is_file():
        return repo_relative
    return candidate
