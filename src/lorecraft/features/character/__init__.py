"""Character feature: the character-sheet aggregator (skills/traits/reputation
read model behind the `skills`/`traits`/`stats` commands).

Self-contained Tier 2 package (tier split, step 8): the service lives in
`service.py`. Passive manifest — `CharacterInfoService` is built by the
`ServiceContainer`; it reads across the skills/traits/reputation features.
"""

from __future__ import annotations

from lorecraft.features.manifest import FeatureManifest, register_feature

manifest = FeatureManifest(key="character", name="Character Info")

register_feature(manifest)
