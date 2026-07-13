"""Generic ability *mechanism* — pure, data-driven, opinion-free (Tier 1).

Mirrors `engine/game/leveling.py`: this module knows *how* a class of thing
works (whether an ability can be learned, whether it can be performed right now,
how a proficiency grows by use) but never *what* any particular ability or
discipline is. Every `AbilityDef` is constructed from data a Tier 2 caller loads
from YAML (`world_content/disciplines.yaml` / `abilities.yaml`); no ability id,
discipline id, room id, or item id is hardcoded anywhere here. No session, no IO,
no `GameContext`.

See `docs/discipline_ability_system.md` §2 (the Tier 1 mechanism list) and §5.2
(the `usage:` descriptor shape this module's value objects mirror).
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field

from lorecraft.engine.game.checks import skill_check
from lorecraft.engine.game.modifiers import Modifier, resolve
from lorecraft.engine.game.rng import GameRng
from lorecraft.engine.models.player import PlayerStats
from lorecraft.errors import ValidationError

# The `Player.flags` namespace prefix for *durable* usage-requirement states
# (§5.3). A required character/target state ``hidden`` is satisfied by a
# ``state.hidden`` flag (durable) *or* a held ``ActiveEffect`` whose
# ``effect_key`` is ``hidden`` (transient). Distinct from the existing
# ``ability.<id>`` flag prefix, which records *ownership* of an ability.
STATE_FLAG_PREFIX = "state."

# Modifier key the proficiency-growth roll resolves against, so a Tier 2 source
# (a "fast learner" trait, a teaching bonus) can nudge the learn rate without
# this mechanism knowing what those sources are. A namespaced mechanism key, not
# world content.
PROFICIENCY_IMPROVE_KEY = "proficiency.improve_chance"


@dataclass(frozen=True)
class ResourceCost:
    """One resource an ability spends to be performed (§5.2 `usage.resource`).

    `type` is an open string keying into whatever resource meters exist — today
    Lorecraft has exactly one (`stamina`, via the fatigue feature's meter), but
    the mechanism never hardcodes that name: the affordability check reads
    ``actor_state.resources[type]`` generically. `cost` of 0 means "declared but
    free" (the field exists for future abilities; most v1 abilities cost none).
    """

    type: str
    cost: float = 0.0


@dataclass(frozen=True)
class UsageRequirements:
    """What must hold for an ability to be *performed* (§5.2 `usage:` block).

    Distinct from *acquisition* requirements (what's needed to learn it). All
    fields default to "no requirement", so an ability with an empty
    `UsageRequirements` is always performable.
    """

    # State names the actor must currently hold (durable `state.<name>` flag or
    # transient held ActiveEffect key — see STATE_FLAG_PREFIX / §5.3).
    character_states: tuple[str, ...] = ()
    # State names the target must currently hold (ignored when there is no target).
    target_states: tuple[str, ...] = ()
    # Terrain tags, any one of which satisfies the requirement (e.g. ("outdoor",)
    # replaces `forage`'s old hardcoded `Room.indoor == False` Python check).
    terrain: tuple[str, ...] = ()
    # Resource the actor spends, or None for a free ability.
    resource: ResourceCost | None = None
    # Real-time cooldown between uses; 0 = no cooldown.
    cooldown_seconds: float = 0.0


@dataclass(frozen=True)
class AbilityDef:
    """One ability's *structural* data (§5.2) — the Tier 1 value object.

    Holds only mechanism-relevant fields; display name, description, and flavor
    text are Tier-2-only and never reach this layer. `ability_type` and
    `activation_type` are plain strings, not validated enums (§5.5) — adding a
    new type later (e.g. when combat unshelves) is a content change, not an
    engine change.

    Attributes:
        id: Stable ability identifier (data-supplied; never hardcoded here).
        discipline_id: The discipline this ability belongs to.
        tier: Depth within its discipline/branch (1 = entry tier).
        ability_type: ``active`` | ``passive`` | ``interaction`` | ``reaction``
            (open string; §5.5).
        activation_type: ``instant`` | ``maintained`` | ``triggered`` (open
            string; §5.5).
        prerequisites: Ability ids that must already be owned to learn this one.
        cost: Skill points to acquire it.
        required_discipline_rank: Minimum discipline rank to learn it (§4).
        required_level: Minimum character level to learn it, or None for no gate.
        usage: The perform-time requirement descriptor (§5.2 `usage:`).
    """

    id: str
    discipline_id: str
    tier: int
    ability_type: str
    activation_type: str
    prerequisites: tuple[str, ...] = ()
    cost: int = 0
    required_discipline_rank: int = 0
    required_level: int | None = None
    usage: UsageRequirements = field(default_factory=UsageRequirements)


# --- Acquisition: can this player *learn* this ability? -----------------------


@dataclass(frozen=True)
class AcquisitionResult:
    """Outcome of :func:`check_acquisition`.

    `allowed` is the conjunction of the four sub-checks; the individual booleans
    (and `missing_prerequisites`) let a Tier 2 caller build a specific "why not"
    message without re-deriving the reason.
    """

    allowed: bool
    affordable: bool
    prerequisites_met: bool
    rank_met: bool
    level_met: bool
    missing_prerequisites: tuple[str, ...] = ()


def check_acquisition(
    player_state: PlayerStats,
    ability: AbilityDef,
    discipline_rank: int,
) -> AcquisitionResult:
    """Generic "can this player learn this ability" check (§2).

    Verifies only the *abstract* acquisition conditions — the player can afford
    the skill-point cost, already owns every prerequisite ability, and meets the
    discipline-rank and character-level gates. Knows nothing about *what* the
    ability unlocks; the caller decides what to do when `allowed` is True.

    Ownership of prerequisites is read from ``player_state.unlocked_nodes`` (the
    query/UI record of owned abilities; a "node" is an "ability" post-rename).
    ``discipline_rank`` is supplied by the caller from its per-discipline
    accumulator (§4) rather than read here, keeping this mechanism ignorant of
    how rank is stored.
    """
    owned = set(player_state.unlocked_nodes)
    missing = tuple(p for p in ability.prerequisites if p not in owned)

    affordable = player_state.skill_points >= ability.cost
    prerequisites_met = not missing
    rank_met = discipline_rank >= ability.required_discipline_rank
    level_met = (
        ability.required_level is None or player_state.level >= ability.required_level
    )

    return AcquisitionResult(
        allowed=affordable and prerequisites_met and rank_met and level_met,
        affordable=affordable,
        prerequisites_met=prerequisites_met,
        rank_met=rank_met,
        level_met=level_met,
        missing_prerequisites=missing,
    )


# --- Usage: can this ability be *performed* right now? ------------------------


@dataclass(frozen=True)
class ActorState:
    """A snapshot of one entity's perform-time state, assembled by the caller.

    The Tier 2 caller builds this from the entity's live `Player.flags`,
    held `ActiveEffect` rows, and resource meters (§5.3) — this module never
    touches the DB. Used for both the acting entity and (optionally) its target.

    Attributes:
        flags: The entity's truthy flag keys (e.g. ``{"state.hidden"}``). Only
            the ``state.<name>`` namespace is consulted for usage; other flags
            are harmless if present.
        active_effects: `effect_key`s of the entity's currently-held
            `ActiveEffect`s (transient states like ``"burning"``).
        resources: Current resource-meter values keyed by resource type
            (e.g. ``{"stamina": 40.0}``).
        cooldowns: Per-ability cooldown expiry epochs — ``ability_id`` to the
            epoch at/after which it is usable again. A missing entry means the
            ability is off cooldown.
    """

    flags: frozenset[str] = frozenset()
    active_effects: frozenset[str] = frozenset()
    resources: Mapping[str, float] = field(default_factory=dict)
    cooldowns: Mapping[str, float] = field(default_factory=dict)

    def holds_state(self, state_name: str) -> bool:
        """True if this entity holds ``state_name`` durably or transiently (§5.3)."""
        return (
            f"{STATE_FLAG_PREFIX}{state_name}" in self.flags
            or state_name in self.active_effects
        )


@dataclass(frozen=True)
class WorldState:
    """The ambient perform-time context (current time + local terrain).

    Attributes:
        now_epoch: Current game epoch, compared against cooldown expiries.
        terrain: Terrain tags of the actor's current location (e.g.
            ``{"outdoor", "forest"}``) — matched against an ability's required
            terrain.
    """

    now_epoch: float = 0.0
    terrain: frozenset[str] = frozenset()


@dataclass(frozen=True)
class UsageResult:
    """Outcome of :func:`check_usage`.

    `usable` is the conjunction of every sub-check; the individual booleans and
    the missing-state tuples let a caller narrate the specific block.
    """

    usable: bool
    character_states_met: bool
    target_states_met: bool
    terrain_met: bool
    resource_met: bool
    cooldown_ready: bool
    missing_character_states: tuple[str, ...] = ()
    missing_target_states: tuple[str, ...] = ()


# --- Cooldown / resource primitives -------------------------------------------
#
# Two small generic checks, keyed off the numeric shapes the existing meter /
# `ActiveEffect` primitives already expose — a resource is a `Meter.current`
# (stamina is Lorecraft's only one today), a cooldown is naturally an
# `ActiveEffect` whose `expires_at_epoch` gates re-use. Deliberately NOT a
# multi-resource registry: there is exactly one resource to spend today, so a
# plain available-vs-cost comparison is all the mechanism needs.


def can_afford_resource(available: float, cost: float) -> bool:
    """True if ``available`` covers ``cost`` (a resource-ledger affordability check).

    Generic over resource type — the caller resolves *which* meter's value
    ``available`` is; this only compares magnitudes. A negative cost is a caller
    bug, not "free", so it is rejected loudly.
    """
    if cost < 0:
        raise ValidationError(
            f"resource cost must be non-negative, got {cost}",
            code="validation_resource_cost",
        )
    return available >= cost


def cooldown_expiry(started_epoch: float, cooldown_seconds: float) -> float:
    """The epoch a cooldown started at ``started_epoch`` expires.

    Mirrors how an `ActiveEffect` derives `expires_at_epoch` from its
    `applied_at_epoch` — a Tier 2 caller can store the returned value on such a
    row and later feed it to :func:`is_off_cooldown`.
    """
    if cooldown_seconds < 0:
        raise ValidationError(
            f"cooldown_seconds must be non-negative, got {cooldown_seconds}",
            code="validation_cooldown_seconds",
        )
    return started_epoch + cooldown_seconds


def is_off_cooldown(now_epoch: float, expires_at_epoch: float | None) -> bool:
    """True if a cooldown expiring at ``expires_at_epoch`` has elapsed by ``now_epoch``.

    ``None`` means "no cooldown recorded" (never used, or already swept) — always
    ready. Mirrors the `ActiveEffect` sweep's ``now >= expires_at_epoch`` test.
    """
    return expires_at_epoch is None or now_epoch >= expires_at_epoch


def check_usage(
    actor_state: ActorState,
    ability: AbilityDef,
    target_state: ActorState | None,
    world_state: WorldState,
) -> UsageResult:
    """Generic "can this ability be performed right now" check (§2, §5.3).

    New capability with no equivalent in today's system — verbs currently
    hardcode their own gating in Python (`forage`'s `Room.indoor == False`). This
    evaluates an ability's data-driven `usage` descriptor generically:

    - **character/target states** — every required state must be held by the
      actor (resp. target) as a durable ``state.<name>`` flag or a transient held
      `ActiveEffect` (§5.3). A target requirement with no target present fails.
    - **terrain** — satisfied if any one required terrain tag is present in the
      location's tags (empty requirement = any terrain).
    - **resource** — the actor must have enough of the declared resource.
    - **cooldown** — the ability must be off cooldown at ``world_state.now_epoch``.

    Knows nothing about *which* states/terrain/resources mean what — that is all
    data on the `AbilityDef`.
    """
    req = ability.usage

    missing_character = tuple(
        s for s in req.character_states if not actor_state.holds_state(s)
    )
    character_states_met = not missing_character

    if req.target_states:
        if target_state is None:
            missing_target = req.target_states
        else:
            missing_target = tuple(
                s for s in req.target_states if not target_state.holds_state(s)
            )
    else:
        missing_target = ()
    target_states_met = not missing_target

    terrain_met = not req.terrain or bool(set(req.terrain) & world_state.terrain)

    if req.resource is not None and req.resource.cost > 0:
        available = actor_state.resources.get(req.resource.type, 0.0)
        resource_met = can_afford_resource(available, req.resource.cost)
    else:
        resource_met = True

    cooldown_ready = is_off_cooldown(
        world_state.now_epoch, actor_state.cooldowns.get(ability.id)
    )

    return UsageResult(
        usable=(
            character_states_met
            and target_states_met
            and terrain_met
            and resource_met
            and cooldown_ready
        ),
        character_states_met=character_states_met,
        target_states_met=target_states_met,
        terrain_met=terrain_met,
        resource_met=resource_met,
        cooldown_ready=cooldown_ready,
        missing_character_states=missing_character,
        missing_target_states=missing_target,
    )


# --- Proficiency: use-based growth of a per-discipline/ability competence -----


def resolve_proficiency(
    rng: GameRng,
    base_level: int,
    modifiers: Iterable[Modifier],
    improve_chance: float,
    max_rank: int,
) -> float:
    """Roll one use-based proficiency-growth step and return the new level (§2).

    Generalizes `SkillService.record_use()`'s "learn by doing" mechanic, with its
    two policy dials — `improve_chance` and `max_rank` — lifted out of the module
    constants they are today (`features/skills/service.py`'s
    `IMPROVE_CHANCE`/`MAX_LEVEL`) into **parameters** the Tier 2 caller supplies
    from config. The mechanism knows *how* to roll a chance and cap a level; it
    never decides *what* the chance or cap should be.

    Composition (both are existing Tier 1 primitives):

    - `modifiers.py::resolve()` scales the base improve chance by any modifier
      keyed to :data:`PROFICIENCY_IMPROVE_KEY`, so a "fast learner" trait or
      teaching bonus can raise the learn rate data-drivenly.
    - `checks.py::skill_check()` performs the actual roll (the chance expressed on
      a 0-100 target scale). This inherits `skill_check`'s ``CHECK_FLOOR``/
      ``CHECK_CEIL`` bounds — there is always at least a 5% and at most a 95%
      chance to improve, so learning is never impossible nor guaranteed.

    Note: `rng` (the sole sanctioned `GameRng`) is required — growth is a
    randomized roll, and `skill_check` cannot be composed without it — so it is
    threaded as the first parameter, mirroring `skill_check`'s own convention.
    Returns the (possibly incremented) proficiency as a float; the caller ints/
    persists it at its own edge.
    """
    if not 0.0 <= improve_chance <= 1.0:
        raise ValidationError(
            f"improve_chance must be in [0, 1], got {improve_chance}",
            code="validation_improve_chance",
        )
    if max_rank < 0:
        raise ValidationError(
            f"max_rank must be non-negative, got {max_rank}",
            code="validation_max_rank",
        )
    if base_level >= max_rank:
        return float(max_rank)

    learn_target = resolve(PROFICIENCY_IMPROVE_KEY, improve_chance * 100.0, modifiers)
    result = skill_check(
        rng, base=learn_target, difficulty=0, key=PROFICIENCY_IMPROVE_KEY
    )
    return float(base_level + (1 if result.success else 0))
