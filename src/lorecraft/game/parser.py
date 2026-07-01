"""Text command parser with semantic roles and optional context resolution."""

from __future__ import annotations

import difflib
import shlex
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, cast

from lorecraft.types import JsonValue

if TYPE_CHECKING:
    from lorecraft.game.context import GameContext

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
    "pick": "take",
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
        "put",
        "wear",
        "remove",
        "drop",
        "buy",
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


@dataclass(frozen=True)
class ParsedCommand:
    verb: str
    raw: str
    roles: dict[str, JsonValue] = field(default_factory=dict)
    resolved_ids: dict[str, str] = field(default_factory=dict)
    parse_notes: str = ""

    @property
    def noun(self) -> str | None:
        """Primary object phrase for legacy command handlers."""
        if "direction" in self.roles:
            return str(self.roles["direction"])
        if "message" in self.roles:
            return str(self.roles["message"])
        if "choice_index" in self.roles:
            return str(self.roles["choice_index"])
        for role_key in ("object", "target", "recipient"):
            if role_key not in self.roles:
                continue
            phrase = str(self.roles[role_key])
            quantity = self.roles.get("quantity")
            if quantity is not None and str(quantity) == phrase:
                return phrase
            parts: list[str] = []
            if quantity is not None:
                parts.append(str(quantity))
            adjectives = self.roles.get("adjectives")
            if isinstance(adjectives, list):
                parts.extend(str(adj) for adj in adjectives)
            parts.append(phrase)
            return " ".join(parts)
        return None


@dataclass(frozen=True)
class ParseResult:
    commands: list[ParsedCommand] = field(default_factory=list)
    error_message: str | None = None
    suggestions: list[str] = field(default_factory=list)


@dataclass
class ParseStep:
    name: str
    details: dict[str, JsonValue] = field(default_factory=dict)


@dataclass
class ParseDiagnostics:
    raw: str
    normalized: str = ""
    tokens: list[str] = field(default_factory=list)
    steps: list[ParseStep] = field(default_factory=list)
    final_result: ParseResult | None = None
    error: str | None = None


def registry_verb(verb: str) -> str:
    return REGISTRY_VERB_ALIASES.get(verb, verb)


def _resolve_shortest_verb_prefix(token: str) -> str | None:
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


def _resolve_verb_token(verb_token: str) -> str:
    if verb_token in TOKEN_VERB_ALIASES:
        return TOKEN_VERB_ALIASES[verb_token]
    if verb_token in VERB_ALIASES:
        return VERB_ALIASES[verb_token]
    if verb_token in KNOWN_COMMAND_VERBS:
        return verb_token
    prefix_match = _resolve_shortest_verb_prefix(verb_token)
    if prefix_match is not None:
        return prefix_match
    return verb_token


def normalize(text: str) -> str:
    if not text:
        return ""
    return " ".join(text.strip().lower().split())


def tokenize(text: str) -> list[str]:
    text = text.strip()
    if not text:
        return []
    try:
        return shlex.split(text)
    except ValueError:
        return text.split()


def _make_phrase(token_list: list[str]) -> str | None:
    if not token_list:
        return None
    cleaned: list[str] = []
    for tok in token_list:
        for word in tok.split():
            if word.lower() not in ARTICLES:
                cleaned.append(word)
    return " ".join(cleaned) if cleaned else None


def _extract_quantity_and_adjectives(
    phrase: str | None,
) -> tuple[int | None, list[str], str | None]:
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


def _direct_role_for_verb(verb: str) -> str:
    if verb in OBJECT_VERBS:
        return "object"
    if verb in {"talk", "ask"}:
        return "recipient"
    return "target"


def _assign_direct_role(
    roles: dict[str, JsonValue],
    verb: str,
    *,
    direct_role: str | None,
    quantity: int | None,
    adjectives: list[str],
    noun: str | None,
    direct_phrase: str | None,
) -> None:
    role_key = direct_role or _direct_role_for_verb(verb)
    if quantity is not None:
        roles["quantity"] = quantity
    if adjectives:
        roles["adjectives"] = cast(JsonValue, adjectives)
    if noun:
        roles[role_key] = noun
    elif direct_phrase:
        roles[role_key] = direct_phrase


def _find_first_preposition(tokens: list[str]) -> tuple[int, str] | None:
    for index, token in enumerate(tokens):
        lowered = token.lower()
        if lowered in PREPOSITIONS:
            return index, lowered
    return None


def _map_prep_to_role(prep: str) -> str:
    return PREP_TO_ROLE.get(prep, "target")


def parse_command(
    raw: str,
    context: GameContext | None = None,
) -> ParseResult:
    if not raw or not raw.strip():
        return ParseResult(
            error_message="You mumble something incomprehensible to yourself."
        )

    if ";" in raw:
        parts = [part.strip() for part in raw.split(";") if part.strip()]
        commands: list[ParsedCommand] = []
        last_object: str | None = None
        for part in parts:
            if " it " in f" {part} " or part.strip() == "it":
                if last_object:
                    part = part.replace(" it ", f" {last_object} ").replace(
                        "it", last_object
                    )
            sub_result = parse_command(part, context=context)
            if sub_result.error_message:
                return sub_result
            if sub_result.commands:
                cmd = sub_result.commands[0]
                commands.append(cmd)
                if "object" in cmd.roles:
                    last_object = str(cmd.roles["object"])
                elif "target" in cmd.roles:
                    last_object = str(cmd.roles["target"])
        return ParseResult(commands=commands)

    tokens = tokenize(raw)
    if not tokens:
        return ParseResult(
            error_message="You mumble something incomprehensible to yourself."
        )

    verb_token = tokens[0].lower()
    if verb_token in DIRECTION_ALIASES:
        return ParseResult(
            commands=[
                ParsedCommand(
                    verb="move",
                    raw=raw,
                    roles={"direction": DIRECTION_ALIASES[verb_token]},
                )
            ]
        )
    if verb_token in DIRECTIONS:
        return ParseResult(
            commands=[
                ParsedCommand(verb="move", raw=raw, roles={"direction": verb_token})
            ]
        )

    verb = _resolve_verb_token(verb_token)
    phrasal_role_hint: str | None = None

    for length in (3, 2):
        if len(tokens) >= length:
            phrase = " ".join(token.lower() for token in tokens[:length])
            if phrase in PHRASAL_VERBS:
                verb = PHRASAL_VERBS[phrase]
                phrasal_role_hint = PHRASAL_ROLE_HINTS.get(phrase)
                tokens = [verb, *tokens[length:]]
                break

    if verb in DIRECTIONS:
        return ParseResult(
            commands=[ParsedCommand(verb="move", raw=raw, roles={"direction": verb})]
        )

    rest = tokens[1:]
    if verb in {"choice", "choose"} and len(rest) == 1 and rest[0].isdigit():
        return ParseResult(
            commands=[
                ParsedCommand(
                    verb=verb,
                    raw=raw,
                    roles={"choice_index": int(rest[0])},
                )
            ]
        )

    if verb in {"go", "move"} and len(rest) == 1:
        direction = rest[0].lower()
        if direction in DIRECTION_ALIASES:
            direction = DIRECTION_ALIASES[direction]
        if direction in DIRECTIONS:
            return ParseResult(
                commands=[
                    ParsedCommand(verb="move", raw=raw, roles={"direction": direction})
                ]
            )
    if verb == "look" and _find_first_preposition(rest) is not None:
        verb = "examine"

    prep_info = _find_first_preposition(rest)
    roles: dict[str, JsonValue] = {}

    if prep_info:
        index, prep = prep_info
        direct_tokens = rest[:index]
        indirect_tokens = rest[index + 1 :]
        direct_phrase = _make_phrase(direct_tokens)
        indirect_phrase = _make_phrase(indirect_tokens)

        quantity, adjectives, noun = _extract_quantity_and_adjectives(direct_phrase)
        _assign_direct_role(
            roles,
            verb,
            direct_role=phrasal_role_hint,
            quantity=quantity,
            adjectives=adjectives,
            noun=noun,
            direct_phrase=direct_phrase,
        )

        role_for_prep = _map_prep_to_role(prep)
        if indirect_phrase:
            roles[role_for_prep] = indirect_phrase
        roles.setdefault("preposition", prep)
    else:
        direct_phrase = _make_phrase(rest)
        quantity, adjectives, noun = _extract_quantity_and_adjectives(direct_phrase)
        _assign_direct_role(
            roles,
            verb,
            direct_role=phrasal_role_hint,
            quantity=quantity,
            adjectives=adjectives,
            noun=noun,
            direct_phrase=direct_phrase,
        )

    if (
        verb in {"say", "whisper", "shout", "yell", "scream", "tell"}
        and "object" in roles
    ):
        roles["message"] = roles.pop("object")

    syntactic_cmd = ParsedCommand(verb=verb, raw=raw, roles=roles)

    if context is not None:
        try:
            visible = context.get_visible_entities()
            inventory = context.get_inventory()
            candidates = list(visible) + list(inventory)
        except Exception:
            candidates = []

        def resolve_phrase(
            phrase: str | None,
        ) -> tuple[str | None, list[str], str]:
            if not phrase:
                return None, [], ""
            matches: list[tuple[float, str, str]] = []
            for item in candidates:
                if not isinstance(item, (list, tuple)) or len(item) < 2:
                    continue
                entity_id, name = item[0], item[1]
                aliases = item[2] if len(item) > 2 else []
                score = _score_match(phrase, name, aliases)
                if score > 0.5:
                    matches.append((score, entity_id, name))
            if not matches:
                return None, [], ""
            matches.sort(reverse=True)
            best_score, best_id, best_name = matches[0]
            if normalize(phrase) == normalize(best_name):
                return best_id, [], ""
            close = [match for match in matches[1:] if match[0] > best_score - 0.2]
            if close:
                unique_names = {match[2] for match in matches[:4]}
                if len(unique_names) == 1:
                    note = (
                        f"fuzzy matched '{phrase}' to '{best_name}'"
                        if best_score < 0.92
                        else ""
                    )
                    return best_id, [], note
                return (
                    None,
                    [match[2] for match in matches[:4]],
                    (f"Which '{phrase}' did you mean?"),
                )
            note = (
                f"fuzzy matched '{phrase}' to '{best_name}'"
                if best_score < 0.92
                else ""
            )
            return best_id, [], note

        resolved: dict[str, str] = {}
        notes: list[str] = []

        def phrase_for_role(role_key: str) -> str | None:
            phrase = roles.get(role_key)
            if phrase is None:
                return None
            adjectives = roles.get("adjectives")
            if isinstance(adjectives, list) and adjectives:
                return " ".join([*(str(adj) for adj in adjectives), str(phrase)])
            return str(phrase)

        for role_key in ("object", "target"):
            if role_key not in roles:
                continue
            phrase = phrase_for_role(role_key)
            if phrase and (
                "everything" in phrase.lower() or "except" in phrase.lower()
            ):
                continue
            resolved_id, suggestions, note = resolve_phrase(phrase)
            if suggestions:
                # take/drop object ambiguity → InventoryService numbered prompts
                if not (verb in {"take", "drop"} and role_key == "object"):
                    return ParseResult(error_message=note, suggestions=suggestions)
                resolved_id = None
            if resolved_id:
                resolved[role_key] = resolved_id
                if note:
                    notes.append(note)

        def resolve_phrase_soft(
            phrase: str | None,
        ) -> tuple[str | None, str]:
            if not phrase:
                return None, ""
            matches: list[tuple[float, str, str]] = []
            for item in candidates:
                if not isinstance(item, (list, tuple)) or len(item) < 2:
                    continue
                entity_id, name = item[0], item[1]
                aliases = item[2] if len(item) > 2 else []
                score = _score_match(phrase, name, aliases)
                if score > 0.5:
                    matches.append((score, entity_id, name))
            if not matches:
                return None, ""
            matches.sort(reverse=True)
            best_score, best_id, best_name = matches[0]
            note = (
                f"fuzzy matched '{phrase}' to '{best_name}'"
                if best_score < 0.92
                else ""
            )
            return best_id, note

        for role_key in ("instrument", "recipient", "source", "destination"):
            if role_key not in roles or role_key in resolved:
                continue
            phrase = roles[role_key]
            resolved_id, note = resolve_phrase_soft(
                str(phrase) if phrase is not None else None
            )
            if resolved_id:
                resolved[role_key] = resolved_id
                if note:
                    notes.append(note)

        if resolved or notes:
            syntactic_cmd = ParsedCommand(
                verb=verb,
                raw=raw,
                roles=roles,
                resolved_ids=resolved,
                parse_notes="; ".join(notes),
            )

    return ParseResult(commands=[syntactic_cmd])


def parse(raw: str) -> ParsedCommand:
    """Backward-compatible single-command parse without context resolution."""
    result = parse_command(raw)
    if result.error_message and not result.commands:
        return ParsedCommand(verb="", raw=raw)
    if not result.commands:
        return ParsedCommand(verb="", raw=raw)
    command = result.commands[0]
    return ParsedCommand(
        verb=registry_verb(command.verb),
        raw=command.raw,
        roles=command.roles,
        resolved_ids=command.resolved_ids,
        parse_notes=command.parse_notes,
    )


def _score_match(query: str, name: str, aliases: list[str] | None = None) -> float:
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
        (_score_match(normalized_query, alias) for alias in (aliases or [])),
        default=0.0,
    )
    return max(ratio * 0.8, best_alias)


def diagnose_command(
    raw: str,
    context: GameContext | None = None,
    *,
    verbose: bool = True,
) -> ParseDiagnostics:
    diag = ParseDiagnostics(raw=raw)
    diag.normalized = normalize(raw)
    diag.tokens = tokenize(diag.normalized)
    diag.steps.append(
        ParseStep(
            "normalize_tokenize",
            {
                "normalized": diag.normalized,
                "tokens": cast(JsonValue, diag.tokens),
            },
        )
    )

    result = parse_command(raw, context=context)
    diag.final_result = result

    if result.commands:
        diag.steps.append(
            ParseStep(
                "final_commands",
                {
                    "count": len(result.commands),
                    "verbs": cast(
                        JsonValue, [command.verb for command in result.commands]
                    ),
                    "roles": cast(
                        JsonValue, [command.roles for command in result.commands]
                    ),
                },
            )
        )
    else:
        diag.error = result.error_message
        diag.steps.append(
            ParseStep(
                "error",
                {
                    "message": result.error_message,
                    "suggestions": cast(JsonValue, result.suggestions),
                },
            )
        )

    if verbose:
        _print_diagnostics(diag)
    return diag


def _print_diagnostics(diag: ParseDiagnostics) -> None:
    print(f"\n{'=' * 60}")
    print("LORECRAFT PARSER DIAGNOSTICS")
    print(f"Raw input : {diag.raw!r}")
    print(f"Normalized: {diag.normalized}")
    print(f"Tokens    : {diag.tokens}")
    print("-" * 60)
    for step in diag.steps:
        print(f"\n[ {step.name} ]")
        for key, value in step.details.items():
            print(f"  {key}: {value}")
    if diag.final_result:
        print("\n--- FINAL RESULT ---")
        if diag.final_result.commands:
            for index, command in enumerate(diag.final_result.commands):
                print(f"Command {index + 1}: verb={command.verb}")
                print(f"  roles: {command.roles}")
                if command.resolved_ids:
                    print(f"  resolved: {command.resolved_ids}")
                if command.parse_notes:
                    print(f"  notes: {command.parse_notes}")
        if diag.final_result.error_message:
            print(f"Error (in-character): {diag.final_result.error_message}")
            if diag.final_result.suggestions:
                print(f"Suggestions: {diag.final_result.suggestions}")
    print("=" * 60 + "\n")
