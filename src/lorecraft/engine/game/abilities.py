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

from dataclasses import dataclass, field

# The `Player.flags` namespace prefix for *durable* usage-requirement states
# (§5.3). A required character/target state ``hidden`` is satisfied by a
# ``state.hidden`` flag (durable) *or* a held ``ActiveEffect`` whose
# ``effect_key`` is ``hidden`` (transient). Distinct from the existing
# ``ability.<id>`` flag prefix, which records *ownership* of an ability.
STATE_FLAG_PREFIX = "state."


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
