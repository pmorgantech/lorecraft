> **📦 Archived (2026-07-18).** Merged into [`parser_and_commands.md`](../engine/parser_and_commands.md),
> now the single canonical parser/command-authoring reference. Kept here only for history.

# Command Parser — Integration Guide

This document describes how the Lorecraft parser structures player input, how command
handlers should consume that structure, and which **command patterns** apply to different
verb families.

For implementation details and diagnostics, see `src/lorecraft/engine/game/parser.py` and
`tools/parser_diag.py`.

For **authoring new commands**, item disambiguation behaviour, and the Key Gallery test
room, see **[parser_and_commands.md](../engine/parser_and_commands.md)**.

---

## Parser output model

`parse_command(raw, context=ctx)` returns a `ParseResult`:

| Field | Meaning |
|-------|---------|
| `commands` | One or more `ParsedCommand` structs (semicolon-separated compounds) |
| `error_message` | In-character failure text when parsing or disambiguation fails |
| `suggestions` | Short list of likely matches (e.g. ambiguous `take key`) |

Each `ParsedCommand` contains:

| Field | Meaning |
|-------|---------|
| `verb` | Normalized verb (`move`, `take`, `give`, `examine`, …) |
| `raw` | Original player text (audit / replay) |
| `roles` | Semantic role dictionary (see below) |
| `resolved_ids` | Optional entity IDs after `GameContext` fuzzy match |
| `parse_notes` | Parser diagnostics (non-player-facing) |
| `noun` | **Legacy** convenience property — primary phrase for old handlers |

### Role keys (v1)

Roles are a flexible dictionary. Common keys:

| Role | Typical use |
|------|-------------|
| `object` | Item being manipulated (`take sword`, `drop coin`) |
| `target` | Entity acted upon (`open door`, `attack goblin`) |
| `instrument` | Tool/weapon (`unlock chest with key`) |
| `recipient` | Person receiving something (`give coin to Gabriel`) |
| `source` | Origin container (`take coin from purse`) |
| `destination` | Destination container/surface (`put apple in backpack`) |
| `direction` | Movement direction (`north`, `up`) |
| `quantity` | Numeric amount (`take 2 coin`) |
| `adjectives` | Leading modifiers (`red` in `take red potion`) |
| `message` | Spoken text (`say hello`, `whisper "psst" to Mira`) |
| `topic` | Dialogue subject (`ask Mira about quests`) |

**v1 limitations** (by design):

- No deep nesting (`take coin from purse in chest` is not auto-unpacked).
- Pronoun carry in compounds is basic (`take lantern; light it`).
- Role vocabulary may be standardized further in v2.

---

## Command patterns

Handlers should identify their **pattern** and read the matching roles — not assume a single
`noun` string covers every verb.

Taxonomy and helpers live in `src/lorecraft/engine/game/command_patterns.py`.

| Pattern | Verbs (examples) | Roles to read | Handler responsibility |
|---------|------------------|---------------|------------------------|
| **Movement** | `go`, `n`, `north` | `direction` | Move player via `MovementService` |
| **Bare** | `look`, `l`, `inventory`, `i` | _(none)_ | Room summary / inventory panel |
| **Object manipulation** | `take`, `drop`, `wear`, `remove` | `object`, `quantity`, `adjectives` | Resolve item in room or inventory; honour `all` / `everything` |
| **Container** | `put`, `open`, `close`, `examine`, `look in` | `object`, `destination` / `source` / `target` | Container graph; `look in chest` → `destination=chest` |
| **Transfer** | `give` | `object`, `recipient` | Requires **both**; validate recipient is present |
| **Tool use** | `unlock`, `use`, `lock` | `target` or `object`, `instrument`, `destination` | Tool + target pairing |
| **Combat** | `attack`, `kill` | `target`, `instrument` | Combat target selection |
| **Speech** | `say`, `yell`, `whisper`, `shout`, `scream` | `message`, optional `recipient` | Audience routing (see below) |
| **Social gesture** | `wave`, `bow`, `nod`, `smile` | optional `target` / `recipient` | Room-wide if undirected; directed `AT` one entity |
| **NPC dialogue** | `talk`, `ask`, `choice`, `bye` | `recipient`, `topic` | Dialogue trees / flags |
| **Meta** | `help`, `quit`, `save`, `load` | varies | Out-of-world or slot IO |

Use `pattern_for_verb(cmd.verb)` and typed helpers (`speech_roles`, `transfer_roles`,
`container_roles`, `gesture_roles`, …) when implementing handlers.

---

## How handlers should consume parser output

### Today (legacy bridge)

`CommandEngine` still calls:

```python
command.handler(parsed.noun, ctx)
```

`parsed.noun` collapses the most relevant role into one string for simple commands. This
works for movement and basic `take sword`, but **loses structure** for `give X to Y`,
`whisper "hi" to Gabriel`, or `put apple in chest`.

### Recommended (pattern-aware)

New handlers should accept the full `ParsedCommand` (or use pattern helpers):

```python
from lorecraft.engine.game.command_patterns import (
    CommandPattern,
    pattern_for_verb,
    speech_roles,
    transfer_roles,
)

def handle_give(parsed: ParsedCommand, ctx: GameContext) -> None:
    roles = transfer_roles(parsed)
    if roles is None:
        ctx.say("Give what to whom?")
        return
    # Prefer resolved_ids when present; fall back to phrase match
    item_id = roles.object_id or resolve_item(roles.object_phrase, ctx)
    recipient_id = roles.recipient_id or resolve_actor(roles.recipient, ctx)
    ...
```

Migration path:

1. Add pattern helpers to new verbs.
2. Gradually change `CommandHandler` signature to `(ParsedCommand, GameContext)`.
3. Keep `parsed.noun` only as a fallback for inventory-style single-phrase verbs.

---

## Pattern-specific guidance

### Movement

```
north          → verb=move, direction=north
go north       → verb=move, direction=north
n              → verb=move, direction=north
```

Registry maps `move` → `go` via `registry_verb()`.

### Object manipulation

```
take sword           → object=sword
take red potion      → object=potion, adjectives=[red]
take 2 coin          → object=coin, quantity=2
take all             → object=all   (service takes all takeable room items)
take all coin        → object=all coin
drop everything      → object=everything
```

Use `object_phrase(parsed)` or `parse_item_target(parsed.noun)` in `InventoryService`.

### Containers

```
put apple in backpack    → object=apple, destination=backpack
take coin from purse     → object=coin, source=purse
look in chest            → verb=examine, destination=chest
look at sword            → verb=examine, target=sword
open chest               → target=chest
```

`container_roles(parsed)` normalizes `destination` vs `target`.

### Transfer (give)

```
give lead pipe to Gabriel  → object=lead pipe, recipient=Gabriel
```

**Both roles required.** Missing recipient → “Give to whom?”; missing object → “Give what?”

### Speech and audience

| Input style | Parsed roles | Intended audience |
|-------------|--------------|-------------------|
| `say hello` | `message=hello` | Current room |
| `yell help` | `message=help` | Current room (loud) |
| `whisper "psst" to Gabriel` | `message`, `recipient` | One player/NPC |
| `tell Gabriel hello` | _(future: recipient + message split)_ | One player/NPC |

**Planned routing** (handler responsibility, not parser):

- `say` / `yell` → `tell_room`
- `whisper` / `tell` → single recipient in same room (fail if absent)
- `shout` / `scream` → room + adjacent rooms (once proximity model exists)

Parser only extracts roles; range logic belongs in a `SpeechService`.

### Social gestures

```
wave              → undirected (room-wide emote)
wave at Gabriel   → target=Gabriel
bow to Mira       → recipient=Mira
```

Use `gesture_roles(parsed)`. Undirected → broadcast short emote; directed → verify
target is visible.

### NPC dialogue

```
talk to Mira              → recipient=Mira
ask Mira about quests     → recipient=Mira, topic=quests
```

`talk` currently uses legacy `noun` matching; migrate to `recipient` + `resolved_ids`.

---

## Context resolution and disambiguation

When `GameContext` is passed to `parse_command`:

- `get_visible_entities()` — room items + NPCs as `(id, name, aliases)`
- `get_inventory()` — carried items

Strict disambiguation applies to **`take` / `drop` object** roles when multiple matches
score similarly (`take key` with several keys present).

Other roles use best-effort fuzzy match without blocking the command.

Prefer `resolved_ids[role]` in handlers when set.

---

## Compound commands

Semicolon separates sequential commands:

```
unlock chest with key; open chest; take gem
```

`CommandEngine` executes each `ParsedCommand` in order. Fail-fast on first parse error.

Basic pronoun carry: `take lantern; light it` substitutes `it` from the previous command's
object.

---

## Testing

| Suite | Purpose |
|-------|---------|
| `tests/game/test_parser_comprehensive.py` | Regression: roles, compounds, ambiguity |
| `tests/game/test_parser_patterns.py` | Pattern-grouped coverage by interaction type |
| `tests/unit/test_command_patterns.py` | Helper/unit tests for role extractors |
| `tests/unit/test_parser.py` | Legacy `parse()` bridge |

Run:

```bash
python -m pytest tests/game/ tests/unit/test_command_patterns.py -q
python tools/parser_diag.py "give the lead pipe to Gabriel"
```

When adding a verb:

1. Assign a `CommandPattern` in `VERB_PATTERNS`.
2. Add parametrized cases to `test_parser_patterns.py`.
3. Document expected roles in this file.
4. Implement handler using pattern helpers — not raw string splitting.

---

## Diagnostics

```bash
python tools/parser_diag.py "take red potion; light it"
python tools/parser_diag.py --json "whisper \"hi\" to Gabriel"
```

Shows normalization, tokens, role extraction, and resolution steps.
