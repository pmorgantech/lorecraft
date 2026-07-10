"""NPC AI feature: the autonomous agency loop (scripting engine A3).

Wakes an NPC's ``ai`` config (`docs/scripting_engine_design.md` §3.2) so it moves under its own
initiative — ``wander`` / ``patrol`` — emitting ``NPC_MOVED`` (the first real emitter), which
the trigger service turns into ``encounter`` for co-located players. Built entirely on existing
primitives: the event bus, the seedable RNG, and the actor-less ``StandaloneWorldContext`` (A1).

The service holds the live engine/manager/rng, so it is constructed and bus-registered in
``main.py`` (gated on this feature) rather than in the no-arg ServiceContainer — the same shape
as the light/economy/quest-timer schedulable services.
"""

from __future__ import annotations

from lorecraft.features.manifest import FeatureManifest, register_feature

manifest = FeatureManifest(key="npc_ai", name="Autonomous NPC Behavior")

register_feature(manifest)
