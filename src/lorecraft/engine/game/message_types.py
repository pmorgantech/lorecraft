"""Semantic message-type taxonomy for player-facing output (Sprint 56).

Tags each engine-emitted message with *why* it exists — not just its text —
so clients can filter, route, or style by type (mute combat spam, render
warnings distinctly, speak tells aloud on a screen reader) without further
engine work. Mirrors `ChatScope`'s "small, named taxonomy" discipline
(`channels.py`) and the `EventBus`'s small event-name vocabulary: reuse the
closest existing type rather than adding a one-off per feature.
"""

from __future__ import annotations

from enum import Enum


class MessageType(str, Enum):
    """Where a `GameContext.say()` message fits in the output taxonomy.

    Deliberately small (ten entries) — see the module docstring. `SYSTEM`
    is the default for `say()` calls that haven't been given a more specific
    type; it is not itself a signal to style distinctly (most of the engine's
    existing narration defaults here), whereas the others are meaningful
    routing/filtering hooks once call sites opt in.

    `HELP` tags the `help` command's documentation output (Sprint 71.4) — a
    distinct, cross-cutting *reference* category (not gameplay narration, a
    warning, or a per-feature hint), so the frontend can style command/topic
    listings with bold/color without any markup leaking into engine-adjacent
    text.

    `LEVEL` tags the "You reach level N!" line a reward grant emits when XP
    crosses a threshold (Sprint 73.9). A dedicated type — not reused `SYSTEM`
    or `QUEST`, since a level-up can come from a discovery too — so the
    frontend can style/celebrate it distinctly.
    """

    ROOM_EVENT = "room_event"
    CHAT = "chat"
    TELL = "tell"
    COMBAT = "combat"
    QUEST = "quest"
    WARNING = "warning"
    HINT = "hint"
    HELP = "help"
    LEVEL = "level"
    SYSTEM = "system"


class Message(str):
    """A `GameContext.say()` message tagged with its `MessageType`.

    Subclasses `str` on purpose: `ctx.messages` was `list[str]` before Sprint
    56, and a huge number of call sites (tests included) compare it, iterate
    it, or call `.startswith()`/`in` on its elements as plain strings. A str
    subclass keeps every one of those working unchanged — `Message("hi",
    MessageType.CHAT) == "hi"` is `True` — while adding `.type` for the new
    consumers (`frontend.py`'s feed rendering) that want to read it. JSON
    serialization (the `/ws` response) also degrades gracefully: a str
    subclass serializes as its plain string value, silently dropping `.type`,
    so the existing wire format is unaffected until a consumer opts in.
    """

    type: MessageType

    def __new__(cls, text: str, type: MessageType = MessageType.SYSTEM) -> Message:
        obj = super().__new__(cls, text)
        obj.type = type
        return obj
