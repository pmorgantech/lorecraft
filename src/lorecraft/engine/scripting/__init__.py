"""The scripting subsystem (Tier 1 engine).

A cohesive home for the declarative-scripting primitives described in
``docs/scripting_engine_design.md``:

* :mod:`~lorecraft.engine.scripting.vocabulary` — self-describing descriptors and the
  governed catalog (the "language" is a designed, introspectable API; §8).
* :mod:`~lorecraft.engine.scripting.catalog` — render the catalog to JSON / builder-guide doc.
* :mod:`~lorecraft.engine.scripting.validator` — fail-closed author-time linting of
  ``when:`` / ``do:`` blocks against the catalog.

Follow-up Phase-A modules land here as they're built: ``triggers`` (the ``on``/``when``/``do``
binding service). The subsystem depends *on* ``engine.game`` primitives (e.g. ``WorldContext``);
``engine.game`` never imports back into it, keeping the arrow one-way.
"""

from __future__ import annotations

from lorecraft.engine.scripting.catalog import render_json, render_markdown
from lorecraft.engine.scripting.validator import (
    ValidationIssue,
    validate_conditions,
    validate_effects,
)
from lorecraft.engine.scripting.vocabulary import (
    CapabilitySig,
    ParamSpec,
    Subject,
    VocabEntry,
    Vocabulary,
    VocabKind,
    VocabularyError,
    global_vocabulary,
)

__all__ = [
    "CapabilitySig",
    "ParamSpec",
    "Subject",
    "ValidationIssue",
    "VocabEntry",
    "VocabKind",
    "Vocabulary",
    "VocabularyError",
    "global_vocabulary",
    "render_json",
    "render_markdown",
    "validate_conditions",
    "validate_effects",
]
