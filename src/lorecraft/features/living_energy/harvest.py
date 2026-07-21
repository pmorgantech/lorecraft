"""Harvest: the `harvest <channel>` verb + its depletable-node yield tables
(roadmap_world.md gap #2).

`harvest` is the second reference *active ability* (after `forage`), unlocked by
the skill tree: its command registers with
`conditions=[..., actor_has_flag:ability.harvest]`, so it is invisible and
unusable — hidden from `help` too — until the node is bought.

Where `forage` yields from an *infinite* terrain table, `harvest` draws down a
*depletable* per-`(zone, channel)` node: it reads gap #1's Tier 1
`ZoneEnergyService` state, refuses to harvest an exhausted node, and on a
successful survival check draws the node down by a content-authored amount
(clamped at zero — the "you took the last of it" signal). The Tier 1 drift sweep
regenerates the node toward its baseline over time.

Which channels yield which items, in which zones, at what difficulty/draw is all
*content* (`world_content/harvest.yaml`) keyed by channel — no item ids, zones,
or dials are hardcoded here. The channel identities themselves are the
`living_energy` feature's policy (`channels.py`).
"""

from __future__ import annotations

from pathlib import Path

import yaml
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.engine import Engine

from lorecraft.engine.game.checks import skill_check
from lorecraft.engine.game.context import GameContext
from lorecraft.engine.game.holders import Location
from lorecraft.engine.game.message_types import MessageType
from lorecraft.engine.game.modifiers import get_registry as get_modifier_registry
from lorecraft.engine.services.zone_energy import ZoneEnergyService
from lorecraft.errors import NotFoundError
from lorecraft.features.disciplines.service import ProficiencyService
from lorecraft.features.living_energy.channels import CHANNELS

HARVEST_SCHEMA_VERSION = 1

# Default content location, matching config's ``harvest_yaml_path``. The server's
# authoritative (env-override-respecting) load happens in ``main.py``; this default
# only backs the feature ``register_fn`` fill-in on the enable path (doc-gen/tests),
# so it deliberately does not import ``lorecraft.config``.
DEFAULT_HARVEST_YAML_PATH = "world_content/harvest.yaml"


class HarvestProfile(BaseModel):
    """One channel's depletable-harvest policy (Tier 2 content).

    ``channel`` names the gap #1 energy channel this profile draws from;
    ``zones`` is the allowlist of ``Room.zone`` values where that channel is
    present (harvest's availability gate — replacing forage's terrain gate,
    since e.g. Dreamveil is underground, not outdoor). ``draw_amount`` is drawn
    from the node on a success (clamped at 0); ``min_harvestable`` is the floor
    at or below which the node reads as exhausted.
    """

    channel: str
    discipline: str
    check_key: str
    difficulty: int
    draw_amount: float
    min_harvestable: float
    yields: list[str] = Field(default_factory=list)
    zones: list[str] = Field(default_factory=list)
    required_tool: str | None = None

    @field_validator("channel", "discipline", "check_key")
    @classmethod
    def _non_empty(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("harvest profile field must be non-empty")
        return value

    @field_validator("draw_amount", "min_harvestable")
    @classmethod
    def _non_negative(cls, value: float) -> float:
        if value < 0:
            raise ValueError("harvest profile amounts must be non-negative")
        return value


class HarvestDocument(BaseModel):
    version: int = HARVEST_SCHEMA_VERSION
    profiles: list[HarvestProfile] = Field(default_factory=list)


def validate_harvest_document(data: object) -> HarvestDocument:
    return HarvestDocument.model_validate(data)


def load_harvest_yaml(path: str | Path) -> HarvestDocument:
    text = Path(path).read_text(encoding="utf-8")
    return validate_harvest_document(yaml.safe_load(text) or {})


class HarvestRegistry:
    """Channel -> its harvest profile, validating each channel is a real one."""

    def __init__(self) -> None:
        self._by_channel: dict[str, HarvestProfile] = {}

    def register(self, profile: HarvestProfile) -> None:
        if profile.channel not in CHANNELS:
            raise NotFoundError(
                f"harvest profile references unknown channel {profile.channel!r}",
                "not_found_living_energy_channel",
            )
        self._by_channel[profile.channel] = profile

    def load_document(self, document: HarvestDocument) -> None:
        for profile in document.profiles:
            self.register(profile)

    def get(self, channel: str) -> HarvestProfile | None:
        return self._by_channel.get(channel)

    def is_empty(self) -> bool:
        return not self._by_channel

    def clear(self) -> None:
        self._by_channel.clear()


_registry = HarvestRegistry()


def get_registry() -> HarvestRegistry:
    return _registry


class HarvestService:
    """Handles `harvest <channel>`: a survival check against a depletable node."""

    def __init__(
        self,
        registry: HarvestRegistry | None = None,
        proficiency: ProficiencyService | None = None,
        zone_energy: ZoneEnergyService | None = None,
    ) -> None:
        self._registry = registry or get_registry()
        self._proficiency = proficiency or ProficiencyService()
        # Preferred wiring: the composition layer injects the same engine-backed
        # ``ZoneEnergyService`` singleton it built for the drift sweep (see
        # ``main.py`` -> ``register_living_energy_commands``), matching the
        # ``MeterService``/``EffectService`` injection convention. The lazy
        # fallback below only covers un-injected construction (standalone router
        # use / tests that never invoke ``harvest``).
        self._zone_energy = zone_energy

    def _zone_energy_service(self, ctx: GameContext) -> ZoneEnergyService:
        if self._zone_energy is None:
            # ``Session.get_bind()`` is typed ``Engine | Connection``;
            # ``ZoneEnergyService`` needs a concrete ``Engine`` (only for its own
            # short-lived sweep session, which this un-registered fallback instance
            # never runs). Narrow type-safely — a ``Connection`` yields its owning
            # ``Engine`` via ``.engine`` — rather than casting past the union.
            bind = ctx.session.get_bind()
            engine = bind if isinstance(bind, Engine) else bind.engine
            self._zone_energy = ZoneEnergyService(engine)
        return self._zone_energy

    def harvest(self, ctx: GameContext, channel: str) -> None:
        profile = self._registry.get(channel)
        if profile is None:
            ctx.say(
                "You don't know how to harvest that.",
                MessageType.WARNING,
            )
            return

        # Fail-closed: a room with no zone can carry no living-energy node.
        zone = ctx.room.zone
        if zone is None:
            ctx.say(
                "There is no living energy to harvest here.",
                MessageType.WARNING,
            )
            return

        # Presence gate: the channel is only harvestable in its allowlisted zones.
        if zone not in profile.zones:
            ctx.say(
                f"There is no {channel} to harvest in this region.",
                MessageType.WARNING,
            )
            return

        base = self._proficiency.get_rank(
            ctx.session, ctx.player.id, profile.discipline
        )
        modifiers = get_modifier_registry().collect(
            ctx.session, "player", ctx.player.id
        )
        result = skill_check(
            ctx.rng,
            base=base,
            difficulty=profile.difficulty,
            modifiers=modifiers,
            key=profile.check_key,
        )

        # Materialize the PlayerStats row (get-or-create) before record_use,
        # which hard-raises on a missing row (mirrors ForageService).
        ctx.player_repo.stats(ctx.player.id)
        self._proficiency.record_use(
            ctx.session, ctx.rng, ctx.player.id, profile.discipline
        )

        if not result.success:
            ctx.say(f"You work at the {channel} but come away with nothing.")
            return

        # Depletion gate: read the node and refuse if it's at or below the
        # harvestable floor. get() lazily seeds the node at its channel baseline.
        zone_energy = self._zone_energy_service(ctx)
        state = zone_energy.get(ctx.session, zone, channel)
        if state.intensity <= profile.min_harvestable:
            ctx.say(
                f"The {channel} here is spent — nothing worth taking remains.",
                MessageType.HINT,
            )
            return

        # Resolve a yield that actually exists in the world (content may name an
        # item id that isn't seeded) *before* drawing the node down, so a content
        # typo never silently depletes a zone (mirrors forage's guard-before-effect).
        candidates = [
            item_id
            for item_id in profile.yields
            if ctx.item_repo.get(item_id) is not None
        ]
        if not candidates:
            ctx.say(
                f"You draw the {channel}, but it slips away before you can vial it."
            )
            return

        # Draw the node down (clamped at zero). clamped_low means this draw hit
        # the floor — the caller's "you took the last of it" signal.
        change = zone_energy.adjust(ctx.session, state, -profile.draw_amount)

        item_id = ctx.rng.choice(candidates)
        item = ctx.item_repo.get(item_id)
        assert item is not None
        ctx.item_location.spawn(item_id, Location("player", ctx.player.id))
        ctx.say(f"You harvest the {channel} and collect {item.name}.", MessageType.HINT)
        ctx.tell_room(f"{ctx.player.username} harvests {channel} from the area.")

        if change.clamped_low:
            ctx.say(
                f"That was the last of the {channel} here — it will need time to recover.",
                MessageType.HINT,
            )
