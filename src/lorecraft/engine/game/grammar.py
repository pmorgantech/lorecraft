"""Parser grammar rules, articles, prepositions, and text normalization."""

from __future__ import annotations

import difflib
import shlex

ARTICLES = {"a", "an", "the", "some", "one"}

PREPOSITIONS = {
    "on",
    "in",
    "into",
    "to",
    "at",
    "with",
    "from",
    "onto",
    "upon",
    "under",
    "behind",
    "inside",
    "out",
    "off",
    "about",
}
PREP_TO_ROLE = {
    "on": "destination",
    "in": "destination",
    "into": "destination",
    "to": "recipient",
    "at": "target",
    "with": "instrument",
    "from": "source",
    "about": "topic",
}

# Verbs with no recipient/destination concept whose entire argument is a
# single opaque message — never split on a preposition inside it. Unlike
# whisper/tell (which legitimately split on "to <recipient>"), report has
# nothing to split against, so "report the keys stay in the room pane" must
# not fragment on "in" the way an object/destination phrase legitimately
# would ("put the keys in the chest"). See parse_command's prep_info check.
FREE_TEXT_VERBS = frozenset(
    {
        "emote",
        "newbie",
        "pose",
        "reply",
        "report",
        "/report",
        "say",
        "shout",
        "tell",
        "whisper",
        "yell",
    }
)

PHRASAL_VERBS = {
    "pick up": "take",
    "look at": "examine",
    "look in": "examine",
    "go to": "move",
}

TOKEN_VERB_ALIASES = {
    "l": "look",
    "i": "inventory",
    "inv": "inventory",
    "x": "examine",
    "examine": "examine",
    "inspect": "examine",
}

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

DIRECTIONS = frozenset(
    {
        "north",
        "south",
        "east",
        "west",
        "up",
        "down",
        "northeast",
        "northwest",
        "southeast",
        "southwest",
        *DIRECTION_ALIASES.values(),
    }
)

# The direction an arriving player is said to have come FROM — i.e. the
# reverse of the exit direction they took. Used for arrival narration
# ("X arrives from the {opposite}.") in the destination room.
OPPOSITE_DIRECTIONS = {
    "north": "south",
    "south": "north",
    "east": "west",
    "west": "east",
    "up": "below",
    "down": "above",
    "northeast": "southwest",
    "northwest": "southeast",
    "southeast": "northwest",
    "southwest": "northeast",
}

VERB_ALIASES = {
    "n": "move",
    "north": "move",
    "south": "move",
    "east": "move",
    "west": "move",
    "up": "move",
    "down": "move",
    "get": "take",
    "grab": "take",
    # NB: bare "pick" is NOT a `take` alias — Sprint 74.6 gives `pick` to the
    # lockpicking verb (`pick <direction>`). "pick up <item>" still means take,
    # via PHRASAL_VERBS above; `take`/`get`/`grab` remain the take synonyms.
}

REGISTRY_VERB_ALIASES = {"move": "go"}

KNOWN_COMMAND_VERBS = frozenset(
    {
        "look",
        "take",
        "drop",
        "examine",
        "inspect",
        "inventory",
        "go",
        "help",
        "quit",
        "save",
        "load",
        "talk",
        "speak",
        "choice",
        "choose",
        "say",
        "bye",
        "farewell",
        "goodbye",
        "north",
        "south",
        "east",
        "west",
        *TOKEN_VERB_ALIASES.values(),
        *VERB_ALIASES.values(),
        *PHRASAL_VERBS.values(),
    }
)

QUANTITY_WORDS = {"all", "everything", "some"}

MODIFIER_WORDS = frozenset(
    {
        "red",
        "blue",
        "green",
        "black",
        "white",
        "small",
        "large",
        "big",
        "old",
        "new",
        "worn",
        "healing",
        "brass",
        "iron",
        "sharp",
        "rusty",
        "broken",
        "golden",
        "silver",
        "wooden",
    }
)

OBJECT_VERBS = frozenset(
    {
        "take",
        "give",
        "offer",
        "put",
        "wear",
        "remove",
        "drop",
        "buy",
        "sell",
        "use",
        "say",
        "whisper",
        "shout",
        "yell",
        "scream",
    }
)

PHRASAL_ROLE_HINTS = {
    "look at": "target",
    "look in": "destination",
}

DEFERRED_DISAMBIGUATION_ROLE = {
    "take": "object",
    "drop": "object",
    "examine": "target",
    "use": "object",
    "give": "object",
}


def normalize(text: str) -> str:
    """Normalize text to lowercase with normalized whitespace."""
    if not text:
        return ""
    return " ".join(text.strip().lower().split())


def tokenize(text: str) -> list[str]:
    """Tokenize text, handling quoted strings."""
    text = text.strip()
    if not text:
        return []
    try:
        return shlex.split(text)
    except ValueError:
        return text.split()


def make_phrase(token_list: list[str]) -> str | None:
    """Join tokens into a phrase, stripping articles."""
    if not token_list:
        return None
    cleaned: list[str] = []
    for tok in token_list:
        for word in tok.split():
            if word.lower() not in ARTICLES:
                cleaned.append(word)
    return " ".join(cleaned) if cleaned else None


def extract_quantity_and_adjectives(
    phrase: str | None,
) -> tuple[int | None, list[str], str | None]:
    """Extract quantity prefix and adjectives from a phrase."""
    if not phrase:
        return None, [], None
    words = phrase.split()
    quantity: int | None = None
    start = 0
    if words and words[0].isdigit():
        quantity = int(words[0])
        start = 1
    remaining = words[start:]
    if not remaining:
        return quantity, [], None
    if quantity is not None:
        return quantity, [], " ".join(remaining)
    if remaining[0] in QUANTITY_WORDS:
        return quantity, [], " ".join(remaining)
    if len(remaining) > 1 and all(
        word.lower() in MODIFIER_WORDS for word in remaining[:-1]
    ):
        return quantity, remaining[:-1], remaining[-1]
    return quantity, [], " ".join(remaining)


def direct_role_for_verb(verb: str) -> str:
    """Determine the direct semantic role for a verb."""
    if verb in OBJECT_VERBS:
        return "object"
    if verb in {"talk", "ask"}:
        return "recipient"
    return "target"


def find_first_preposition(tokens: list[str]) -> tuple[int, str] | None:
    """Find the first preposition in a token list."""
    for index, token in enumerate(tokens):
        lowered = token.lower()
        if lowered in PREPOSITIONS:
            return index, lowered
    return None


def map_prep_to_role(prep: str) -> str:
    """Map preposition to semantic role."""
    return PREP_TO_ROLE.get(prep, "target")


def registry_verb(verb: str) -> str:
    """Map verb to registry name (e.g., 'move' → 'go')."""
    return REGISTRY_VERB_ALIASES.get(verb, verb)


def resolve_shortest_verb_prefix(token: str) -> str | None:
    """Resolve a partial verb to the shortest unique registered command match."""
    matches = sorted(
        {verb for verb in KNOWN_COMMAND_VERBS if verb.startswith(token)},
        key=len,
    )
    if not matches or matches[0] == token:
        return None
    shortest_len = len(matches[0])
    shortest = [verb for verb in matches if len(verb) == shortest_len]
    if len(shortest) == 1:
        return shortest[0]
    return None


def resolve_verb_token(verb_token: str) -> str:
    """Resolve a verb token to a canonical verb name."""
    if verb_token in TOKEN_VERB_ALIASES:
        return TOKEN_VERB_ALIASES[verb_token]
    if verb_token in VERB_ALIASES:
        return VERB_ALIASES[verb_token]
    if verb_token in KNOWN_COMMAND_VERBS:
        return verb_token
    prefix_match = resolve_shortest_verb_prefix(verb_token)
    if prefix_match is not None:
        return prefix_match
    return verb_token


def score_match(query: str, name: str, aliases: list[str] | None = None) -> float:
    """Score how well a query matches a name or its aliases (0.0 to 1.0)."""
    normalized_query = normalize(query)
    normalized_name = normalize(name)
    if not normalized_query:
        return 0.0
    if normalized_query == normalized_name:
        return 1.0
    if normalized_query in normalized_name or normalized_name in normalized_query:
        return 0.9
    query_words = set(normalized_query.split())
    name_words = set(normalized_name.split())
    if query_words and name_words:
        overlap = len(query_words & name_words) / max(len(query_words), len(name_words))
        if overlap > 0.4:
            return 0.6 + 0.3 * overlap
    ratio = difflib.SequenceMatcher(None, normalized_query, normalized_name).ratio()
    best_alias = max(
        (score_match(normalized_query, alias) for alias in (aliases or [])),
        default=0.0,
    )
    return max(ratio * 0.8, best_alias)
