"""Text command parser."""

from __future__ import annotations

from dataclasses import dataclass


DIRECTION_ALIASES = {
    "n": "north",
    "s": "south",
    "e": "east",
    "w": "west",
    "ne": "northeast",
    "nw": "northwest",
    "se": "southeast",
    "sw": "southwest",
    "u": "up",
    "d": "down",
}

VERB_ALIASES = {
    "get": "take",
    "pick": "take",
    "grab": "take",
    "l": "look",
    "i": "inventory",
    "inv": "inventory",
}

ARTICLES = {"a", "an", "the"}


@dataclass(frozen=True)
class ParsedCommand:
    verb: str
    noun: str | None
    raw: str


def parse(raw: str) -> ParsedCommand:
    normalized = " ".join(raw.strip().lower().split())
    if not normalized:
        return ParsedCommand(verb="", noun=None, raw=raw)

    parts = normalized.split(" ", 1)
    verb = parts[0]
    remainder = parts[1] if len(parts) == 2 else ""

    if verb in DIRECTION_ALIASES:
        return ParsedCommand(verb="go", noun=DIRECTION_ALIASES[verb], raw=raw)

    if verb in DIRECTION_ALIASES.values() and not remainder:
        return ParsedCommand(verb="go", noun=verb, raw=raw)

    verb = VERB_ALIASES.get(verb, verb)
    noun = _clean_noun(remainder)
    return ParsedCommand(verb=verb, noun=noun, raw=raw)


def _clean_noun(text: str) -> str | None:
    words = [word for word in text.split() if word not in ARTICLES]
    if not words:
        return None
    return " ".join(words)
