"""Social commands: talk, choice, say, bye."""

from __future__ import annotations

from lorecraft.game.context import GameContext
from lorecraft.game.registry import CommandRegistry, CommandScope
from lorecraft.npc.dialogue import DialogueService, _NPC_KEY


def register_social_commands(registry: CommandRegistry) -> None:
    service = DialogueService()

    @registry.register(
        "talk",
        "speak",
        scope=CommandScope.SOCIAL,
        help="talk <name> — start a conversation with an NPC",
    )
    def talk_command(noun: str | None, ctx: GameContext) -> None:
        if noun is None:
            ctx.say("Talk to whom?")
            return
        npc = ctx.npc_repo.find_in_room(ctx.room.id, noun)
        if npc is None:
            ctx.say(f"There is no {noun} here.")
            return
        service.start(npc.id, ctx)

    @registry.register(
        "choice",
        "choose",
        scope=CommandScope.SOCIAL,
        help="choice <number> — pick a dialogue reply",
    )
    def choice_command(noun: str | None, ctx: GameContext) -> None:
        if not ctx.player.flags.get(_NPC_KEY):
            ctx.say("You are not in a conversation.")
            return
        if noun is None:
            ctx.say("Choose a number.")
            return
        try:
            index = int(noun)
        except ValueError:
            ctx.say("Enter the number of your choice.")
            return
        service.choose(index, ctx)

    @registry.register(
        "say",
        scope=CommandScope.SOCIAL,
        help="say <message> — speak aloud to the room",
    )
    def say_command(noun: str | None, ctx: GameContext) -> None:
        if noun is None:
            ctx.say("Say what?")
            return
        ctx.say(f'You say: "{noun}"')
        ctx.tell_room(f'{ctx.player.username} says: "{noun}"')

    @registry.register(
        "bye",
        "farewell",
        "goodbye",
        scope=CommandScope.SOCIAL,
        help="bye — end the current conversation",
    )
    def bye_command(noun: str | None, ctx: GameContext) -> None:
        del noun
        if not ctx.player.flags.get(_NPC_KEY):
            ctx.say("You are not speaking with anyone.")
            return
        service.end(ctx)
        ctx.say("Farewell.")
