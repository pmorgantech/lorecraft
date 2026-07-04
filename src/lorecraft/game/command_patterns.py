"""Command pattern taxonomy and helpers for consuming parser output."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from lorecraft.game.parser import ParsedCommand

# Semantic role keys produced by the parser (flexible vocabulary for v1).
ROLE_OBJECT = "object"
ROLE_TARGET = "target"
ROLE_INSTRUMENT = "instrument"
ROLE_RECIPIENT = "recipient"
ROLE_SOURCE = "source"
ROLE_DESTINATION = "destination"
ROLE_DIRECTION = "direction"
ROLE_QUANTITY = "quantity"
ROLE_ADJECTIVES = "adjectives"
ROLE_MESSAGE = "message"
ROLE_TOPIC = "topic"
ROLE_PREPOSITION = "preposition"


class CommandPattern(StrEnum):
    """How a handler should interpret parsed roles."""

    MOVEMENT = "movement"
    BARE = "bare"
    OBJECT_MANIPULATION = "object_manipulation"
    CONTAINER = "container"
    TRANSFER = "transfer"
    TOOL_USE = "tool_use"
    COMBAT = "combat"
    SPEECH = "speech"
    SOCIAL_GESTURE = "social_gesture"
    NPC_DIALOGUE = "npc_dialogue"
    META = "meta"
    UNKNOWN = "unknown"


VERB_PATTERNS: dict[str, CommandPattern] = {
    "move": CommandPattern.MOVEMENT,
    "go": CommandPattern.MOVEMENT,
    "look": CommandPattern.BARE,
    "inventory": CommandPattern.BARE,
    "help": CommandPattern.META,
    "quit": CommandPattern.META,
    "save": CommandPattern.META,
    "load": CommandPattern.META,
    "take": CommandPattern.OBJECT_MANIPULATION,
    "drop": CommandPattern.OBJECT_MANIPULATION,
    "wear": CommandPattern.OBJECT_MANIPULATION,
    "remove": CommandPattern.OBJECT_MANIPULATION,
    "buy": CommandPattern.OBJECT_MANIPULATION,
    "give": CommandPattern.TRANSFER,
    "offer": CommandPattern.TRANSFER,
    "put": CommandPattern.CONTAINER,
    "examine": CommandPattern.CONTAINER,
    "open": CommandPattern.CONTAINER,
    "close": CommandPattern.CONTAINER,
    "unlock": CommandPattern.TOOL_USE,
    "lock": CommandPattern.TOOL_USE,
    "use": CommandPattern.TOOL_USE,
    "attack": CommandPattern.COMBAT,
    "kill": CommandPattern.COMBAT,
    "say": CommandPattern.SPEECH,
    "whisper": CommandPattern.SPEECH,
    "shout": CommandPattern.SPEECH,
    "scream": CommandPattern.SPEECH,
    "yell": CommandPattern.SPEECH,
    "tell": CommandPattern.SPEECH,
    "wave": CommandPattern.SOCIAL_GESTURE,
    "bow": CommandPattern.SOCIAL_GESTURE,
    "smile": CommandPattern.SOCIAL_GESTURE,
    "nod": CommandPattern.SOCIAL_GESTURE,
    "talk": CommandPattern.NPC_DIALOGUE,
    "ask": CommandPattern.NPC_DIALOGUE,
    "choice": CommandPattern.NPC_DIALOGUE,
    "bye": CommandPattern.NPC_DIALOGUE,
}


@dataclass(frozen=True)
class SpeechRoles:
    message: str
    recipient: str | None = None
    recipient_id: str | None = None


@dataclass(frozen=True)
class TransferRoles:
    object_phrase: str
    recipient: str
    object_id: str | None = None
    recipient_id: str | None = None
    quantity: int | None = None


@dataclass(frozen=True)
class ContainerRoles:
    object_phrase: str | None
    container_phrase: str | None
    source_phrase: str | None = None
    object_id: str | None = None
    container_id: str | None = None
    source_id: str | None = None


@dataclass(frozen=True)
class GestureRoles:
    gesture: str
    target: str | None = None
    target_id: str | None = None


def pattern_for_verb(verb: str) -> CommandPattern:
    return VERB_PATTERNS.get(verb, CommandPattern.UNKNOWN)


def role_str(parsed: ParsedCommand, key: str) -> str | None:
    value = parsed.roles.get(key)
    if value is None:
        return None
    return str(value)


def role_int(parsed: ParsedCommand, key: str) -> int | None:
    value = parsed.roles.get(key)
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value.isdigit():
        return int(value)
    return None


def role_adjectives(parsed: ParsedCommand) -> list[str]:
    value = parsed.roles.get(ROLE_ADJECTIVES)
    if not isinstance(value, list):
        return []
    return [str(item) for item in value]


def resolved_id(parsed: ParsedCommand, key: str) -> str | None:
    return parsed.resolved_ids.get(key)


def object_phrase(parsed: ParsedCommand) -> str | None:
    """Full object phrase including quantity and adjectives when present."""
    phrase = role_str(parsed, ROLE_OBJECT)
    if phrase is None:
        return None
    parts: list[str] = []
    quantity = role_int(parsed, ROLE_QUANTITY)
    if quantity is not None:
        parts.append(str(quantity))
    parts.extend(role_adjectives(parsed))
    parts.append(phrase)
    return " ".join(parts)


def movement_direction(parsed: ParsedCommand) -> str | None:
    return role_str(parsed, ROLE_DIRECTION)


def speech_roles(parsed: ParsedCommand) -> SpeechRoles | None:
    message = role_str(parsed, ROLE_MESSAGE)
    if message is None:
        return None
    return SpeechRoles(
        message=message,
        recipient=role_str(parsed, ROLE_RECIPIENT),
        recipient_id=resolved_id(parsed, ROLE_RECIPIENT),
    )


def transfer_roles(parsed: ParsedCommand) -> TransferRoles | None:
    object_name = role_str(parsed, ROLE_OBJECT)
    recipient = role_str(parsed, ROLE_RECIPIENT)
    if object_name is None or recipient is None:
        return None
    return TransferRoles(
        object_phrase=object_name,
        recipient=recipient,
        object_id=resolved_id(parsed, ROLE_OBJECT),
        recipient_id=resolved_id(parsed, ROLE_RECIPIENT),
        quantity=role_int(parsed, ROLE_QUANTITY),
    )


def container_roles(parsed: ParsedCommand) -> ContainerRoles:
    return ContainerRoles(
        object_phrase=role_str(parsed, ROLE_OBJECT),
        container_phrase=role_str(parsed, ROLE_DESTINATION)
        or role_str(parsed, ROLE_TARGET),
        source_phrase=role_str(parsed, ROLE_SOURCE),
        object_id=resolved_id(parsed, ROLE_OBJECT),
        container_id=resolved_id(parsed, ROLE_DESTINATION)
        or resolved_id(parsed, ROLE_TARGET),
        source_id=resolved_id(parsed, ROLE_SOURCE),
    )


def gesture_roles(parsed: ParsedCommand) -> GestureRoles:
    return GestureRoles(
        gesture=parsed.verb,
        target=role_str(parsed, ROLE_TARGET) or role_str(parsed, ROLE_RECIPIENT),
        target_id=resolved_id(parsed, ROLE_TARGET)
        or resolved_id(parsed, ROLE_RECIPIENT),
    )


def required_roles_for_pattern(pattern: CommandPattern) -> tuple[str, ...]:
    """Role keys handlers should consult for each pattern (v1 guidance)."""
    return _REQUIRED_ROLES[pattern]


_REQUIRED_ROLES: dict[CommandPattern, tuple[str, ...]] = {
    CommandPattern.MOVEMENT: (ROLE_DIRECTION,),
    CommandPattern.BARE: (),
    CommandPattern.OBJECT_MANIPULATION: (ROLE_OBJECT, ROLE_QUANTITY),
    CommandPattern.CONTAINER: (
        ROLE_OBJECT,
        ROLE_DESTINATION,
        ROLE_SOURCE,
        ROLE_TARGET,
    ),
    CommandPattern.TRANSFER: (ROLE_OBJECT, ROLE_RECIPIENT),
    CommandPattern.TOOL_USE: (ROLE_TARGET, ROLE_OBJECT, ROLE_INSTRUMENT),
    CommandPattern.COMBAT: (ROLE_TARGET, ROLE_INSTRUMENT),
    CommandPattern.SPEECH: (ROLE_MESSAGE, ROLE_RECIPIENT),
    CommandPattern.SOCIAL_GESTURE: (ROLE_TARGET, ROLE_RECIPIENT),
    CommandPattern.NPC_DIALOGUE: (ROLE_RECIPIENT, ROLE_TOPIC),
    CommandPattern.META: (),
    CommandPattern.UNKNOWN: (),
}
