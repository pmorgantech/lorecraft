"""Discipline/ability player verbs: `train`/`learn` and the read-only `abilities`
query (Sprint 78.7, relocated from progression 74.3/74.8).

`train` with no argument lists what you can learn now (and what remains locked);
with an ability id it attempts the purchase via `AbilityService` (driving the
Tier 1 `check_acquisition`). `abilities` mirrors the read-only `quests` command —
it reports owned abilities and what is currently trainable, without mutating
anything. Both emit exactly one cohesive `ctx.say()` call (the info-command
cohesion pattern), not a line-per-item stream.

The complementary read-only `disciplines` verb (your rank in each discipline)
lives with the other character-info verbs in `features/character/`.
"""

from __future__ import annotations

from lorecraft.engine.game.context import GameContext
from lorecraft.engine.game.message_types import MessageType
from lorecraft.engine.game.registry import CommandRegistry
from lorecraft.features.disciplines.abilities import AbilityRecord
from lorecraft.features.disciplines.service import AbilityService


def _skill_points(ctx: GameContext) -> int:
    stats = ctx.player_repo.stats(ctx.player.id)
    return stats.skill_points if stats is not None else 0


def _ability_line(ability: AbilityRecord, *, marker: str) -> str:
    return (
        f"  {marker} {ability.name} ({ability.cost} sp, {ability.discipline}) "
        f"— {ability.description.strip()}"
    )


def register_discipline_commands(
    registry: CommandRegistry, service: AbilityService | None = None
) -> None:
    abilities = service or AbilityService()

    @registry.register(
        "train",
        "learn",
        help="train [ability] — spend skill points to learn an ability (no arg lists them)",
    )
    def train_command(noun: str | None, ctx: GameContext) -> None:
        if noun is None:
            _list_trainable(abilities, ctx)
            return
        result = abilities.purchase(ctx, noun.strip())
        if result.ok:
            ctx.say(result.reason, MessageType.LEVEL)
            ctx.push_update("skill_points", _skill_points(ctx))
        else:
            ctx.say(result.reason, MessageType.WARNING)

    @registry.register(
        "abilities",
        "abils",
        help="abilities — list abilities you know and can currently train",
    )
    def abilities_command(noun: str | None, ctx: GameContext) -> None:
        del noun
        owned = abilities.owned_nodes(ctx)
        available = abilities.available_nodes(ctx)
        lines = [f"Skill points: {_skill_points(ctx)}."]
        if owned:
            lines.append("Abilities you know:")
            lines.extend(_ability_line(a, marker="✓") for a in owned)
        else:
            lines.append("You have not trained any abilities yet.")
        if available:
            lines.append("Ready to train:")
            lines.extend(_ability_line(a, marker="•") for a in available)
        ctx.say("\n".join(lines), MessageType.HELP)


def _list_trainable(abilities: AbilityService, ctx: GameContext) -> None:
    available = abilities.available_nodes(ctx)
    locked = abilities.locked_nodes(ctx)
    lines = [f"Skill points: {_skill_points(ctx)}."]
    if available:
        lines.append("You can train:")
        lines.extend(_ability_line(a, marker="•") for a in available)
    else:
        lines.append("Nothing is ready to train right now.")
    if locked:
        lines.append("Still locked (need prerequisites, rank, or more points):")
        lines.extend(_ability_line(a, marker="✗") for a in locked)
    ctx.say("\n".join(lines), MessageType.HELP)
