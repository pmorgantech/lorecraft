# Combat System Implementation Guide

## Overview

Combat is **tick-based**, leveraging the real-time world clock. Multiple players can fight the same NPC concurrently on independent rhythms. Combat is resolved each tick via damage rolls, healing, and AI decisions.

---

## Combat Model: Tick-Based with Speed

Each combatant has:
- **speed:** Number of game ticks between actions (e.g., 10 ticks = slower, 5 ticks = faster)
- **next_action_tick:** The game epoch at which they will act next

```
CombatSession
  ├── combatant: Player A (speed=10 ticks, next_action=tick 1000)
  ├── combatant: Player B (speed=15 ticks, next_action=tick 1500)
  └── combatant: NPC (speed=12 ticks, next_action=tick 1200)
```

On each `COMBAT_TICK_DUE` work event (emitted by the scheduler): resolve actions for any combatant whose `next_action_tick <= current_tick`.

---

## Stat Model

Six core attributes serving both combat and world-skill roles:

| Stat | Combat Role | World Role |
|---|---|---|
| **Strength** | Melee damage bonus | Forced entry, heavy object interaction |
| **Agility** | Hit chance, speed | Lockpicking, evasion, stealth |
| **Vitality** | Max HP, HP regen | Endurance, poison resistance |
| **Intellect** | Magic power (future) | Puzzle solving, lore checks |
| **Presence** | NPC persuasion, threat | Dialogue branch unlocks, intimidation |
| **Fortitude** | Armor effectiveness | Disease resistance, willpower checks |

```python
class PlayerStats(SQLModel, table=True):
    player_id: str = Field(primary_key=True, foreign_key="player.id")
    strength: int = 10
    agility: int = 10
    vitality: int = 10
    intellect: int = 10
    presence: int = 10
    fortitude: int = 10
    max_hp: int = 100
    current_hp: int = 100
    level: int = 1
    xp: int = 0
    xp_to_next: int = 100
    skills: dict = Field(default_factory=dict, sa_column=Column(JSON))  # skill_name → 0-100
```

**Important:** Derived stats (armor, resistances) are computed at runtime from base stats + equipment + buffs. Never store derived stats.

---

## Combat Session Lifecycle

### 1. Session Creation

A player attacks an NPC, triggering combat:

```python
@register("attack", scope=CommandScope.WORLD, conditions=[CommandCondition.NOT_IN_COMBAT])
async def do_attack(target: str, ctx: GameContext):
    """
    Player attacks an NPC or consensual player.
    """
    # 1. Find target NPC or player
    npc = ctx.npc_repo.find_in_room(target, ctx.room.id)

    if not npc:
        ctx.say("You don't see that here.")
        return

    # 2. Check rule engine (PvP consent, NPC behavior, etc.)
    rule_result = ctx.rules.check("attack", ctx, {"target_id": npc.id})
    if not rule_result.allowed:
        ctx.say(rule_result.reason or "You can't do that.")
        return

    # 3. Create combat session
    session = await ctx.combat_service.create_session(
        player_id=ctx.player.id,
        npc_id=npc.id,
        room_id=ctx.room.id,
        ctx=ctx
    )

    ctx.player.active_combat_session_id = session.id
    ctx.say(f"Combat with {npc.name} begins!")
    ctx.tell_room(f"{ctx.player.username} attacks {npc.name}!")
    ctx.emit(GameEvent.COMBAT_STARTED, {
        "session_id": session.id,
        "player_id": ctx.player.id,
        "npc_id": npc.id,
        "room_id": ctx.room.id,
    })


async def create_session(self, player_id: str, npc_id: str, room_id: str, ctx: GameContext) -> CombatSession:
    """
    Create a new combat session.
    """
    player = ctx.player_repo.get(player_id)
    npc = ctx.npc_repo.get(npc_id)

    # Compute initial speed from stats
    player_speed = 10 - (ctx.player_stats.agility - 10) // 2  # Lower speed = faster
    npc_speed = 10  # NPCs have fixed speed

    session = CombatSession(
        id=str(uuid.uuid4()),
        room_id=room_id,
        started_at=ctx.clock.game_epoch,
        status="active",
        combatants=[
            {
                "entity_id": player_id,
                "entity_type": "player",
                "next_action_tick": ctx.clock.game_epoch + player_speed,
                "speed": player_speed,
                "hp": player.stats.current_hp,
                "max_hp": player.stats.max_hp,
            },
            {
                "entity_id": npc_id,
                "entity_type": "npc",
                "next_action_tick": ctx.clock.game_epoch + npc_speed,
                "speed": npc_speed,
                "hp": npc.current_hp,
                "max_hp": npc.max_hp,
            }
        ]
    )

    ctx.audit.record(ctx, GameEvent.COMBAT_STARTED, target_id=npc_id)
    ctx.session.add(session)
    ctx.session.commit()

    # Schedule the first combat tick
    scheduler.schedule(
        "combat_tick",
        at_game_epoch=ctx.clock.game_epoch + 1,
        payload={"session_id": session.id}
    )

    return session
```

### 2. Combat Tick Resolution

On each `COMBAT_TICK_DUE` event:

```python
async def resolve_combat_tick(session_id: str, ctx: GameContext):
    """
    Resolve actions for all combatants whose next_action_tick has arrived.
    """
    session = ctx.session.query(CombatSession).filter(
        CombatSession.id == session_id
    ).first()

    if not session or session.status != "active":
        return

    current_tick = ctx.clock.game_epoch

    # Find combatants ready to act
    ready = [c for c in session.combatants if c["next_action_tick"] <= current_tick]

    for combatant in ready:
        entity_id = combatant["entity_id"]
        entity_type = combatant["entity_type"]

        if entity_type == "player":
            # Player's next action (from queue or AI)
            player = ctx.player_repo.get(entity_id)
            action = dequeue_player_action(entity_id)  # Or default to "attack"

            if action:
                target = find_action_target(session, entity_id)
                await resolve_player_action(session, combatant, action, target, ctx)

        elif entity_type == "npc":
            # NPC decision logic
            npc = ctx.npc_repo.get(entity_id)
            decision = npc_combat_ai.decide(npc, session, ctx)
            await resolve_npc_action(session, combatant, decision, ctx)

        # Reschedule this combatant's next action
        combatant["next_action_tick"] = current_tick + combatant["speed"]

    # Check for session end (all NPCs dead or all players fled)
    if should_end_combat(session):
        await end_combat_session(session, ctx)
    else:
        # Schedule next tick
        scheduler.schedule(
            "combat_tick",
            at_game_epoch=current_tick + 1,
            payload={"session_id": session.id}
        )
```

### 3. Damage Resolution

```python
def resolve_attack(attacker: dict, defender: dict, weapon: Item, ctx: GameContext) -> dict:
    """
    Roll to hit, compute damage, apply armor.
    Returns: {"hit": bool, "damage": int, "message": str}
    """
    # Hit roll: d20 + agility modifier
    d20 = random.randint(1, 20)
    attacker_agility = ctx.player_stats.agility if attacker["entity_type"] == "player" else 10
    hit_roll = d20 + (attacker_agility - 10) // 2

    # Defender's defense threshold (derived from armor + fortitude)
    defender_fortitude = 10  # Simplified; would be loaded from DB
    defense_threshold = 10 + (defender_fortitude - 10) // 2

    if hit_roll < defense_threshold:
        return {"hit": False, "damage": 0, "message": f"Miss!"}

    # Damage roll
    weapon_min = weapon.damage_min if hasattr(weapon, 'damage_min') else 5
    weapon_max = weapon.damage_max if hasattr(weapon, 'damage_max') else 12
    raw_damage = weapon_min + random.randint(0, weapon_max - weapon_min)

    # Strength bonus
    attacker_strength = ctx.player_stats.strength if attacker["entity_type"] == "player" else 10
    raw_damage += (attacker_strength - 10) // 2

    # Armor reduction (simplified)
    armor_reduction = 2  # Would be loaded from defender's equipment
    final_damage = max(0, raw_damage - armor_reduction)

    # Critical hit (natural 20)
    if d20 == 20:
        final_damage *= 2
        return {"hit": True, "damage": final_damage, "message": f"Critical hit! {final_damage} damage!"}

    return {"hit": True, "damage": final_damage, "message": f"Hit! {final_damage} damage."}


async def resolve_player_action(session: CombatSession, attacker: dict, action: str, target: dict, ctx: GameContext):
    """
    Resolve a player's combat action.
    """
    if action == "attack":
        player = ctx.player_repo.get(attacker["entity_id"])
        # Get player's equipped weapon
        weapon = ctx.item_repo.get(player.equipped_weapon_id) if player.equipped_weapon_id else Item(
            id="fist",
            name="Fists",
            damage_min=1,
            damage_max=3
        )

        result = resolve_attack(attacker, target, weapon, ctx)

        if result["hit"]:
            target["hp"] -= result["damage"]
            ctx.audit.record(ctx, GameEvent.PLAYER_ATTACKED, target_id=target["entity_id"])

        # Broadcast to room
        player_name = ctx.player_repo.get(attacker["entity_id"]).username
        target_name = ctx.npc_repo.get(target["entity_id"]).name if target["entity_type"] == "npc" else ctx.player_repo.get(target["entity_id"]).username

        await ctx.manager.broadcast_to_room(session.room_id, {
            "type": "combat_update",
            "session_id": session.id,
            "message": f"{player_name} {result['message']} {target_name}",
            "log": [result]
        })
```

### 4. Session End

When combat resolves (all NPCs dead, all players fled, etc.):

```python
async def end_combat_session(session: CombatSession, ctx: GameContext):
    """
    End a combat session and clean up.
    """
    session.status = "resolved"

    # Award XP to surviving players
    for combatant in session.combatants:
        if combatant["entity_type"] == "player" and combatant["hp"] > 0:
            player = ctx.player_repo.get(combatant["entity_id"])
            xp_earned = 100  # Simplified
            player.stats.xp += xp_earned
            player.active_combat_session_id = None
            ctx.audit.record(ctx, GameEvent.COMBAT_ENDED, target_id=combatant["entity_id"], summary=f"Awarded {xp_earned} XP")

    # Clean up dead NPCs
    for combatant in session.combatants:
        if combatant["entity_type"] == "npc" and combatant["hp"] <= 0:
            npc = ctx.npc_repo.get(combatant["entity_id"])
            npc.current_hp = 0
            await drop_loot(npc, session.room_id, ctx)
            ctx.audit.record(ctx, GameEvent.NPC_DIED, target_id=npc.id)

            # Respawn if configured
            if npc.respawn_seconds:
                scheduler.schedule(
                    "npc_respawn",
                    at_game_epoch=ctx.clock.game_epoch + npc.respawn_seconds,
                    payload={"npc_id": npc.id}
                )

    ctx.session.commit()

    # Emit event
    ctx.emit(GameEvent.COMBAT_ENDED, {"session_id": session.id})

    # Broadcast to room
    await ctx.manager.broadcast_to_room(session.room_id, {
        "type": "system",
        "text": "Combat has ended."
    })
```

---

## NPC Combat AI

NPCs have distinct behaviors:

```python
class NPCCombatBehavior(str, Enum):
    AGGRESSIVE    # Attacks on sight or when threatened
    DEFENSIVE     # Fights back when attacked, may flee if losing
    COWARDLY      # Flees early (< 50% HP); negotiates if cornered
    TERRITORIAL   # Attacks only in their zone, otherwise ignores
    GUARD         # Calls for reinforcements instead of fleeing


async def npc_combat_ai_decide(npc: NPC, session: CombatSession, ctx: GameContext) -> str:
    """
    NPC decision logic fires each time their combat tick resolves.
    """
    npc_combatant = next(c for c in session.combatants if c["entity_id"] == npc.id)
    hp_percent = npc_combatant["hp"] / npc_combatant["max_hp"]

    if npc.behavior == "aggressive":
        return "attack"

    elif npc.behavior == "defensive":
        if hp_percent < 0.3:
            return "flee"
        return "attack"

    elif npc.behavior == "cowardly":
        if hp_percent < 0.5:
            if hp_percent < 0.1:
                # Cornered — negotiate
                return "dialogue"
            return "flee"
        return "attack"

    elif npc.behavior == "territorial":
        # Check if in home zone
        zone = npc.home_zone or None
        if zone and session.room_id != npc.home_room_id:
            return "flee"
        return "attack"

    elif npc.behavior == "guard":
        return "call_reinforcements"

    return "idle"
```

### Fleeing

When an NPC flees, it transitions back to its schedule:

```python
async def resolve_npc_flee(npc: NPC, session: CombatSession, ctx: GameContext):
    """
    NPC flees combat. Transition back to schedule or FLED waypoint.
    """
    npc.current_room_id = npc.home_room_id  # Or a FLED waypoint

    # Remove from combat session
    session.combatants = [c for c in session.combatants if c["entity_id"] != npc.id]

    if not session.combatants or all(c["entity_type"] == "player" for c in session.combatants):
        # All NPCs fled or dead
        await end_combat_session(session, ctx)

    ctx.emit(GameEvent.NPC_FLED, {"npc_id": npc.id, "session_id": session.id})
```

---

## Kill Credit & Loot Ownership

Multiple players can fight the same NPC. Credit is **participation-based**, not last-hit:

```python
def compute_kill_credit(session: CombatSession) -> dict[str, float]:
    """
    Compute XP/loot share based on damage dealt.
    Returns: {player_id: credit_fraction}
    """
    damage_by_player = {}
    total_damage = 0

    # Simplified: track damage in combat log
    for log_entry in session.combat_log:
        if log_entry["attacker_type"] == "player":
            player_id = log_entry["attacker_id"]
            damage = log_entry["damage"]
            damage_by_player[player_id] = damage_by_player.get(player_id, 0) + damage
            total_damage += damage

    if total_damage == 0:
        return {}

    credit = {}
    for player_id, damage in damage_by_player.items():
        credit[player_id] = damage / total_damage

    return credit


async def drop_loot(npc: NPC, room_id: str, ctx: GameContext):
    """
    Drop loot from NPC death.
    """
    if not npc.loot_table:
        return

    for item_id, drop_chance in npc.loot_table.items():
        if random.random() < drop_chance:
            item = ctx.item_repo.get(item_id)
            room_item = RoomItem(room_id=room_id, item_id=item_id, quantity=1)
            ctx.session.add(room_item)

    ctx.session.commit()
```

---

## Combat-Gated Commands

Commands like `SLEEP`, `FAST_TRAVEL`, `TRADE` require condition `NOT_IN_COMBAT`:

```python
class CommandCondition(str, Enum):
    NOT_IN_COMBAT = "not_in_combat"
    IN_COMBAT = "in_combat"


def evaluate_condition(condition: CommandCondition, ctx: GameContext) -> bool:
    if condition == CommandCondition.NOT_IN_COMBAT:
        return ctx.player.active_combat_session_id is None
    elif condition == CommandCondition.IN_COMBAT:
        return ctx.player.active_combat_session_id is not None
    # ... other conditions
```

---

## Testing

```python
@pytest.mark.asyncio
async def test_combat_tick_resolution():
    """Verify that combat tick resolves actions."""
    db = create_in_memory_db()
    ctx = build_test_context(db)

    player = create_test_player(db, "warrior")
    npc = create_test_npc(db, "goblin")

    # Create combat session
    session = await ctx.combat_service.create_session(
        player_id=player.id,
        npc_id=npc.id,
        room_id=ctx.room.id,
        ctx=ctx
    )

    # Simulate combat tick
    await resolve_combat_tick(session.id, ctx)

    # Verify damage was dealt
    session_updated = db.query(CombatSession).filter(
        CombatSession.id == session.id
    ).first()
    npc_combatant = next(
        c for c in session_updated.combatants if c["entity_id"] == npc.id
    )

    assert npc_combatant["hp"] < npc_combatant["max_hp"]
```

---

*See also: [ARCHITECTURE.md § Combat System](ARCHITECTURE.md#15-subsystem-combat-system)*
