"""Canonical event-trail hashing for replay determinism (Rust-port Phase 0).

A thin, dependency-light composition over
`lorecraft.tools.session_replay.normalize_events`: it collapses a normalised
audit trail into a single stable SHA-256 digest, so replay determinism can be
asserted as one hash comparison instead of a list `==` diff, and so the same
byte-canonicalisation rules can later be shared with a Rust reimplementation.

Kept separate from `session_replay.py` on purpose — that module pulls in
SQLModel/argparse for its record/CLI paths; this one only needs `hashlib`,
`json`, and the pure `normalize_events` projection, so parity harnesses can
import it cheaply.

Float policy: `canonical_json` **rejects** floats (raises `TypeError`). The
input here is always the normalised event dicts (`str | None` values today),
so the rejection costs nothing now, and it pre-empts a future Python/Rust-serde
float-formatting parity divergence by forcing pre-quantised int/str values at
the boundary rather than trusting two languages to format `0.1` identically.
"""

from __future__ import annotations

import json
from collections.abc import Iterable
from hashlib import sha256
from typing import cast

from lorecraft.engine.models.audit import AuditEvent
from lorecraft.tools.session_replay import normalize_events
from lorecraft.types import JsonValue


def _reject_floats(obj: JsonValue) -> None:
    """Recursively assert no `float` appears in `obj` (bools/ints are fine).

    `bool` is a subclass of `int` and is allowed; only genuine `float` values
    are rejected, since they are the ones that risk cross-language formatting
    divergence.
    """
    if isinstance(obj, float):
        raise TypeError(
            "canonical_json rejects floats to guarantee cross-language byte "
            f"parity; got {obj!r}. Pre-quantise to int or str before hashing."
        )
    if isinstance(obj, dict):
        for value in obj.values():
            _reject_floats(value)
    elif isinstance(obj, list):
        for item in obj:
            _reject_floats(item)


def canonical_json(obj: JsonValue) -> bytes:
    """Serialise `obj` to canonical UTF-8 JSON bytes (sorted keys, no spaces).

    Deterministic and stable: `sort_keys` fixes object key order,
    `separators=(",", ":")` strips insignificant whitespace, and
    `ensure_ascii=False` keeps non-ASCII as UTF-8 rather than `\\uXXXX`
    escapes. Floats are rejected up front (see module docstring).
    """
    _reject_floats(obj)
    return json.dumps(
        obj,
        sort_keys=True,
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode("utf-8")


def hash_events(events: Iterable[AuditEvent]) -> str:
    """Return the SHA-256 hex digest of an audit trail's normalised shape.

    `normalize_events` strips run-specific ids/timestamps to the same stable
    projection the audit-regression golden diff uses, so equal trails (modulo
    run noise) hash equal, and any change to event type/summary/target/room/
    severity or their order changes the digest.
    """
    # normalize_events returns list[dict[str, str | None]]; those values are all
    # JSON scalars, so the trail is a valid JsonValue. The cast only bridges
    # list/dict invariance (NormalizedEvent's value type isn't literally
    # JsonValue) — canonical_json still validates the structure at runtime.
    trail = cast(JsonValue, normalize_events(events))
    return sha256(canonical_json(trail)).hexdigest()
