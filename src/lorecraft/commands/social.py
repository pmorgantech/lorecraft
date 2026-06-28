"""Social commands: talk, choice, say, bye."""

from __future__ import annotations

from typing import cast

from lorecraft.game.context import GameContext
from lorecraft.game.registry import CommandRegistry
from lorecraft.npc.dialogue import DialogueService, _NPC_KEY


def register_social_commands(registry: CommandRegistry) -> None:
    service = DialogueService()

    @registry.register("talk", "speak")
    def talk_command(noun: str | None, ctx: object) -> None:
        game_ctx = cast(GameContext, ctx)
        if noun is None:
            game_ctx.say("Talk to whom?")
            return
        npcs = game_ctx.npc_repo.in_room(game_ctx.room.id)
        npc = next((n for n in npcs if n.name.lower().startswith(noun.lower())), None)
        if npc is None:
            game_ctx.say(f"There is no {noun} here.")
            return
        service.start(npc.id, game_ctx)

    @registry.register("choice", "choose")
    def choice_command(noun: str | None, ctx: object) -> None:
        game_ctx = cast(GameContext, ctx)
        if not game_ctx.player.flags.get(_NPC_KEY):
            game_ctx.say("You are not in a conversation.")
            return
        if noun is None:
            game_ctx.say("Choose a number.")
            return
        try:
            index = int(noun)
        except ValueError:
            game_ctx.say("Enter the number of your choice.")
            return
        service.choose(index, game_ctx)

    @registry.register("say")
    def say_command(noun: str | None, ctx: object) -> None:
        game_ctx = cast(GameContext, ctx)
        if noun is None:
            game_ctx.say("Say what?")
            return
        game_ctx.say(f'You say: "{noun}"')
        game_ctx.tell_room(f'{game_ctx.player.username} says: "{noun}"')

    @registry.register("bye", "farewell", "goodbye")
    def bye_command(noun: str | None, ctx: object) -> None:
        game_ctx = cast(GameContext, ctx)
        del noun
        if not game_ctx.player.flags.get(_NPC_KEY):
            game_ctx.say("You are not speaking with anyone.")
            return
        service.end(game_ctx)
        game_ctx.say("Farewell.")
