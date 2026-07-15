"""Combat feature policy constants and small decision helpers."""

from __future__ import annotations

from dataclasses import dataclass

STATUS_ACTIVE = "active"
STATUS_DOWNED = "downed"
STATUS_DEFEATED = "defeated"
STATUS_ESCAPED = "escaped"

ENGAGEMENT_ENGAGED = "engaged"
ENGAGEMENT_UNENGAGED = "unengaged"
ENGAGEMENT_GUARDING = "guarding"

STANCE_BALANCED = "balanced"
STANCE_AGGRESSIVE = "aggressive"
STANCE_DEFENSIVE = "defensive"
STANCE_MOBILE = "mobile"
VALID_STANCES = (
    STANCE_BALANCED,
    STANCE_AGGRESSIVE,
    STANCE_DEFENSIVE,
    STANCE_MOBILE,
)

REACTION_DEFENSIVE = "defensive"
REACTION_CONSERVE = "conserve"
REACTION_NEVER = "never"
VALID_REACTION_POLICIES = (
    REACTION_DEFENSIVE,
    REACTION_CONSERVE,
    REACTION_NEVER,
)


@dataclass(frozen=True)
class StancePolicy:
    """Tier 2 tactical trade-offs applied to immutable combat snapshots."""

    attack_bonus: float = 0.0
    defense_bonus: int = 0
    damage_multiplier: float = 1.0
    flee_stamina_delta: float = -8.0


STANCE_POLICIES: dict[str, StancePolicy] = {
    STANCE_BALANCED: StancePolicy(),
    STANCE_AGGRESSIVE: StancePolicy(
        attack_bonus=3.0,
        defense_bonus=-2,
        damage_multiplier=1.1,
        flee_stamina_delta=-10.0,
    ),
    STANCE_DEFENSIVE: StancePolicy(
        attack_bonus=-2.0,
        defense_bonus=4,
        damage_multiplier=0.9,
        flee_stamina_delta=-8.0,
    ),
    STANCE_MOBILE: StancePolicy(
        attack_bonus=-1.0,
        defense_bonus=1,
        damage_multiplier=0.9,
        flee_stamina_delta=-4.0,
    ),
}


@dataclass(frozen=True)
class DefeatDecision:
    """Tier 2 policy for what 0 HP means for a combat participant."""

    status: str
    clears_player_combat: bool


def defeat_decision_for(actor_type: str) -> DefeatDecision:
    """Return the default non-lethal PvE defeat policy for an actor type."""

    if actor_type == "player":
        return DefeatDecision(
            status=STATUS_DOWNED,
            clears_player_combat=True,
        )
    return DefeatDecision(
        status=STATUS_DEFEATED,
        clears_player_combat=False,
    )


def normalize_stance(value: str | None) -> str | None:
    """Return a known stance key, or None for invalid input."""

    if value is None:
        return None
    normalized = value.strip().lower()
    return normalized if normalized in STANCE_POLICIES else None


def stance_policy_for(stance: str | None) -> StancePolicy:
    """Return the configured stance policy, defaulting to balanced."""

    return STANCE_POLICIES.get(
        stance or STANCE_BALANCED, STANCE_POLICIES[STANCE_BALANCED]
    )


def normalize_reaction_policy(value: str | None) -> str | None:
    """Return a known reaction policy key, or None for invalid input."""

    if value is None:
        return None
    normalized = value.strip().lower()
    return normalized if normalized in VALID_REACTION_POLICIES else None
