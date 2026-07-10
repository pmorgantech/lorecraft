"""The scripting subsystem (Tier 1 engine).

A cohesive home for the declarative-scripting primitives described in
``docs/scripting_engine_design.md``:

* :mod:`~lorecraft.engine.scripting.vocabulary` — self-describing descriptors and the
  governed catalog (the "language" is a designed, introspectable API; §8).

Follow-up Phase-A modules land here as they're built: ``triggers`` (the ``on``/``when``/``do``
binding service), ``validator`` (the author-time linter), and ``catalog`` (doc/JSON
generation). The subsystem depends *on* ``engine.game`` primitives (e.g. ``WorldContext``);
``engine.game`` never imports back into it, keeping the arrow one-way.
"""

from __future__ import annotations

from lorecraft.engine.scripting.vocabulary import (
    CapabilitySig,
    ParamSpec,
    Subject,
    VocabEntry,
    Vocabulary,
    VocabKind,
    VocabularyError,
)

__all__ = [
    "CapabilitySig",
    "ParamSpec",
    "Subject",
    "VocabEntry",
    "VocabKind",
    "Vocabulary",
    "VocabularyError",
]
