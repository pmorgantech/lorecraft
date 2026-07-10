"""Follow feature: social movement (Sprint 47) + escort quests (Sprint 68).

`follow <player>` makes you move with a target when they move; `unfollow`
stops. Overt (both sides see narration), not stealthy. A lightweight slice of
the wishlist's *player groups / parties* idea — a natural pairing with transit
(board the ferry together) without building parties.

Escort quests reuse the same movement cascade so an NPC can be the one
following, started/stopped via the "start_escort"/"end_escort" dialogue/quest
side effects and checked via the "npc_following"/"npc_present" quest
conditions (`conditions.py`).

Self-contained Tier 2 package: `FollowService` (`service.py`) holds the
in-memory player-follow graph + the escort movement cascade and subscribes to
`PLAYER_MOVED`; the `follow`/`unfollow` verbs live in `commands.py`. It
depends on the `movement` feature — a follower's auto-move re-runs the
standard movement gates via `MovementService.move`.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from lorecraft.features.follow.conditions import register as _register_conditions
from lorecraft.features.manifest import FeatureManifest, register_feature

if TYPE_CHECKING:
    from lorecraft.state import AppState


def _wire(state: "AppState") -> None:
    if state.services.follow is not None:
        _register_conditions(state.services.follow)


manifest = FeatureManifest(key="follow", name="Follow", register_fn=_wire)

register_feature(manifest)
