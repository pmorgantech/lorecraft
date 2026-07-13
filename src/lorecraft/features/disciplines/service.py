"""Discipline/Ability policy services (Sprint 78.6).

Two Tier 2 services drive the opinion-free Tier 1 `engine.game.abilities`
mechanism with content-supplied data:

- **`ProficiencyService`** — per-discipline, use-based rank growth. Replaces the
  deleted `features/skills/` `SkillService`: `record_use` rolls the Tier 1
  `resolve_proficiency` step with the *discipline's* own `improve_chance`/
  `max_rank` dials (not the old module constants), and `get_rank` reads
  `PlayerStats.discipline_ranks`. A discipline rank is the base a `skill_check`
  now rolls against (the check `key=` stays the `skill.<name>` resolver namespace
  per Option A — this service supplies the *base*, not the key).
- **`AbilityService`** — the skill-point *sink*. Replaces the deleted
  `SkillTreeService`: `purchase` drives the Tier 1 `check_acquisition` (cost +
  prerequisites + discipline rank + level) and, on success, performs the same
  dual-write the old tree did (record the ability in `unlocked_nodes` *and* set
  its `ability.<id>` flag on `Player.flags`).

Stateless per call, mutating the caller's session objects without committing —
the same session discipline every other Tier 2 service follows.
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlmodel import Session

from lorecraft.engine.game.abilities import (
    AcquisitionResult,
    check_acquisition,
    resolve_proficiency,
)
from lorecraft.engine.game.context import GameContext
from lorecraft.engine.game.rng import GameRng
from lorecraft.engine.models.player import PlayerStats
from lorecraft.errors import NotFoundError
from lorecraft.features.disciplines.abilities import (
    AbilityRecord,
    AbilityRegistry,
    DisciplineRegistry,
    get_ability_registry,
    get_discipline_registry,
)

BASE_RANK = 0


class ProficiencyService:
    """Per-discipline rank growth-by-use, backed by `PlayerStats.discipline_ranks`."""

    def __init__(self, registry: DisciplineRegistry | None = None) -> None:
        self._registry = registry or get_discipline_registry()

    def get_rank(self, session: Session, player_id: str, discipline_id: str) -> int:
        stats = session.get(PlayerStats, player_id)
        if stats is None:
            return BASE_RANK
        rank = stats.discipline_ranks.get(discipline_id)
        return int(rank) if isinstance(rank, (int, float)) else BASE_RANK

    def record_use(
        self,
        session: Session,
        rng: GameRng,
        player_id: str,
        discipline_id: str,
    ) -> bool:
        """Roll a use-based growth step for ``discipline_id``. Returns True if it grew.

        Sources the ``improve_chance``/``max_rank`` dials from the discipline's own
        content (not a module constant); an unknown discipline never grows. The
        proficiency-improve modifier hook (§2) is left un-fed here — matching the
        old `SkillService.record_use`'s modifier-free growth — but remains available
        to a future caller via `resolve_proficiency`'s `modifiers` parameter.
        """
        stats = session.get(PlayerStats, player_id)
        if stats is None:
            raise NotFoundError(
                f"No PlayerStats for player {player_id}", "not_found_player_stats"
            )
        discipline = self._registry.get(discipline_id)
        if discipline is None:
            return False

        current = self.get_rank(session, player_id, discipline_id)
        new_rank = resolve_proficiency(
            rng,
            base_level=current,
            modifiers=(),
            improve_chance=discipline.improve_chance,
            max_rank=discipline.max_rank,
        )
        if int(new_rank) <= current:
            return False
        # Reassign the JSON column (not in-place mutate) so SQLAlchemy detects the
        # change — same discipline as flags / unlocked_nodes.
        stats.discipline_ranks = {
            **stats.discipline_ranks,
            discipline_id: int(new_rank),
        }
        session.add(stats)
        return True


@dataclass(frozen=True)
class PurchaseResult:
    """Outcome of a purchase attempt, with a player-facing reason on failure."""

    ok: bool
    reason: str
    ability: AbilityRecord | None = None


class AbilityService:
    """Ability acquisition — the skill-point sink, driving Tier 1 check_acquisition."""

    def __init__(
        self,
        registry: AbilityRegistry | None = None,
        proficiency: ProficiencyService | None = None,
    ) -> None:
        self._registry = registry or get_ability_registry()
        self._proficiency = proficiency or ProficiencyService()

    def _unlocked(self, ctx: GameContext) -> set[str]:
        stats = ctx.player_repo.stats(ctx.player.id)
        return set(stats.unlocked_nodes) if stats is not None else set()

    def _rank(self, ctx: GameContext, discipline_id: str) -> int:
        return self._proficiency.get_rank(ctx.session, ctx.player.id, discipline_id)

    def owned_nodes(self, ctx: GameContext) -> list[AbilityRecord]:
        unlocked = self._unlocked(ctx)
        return [r for r in self._registry.all() if r.id in unlocked]

    def available_nodes(self, ctx: GameContext) -> list[AbilityRecord]:
        """Not-yet-owned abilities whose full acquisition check currently passes."""
        stats = ctx.player_repo.stats(ctx.player.id)
        if stats is None:
            return []
        unlocked = set(stats.unlocked_nodes)
        available: list[AbilityRecord] = []
        for record in self._registry.all():
            if record.id in unlocked:
                continue
            rank = self._rank(ctx, record.discipline)
            if check_acquisition(stats, record.to_ability_def(), rank).allowed:
                available.append(record)
        return available

    def locked_nodes(self, ctx: GameContext) -> list[AbilityRecord]:
        """Not-yet-owned abilities blocked by cost, prerequisites, rank, or level."""
        stats = ctx.player_repo.stats(ctx.player.id)
        if stats is None:
            return list(self._registry.all())
        unlocked = set(stats.unlocked_nodes)
        locked: list[AbilityRecord] = []
        for record in self._registry.all():
            if record.id in unlocked:
                continue
            rank = self._rank(ctx, record.discipline)
            if not check_acquisition(stats, record.to_ability_def(), rank).allowed:
                locked.append(record)
        return locked

    def purchase(self, ctx: GameContext, ability_id: str) -> PurchaseResult:
        """Attempt to learn `ability_id`. Never silently no-ops — every failure
        path returns a distinct reason. On success mutates stats + flags in place."""
        record = self._registry.get(ability_id)
        if record is None:
            return PurchaseResult(False, f"There is no ability called '{ability_id}'.")

        stats = ctx.player_repo.stats(ctx.player.id)
        if stats is None:
            return PurchaseResult(False, "You have no skill points to spend.", record)

        if record.id in stats.unlocked_nodes:
            return PurchaseResult(False, f"You already know {record.name}.", record)

        rank = self._rank(ctx, record.discipline)
        result = check_acquisition(stats, record.to_ability_def(), rank)
        if not result.allowed:
            return PurchaseResult(False, self._deny_reason(record, result), record)

        # Commit: spend points, record the ability, set every unlock flag. Reassign
        # the JSON columns so SQLAlchemy detects the change (same discipline as the
        # old skill tree's dual-write).
        stats.skill_points -= record.cost
        stats.unlocked_nodes = [*stats.unlocked_nodes, record.id]
        ctx.player_repo.save_stats(stats)
        new_flags = dict(ctx.player.flags)
        for flag in record.unlock.flags:
            new_flags[flag] = True
        ctx.player.flags = new_flags
        return PurchaseResult(True, f"You train {record.name}.", record)

    def _deny_reason(self, record: AbilityRecord, result: AcquisitionResult) -> str:
        """Build the most specific player-facing denial from an AcquisitionResult."""
        if not result.prerequisites_met:
            names = ", ".join(
                self._display_name(p) for p in result.missing_prerequisites
            )
            return f"You must train {names} first."
        if not result.rank_met:
            return (
                f"{record.name} needs {record.required_discipline_rank} "
                f"{record.discipline} rank; keep practising."
            )
        if not result.level_met:
            return f"{record.name} needs character level {record.required_level}."
        return (
            f"{record.name} costs {record.cost} skill "
            f"{_points(record.cost)}; you don't have enough."
        )

    def _display_name(self, ability_id: str) -> str:
        record = self._registry.get(ability_id)
        return record.name if record is not None else ability_id


def _points(cost: int) -> str:
    return "point" if cost == 1 else "points"
