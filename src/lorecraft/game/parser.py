"""Text command parser with semantic roles and optional context resolution."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, cast

from lorecraft.game.diagnostics import (
    ParseDiagnostics,
    ParseStep,
    diagnose_command,
)
from lorecraft.game.grammar import (
    DEFERRED_DISAMBIGUATION_ROLE,
    DIRECTION_ALIASES,
    DIRECTIONS,
    PHRASAL_ROLE_HINTS,
    PHRASAL_VERBS,
    direct_role_for_verb,
    extract_quantity_and_adjectives,
    find_first_preposition,
    make_phrase,
    map_prep_to_role,
    normalize,
    registry_verb,
    resolve_verb_token,
    score_match,
    tokenize,
)
from lorecraft.types import JsonValue

if TYPE_CHECKING:
    from lorecraft.game.context import GameContext

log = logging.getLogger(__name__)

__all__ = [
    "ParsedCommand",
    "ParseResult",
    "ParseDiagnostics",
    "ParseStep",
    "parse_command",
    "parse",
    "diagnose_command",
    "normalize",
    "tokenize",
    "registry_verb",
]


@dataclass(frozen=True)
class ParsedCommand:
    """Parsed command with verb, roles, and optional resolved entity IDs."""

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
    """Result of parsing a command string."""

    commands: list[ParsedCommand] = field(default_factory=list)
    error_message: str | None = None
    suggestions: list[str] = field(default_factory=list)


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
    """Assign the direct semantic role based on verb and parsed components."""
    role_key = direct_role or direct_role_for_verb(verb)
    if quantity is not None:
        roles["quantity"] = quantity
    if adjectives:
        roles["adjectives"] = cast(JsonValue, adjectives)
    if noun:
        roles[role_key] = noun
    elif direct_phrase:
        roles[role_key] = direct_phrase


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

    verb = resolve_verb_token(verb_token)
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
    if verb == "look" and find_first_preposition(rest) is not None:
        verb = "examine"

    prep_info = find_first_preposition(rest)
    roles: dict[str, JsonValue] = {}

    if prep_info:
        index, prep = prep_info
        direct_tokens = rest[:index]
        indirect_tokens = rest[index + 1 :]
        direct_phrase = make_phrase(direct_tokens)
        indirect_phrase = make_phrase(indirect_tokens)

        quantity, adjectives, noun = extract_quantity_and_adjectives(direct_phrase)
        _assign_direct_role(
            roles,
            verb,
            direct_role=phrasal_role_hint,
            quantity=quantity,
            adjectives=adjectives,
            noun=noun,
            direct_phrase=direct_phrase,
        )

        role_for_prep = map_prep_to_role(prep)
        if indirect_phrase:
            roles[role_for_prep] = indirect_phrase
        roles.setdefault("preposition", prep)
    else:
        direct_phrase = make_phrase(rest)
        quantity, adjectives, noun = extract_quantity_and_adjectives(direct_phrase)
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
        except Exception as e:
            log.debug("get_suggestions_context_access_failed: %s", str(e))
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
                score_val = score_match(phrase, name, aliases)
                if score_val > 0.5:
                    matches.append((score_val, entity_id, name))
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
                if DEFERRED_DISAMBIGUATION_ROLE.get(verb) != role_key:
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
                score_val = score_match(phrase, name, aliases)
                if score_val > 0.5:
                    matches.append((score_val, entity_id, name))
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
