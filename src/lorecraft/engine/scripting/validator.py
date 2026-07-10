"""Author-time validation of ``when:`` / ``do:`` blocks against the vocabulary catalog.

This is the **fail-closed** half of §8.5: at authoring / load / CI time, every condition and
effect name is checked against the catalog and obvious param-shape mistakes are reported, so a
typo is caught *where it was written* instead of silently no-op'ing at runtime (the registries
stay fail-open at execution). The same validator is meant to back richer surfaces later (an
editor LSP, the webui builder form) — it's a pure library, not welded to the load path.

Pure Tier 1: it validates data against a :class:`~lorecraft.engine.scripting.vocabulary.Vocabulary`
and imports no features. A2 wires it into the ``triggers:`` loader once that schema exists.

Two authoring shapes are accepted for a block of named entries, matching the surfaces in
``docs/scripting_engine_design.md`` Appendix A:

* a **map** ``{name: data, ...}`` (dialogue conditions / side effects today), and
* an ordered **list of single-key maps** ``[{name: data}, ...]`` (a trigger ``do:`` sequence).

``when:`` additionally allows one level of ``any:`` / ``all:`` boolean grouping; deeper nesting
is the Phase-B behavior-tree line and is reported as unsupported.
"""

from __future__ import annotations

from dataclasses import dataclass

from lorecraft.engine.scripting.vocabulary import VocabEntry, VocabKind, Vocabulary
from lorecraft.types import JsonValue

_BOOL_GROUPS = ("any", "all")


@dataclass(frozen=True)
class ValidationIssue:
    """One author-time problem: an unknown/misused name or a bad param shape."""

    location: str  # where in the source, e.g. "brass_sentinel.triggers[0].when"
    name: str  # the offending vocabulary name ("" for structural issues)
    message: str

    def __str__(self) -> str:
        return f"{self.location}: {self.message}"


def _iter_named(block: JsonValue) -> list[tuple[str, JsonValue]]:
    """Yield ``(name, data)`` pairs from either accepted block shape.

    A list may hold single-key maps (``[{name: data}]``) or bare string names
    (``[name]``, data defaulting to ``None``). Unrecognised list items are surfaced under the
    empty name so the caller reports a structural error rather than silently skipping them.
    """
    pairs: list[tuple[str, JsonValue]] = []
    if isinstance(block, dict):
        return list(block.items())
    if isinstance(block, list):
        for item in block:
            if isinstance(item, str):
                pairs.append((item, None))
            elif isinstance(item, dict) and len(item) == 1:
                pairs.extend(item.items())
            else:
                pairs.append(("", item))  # malformed entry — flagged by the caller
    return pairs


def _check_params(
    entry: VocabEntry, data: JsonValue, location: str
) -> list[ValidationIssue]:
    """Best-effort param-shape check.

    Conservative on purpose while the legacy encodings coexist (§8.4): a descriptor with two or
    more params is checked as a map (its required keys must be present); zero- and single-param
    descriptors accept the legacy scalar / list / colon-string forms without complaint. A0.5's
    rename to structured maps lets this tighten to every param later.
    """
    required = [p.name for p in entry.params if p.required]
    if len(entry.params) < 2:
        return []
    if not isinstance(data, dict):
        return [
            ValidationIssue(
                location,
                entry.name,
                f"'{entry.name}' expects a map with keys {required}",
            )
        ]
    missing = [key for key in required if key not in data]
    if missing:
        return [
            ValidationIssue(
                location,
                entry.name,
                f"'{entry.name}' is missing required param(s): {missing}",
            )
        ]
    return []


def _check_entry(
    name: str,
    data: JsonValue,
    vocab: Vocabulary,
    expected: VocabKind,
    location: str,
) -> list[ValidationIssue]:
    if not name:
        return [ValidationIssue(location, "", "malformed entry (expected a name)")]
    entry = vocab.get(name)
    if entry is None:
        return [ValidationIssue(location, name, f"unknown {expected.value} '{name}'")]
    if entry.kind is not expected:
        return [
            ValidationIssue(
                location,
                name,
                f"'{name}' is a {entry.kind.value}, not a {expected.value}",
            )
        ]
    return _check_params(entry, data, location)


def validate_conditions(
    block: JsonValue,
    vocab: Vocabulary,
    *,
    location: str = "when",
    _depth: int = 0,
) -> list[ValidationIssue]:
    """Validate a ``when:`` block; recurses one level into ``any:`` / ``all:`` groups."""
    issues: list[ValidationIssue] = []
    for name, data in _iter_named(block):
        if name in _BOOL_GROUPS:
            if _depth >= 1:
                issues.append(
                    ValidationIssue(
                        f"{location}.{name}",
                        name,
                        "nested boolean groups beyond one level are not supported "
                        "in Phase A (see design §5, behavior-tree grammar is Phase B)",
                    )
                )
                continue
            members = data if isinstance(data, list) else []
            if not isinstance(data, list):
                issues.append(
                    ValidationIssue(
                        f"{location}.{name}",
                        name,
                        f"'{name}' expects a list of conditions",
                    )
                )
            for i, member in enumerate(members):
                issues.extend(
                    validate_conditions(
                        member,
                        vocab,
                        location=f"{location}.{name}[{i}]",
                        _depth=_depth + 1,
                    )
                )
            continue
        issues.extend(_check_entry(name, data, vocab, VocabKind.CONDITION, location))
    return issues


def validate_effects(
    block: JsonValue, vocab: Vocabulary, *, location: str = "do"
) -> list[ValidationIssue]:
    """Validate a ``do:`` block (a map or an ordered list of single-key maps)."""
    issues: list[ValidationIssue] = []
    for name, data in _iter_named(block):
        issues.extend(_check_entry(name, data, vocab, VocabKind.EFFECT, location))
    return issues
