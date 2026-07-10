# Scripting vocabulary reference

<!-- GENERATED FILE — do not edit by hand. Regenerate with `make scripting-docs`. -->

The declarative vocabulary a builder writes in `when:` / `do:` blocks and NPC
`behavior:` — generated from the self-describing descriptors registered into the
engine (see [`scripting_engine_design.md`](scripting_engine_design.md) §8). Each entry
shows its subject role, capability signature, and parameters.

_18 entries._

## Conditions (`when:`)

### combat

#### `in_combat`

The actor is currently in a combat session.

- **Subject:** `actor`
- **Capability:** `combat/session` · `has`
- **Params:** _none_

#### `not_in_combat`

The actor is not currently in a combat session.

- **Subject:** `actor`
- **Capability:** `combat/session` · `lacks`
- **Params:** _none_

### environment

#### `requires_light`

The room is lit, or the actor carries a lit light source.

- **Subject:** `self`
- **Capability:** `light/level` · `at_least`
- **Params:** _none_

### flags

#### `flag_not_set`

The named flag is not set on the actor.

- **Subject:** `actor`
- **Capability:** `flags/<flag>` · `lacks`
- **Params:**
  - `flag` (`flag`, required) — Flag name (colon-string param).

#### `flag_set`

The named flag is set on the actor.

- **Subject:** `actor`
- **Capability:** `flags/<flag>` · `has`
- **Params:**
  - `flag` (`flag`, required) — Flag name (colon-string param).

#### `forbidden_flags`

None of the named flags are set on the actor.

- **Subject:** `actor`
- **Capability:** `flags/<flag>` · `lacks`
- **Params:**
  - `flags` (`list[str]`, required) — Flag names that must all be clear.

#### `required_flags`

All named flags are set on the actor.

- **Subject:** `actor`
- **Capability:** `flags/<flag>` · `has`
- **Params:**
  - `flags` (`list[str]`, required) — Flag names that must all be set.

### inventory

#### `item_in_inventory`

The actor carries at least one of the named item.

- **Subject:** `actor`
- **Capability:** `inventory/item` · `has`
- **Params:**
  - `item_id` (`item_id`, required) — Item id (colon-string param).

### presence

#### `npc_present`

The named NPC is in the current room.

- **Subject:** `self`
- **Capability:** `presence/npc` · `has`
- **Params:**
  - `npc_id` (`npc_id`, required) — NPC id (colon-string param).

#### `object_present`

The named item is in the current room or held by the actor.

- **Subject:** `self`
- **Capability:** `presence/item` · `has`
- **Params:**
  - `item_id` (`item_id`, required) — Item id (colon-string param).

## Effects (`do:`)

### dialogue

#### `end_dialogue`

Close the actor's current dialogue session.

- **Subject:** `actor`
- **Capability:** `dialogue/session` · `clear`
- **Params:** _none_

### effects

#### `apply_effect`

Apply a timed ActiveEffect to a target (actor | room | stored_item).

- **Subject:** `target`
- **Capability:** `effects/active` · `apply`
- **Params:**
  - `effect` (`effect_key`, required) — Registered effect definition key.
  - `target` (`subject`, optional) — actor (default) | room | stored_item.
  - `ticks` (`int`, optional) — Duration; omitted = permanent.

### flags

#### `clear_flags`

Remove one or more boolean flags from the actor.

- **Subject:** `actor`
- **Capability:** `flags/<flag>` · `clear`
- **Params:**
  - `flags` (`list[str]`, required) — Flag names to clear.

#### `set_flags`

Set one or more boolean flags on the actor.

- **Subject:** `actor`
- **Capability:** `flags/<flag>` · `set`
- **Params:**
  - `flags` (`list[str]`, required) — Flag names to set true.

### inventory

#### `give_item`

Give the actor one of an item (no-op if already carried).

- **Subject:** `actor`
- **Capability:** `inventory/item` · `give`
- **Params:**
  - `item_id` (`item_id`, required) — Item to grant.

### narration

#### `narrate_room`

Broadcast a line to a room's occupants. Scalar form `narrate_room: "text"` targets the actor's room; map form `{text, room?}` can target another room.

- **Subject:** `world`
- **Capability:** `narration/room` · `broadcast`
- **Params:**
  - `text` (`str`, required) — The line to narrate (or a {text, room?} map).

#### `narrate_zone`

Broadcast a line to every room in a zone (defaults to the actor's area).

- **Subject:** `world`
- **Capability:** `narration/zone` · `broadcast`
- **Params:**
  - `text` (`str`, required) — The line (or a {text, area?} map).

### quests

#### `start_quest`

Start a quest for the actor at its first stage (no-op if already started).

- **Subject:** `actor`
- **Capability:** `quests/quest` · `start`
- **Params:**
  - `quest_id` (`quest_id`, required) — Quest to start.

## ⚠ Capability overlaps

These names share a capability signature — likely duplicates to reconcile to one
canonical name (`docs/scripting_engine_design.md` §8.3):

- `flag_not_set`, `forbidden_flags` — all `actor:flags:<flag>:lacks`
- `flag_set`, `required_flags` — all `actor:flags:<flag>:has`
