#!/usr/bin/env python3
"""
Lorecraft Parser Diagnostic CLI
Usage:
    python tools/parser_diag.py "give the lead pipe to Gabriel"
    python tools/parser_diag.py --json "take red potion; light it"
"""

import argparse
import json
import sys
from pathlib import Path

# Make sure we can import from src
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from lorecraft.game.parser import diagnose_command, GameContext


def main():
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

    # Use stub context (extend with real one if you want richer resolution in diagnostics)
    context = GameContext()

    diag = diagnose_command(args.command, context=context, verbose=not args.no_verbose)

    if args.json:
        # Simple serialization
        output = {
            "raw": diag.raw,
            "normalized": diag.normalized,
            "tokens": diag.tokens,
            "steps": [{"name": s.name, "details": s.details} for s in diag.steps],
            "error": diag.error,
        }
        if diag.final_result:
            output["final_result"] = {
                "commands": [
                    {
                        "verb": c.verb,
                        "roles": c.roles,
                        "resolved_ids": c.resolved_ids,
                        "parse_notes": c.parse_notes,
                    }
                    for c in diag.final_result.commands
                ],
                "error_message": diag.final_result.error_message,
                "suggestions": diag.final_result.suggestions,
            }
        print(json.dumps(output, indent=2, default=str))


if __name__ == "__main__":
    main()
