# Death & Resurrection — Design

> **Status:** Implementation-ready design (2026-07-03; revised same day for Tier 1 alignment).
> Resolves the long-standing **death-penalty open question**
> (roadmap Sprint 31.2, [`wishlist.md`](wishlist.md) decisions table). Referenced by the combat
> sprints ([`combat_system.md`](combat_system.md), [Sprints 31–33](roadmap.md#sprint-31--combat-core-services-supporting-system)) and PvP ([Sprint 34](roadmap.md#sprint-34--pvp-consent)).
>
> **Tier 1 dependencies ([`engine_core.md`](engine_core.md)):** the death trigger is
> `METER_DEPLETED` with `key == "hp"` (**meters**, §3.3 — there is no `current_hp` column);
> the corpse is a **container instance** holding **stacks** (§3.1–§3.2); coin/loot penalties
> are **one `execute_exchange`** (§3.7); the weakened debuff is an **`ActiveEffect`** (§3.4).
> Event names come from the existing `GameEvent` enum: **`PLAYER_DIED` / `PLAYER_RESPAWNED`**
> (the earlier draft's `PLAYER_RESURRECTED` does not exist — engine_core §4.h).
>
> **Design intent (from the product owner, 2026-07-03):** death is **not** permanent. You are
> **resurrected**, but you **lose some money and some loot**. Meaningful sting, not a
> progress-wipe — consistent with the pillars (combat is a *supporting* system, not a punishing
> grind) and with the "soft respawn" lean that was already on the roadmap.

---

## 1. Where we build from (existing primitives)

Much of the respawn scaffolding already exists:

- **`Player.respawn_room_id`** — where you come back. Already modeled.
- **`Player.ghost_state: bool`** — a between-death-and-resurrection flag. Already modeled.
- **`Player.active_combat_session_id`** — cleared on death.
- **hp meter** (engine_core §3.3) — the death module's entrypoint is a `METER_DEPLETED`
  handler filtered to `key == "hp"`, `entity_type == "player"`. Respawn hp is
  `MeterService.set_current(hp_meter, maximum × respawn_hp_fraction)`.
- **Ledger holders** ([`trade_economy.md`](archive/trade_economy.md), engine_core §3.7) — carried
  money is `CoinBalance("player", id)`; banked money is a different holder the death code
  never touches. That's the whole carried-vs-banked mechanic: *dodgeable by planning*.
- **Container instances** ([`inventory_equipment.md`](archive/inventory_equipment.md) §7) — a **corpse
  is a container** holding dropped stacks; reuses the container model, no new mechanism.
- **`SchedulerService`** — corpse decay timer (`job_type="corpse_decay"`).
- **Rollback lifecycle** ([Sprint 14](roadmap.md#sprint-14--unify-command-lifecycle-)) — death is applied as one auditable transaction.

---

## 2. What happens on death

Triggered by `METER_DEPLETED(key="hp")` — from combat, hazards, or later afflictions; the
death module doesn't care which:

1. **Emit `PLAYER_DIED`** (audited, severity WARNING) with cause, killer (if any), room.
2. **Spawn the corpse** (§4): `ItemLocationService.spawn(corpse_item_id, Location("room",
   death_room_id))` — the item's `capacity` makes the container component apply, so it gets
   an instance.
3. **Apply penalties** (§3) — coin loss + loot drop into the corpse, as **one
   `execute_exchange`** (all legs validate, then all apply — no partial penalty).
4. **Resurrect** — hp meter to `maximum × respawn_hp_fraction`, move the player to
   `respawn_room_id`, clear `active_combat_session_id`, apply the **weakened** `ActiveEffect`
   (§5).
5. **Emit `PLAYER_RESPAWNED`** (audited; existing enum member) and narrate ("You wake at the
   temple, dazed and lighter of purse.").

`ghost_state` optionally covers a brief window between steps 1 and 4 (e.g. a walk-to-your-corpse
ghost mode); simplest v1 resurrects immediately and skips the ghost walk.

---

## 3. The penalty: lose *some* money and *some* loot

Tunable, forgiving defaults; all values world-configurable:

**Money**
- Lose a percentage of **carried coins** (`CoinBalance("player", id)`, default ~20%), not a
  flat amount — scales with what you're risking.
- **Banked money is never lost** — structurally: the penalty exchange only names the
  `("player", id)` holder; `("bank_account", …)` is untouchable by construction
  ([`trade_economy.md`](archive/trade_economy.md) §9). Carry cash on a safe road; bank it before a
  dungeon.
- Lost coins are **dropped into the corpse** (`CoinBalance("container", corpse_instance_id)`,
  retrievable §4), not deleted — so a fast recovery loses little, a failed one loses it all.

**Loot**
- A subset of the player's stacks moves into the corpse. Default policy (configurable):
  - **Equipped items are kept** — mechanically: only `slot is None` (unequipped) stacks are
    candidates. Avoids the death-spiral of losing your only weapon/light.
  - **`bound` items are kept** (never lost — protects quest integrity, per
    [`inventory_equipment.md`](archive/inventory_equipment.md); the `Item.bound` field is Sprint 16).
  - A fraction of the remaining candidates drops (default: all, or a percentage — world-tunable
    via `loot_policy`/`loot_drop_fraction`; the fraction *selection* uses the seeded `rng`).

**Mechanics:** penalty = **one `execute_exchange`** with a coin leg (player → corpse) and one
stack leg per dropped stack. All legs validate first, then all apply — a crash mid-death can
never take your coins without spawning the corpse (engine_core §3.7).

Net effect: you always keep your identity (gear, quests, banked wealth) and always have a reason
to hustle back to your corpse.

---

## 4. The corpse (retrieval loop)

- A corpse is an ordinary container: an item stack in the death room whose instance holds the
  dropped stacks (`Location("container", corpse_instance_id)`) and coin balance. **The corpse
  item definition comes from world config** (`death.corpse_item_id`, §6) — the engine defines
  no items; the dev world ships a `corpse` item (with `capacity`, `takeable: false`).
- Retrieval: return, `take from corpse` / `loot corpse` — ordinary container `move()` calls
  plus a coin exchange corpse→player. This *is* the risk — the road back may be dangerous,
  and in PvP the killer may have looted it first (§7).
- **Decay:** a scheduled `corpse_decay` job (default ~30 real minutes / a world-day) either
  removes the corpse (contents lost) or sweeps contents to a **lost-and-found** at the respawn
  point for a fee (kinder option; world-configurable). Prevents orphaned corpses accumulating.
- Multiple deaths → multiple corpses; each independent.

---

## 5. Weakened debuff (soft anti-spam)

A short post-resurrection penalty implemented as a Tier 1 **`ActiveEffect`** (engine_core
§3.4): the death module registers `EffectDef("weakened", modifiers=…)` whose modifiers
(e.g. `stat.* × 0.8 mult`, `combat.speed` penalty) flow through the resolver automatically;
`EffectService.apply(..., duration_ticks=weakened_duration_ticks)` and the scheduler sweep
expires it. Discourages zerg-rushing the same fight, gives death felt weight without lasting
harm; fades on its own — no corpse-run required to clear it.

---

## 6. Configuration (world-tunable)

```yaml
death:
  corpse_item_id: corpse           # an Item the world defines (capacity set, takeable: false)
  respawn_hp_fraction: 0.25
  coin_loss_fraction: 0.20        # of CARRIED coins; banked always safe
  loot_policy: drop_unequipped     # keep_all | drop_unequipped | drop_fraction
  loot_drop_fraction: 1.0          # used when loot_policy = drop_fraction
  keep_equipped: true
  keep_bound: true
  corpse_decay_ticks: 1440
  corpse_decay_mode: lost_and_found   # vanish | lost_and_found
  lost_and_found_fee_fraction: 0.10
  weakened_duration_ticks: 180
```

Worlds can dial this from near-costless (teaching worlds) to harsh (hardcore servers) without
code changes. A per-world `pvp_death` override (§7) allows different rules for player kills.

---

## 7. PvP interaction (Sprint 34)

When the killer is another player (`pvp_consent` duels):

- Same soft model by default: victim resurrects, drops a corpse.
- **Open design lever:** does the killer get the victim's dropped coins/loot (transfer), or does
  it just drop into the corpse for anyone to grab (including the victim if they're quick)?
  - Lean: **drops into the corpse**, killer may loot it — creates real stakes without the engine
    auto-awarding spoils, and keeps PvE/PvP death on one mechanism.
- Consent-gated PvP means players opt into these stakes; non-consenting players can't be
  corpse-camped.

---

## 8. Robbers (NPC threat) — see wishlist

Robbers ([`wishlist.md`](wishlist.md)) reuse this exact carried-vs-banked model **without
killing you**: a successful robbery skims carried `coins` (and maybe a carried item), banked
money is safe. Same lesson as death ("don't carry what you can't afford to lose"), lower
stakes, and a strong incentive to use banks and safe transit. Design lands in a later sprint;
noted here because it shares the money/loot-at-risk core.

---

## 9. Events

- `PLAYER_DIED` (WARNING) — cause, killer, room, penalties applied. *(existing member)*
- `PLAYER_RESPAWNED` (INFO) — respawn room, restored hp. *(existing member)*
- `CORPSE_LOOTED` — who reclaimed what (audit/quest hooks). *(new additive member)*
- `CORPSE_DECAYED` — vanish or swept to lost-and-found. *(new additive member)*

All on the existing audit trail; the audit-regression harness can diff a scripted death.

---

## 10. Testing

- **Unit:** penalty math (coin fraction of carried only; banked untouched; equipped/bound kept);
  corpse contents = exactly what dropped; respawn HP/room; weakened applied + expires.
- **Integration:** die → resurrect at `respawn_room_id` → walk back → `loot corpse` restores
  goods; corpse decay to lost-and-found; save/load and disconnect during ghost/corpse state.
- **Simulation:** PvP death drops a corpse the killer can loot; two players racing to a corpse;
  audit-regression diff of a scripted death sequence.

---

## 11. Non-goals / open questions

- **Permadeath** — explicitly rejected per design intent (a hardcore per-world toggle could set
  extreme penalties, but true character deletion is out of scope).
- **XP / level loss** on death — not in v1 (progression is exploration/knowledge-driven, not a
  grind to protect); revisit only if leveling lands.
- **Open:** immediate resurrect vs. a ghost-walk-to-corpse window (`ghost_state`)? Lean:
  immediate in v1, ghost walk as a later option.
- **Open:** corpse decay → vanish vs. lost-and-found default? Lean: lost-and-found (kinder,
  fewer "lost my everything" moments).

---

*See [`roadmap.md`](roadmap.md) [Sprints 31](roadmap.md#sprint-31--combat-core-services-supporting-system) (combat death/respawn) & 34 (PvP),
[`combat_system.md`](combat_system.md), [`trade_economy.md`](archive/trade_economy.md) (banks vs.
carried money), [`inventory_equipment.md`](archive/inventory_equipment.md) (corpse = container), and
[`wishlist.md`](wishlist.md) (robbers).*
