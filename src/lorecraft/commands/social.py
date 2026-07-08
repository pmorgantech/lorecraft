"""Social commands: talk, choice, say, tell, topic channels, bye."""

from __future__ import annotations

from lorecraft.engine.game.channels import (
    TELL_CHANNEL,
    Channel,
    ChatScope,
)
from lorecraft.engine.game.channels import (
    get_registry as get_channel_registry,
)
from lorecraft.engine.game.context import GameContext
from lorecraft.engine.game.message_types import MessageType
from lorecraft.engine.game.registry import CommandRegistry, CommandScope
from lorecraft.features.npc.dialogue import DialogueService, _NPC_KEY

# Topic channels are *content*, registered here in the composition layer (the
# engine owns only the ChannelRegistry mechanism — Sprint 52 decision; a
# world-YAML channel loader is the planned follow-on). `newbie` seeds the
# capacity: P2ALL, on by default, muteable.
NEWBIE_CHANNEL = Channel(
    id="newbie",
    scope=ChatScope.P2ALL,
    tag="Newbie",
    color="amber",
    muteable=True,
    default_subscribed=True,
)


def register_social_commands(
    registry: CommandRegistry, dialogue_service: DialogueService | None = None
) -> None:
    service = dialogue_service or DialogueService()
    channel_registry = get_channel_registry()
    channel_registry.register(NEWBIE_CHANNEL)

    @registry.register(
        "talk",
        "speak",
        scope=CommandScope.SOCIAL,
        help="talk <name> — start a conversation with an NPC",
    )
    def talk_command(noun: str | None, ctx: GameContext) -> None:
        if noun is None:
            ctx.say("Talk to whom?", MessageType.WARNING)
            return
        npc = ctx.npc_repo.find_in_room(ctx.room.id, noun)
        if npc is None:
            ctx.say(f"There is no {noun} here.", MessageType.WARNING)
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
            ctx.say("You are not in a conversation.", MessageType.WARNING)
            return
        if noun is None:
            ctx.say("Choose a number.", MessageType.WARNING)
            return
        try:
            index = int(noun)
        except ValueError:
            ctx.say("Enter the number of your choice.", MessageType.WARNING)
            return
        service.choose(index, ctx)

    @registry.register(
        "say",
        scope=CommandScope.SOCIAL,
        help="say <message> — speak aloud to the room",
    )
    def say_command(noun: str | None, ctx: GameContext) -> None:
        if noun is None:
            ctx.say("Say what?", MessageType.WARNING)
            return
        # Chat channel (Sprint 45): conversation, not room narration — lets
        # clients route it to a chat pane when separate_chat is on.
        ctx.say_chat(f'You say: "{noun}"')
        ctx.tell_room_chat(f'{ctx.player.username} says: "{noun}"')

    @registry.register(
        "tell",
        "whisper",
        scope=CommandScope.SOCIAL,
        help="tell <player> <message> — send a private message to an online player",
    )
    def tell_command(noun: str | None, ctx: GameContext) -> None:
        # P2P channel (Sprint 52.4). Offline targets are rejected — no
        # store-and-forward (that's a future mail feature, by decision).
        if noun is None:
            ctx.say("Tell whom what?", MessageType.WARNING)
            return
        parts = noun.split(None, 1)
        if len(parts) < 2:
            ctx.say("Tell them what?", MessageType.WARNING)
            return
        target_name, message = parts
        target = ctx.player_repo.by_username(target_name)
        if target is None:
            ctx.say(f"There's no one called '{target_name}'.", MessageType.WARNING)
            return
        if target.id == ctx.player.id:
            ctx.say("You mutter to yourself.", MessageType.WARNING)
            return
        if not ctx.manager.is_connected(target.id):
            ctx.say(f"{target.username} isn't online right now.", MessageType.WARNING)
            return
        ctx.chat_echo(TELL_CHANNEL, f'You tell {target.username}: "{message}"')
        ctx.chat_out(
            TELL_CHANNEL,
            f'{ctx.player.username} tells you: "{message}"',
            target_player_id=target.id,
        )

    # Verb-per-channel (Sprint 52.4 decision): every registered P2ALL topic
    # channel speaks through a verb named after it — `newbie hello`. The
    # server text carries the "(Tag)" prefix so every render path (WS, HTMX,
    # dev client) shows it; clients add per-channel color from the payload's
    # channel field.
    def _register_topic_verb(channel: Channel) -> None:
        @registry.register(
            channel.id,
            scope=CommandScope.SOCIAL,
            help=f"{channel.id} <message> — speak on the {channel.tag} channel",
        )
        def topic_command(noun: str | None, ctx: GameContext) -> None:
            if noun is None:
                ctx.say(f"Say what on the {channel.tag} channel?", MessageType.WARNING)
                return
            ctx.chat_echo(channel.id, f'({channel.tag}) You: "{noun}"')
            ctx.chat_out(channel.id, f'({channel.tag}) {ctx.player.username}: "{noun}"')

    for topic_channel in channel_registry.topic_channels():
        _register_topic_verb(topic_channel)

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
            ctx.say("You are not speaking with anyone.", MessageType.WARNING)
            return
        service.end(ctx)
        ctx.say("Farewell.")
