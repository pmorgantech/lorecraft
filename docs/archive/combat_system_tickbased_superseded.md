# Combat System — Design (SUPERSEDED)

> **Status:** SUPERSEDED (2026-07-14 by [`combat_design.md`](combat_design.md), which adopts
> **Scheduled Intent Combat** instead of tick-based). This document described a **tick-based**
> model (global `combat_tick` on world-clock rhythm). The new design replaces the core timing
> model, encounter state structure, and NPC AI approach. Kept for historical reference only.
>
> For current combat design, see [`combat_design.md`](combat_design.md). Roadmap Sprints 85–88.
>
> **Tier 1 dependencies ([`engine_core.md`](engine_core.md)):** hp **meter** (§3.3) — there
> are no `current_hp` columns by the time combat lands; **timed effects** (§3.4) for
> buffs/debuffs; **modifier resolver** (§3.5) for derived attack/defense/armor; **seedable
> `ctx.rng` + `skill_check`** (§3.6) — module-level `random` is lint-banned; **item
> stacks/slots** (§3.2) — the wielded weapon is the `main_hand` slot stack, there is no
> `equipped_weapon_id`; **exchange** (§3.7) for death coin-loss
> ([`death_resurrection.md`](death_resurrection.md)).
>
> Combat ships as `features/combat/` per [`feature-registration.md`](feature-registration.md) —
> its first full consumer. Nothing here edits core engine files.

---

## 1. Combat model: tick-based with speed

Combat is **tick-based on the world clock**, via the existing `SchedulerService`. Multiple
players can fight the same NPC concurrently on independent rhythms.

Each combatant has:

- **speed** — game ticks between actions (lower = faster), derived at session start:
  `player_speed = resolve_for(session, player, "combat.speed", base=10 - (agility - 10) // 2)`;
  NPC speed from YAML (default 10).
- **next_action_epoch** — the game epoch at which they act next.

On each due tick, resolve actions for every combatant whose `next_action_epoch <= now`.

### Scheduling (decided)

One mechanism: `SchedulerService.schedule("combat_tick", at_game_epoch, payload={"session_id": ...})`.
`CombatService.register(bus)` listens for `SCHEDULED_JOB_DUE` and filters
`payload["job_type"] == "combat_tick"` — the same convention every scheduled subsystem uses.
The legacy `GameEvent.COMBAT_TICK_DUE` member is not used for dispatch (it predates the
generic scheduler; leave it in the enum, don't wire it). Handlers receive a
`SchedulerEventContext(game_engine, bus, rng)` — they open their own session, commit it
themselves, and use `event_ctx.rng` for all rolls (engine_core §3.0/§3.6).

---

## 2. Stat model

Six core attributes on `PlayerStats`, serving both combat and world-skill roles:

| Stat | Combat role | World role |
|---|---|---|
| **Strength** | Melee damage bonus | Forced entry, heavy object interaction |
| **Agility** | Hit chance, speed | Lockpicking, evasion, stealth |
| **Vitality** | hp meter maximum, regen | Endurance, poison resistance |
| **Intellect** | Magic power (future) | Puzzle solving, lore checks |
| **Presence** | NPC persuasion, threat | Dialogue branch unlocks, intimidation |
| **Fortitude** | Defense threshold | Disease resistance, willpower checks |

**Runtime hp is the `"hp"` meter** (engine_core §3.3): maximum =
`resolve_for(entity, "meter.hp.max", base=PlayerStats.max_hp | NPC.max_hp)`; damage/healing =
`MeterService.adjust()`. **Never store derived stats** — attack/defense/armor are resolved
per use from base stats + equipment + traits + active effects:

| Resolver key | Base | Typical contributors |
|---|---|---|
| `stat.strength` (etc.) | the `PlayerStats` column | equipment `stat_bonus`, traits, `weakened` effect |
| `combat.armor` | 0 | worn armor `effects: [{type: armor, amount: n}]` |
| `combat.speed` | agility-derived | haste/slow effects |

The `armor` effect descriptor is registered by the combat feature (same descriptor registry
as [`inventory_equipment.md`](archive/inventory_equipment.md) §3). Weapon damage is **data on the
weapon**, also a descriptor — `effects: [{type: weapon_damage, min: 2, max: 7}]` — no new
`Item` columns.

---

## 3. Session lifecycle

`CombatSession` already exists (`models/combat.py`: `id, room_id, started_at, status,
combatants: list[JsonObject]`). Combatant entries hold **tick bookkeeping only** —
`{"entity_type", "entity_id", "speed", "next_action_epoch", "damage_dealt": {...}}`.
**hp is never copied into the session** (it lives in the meter; copying it was the old
design's dupe-state bug).

### Start (`attack` command, Sprint 32)

1. Resolve target NPC/player in room (item-matcher conventions).
2. `ctx.rules.check("attack", ctx, {"target_id": ...})` — **fail-closed** gate: PvP consent,
   NPC protection, room no-combat flags all veto here (engine_core §2).
3. Create session; set `Player.active_combat_session_id`; schedule the first `combat_tick`;
   emit `COMBAT_STARTED` (exists in the enum); narrate via `ctx.say`/`ctx.tell_room`.

### Tick resolution (`CombatService.resolve_tick`, Sprint 31)

For each ready combatant, in **deterministic order** (by `entity_id` — audit-regression
depends on stable iteration, engine_core §3.0):

- **Player action:** dequeued queued action or default `attack`.
- **NPC action:** `npc/combat_ai.py` decides from YAML `behavior` (§5).
- Resolve (§4), apply damage via `MeterService.adjust`, record `damage_dealt`, advance
  `next_action_epoch += speed`, broadcast a `combat_update` WS message to the room
  (via `ConnectionManager.broadcast_to_room`).

End conditions: all NPCs dead/fled, or all players dead/fled → §6. Otherwise schedule the
next `combat_tick`.

### Death mid-session

`MeterService.adjust` crossing hp to 0 emits `METER_DEPLETED` — the **death module**
([`death_resurrection.md`](death_resurrection.md)) owns what happens to a player; the combat
service only removes the dead combatant from the session. For NPCs the combat service emits
`NPC_DIED`, drops loot (§7), and schedules respawn from `NPC.respawn_seconds`.

---

## 4. Attack resolution (all rolls through `rng`)

```python
def resolve_attack(rng: GameRng, session: Session, attacker, defender, weapon: Item | None) -> AttackResult:
    # To-hit: the Tier 1 skill_check (engine_core §3.6) — same helper as lockpicking/barter.
    check = skill_check(
        rng,
        base=resolve_for(session, attacker, "stat.agility", base_agility) * TO_HIT_SCALE,
        difficulty=defense_threshold(session, defender),   # fortitude + armor derived
        key="combat.to_hit",
    )
    if not check.success:
        return AttackResult(hit=False)

    dmin, dmax = weapon_damage(weapon)          # weapon_damage descriptor; UNARMED_RANGE if None
    raw = rng.randint(dmin, dmax) + strength_bonus(session, attacker)
    dealt = max(0, round(raw - resolve_for(session, defender, "combat.armor", 0.0)))
    crit = check.margin >= CRIT_MARGIN          # margin-based crit, deterministic given the roll
    return AttackResult(hit=True, damage=dealt * (2 if crit else 1), crit=crit)
```

Constants (`TO_HIT_SCALE`, `CRIT_MARGIN`, `UNARMED_RANGE`) are feature config —
world-overridable, not engine constants. The wielded weapon is read from the `main_hand`
slot: `stacks_for_owner("player", id)` filtered to `slot == "main_hand"` (engine_core §3.2;
there is **no** `equipped_weapon_id`).

---

## 5. NPC combat AI (`npc/combat_ai.py`, Sprint 31.3)

Behavior modes come from `NPC.behavior` (YAML; the column exists):

| Behavior | Policy |
|---|---|
| `aggressive` | always attack |
| `defensive` | attack; flee below 30% hp |
| `cowardly` | flee below 50%; below 10% and cornered → `dialogue` (negotiate) |
| `territorial` | attack only while `session.room_id == npc.home_room_id`; else flee |
| `guard` | never flees; `call_reinforcements` (emits an event other guards react to) |

hp fractions read the NPC's hp meter. Fleeing moves the NPC to `home_room_id`, removes it
from the session, and emits `NPC_FLED` (exists in the enum). Thresholds are per-behavior
config, overridable per NPC in YAML. Decisions may use `rng` (e.g. flee direction) — never
module `random`.

**Avoidance-first (Sprint 32):** `flee`, `subdue`, `intimidate`, and dialogue-mid-combat are
commands/outcomes of equal rank with `attack`; non-lethal end states set session status
`"resolved_nonlethal"` and emit `COMBAT_ENDED` with an `outcome` payload field.

---

## 6. Session end, kill credit & loot

- Credit is **participation-based, not last-hit**: each combatant entry accumulated
  `damage_dealt` per target; credit fraction = damage share. XP award (if/when leveling
  matters — see [`wishlist.md`](wishlist.md), progression is exploration-led) and loot
  rights both use it.
- Loot: roll `NPC.loot_table` with `rng`, then `ItemLocationService.spawn()` into the room —
  or into a lootable corpse container if the world enables NPC corpses (same corpse mechanism
  as player death). Coin drops are `LedgerService.credit` to the corpse/room-holder — never a
  bare integer.
- Cleanup: clear every surviving player's `active_combat_session_id`; session status
  `"resolved"`; emit `COMBAT_ENDED`; the room gets a final `combat_update` + narration.

---

## 7. Combat-gated commands

Already wired (Sprint 10): `not_in_combat` / `in_combat` conditions exist in
`game/command_conditions.py` reading `Player.active_combat_session_id`. Commands like
`sleep`, `board`, `trade` declare `conditions=["not_in_combat"]`. Sprint 32 completes the
condition set (`has_combat_target`, `NPC_PRESENT`) via the same registry — availability
gates are conditions; integrity gates (consent) are rules (engine_core §2).

---

## 8. Events (all already in `game/events.py` — no new members needed)

`COMBAT_STARTED`, `COMBAT_ENDED`, `PLAYER_ATTACKED`, `NPC_ATTACKED`, `NPC_DIED`, `NPC_FLED`,
`PLAYER_DIED` / `PLAYER_RESPAWNED` (emitted by the death module, not combat). Audit payloads
include `session_id`, damage, and outcome — the audit-regression harness diffs a scripted
fight, which is why every roll goes through the seeded `rng` and iteration order is fixed.

---

## 9. Testing (Sprint 33)

- **Unit:** attack resolution across armor/crit/unarmed branches with a seeded `GameRng`
  (exact expected sequences); AI decision table per behavior × hp fraction; speed/scheduling
  math; kill-credit shares; deterministic combatant ordering.
- **Integration:** full fight through `POST /command` and `/ws` (attack → ticks → NPC death →
  loot on floor); flee path; non-lethal path; combat-gated command refusals.
- **Simulation:** two players fighting one NPC concurrently over real sockets (credit split,
  no lost updates on the shared hp meter); **audit-regression**: a seeded scripted fight run
  against two fresh servers diffs identical (the §3.6 determinism contract, end-to-end).

---

*See [`engine_core.md`](engine_core.md) (primitives), [`death_resurrection.md`](death_resurrection.md)
(death/respawn policy), [`inventory_equipment.md`](archive/inventory_equipment.md) (weapon/armor as
effect descriptors), [`feature-registration.md`](feature-registration.md) (module layout), and
[architecture.md §15](architecture.md#15-subsystem-combat-system) (original subsystem sketch,
superseded where it conflicts with this doc).*
