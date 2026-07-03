# Death & Resurrection — Design

> **Status:** Design (2026-07-03). Resolves the long-standing **death-penalty open question**
> (roadmap Sprint 31.1, [`wishlist.md`](wishlist.md) decisions table). Referenced by the combat
> sprints ([`combat_system.md`](combat_system.md), [Sprints 31–33](roadmap.md#sprint-31--combat-core-services-supporting-system)) and PvP ([Sprint 34](roadmap.md#sprint-34--pvp-consent)).
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
- **`PlayerStats.current_hp` / `max_hp`** — death trigger is `current_hp <= 0`.
- **`Player.coins` + `BankAccount`** ([`trade_economy.md`](trade_economy.md)) — the carried-vs-
  banked split is what makes a money penalty *dodgeable by planning* (bank before a fight).
- **`ItemInstance` containers** ([`inventory_equipment.md`](inventory_equipment.md)) — a **corpse
  is a container** holding dropped loot; reuses the container model, no new mechanism.
- **`SchedulerService`** — corpse decay timer.
- **Rollback lifecycle** ([Sprint 14](roadmap.md#sprint-14--unify-command-lifecycle-)) — death is applied as one auditable transaction.

---

## 2. What happens on death

Triggered when `current_hp <= 0` (from combat, hazards, or later afflictions):

1. **Emit `PLAYER_DIED`** (audited, severity WARNING) with cause, killer (if any), room.
2. **Apply penalties** (§3) — coin loss + loot drop, in one transaction.
3. **Spawn a corpse** (§4) in the death room holding the dropped loot.
4. **Resurrect** — set `current_hp` to a fraction of `max_hp` (e.g. 25%), move the player to
   `respawn_room_id`, clear `active_combat_session_id`, apply a short **weakened** debuff (§5).
5. **Emit `PLAYER_RESURRECTED`** (audited) and narrate ("You wake at the temple, dazed and
   lighter of purse.").

`ghost_state` optionally covers a brief window between steps 1 and 4 (e.g. a walk-to-your-corpse
ghost mode); simplest v1 resurrects immediately and skips the ghost walk.

---

## 3. The penalty: lose *some* money and *some* loot

Tunable, forgiving defaults; all values world-configurable:

**Money**
- Lose a percentage of **carried `coins`** (default ~20%), not a flat amount — scales with what
  you're risking.
- **Banked money is never lost.** This is the core lever: banking before danger is the
  player's agency over the penalty ([`trade_economy.md`](trade_economy.md) §9). Carry cash on a
  safe road; bank it before a dungeon.
- Lost coins are **dropped into the corpse** (retrievable, §4), not deleted — so a fast recovery
  loses little, a failed recovery loses it all.

**Loot**
- A subset of **carried inventory** drops into the corpse. Default policy (configurable):
  - **Equipped items are kept** (you resurrect wearing your gear) — avoids the death-spiral of
    losing your only weapon/light and being unable to recover.
  - **Bound / quest items are kept** (never lost — protects quest integrity, per
    [`inventory_equipment.md`](inventory_equipment.md)).
  - A fraction of the remaining carried, unequipped items drops (default: all of them, or a
    percentage — world-tunable via `death_loot_policy`).

Net effect: you always keep your identity (gear, quests, banked wealth) and always have a reason
to hustle back to your corpse.

---

## 4. The corpse (retrieval loop)

- A corpse is an `ItemInstance` container (`item_id: corpse`, `owner_type: room`) at the death
  room, holding the dropped coins + items.
- Retrieval: return, `take from corpse` / `loot corpse` to reclaim. This *is* the risk — the
  road back may be dangerous, and in PvP the killer may have looted it first (§7).
- **Decay:** a scheduled `corpse_decay` job (default ~30 real minutes / a world-day) either
  removes the corpse (contents lost) or sweeps contents to a **lost-and-found** at the respawn
  point for a fee (kinder option; world-configurable). Prevents orphaned corpses accumulating.
- Multiple deaths → multiple corpses; each independent.

---

## 5. Weakened debuff (soft anti-spam)

A short post-resurrection penalty (e.g. reduced stats / slower actions for a few minutes,
implemented as a temporary trait via the [Sprint 24](roadmap.md#sprint-24--traits--skills) trait registry) discourages zerg-rushing the
same fight and gives death a felt weight without lasting harm. Fades on its own; no corpse-run
required to clear it.

---

## 6. Configuration (world-tunable)

```yaml
death:
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

- `PLAYER_DIED` (WARNING) — cause, killer, room, penalties applied.
- `PLAYER_RESURRECTED` (INFO) — respawn room, restored HP.
- `CORPSE_LOOTED` — who reclaimed what (audit/quest hooks).
- `CORPSE_DECAYED` — vanish or swept to lost-and-found.

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
[`combat_system.md`](combat_system.md), [`trade_economy.md`](trade_economy.md) (banks vs.
carried money), [`inventory_equipment.md`](inventory_equipment.md) (corpse = container), and
[`wishlist.md`](wishlist.md) (robbers).*
