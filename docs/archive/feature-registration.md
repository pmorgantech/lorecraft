> **📦 Archived (2026-07-18).** Predates the tier-split refactor — uses pre-split import
> paths (`lorecraft.game.*` instead of `lorecraft.engine.game.*`) and describes combat as
> "planned Sprint 31" (shipped long since). The actual current registration pattern is the
> `FeatureManifest` + `discover_features()` system — see `AGENTS.md`'s "Codebase structure"
> section and `src/lorecraft/features/manifest.py` / `loader.py`. Kept here only for history.

# Feature Registration Pattern

**Goal:** Add new gameplay features (combat, trading, PvP) without modifying core engine code.

## Structure

Each feature is self-contained in its own module tree and registers with shared, pluggable registries:

```
features/
  combat/                    # Example: Combat feature
    models.py                # CombatSession, CombatAction
    service.py               # CombatService
    commands.py              # @registry.register("attack", "flee", ...)
    events.py                # Event handlers (bus.on(...))
    conditions.py            # Condition predicates (in_combat, has_target)
    side_effects.py          # Dialogue side effects (start_combat, flee)
    __init__.py              # Feature entry point (exports register_feature)
```

## How to Add a Feature

### 1. Define Models

```python
# features/combat/models.py
from dataclasses import dataclass

@dataclass
class CombatSession:
    """Represents an active combat session."""
    id: str
    attacker_id: str
    defender_id: str
    health: int
    ...
```

Store in the database via SQLModel/SQLAlchemy if persistence is needed.

### 2. Create a Service

```python
# features/combat/service.py
from lorecraft.game.events import EventBus
from lorecraft.types import JsonObject
from lorecraft.game.context import GameContext

class CombatService:
    """Orchestrates combat sessions, ticks, damage, death."""

    def __init__(self):
        self._sessions = {}

    def start_session(self, attacker_id: str, defender_id: str, ctx: GameContext) -> None:
        """Initiate combat between two entities."""
        session = CombatSession(...)
        self._sessions[session.id] = session
        # Queue events for audio/UI/state changes
        ctx.queue_event(GameEvent.COMBAT_STARTED, session_id=session.id, ...)

    def register(self, bus: EventBus) -> None:
        """Register event handlers (follows convention from other services)."""
        bus.on(GameEvent.COMBAT_TICK, self._on_tick)
        bus.on(GameEvent.PLAYER_DIED, self._end_session)
```

### 3. Register Commands

```python
# features/combat/commands.py
from lorecraft.game.registry import CommandRegistry, CommandScope, CommandCondition
from features.combat.service import CombatService

def register_combat_commands(registry: CommandRegistry, service: CombatService) -> None:
    """Register all combat commands with conditions."""

    @registry.register(
        "attack",
        scope=CommandScope.WORLD,
        conditions=[
            CommandCondition.IN_COMBAT,
            "has_combat_target",  # Custom condition
        ],
        help="attack <target> — strike an opponent"
    )
    def attack_command(noun: str | None, ctx: GameContext) -> None:
        if noun is None:
            ctx.say("Attack what?")
            return
        service.attack(noun, ctx)
```

### 4. Register Conditions

Register with the appropriate registry based on where conditions are used:

```python
# features/combat/conditions.py
from lorecraft.game.command_conditions import get_registry as get_cmd_registry
from lorecraft.npc.dialogue_conditions import get_registry as get_dialogue_registry
from lorecraft.game.command_conditions import ConditionResult

def register_combat_conditions() -> None:
    """Register combat-specific condition predicates."""
    cmd_registry = get_cmd_registry()
    dialogue_registry = get_dialogue_registry()

    def has_combat_target_check(parameter: str, ctx: GameContext) -> ConditionResult:
        if not ctx.player.active_combat_session_id:
            return ConditionResult(False, "You don't have an active target.")
        return ConditionResult(True)

    cmd_registry.register("has_combat_target", has_combat_target_check)
    dialogue_registry.register("has_combat_target", has_combat_target_check)
```

### 5. Register Dialogue Side Effects

Dialogue can trigger feature actions without hardcoding in dialogue.py:

```python
# features/combat/side_effects.py
from lorecraft.npc.side_effects import get_registry as get_side_effects_registry
from lorecraft.game.context import GameContext

def register_combat_side_effects(service: CombatService) -> None:
    """Register combat side effects for dialogue trees."""
    registry = get_side_effects_registry()

    def start_combat_handler(data: JsonObject, ctx: GameContext) -> None:
        opponent_id = str(data)  # dialogue specifies: start_combat: "npc_soldier"
        service.start_session(ctx.player.id, opponent_id, ctx)

    registry.register("start_combat", start_combat_handler)
```

### 6. Register Event Handlers

Services call `register(bus)` at app lifespan; one convention for all:

```python
# features/combat/service.py
class CombatService:
    def register(self, bus: EventBus) -> None:
        """Handlers for game events that affect combat."""
        bus.on(GameEvent.COMBAT_TICK, self._on_tick)
        bus.on(GameEvent.PLAYER_MOVED, self._on_player_moved)
        bus.on(GameEvent.PLAYER_DIED, self._on_player_death)

    def _on_tick(self, event: Event, ctx: object) -> None:
        # Advance combat session by one tick
        ...
```

### 7. Register with ServiceContainer

Add the service to the container so it's instantiated once and shared:

```python
# src/lorecraft/services/container.py
from features.combat.service import CombatService

@dataclass
class ServiceContainer:
    movement: MovementService = field(default_factory=MovementService)
    inventory: InventoryService = field(default_factory=InventoryService)
    save: SaveSlotService = field(default_factory=SaveSlotService)
    dialogue: DialogueService = field(default_factory=DialogueService)
    quest: QuestService = field(default_factory=QuestService)
    combat: CombatService = field(default_factory=CombatService)  # NEW
```

Then wire it in the app lifespan (main.py):

```python
def lifespan(app: FastAPI) -> AsyncIterator[None]:
    # ... existing setup ...
    services = ServiceContainer.build()

    # Wire up combat
    from features.combat.commands import register_combat_commands
    from features.combat.conditions import register_combat_conditions
    from features.combat.side_effects import register_combat_side_effects

    register_combat_commands(registry, services.combat)
    register_combat_conditions()
    register_combat_side_effects(services.combat)
    services.combat.register(bus)

    # ... rest of setup ...
```

### 8. Register Rules (Optional)

Rule engine allows features to gate actions or modify event payloads:

```python
# features/combat/rules.py
from lorecraft.game.rules import RuleEngine, RuleResult
from lorecraft.types import JsonObject

def register_combat_rules(rules: RuleEngine) -> None:
    """Gate combat-related actions."""

    def can_take_item_in_combat(ctx: object, payload: JsonObject) -> RuleResult:
        """Players can't loot while in combat."""
        from lorecraft.game.context import GameContext
        if isinstance(ctx, GameContext) and ctx.player.active_combat_session_id:
            return RuleResult.block("You can't pick up items while fighting!")
        return RuleResult.allow()

    rules.register_rule("item_taken", can_take_item_in_combat)
```

Then wire it in main.py:

```python
from features.combat.rules import register_combat_rules
register_combat_rules(rules)
```

## Example: Combat Feature

See `features/combat/` (planned [Sprint 31](../project/roadmap.md#sprint-31--combat-core-services-supporting-system)) for the first full consumer of this pattern.

The pattern ensures:
- ✅ New features don't touch core engine files
- ✅ Features register via shared pluggable registries (commands, conditions, side effects, rules, events)
- ✅ One `ServiceContainer` holds all services; instantiated once in app lifespan
- ✅ Services follow `register(bus)` convention for event wiring
- ✅ Dialogue trees reference feature side effects and conditions by name, not hard-coded logic

## When Rules Matter

Rules are rarely needed; most gates should be **conditions** (availability checks). Use rules only for:
- Vetoing actions based on state (e.g., "can't loot while in combat")
- Modifying event payloads (e.g., "damage is halved in rain")
- Cross-feature consistency (e.g., trading disallowed during PvP consent window)
