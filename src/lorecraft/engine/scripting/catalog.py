"""Render the scripting vocabulary catalog to JSON and a builder-guide Markdown doc.

The catalog is *generated* from the self-describing descriptors so it can never drift from
the code (``docs/scripting_engine_design.md`` §8.2). These functions are **pure** — they take
a :class:`~lorecraft.engine.scripting.vocabulary.Vocabulary` and return text. This module is
Tier 1 and must not import features; *populating* the global catalog (importing the feature
registries) is the caller's job — see ``lorecraft.tools.world_cli``'s ``vocabulary`` command,
which lives in the composition layer where importing features is allowed.
"""

from __future__ import annotations

import json

from lorecraft.engine.scripting.vocabulary import VocabEntry, VocabKind, Vocabulary

_KIND_HEADINGS: dict[VocabKind, str] = {
    VocabKind.CONDITION: "Conditions (`when:`)",
    VocabKind.EFFECT: "Effects (`do:`)",
    VocabKind.BEHAVIOR_MODE: "NPC behavior modes (`behavior.mode`)",
}

_DO_NOT_EDIT = "<!-- GENERATED FILE — do not edit by hand. Regenerate with `make scripting-docs`. -->"


def render_json(vocab: Vocabulary) -> str:
    """The authoritative machine-readable catalog (stable key order, trailing newline)."""
    return json.dumps(vocab.to_json(), indent=2, sort_keys=False) + "\n"


def _render_entry(entry: VocabEntry) -> list[str]:
    cap = entry.capability
    lines = [
        f"#### `{entry.name}`",
        "",
        f"{entry.doc}",
        "",
        f"- **Subject:** `{entry.subject.value}`",
        f"- **Capability:** `{cap.domain}/{cap.attribute}` · `{cap.op}`",
    ]
    if entry.params:
        lines.append("- **Params:**")
        for p in entry.params:
            req = "required" if p.required else "optional"
            suffix = f" — {p.doc}" if p.doc else ""
            lines.append(f"  - `{p.name}` (`{p.type}`, {req}){suffix}")
    else:
        lines.append("- **Params:** _none_")
    lines.append("")
    return lines


def render_markdown(vocab: Vocabulary) -> str:
    """A builder-facing reference, grouped by kind → category → name.

    Deterministic output (``vocab.all()`` is sorted), so a CI drift-check can diff the
    committed copy against a fresh render and fail the build if a registration changed
    without regenerating the doc.
    """
    entries = vocab.all()
    lines: list[str] = [
        "# Scripting vocabulary reference",
        "",
        _DO_NOT_EDIT,
        "",
        "The declarative vocabulary a builder writes in `when:` / `do:` blocks and NPC",
        "`behavior:` — generated from the self-describing descriptors registered into the",
        "engine (see [`scripting_engine_design.md`](scripting_engine_design.md) §8). Each entry",
        "shows its subject role, capability signature, and parameters.",
        "",
        f"_{len(entries)} entries._",
        "",
    ]

    for kind in (VocabKind.CONDITION, VocabKind.EFFECT, VocabKind.BEHAVIOR_MODE):
        kind_entries = [e for e in entries if e.kind is kind]
        if not kind_entries:
            continue
        lines += [f"## {_KIND_HEADINGS[kind]}", ""]
        current_category: str | None = None
        for entry in kind_entries:  # already sorted by (category, name)
            if entry.category != current_category:
                current_category = entry.category
                lines += [f"### {current_category}", ""]
            lines += _render_entry(entry)

    overlaps = vocab.overlaps()
    if overlaps:
        lines += [
            "## ⚠ Capability overlaps",
            "",
            "These names share a capability signature — likely duplicates to reconcile to one",
            "canonical name (`docs/scripting_engine_design.md` §8.3):",
            "",
        ]
        for group in overlaps:
            names = ", ".join(f"`{e.name}`" for e in group)
            sig = str(group[0].capability)
            lines.append(f"- {names} — all `{sig}`")
        lines.append("")

    return "\n".join(lines).rstrip("\n") + "\n"
