# Lorecraft Parser v1 Package

This package contains an enhanced, fully deterministic command parser for Lorecraft, plus comprehensive tests and an offline diagnostic tool.

## What's Included

- `src/lorecraft/game/parser.py` — Drop-in improved parser with:
  - Semantic roles (flexible dict)
  - Prepositions, adjectives, quantities, multiple objects
  - Quoted strings, phrasal verbs, synonyms
  - Compound commands separated by `;`
  - Optional GameContext fuzzy resolution + disambiguation
  - Full diagnostic tracing
  - In-character error messages

- `tests/game/test_parser_comprehensive.py` — Large pytest suite covering all your examples + edges, plurals, ambiguity, compounds, etc.

- `tools/parser_diag.py` — Standalone offline CLI to inspect parser guts for any command.

## Quick Start (Development / Testing)

```bash
cd lorecraft_parser_v1

# Run all tests
python -m pytest tests/game/test_parser_comprehensive.py -q

# Diagnostic mode (offline)
python tools/parser_diag.py "give the lead pipe to Gabriel"
python tools/parser_diag.py --json "take red potion; light it"
python tools/parser_diag.py "unlock chest with key; open it"
```

## Integration into Your Repo

1. Copy `src/lorecraft/game/parser.py` over your existing file (or merge the new functions).
2. Add the test file to your `tests/game/` directory.
3. Optionally add `tools/parser_diag.py` to your tools/ folder and make it executable.
4. Update any imports in `engine.py` if the `parse_command` signature changed slightly (it now accepts optional `context`).
5. In `CommandEngine.handle_command`, call:
   ```python
   result = parse_command(command_text, context=game_context)
   if result.error_message:
       player.send_in_character_message(result.error_message)
       if result.suggestions:
           player.send_message("Perhaps you meant: " + ", ".join(result.suggestions))
       return
   for cmd in result.commands:
       # feed cmd.verb + cmd.roles into your Rules / Transaction layer
   ```

## Role Keys (Current v1)

Flexible dictionary. Commonly used keys:
- `object` / `objects`
- `target`
- `instrument` (also `tool`, `weapon`)
- `recipient`
- `source`
- `destination`
- `direction`
- `quantity`
- `adjectives` (list)
- `message`
- `topic`
- `subobject`

We can lock down a stricter standardized vocabulary in v2 if desired.

## v1 Scope & Known Limitations (as discussed)

- No automatic deep nesting (e.g. "coin from purse in chest"). Player must do sequential commands.
- Pronoun resolution ("it") and implicit objects are basic in compounds only. Full history tracking is TODO for v2.
- Role key names are pragmatic rather than rigidly standardized — open for discussion.
- Always returns in-character error messages.

## Future Directions

- Stronger pronoun / implicit object support once GameContext tracks recent actions.
- Standardized role key enum / constants.
- Optional lightweight embedding similarity for even better fuzzy matching (CPU-only, opt-in).

This parser + diagnostics + tests should give you a solid, observable foundation for the text-adventure experience.

If you need adjustments, more test cases, or help wiring it into engine.py / GameContext, just let me know!
