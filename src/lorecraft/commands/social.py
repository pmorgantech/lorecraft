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
from lorecraft.types import JsonObject

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
SHOUT_CHANNEL = Channel(id="shout", scope=ChatScope.P2ROOM, tag="Shout", color="red")
_LAST_TELL_FROM_FLAG = "_last_tell_from"


def _sentence(text: str) -> str:
    text = text.strip()
    if not text:
        return text
    return text if text[-1] in ".!?" else f"{text}."


def _resolve_emote_target(noun: str | None, ctx: GameContext) -> str | None:
    """Best-effort display name for an emote target, or ``None`` for a targetless emote.

    Resolves (in order) an NPC in the room, then a player in the room, by name; otherwise
    returns the raw text so a player can `point at sign` / `wave at the sky` freely. A leading
    ``at`` (``point at sign``) is stripped.
    """
    if not noun:
        return None
    text = noun.strip()
    if text.lower().startswith("at "):
        text = text[3:].strip()
    if not text:
        return None
    npc = ctx.npc_repo.find_in_room(ctx.room.id, text)
    if npc is not None:
        return npc.name
    other = ctx.player_repo.by_username(text)
    if other is not None and other.current_room_id == ctx.room.id:
        return other.username
    return text


def _online_player_names(ctx: GameContext) -> list[str]:
    players = [
        player
        for player_id in ctx.manager.connected_player_ids()
        if (player := ctx.player_repo.get(player_id)) is not None
    ]
    return sorted(player.username for player in players)


def _remember_tell_sender(
    ctx: GameContext, *, recipient_id: str, sender_id: str
) -> None:
    recipient = ctx.player_repo.get(recipient_id)
    if recipient is None:
        return
    recipient.flags = {**recipient.flags, _LAST_TELL_FROM_FLAG: sender_id}


def _send_tell(ctx: GameContext, target_name: str, message: str) -> None:
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
    _remember_tell_sender(ctx, recipient_id=target.id, sender_id=ctx.player.id)
    ctx.chat_echo(TELL_CHANNEL, f'You tell {target.username}: "{message}"')
    ctx.chat_out(
        TELL_CHANNEL,
        f'{ctx.player.username} tells you: "{message}"',
        target_player_id=target.id,
    )


def _zone_shout_recipient_ids(ctx: GameContext) -> list[str]:
    actor_zone = ctx.room.zone
    recipient_ids: list[str] = []
    for player_id in ctx.manager.connected_player_ids():
        if player_id == ctx.player.id:
            continue
        player = ctx.player_repo.get(player_id)
        if player is None:
            continue
        room = ctx.room_repo.get(player.current_room_id)
        if room is None:
            continue
        if actor_zone is None:
            if room.id == ctx.room.id:
                recipient_ids.append(player_id)
        elif room.zone == actor_zone:
            recipient_ids.append(player_id)
    return recipient_ids


def register_social_commands(
    registry: CommandRegistry, dialogue_service: DialogueService | None = None
) -> None:
    service = dialogue_service or DialogueService()
    channel_registry = get_channel_registry()
    channel_registry.register(NEWBIE_CHANNEL)
    channel_registry.register(SHOUT_CHANNEL)

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
        _send_tell(ctx, parts[0], parts[1])

    @registry.register(
        "reply",
        scope=CommandScope.SOCIAL,
        help="reply <message> — reply to the last player who sent you a tell",
    )
    def reply_command(noun: str | None, ctx: GameContext) -> None:
        if noun is None:
            ctx.say("Reply with what?", MessageType.WARNING)
            return
        target_id = ctx.player.flags.get(_LAST_TELL_FROM_FLAG)
        if not isinstance(target_id, str):
            ctx.say("No one has told you anything to reply to.", MessageType.WARNING)
            return
        target = ctx.player_repo.get(target_id)
        if target is None:
            ctx.say("No one has told you anything to reply to.", MessageType.WARNING)
            return
        _send_tell(ctx, target.username, noun)

    @registry.register(
        "who",
        scope=CommandScope.SOCIAL,
        help="who — list players currently online",
    )
    def who_command(noun: str | None, ctx: GameContext) -> None:
        del noun
        names = _online_player_names(ctx)
        if not names:
            ctx.say("No players are online.")
            return
        label = "player" if len(names) == 1 else "players"
        ctx.say(f"Online {label}: {', '.join(names)}")

    @registry.register(
        "shout",
        "yell",
        scope=CommandScope.SOCIAL,
        help="shout <message> — speak loudly to players in your current area",
    )
    def shout_command(noun: str | None, ctx: GameContext) -> None:
        if noun is None:
            ctx.say("Shout what?", MessageType.WARNING)
            return
        ctx.chat_echo(SHOUT_CHANNEL.id, f'You shout: "{noun}"')
        payload: JsonObject = {
            "type": "feed_append",
            "content": f'{ctx.player.username} shouts: "{noun}"',
            "message_type": MessageType.CHAT.value,
            "channel": SHOUT_CHANNEL.id,
        }
        for player_id in _zone_shout_recipient_ids(ctx):
            ctx.defer_delivery(
                lambda player_id=player_id, payload=payload: ctx.manager.send_to_player(
                    player_id, payload
                )
            )

    @registry.register(
        "emote",
        "pose",
        scope=CommandScope.SOCIAL,
        help="emote <action> — pose an action to the room",
    )
    def emote_command(noun: str | None, ctx: GameContext) -> None:
        if noun is None:
            ctx.say("Emote what?", MessageType.WARNING)
            return
        line = _sentence(f"{ctx.player.username} {noun}")
        ctx.say(f"You emote: {line}")
        ctx.tell_room(line)

    def _simple_social(
        verb: str, noun: str | None, ctx: GameContext, *, third_person: str
    ) -> None:
        target = _resolve_emote_target(noun, ctx)
        if target is None:
            ctx.say(f"You {verb}.")
            ctx.tell_room(f"{ctx.player.username} {third_person}.")
            return
        ctx.say(f"You {verb} at {target}.")
        ctx.tell_room(f"{ctx.player.username} {third_person} at {target}.")

    @registry.register(
        "smile",
        scope=CommandScope.SOCIAL,
        help="smile [at <someone>] — smile, optionally at a target",
    )
    def smile_command(noun: str | None, ctx: GameContext) -> None:
        _simple_social("smile", noun, ctx, third_person="smiles")

    @registry.register(
        "laugh",
        scope=CommandScope.SOCIAL,
        help="laugh [at <someone>] — laugh, optionally at a target",
    )
    def laugh_command(noun: str | None, ctx: GameContext) -> None:
        _simple_social("laugh", noun, ctx, third_person="laughs")

    @registry.register(
        "nod",
        scope=CommandScope.SOCIAL,
        help="nod [at <someone>] — nod, optionally at a target",
    )
    def nod_command(noun: str | None, ctx: GameContext) -> None:
        _simple_social("nod", noun, ctx, third_person="nods")

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
        "wave",
        scope=CommandScope.SOCIAL,
        help="wave [at <someone>] — wave, optionally at someone or something",
    )
    def wave_command(noun: str | None, ctx: GameContext) -> None:
        target = _resolve_emote_target(noun, ctx)
        if target is None:
            ctx.say("You wave.")
            ctx.tell_room(f"{ctx.player.username} waves.")
        else:
            ctx.say(f"You wave at {target}.")
            ctx.tell_room(f"{ctx.player.username} waves at {target}.")

    @registry.register(
        "point",
        scope=CommandScope.SOCIAL,
        help="point at <someone/something> — point at a target",
    )
    def point_command(noun: str | None, ctx: GameContext) -> None:
        target = _resolve_emote_target(noun, ctx)
        if target is None:
            ctx.say("Point at what?", MessageType.WARNING)
            return
        ctx.say(f"You point at {target}.")
        ctx.tell_room(f"{ctx.player.username} points at {target}.")

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
