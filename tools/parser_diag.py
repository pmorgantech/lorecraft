#!/usr/bin/env python3
"""Lorecraft parser diagnostic CLI."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from lorecraft.game.parser import diagnose_command


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Lorecraft Parser Diagnostics (offline)"
    )
    parser.add_argument("command", nargs="?", help="Command string to diagnose")
    parser.add_argument(
        "--json", action="store_true", help="Output diagnostics as JSON"
    )
    parser.add_argument(
        "--no-verbose", action="store_true", help="Suppress pretty print"
    )
    args = parser.parse_args()

    if not args.command:
        print("Please provide a command in quotes, e.g.:")
        print('  python tools/parser_diag.py "take the red potion from the chest"')
        sys.exit(1)

    diag = diagnose_command(args.command, context=None, verbose=not args.no_verbose)

    if args.json:
        output = {
            "raw": diag.raw,
            "normalized": diag.normalized,
            "tokens": diag.tokens,
            "steps": [
                {"name": step.name, "details": step.details} for step in diag.steps
            ],
            "error": diag.error,
        }
        if diag.final_result:
            output["final_result"] = {
                "commands": [
                    {
                        "verb": command.verb,
                        "roles": command.roles,
                        "resolved_ids": command.resolved_ids,
                        "parse_notes": command.parse_notes,
                    }
                    for command in diag.final_result.commands
                ],
                "error_message": diag.final_result.error_message,
                "suggestions": diag.final_result.suggestions,
            }
        print(json.dumps(output, indent=2, default=str))


if __name__ == "__main__":
    main()
