"""Parser diagnostics and debugging utilities."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, cast

from lorecraft.types import JsonValue

if TYPE_CHECKING:
    from lorecraft.game.context import GameContext
    from lorecraft.game.parser import ParseResult


@dataclass
class ParseStep:
    """A single step in the parse diagnostic log."""

    name: str
    details: dict[str, JsonValue] = field(default_factory=dict)


@dataclass
class ParseDiagnostics:
    """Full parse diagnostics with steps and final result."""

    raw: str
    normalized: str = ""
    tokens: list[str] = field(default_factory=list)
    steps: list[ParseStep] = field(default_factory=list)
    final_result: ParseResult | None = None
    error: str | None = None


def diagnose_command(
    raw: str,
    context: GameContext | None = None,
    *,
    verbose: bool = True,
) -> ParseDiagnostics:
    """Parse a command and collect diagnostic information."""
    from lorecraft.game.grammar import normalize, tokenize
    from lorecraft.game.parser import parse_command

    diag = ParseDiagnostics(raw=raw)
    diag.normalized = normalize(raw)
    diag.tokens = tokenize(diag.normalized)
    diag.steps.append(
        ParseStep(
            "normalize_tokenize",
            {
                "normalized": diag.normalized,
                "tokens": cast(JsonValue, diag.tokens),
            },
        )
    )

    result = parse_command(raw, context=context)
    diag.final_result = result

    if result.commands:
        diag.steps.append(
            ParseStep(
                "final_commands",
                {
                    "count": len(result.commands),
                    "verbs": cast(
                        JsonValue, [command.verb for command in result.commands]
                    ),
                    "roles": cast(
                        JsonValue, [command.roles for command in result.commands]
                    ),
                },
            )
        )
    else:
        diag.error = result.error_message
        diag.steps.append(
            ParseStep(
                "error",
                {
                    "message": result.error_message,
                    "suggestions": cast(JsonValue, result.suggestions),
                },
            )
        )

    if verbose:
        print_diagnostics(diag)
    return diag


def print_diagnostics(diag: ParseDiagnostics) -> None:
    """Pretty-print parser diagnostics."""
    print(f"\n{'=' * 60}")
    print("LORECRAFT PARSER DIAGNOSTICS")
    print(f"Raw input : {diag.raw!r}")
    print(f"Normalized: {diag.normalized}")
    print(f"Tokens    : {diag.tokens}")
    print("-" * 60)
    for step in diag.steps:
        print(f"\n[ {step.name} ]")
        for key, value in step.details.items():
            print(f"  {key}: {value}")
    if diag.final_result:
        print("\n--- FINAL RESULT ---")
        if diag.final_result.commands:
            for index, command in enumerate(diag.final_result.commands):
                print(f"Command {index + 1}: verb={command.verb}")
                print(f"  roles: {command.roles}")
                if command.resolved_ids:
                    print(f"  resolved: {command.resolved_ids}")
                if command.parse_notes:
                    print(f"  notes: {command.parse_notes}")
        if diag.final_result.error_message:
            print(f"Error (in-character): {diag.final_result.error_message}")
            if diag.final_result.suggestions:
                print(f"Suggestions: {diag.final_result.suggestions}")
    print("=" * 60 + "\n")
