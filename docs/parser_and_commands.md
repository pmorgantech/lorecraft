# Parser Output and Command Authoring

This guide explains how to **author new commands** that consume the advanced parser's
semantic roles, how **item matching and disambiguation** work in practice, and where to
find test data for similar item names.

Related references:

- [command_parser.md](command_parser.md) — parser output model and pattern taxonomy
- `src/lorecraft/engine/game/command_patterns.py` — typed role helpers
- `tests/fixtures/disambig_fixtures.py` — pytest-only similar-item test room

---

## End-to-end command flow

```
Player types text
    ↓
parse_command(raw, context=GameContext)
    ↓
ParseResult (1+ ParsedCommand, or in-character error)
    ↓
CommandEngine (registry lookup, conditions, rules)
    ↓
command.handler(parsed.noun, ctx)   ← legacy bridge today
    ↓
Service layer (InventoryService, MovementService, …)
```

The engine always passes a live `GameContext` into the parser so room items and
inventory can be considered during resolution.

---

## Parser output you should use

Each successful parse yields a `ParsedCommand`:

```python
@dataclass(frozen=True)
class ParsedCommand:
    verb: str
    raw: str
    roles: dict[str, JsonValue]       # semantic slots
    resolved_ids: dict[str, str]      # entity IDs when uniquely matched
    parse_notes: str = ""

    @property
    def noun(self) -> str | None:     # legacy single-phrase shortcut
        ...
```

### When to use `roles` vs `noun` vs `resolved_ids`

| Situation | Use |
|-----------|-----|
| Single-phrase inventory verbs (`take sword`) | `parsed.noun` or `object_phrase(parsed)` is fine short-term |
| Multi-slot verbs (`give X to Y`) | `transfer_roles(parsed)` — **never** rely on `noun` alone |
| Speech (`whisper "hi" to Mira`) | `speech_roles(parsed)` → `message` + optional `recipient` |
| Container verbs (`put X in Y`) | `container_roles(parsed)` |
| After fuzzy match | Prefer `parsed.resolved_ids["object"]` over re-parsing the phrase |

---

## Command patterns (what kind of parsing you need)

Identify your verb's pattern before writing the handler. See `CommandPattern` in
`command_patterns.py`.

### Movement — `direction`

```
north / n / go north
```

```python
from lorecraft.engine.game.command_patterns import movement_direction

direction = movement_direction(parsed)
if direction is None:
    ctx.say("Go where?")
    return
MovementService().move(direction, ctx)
```

Registry note: parser emits `verb="move"`; `registry_verb()` maps to registered `go`.

### Bare — no roles

```
look / l / inventory / i
```

Handler ignores roles; run room or inventory summary.

### Object manipulation — `object`, `quantity`, `adjectives`

```
take red key / take 2 coin / take all / drop everything
```

```python
from lorecraft.engine.game.command_patterns import object_phrase
from lorecraft.services.inventory import InventoryService, parse_item_target

phrase = object_phrase(parsed) or parsed.noun
if phrase is None:
    ctx.say("Take what?")
    return
InventoryService().take_item(phrase, ctx)
```

`InventoryService` understands `all`, quantities, and indexed selectors (`2.coin`).

### Container — `object`, `destination`, `source`, `target`

```
put apple in backpack
take coin from purse
look in chest        → verb examine, destination=chest
open chest           → target=chest
```

Use `container_roles(parsed)` and resolve each slot against room/inventory/container graph.

### Transfer — `object` + `recipient` (both required)

```
give lead pipe to Gabriel
```

```python
roles = transfer_roles(parsed)
if roles is None:
    ctx.say("Give what to whom?")
    return
# resolve roles.object_id / roles.recipient_id when present
```

### Tool use — `target`/`object` + `instrument` + optional `destination`

```
unlock chest with key
use key on chest
```

### Speech — `message` + optional `recipient`

| Player input | Roles | Intended audience (handler) |
|--------------|-------|-----------------------------|
| `say hello` | `message` only | Current room |
| `yell help` | `message` only | Current room (loud) |
| `whisper "psst" to Gabriel` | `message`, `recipient` | One visible actor |
| `tell Gabriel hello` | _(future split)_ | One visible actor |

Parser promotes spoken text into `message` for `say`, `whisper`, `shout`, `yell`, `scream`.

Audience range (adjacent rooms for `shout`, and so on) is **handler/service responsibility**,
not parser responsibility.

### Social gesture — optional `target` / `recipient`

```
wave                  → room-wide emote
wave at Gabriel       → directed
bow to Mira           → recipient=Mira
```

```python
gesture = gesture_roles(parsed)
if gesture.target is None:
    ctx.tell_room(f"{ctx.player.username} waves.")
else:
    # verify target visible, then direct message
    ...
```

### NPC dialogue — `recipient`, `topic`

```
talk to Mira
ask Mira about quests
```

---

## Authoring a new command (checklist)

### 1. Pick a pattern

Add your verb to `VERB_PATTERNS` in `command_patterns.py` if it introduces a new
interaction shape.

### 2. Register the handler

```python
@registry.register("wave", scope=CommandScope.SOCIAL)
def wave_command(noun: str | None, ctx: object) -> None:
    ...
```

### 3. Prefer pattern helpers inside the handler

**Today** handlers receive `(noun, ctx)`. Bridge from the full parse result by storing
`parsed` on the context or migrating the handler signature to `(parsed, ctx)`.

Recommended interim pattern:

```python
def handle_from_payload(payload: JsonObject, ctx: GameContext) -> None:
    parsed = _parsed_from_rule_payload(payload)  # roles + resolved_ids in audit payload
    roles = speech_roles(parsed)
    ...
```

The engine already passes `roles` and `resolved_ids` in rule/audit payloads via
`_command_audit_payload()`.

### 4. Resolve entities in the service layer

| Entity type | Resolution |
|-------------|------------|
| Room items | `ItemRepo.search_in_room(room_id, phrase)` |
| Carried items | `ItemRepo.search_player_items(inventory, phrase)` |
| NPCs | `npc_repo.in_room` + name prefix, or `resolved_ids["recipient"]` |
| Unique match | `resolved_ids` from parser when set |

### 5. Handle ambiguity explicitly

See **Item matching and disambiguation** below.

### 6. Add tests

- Parser role extraction in `tests/game/test_parser_patterns.py`
- Service behaviour in `tests/unit/`
- Fixture room items in `tests/fixtures/disambig_fixtures.py` when names overlap

---

## Item matching and disambiguation

Lorecraft uses **two complementary layers**. They behave differently on purpose.

### Layer 1 — Parser fuzzy match (`GameContext`)

When `parse_command(..., context=ctx)` runs, the parser can attach `resolved_ids` if a
phrase **uniquely** matches a visible or carried entity.

- Uses scoring (`difflib`, substring overlap, aliases).
- **Strict ambiguity errors** for non-inventory roles (e.g. `examine key` when several
  keys match).
- **`take` / `drop` object ambiguity is deferred** to Layer 2 so players get numbered
  choices instead of a dead-end parse error.

### Layer 2 — Inventory word-subset match (`ItemRepo`)

`InventoryService` resolves item phrases via `ItemRepo.search_in_room` /
`search_player_items`:

1. **Exact** normalized name or id match wins.
2. Otherwise **every query word** must appear in the item name (singularized).
   - `herbs` → `Bundle of Dried Herbs`
   - `key` → all items with word `key`
   - `iron` → `Iron Key`, `Rusty Iron Key`, `Rusty Iron Sword`
   - `rusty iron key` → unique `Rusty Iron Key`

When multiple items match, `_prompt_disambiguation()` emits:

```
Which do you mean? (1) Iron Key, (2) Rusty Iron Key, (3) Steel Key, ...
```

and stores:

```python
ctx.updates["disambig_pending"] = {
    "verb": "take",
    "noun": "key",
    "choices": ["Red Key", "Iron Key", ...],
}
```

The WebSocket handler in `main.py` intercepts a bare number (`1`, `2`, …) and rewrites
it to `take Red Key` on the next turn.

### Observed quirks (read before debugging)

| Behaviour | Layer | Notes |
|-----------|-------|-------|
| `take key` → numbered list | Inventory | Parser passes through; service prompts |
| `examine key` → parse error | Parser | No numbered prompt; must type more words |
| `take steel` → single match | Inventory | Word subset unique to Steel Key |
| `take iron` → ambiguous | Inventory | Three iron-related items |
| `take all` | Inventory | Empty query + `take_all`; takes all takeable room items |
| Parser exact name | Parser | `take rusty iron key` may set `resolved_ids["object"]` |

**Authoring guidance:** object-manipulation commands should delegate phrasing to
`InventoryService` and reuse its disambiguation rather than reimplementing string splits.

---

## Key Gallery — similar item test room

A dedicated room holds overlapping names for manual and automated testing.

### Full Ashmoore world (`world_content/world.yaml`)

| Room | How to reach |
|------|----------------|
| `key_gallery` | `north` from `blacksmith_forge` |

### Pytest fixture

```python
from tests.fixtures.disambig_fixtures import seed_disambig_gallery, DISAMBIG_ROOM_ID

seed_disambig_gallery(session, link=None)
player.current_room_id = DISAMBIG_ROOM_ID
```

Tests:

```bash
python -m pytest tests/unit/test_inventory_disambiguation.py -q
python -m pytest tests/game/ -q
```

### Try in-game

Import `world_content/world.yaml` into your DB first (`python scripts/import_world.py --fresh --db game.db`).

```
go north       # blacksmith_forge → key_gallery
look
take key       # numbered disambiguation
take iron      # three-way disambiguation
take steel key # unique take
take all       # takes every takeable item in the room
```

Diagnostics:

```bash
python tools/parser_diag.py "take rusty iron"
```

---

## Example: adding a `tell` command (directed speech)

```python
# commands/social.py
from lorecraft.engine.game.command_patterns import speech_roles

@registry.register("tell")
def tell_command(noun: str | None, ctx: object) -> None:
    game_ctx = cast(GameContext, ctx)
    # Legacy: noun holds message when undirected parse; migrate to ParsedCommand.
    if noun is None:
        game_ctx.say("Tell whom what?")
        return
    # Full parse integration (recommended):
    # roles = speech_roles(parsed)
    # if roles.recipient is None: room error
    # SpeechService.tell(roles.recipient, roles.message, game_ctx)
```

Add parser tests:

```python
@pytest.mark.parametrize("raw,message,recipient", [
    ('tell Gabriel "hello"', "hello", "Gabriel"),  # when tell split is implemented
])
```

---

## Testing matrix for new verbs

| Test type | File | Assert |
|-----------|------|--------|
| Role extraction | `tests/game/test_parser_patterns.py` | `roles` dict per pattern |
| Pattern helpers | `tests/unit/test_command_patterns.py` | typed extractors |
| Item ambiguity | `tests/unit/test_inventory_disambiguation.py` | prompts + unique takes |
| Engine integration | `tests/unit/test_inventory_disambiguation.py` | `CommandEngine` → disambig |
| Regression | `tests/game/test_parser_comprehensive.py` | compounds, edges |

---

## Migration roadmap

1. **Now:** Handlers use `noun`; engine passes rich audit/rule payloads with `roles`.
2. **Next:** Change `CommandHandler` to `(ParsedCommand, GameContext)`.
3. **Then:** Split services (`SpeechService`, `GestureService`, `TransferService`) that
   only accept typed role structs.

Until step 2, use `command_patterns` helpers inside services and accept `noun` as a
compatibility entry point for single-slot verbs.
