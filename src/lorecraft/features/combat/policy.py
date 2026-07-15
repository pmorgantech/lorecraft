"""Combat feature policy constants and small decision helpers."""

from __future__ import annotations

from dataclasses import dataclass

STATUS_ACTIVE = "active"
STATUS_DOWNED = "downed"
STATUS_DEFEATED = "defeated"
STATUS_ESCAPED = "escaped"

ENGAGEMENT_ENGAGED = "engaged"
ENGAGEMENT_UNENGAGED = "unengaged"


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
