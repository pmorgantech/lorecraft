"""Follow feature: social movement (Sprint 47).

`follow <player>` makes you move with a target when they move; `unfollow`
stops. Overt (both sides see narration), not stealthy. A lightweight slice of
the wishlist's *player groups / parties* idea — a natural pairing with transit
(board the ferry together) without building parties.

Self-contained Tier 2 package: `FollowService` (`service.py`) holds the
in-memory follow graph and subscribes to `PLAYER_MOVED`; the `follow`/`unfollow`
verbs live in `commands.py`. It depends on the `movement` feature — a follower's
auto-move re-runs the standard movement gates via `MovementService.move`.
"""

from __future__ import annotations

from lorecraft.features.manifest import FeatureManifest, register_feature

manifest = FeatureManifest(key="follow", name="Follow")

register_feature(manifest)
