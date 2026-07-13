"""Read-only character info queries: traits, skills, reputation, score (Sprint 24, 34.2)."""

from __future__ import annotations

from lorecraft.features.disciplines.abilities import get_discipline_registry
from lorecraft.engine.game import traits as traits_module
from lorecraft.engine.game.context import GameContext
from lorecraft.engine.game.message_types import MessageType
from lorecraft.features.bank.repo import BankRepo
from lorecraft.features.quests.repo import QuestRepo
from lorecraft.features.reputation.repo import ReputationRepo


class CharacterInfoService:
    def list_traits(self, ctx: GameContext) -> None:
        registry = traits_module.get_registry()
        names = sorted(registry.traits_for(ctx.session, "player", ctx.player.id))
        if not names:
            ctx.say("You have no notable traits.")
            ctx.push_update("traits", [])
            return

        lines = ["Your traits:"]
        entries = []
        for name in names:
            trait_def = registry.get(name)
            description = trait_def.description if trait_def is not None else ""
            lines.append(f"  {name}: {description}")
            entries.append({"name": name, "description": description})
        ctx.say("\n".join(lines), MessageType.HELP)
        ctx.push_update("traits", entries)

    def list_disciplines(self, ctx: GameContext) -> None:
        """Report each discipline and the player's current rank in it (Sprint 78).

        Replaces the pre-78 `skills` listing: a discipline rank *is* the former
        flat skill level, now grouped under the five seed disciplines.
        """
        stats = ctx.player_repo.stats(ctx.player.id)
        ranks = stats.discipline_ranks if stats is not None else {}
        registry = get_discipline_registry()

        lines = ["Your disciplines:"]
        entries = []
        for discipline in sorted(registry.all(), key=lambda d: d.name):
            rank = ranks.get(discipline.id, 0)
            lines.append(f"  {discipline.name}: rank {rank}")
            entries.append({"id": discipline.id, "name": discipline.name, "rank": rank})
        ctx.say("\n".join(lines), MessageType.HELP)
        ctx.push_update("disciplines", entries)

    def list_reputation(self, ctx: GameContext) -> None:
        repo = ReputationRepo(ctx.session)
        rows = repo.for_player(ctx.player.id)
        if not rows:
            ctx.say("You have no reputation with anyone yet.")
            ctx.push_update("reputation", [])
            return

        lines = ["Your reputation:"]
        entries = []
        for row in rows:
            lines.append(f"  {row.target_type} {row.target_id}: {row.standing}")
            entries.append(
                {
                    "target_type": row.target_type,
                    "target_id": row.target_id,
                    "standing": row.standing,
                }
            )
        ctx.say("\n".join(lines), MessageType.HELP)
        ctx.push_update("reputation", entries)

    def score(self, ctx: GameContext) -> None:
        """A single progress report (Sprint 34.2, issue-257c6643).

        Aggregates existing state — level/xp, quest completion, wealth
        (carried + banked coins), reputation, and discoveries (rooms/NPCs) —
        with no new persistent schema. Each section reads its own feature's
        tables directly, so a section is simply empty/zero when the player has
        no data there (or the owning feature never ran).
        """
        player = ctx.player
        stats = ctx.player_repo.stats(player.id)

        # Progression.
        level = stats.level if stats is not None else 1
        xp = stats.xp if stats is not None else 0
        xp_to_next = stats.xp_to_next if stats is not None else 0

        # Quests: completed / active out of those started.
        progress = QuestRepo(ctx.session).all_progress(player.id)
        completed = sum(1 for p in progress if p.status == "completed")
        active = sum(1 for p in progress if p.status == "active")

        # Wealth: carried coins + banked (net worth).
        carried = ctx.ledger.balance_of(ctx.session, "player", player.id)
        bank_account = BankRepo(ctx.session).account_for_player(player.id)
        banked = (
            ctx.ledger.balance_of(ctx.session, "bank_account", bank_account.id)
            if bank_account is not None
            else 0
        )

        # Standing and discoveries.
        rep_rows = ReputationRepo(ctx.session).for_player(player.id)
        rooms_found = len(player.visited_rooms)
        npcs_met = len(player.met_npcs)

        lines = [
            f"=== {player.username} — Score ===",
            f"  Level {level}  ({xp}/{xp_to_next} XP)",
            f"  Quests: {completed} completed, {active} in progress",
            f"  Wealth: {carried} carried + {banked} banked = {carried + banked} coins",
            f"  Reputation: standing with {len(rep_rows)} parties",
            f"  Discovered: {rooms_found} rooms, {npcs_met} NPCs met",
        ]
        ctx.say("\n".join(lines), MessageType.HELP)

        ctx.push_update(
            "score",
            {
                "level": level,
                "xp": xp,
                "xp_to_next": xp_to_next,
                "quests_completed": completed,
                "quests_active": active,
                "coins_carried": carried,
                "coins_banked": banked,
                "net_worth": carried + banked,
                "reputation_count": len(rep_rows),
                "rooms_discovered": rooms_found,
                "npcs_met": npcs_met,
            },
        )
