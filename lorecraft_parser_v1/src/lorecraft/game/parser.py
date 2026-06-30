"""
Lorecraft Command Parser v1
Enhanced deterministic parser supporting:
- Prepositions and semantic roles (flexible dict)
- Quoted multi-word names
- Adjectives, quantities, multiple objects
- Phrasal verbs & synonyms
- Compound commands (split on ';')
- Context-aware fuzzy resolution & disambiguation (optional GameContext)
- Diagnostic tracing
- In-character error messages

No deep nested references in v1 (e.g. "coin from purse in chest" is not auto-unpacked).
Pronoun resolution and advanced implicits are basic / TODO for v2.

Role keys are flexible for now. Common keys used:
  object, objects, target, instrument, recipient, source, destination,
  direction, quantity, adjectives (list), message, topic, subobject
We can standardize the exact key vocabulary in a follow-up discussion.
"""

import shlex
import difflib
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional, Tuple

# =============================================================================
# Configuration - easily extended
# =============================================================================

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
    "get": "take",
    "grab": "take",
    "examine": "examine",
    "inspect": "examine",
    "x": "examine",
    "i": "inventory",
    "inv": "inventory",
    "l": "look",
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

VERB_ALIASES = {
    "n": "move",
    "north": "move",
    "south": "move",
    "east": "move",
    "west": "move",
    "up": "move",
    "down": "move",
}

QUANTITY_WORDS = {"all", "everything", "some"}

# =============================================================================
# Data classes
# =============================================================================


@dataclass(frozen=True)
class ParsedCommand:
    verb: str
    roles: Dict[str, Any] = field(default_factory=dict)
    raw: str
    resolved_ids: Dict[str, str] = field(default_factory=dict)
    parse_notes: str = ""


@dataclass(frozen=True)
class ParseResult:
    commands: List[ParsedCommand] = field(default_factory=list)
    error_message: Optional[str] = None  # Always in-character
    suggestions: List[str] = field(default_factory=list)


@dataclass
class ParseStep:
    name: str
    details: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ParseDiagnostics:
    raw: str
    normalized: str = ""
    tokens: List[str] = field(default_factory=list)
    steps: List[ParseStep] = field(default_factory=list)
    final_result: Optional[ParseResult] = None
    error: Optional[str] = None


# =============================================================================
# Core helpers
# =============================================================================


def normalize(text: str) -> str:
    if not text:
        return ""
    text = text.strip().lower()
    # Collapse whitespace but preserve content inside quotes for shlex later
    return " ".join(text.split())


def tokenize(text: str) -> List[str]:
    text = normalize(text)
    if not text:
        return []
    try:
        return shlex.split(text)
    except ValueError:
        # Unbalanced quotes - fallback
        return text.split()


def _strip_articles(words: List[str]) -> List[str]:
    return [w for w in words if w.lower() not in ARTICLES]


def _make_phrase(token_list: List[str]) -> Optional[str]:
    if not token_list:
        return None
    cleaned = []
    for tok in token_list:
        for w in tok.split():
            if w.lower() not in ARTICLES:
                cleaned.append(w)
    return " ".join(cleaned) if cleaned else None


def _extract_quantity_and_adjectives(
    phrase: Optional[str],
) -> Tuple[Optional[int], List[str], Optional[str]]:
    """Very lightweight quantity + adjective extraction for v1."""
    if not phrase:
        return None, [], None
    words = phrase.split()
    quantity = None
    adjectives = []
    noun_words = []
    i = 0
    # crude number at start
    if words and words[0].isdigit():
        quantity = int(words[0])
        i = 1
    for w in words[i:]:
        if w in QUANTITY_WORDS:
            # keep as part of object phrase for "all coins"
            noun_words.append(w)
            continue
        # very simple heuristic: first few words before last are adjectives
        noun_words.append(w)
    # For v1 we treat most leading words as adjectives if >1 word
    if len(noun_words) > 1:
        adjectives = noun_words[:-1]
        noun = noun_words[-1]
    else:
        noun = noun_words[0] if noun_words else None
        adjectives = []
    return quantity, adjectives, noun


def _find_first_preposition(tokens: List[str]) -> Optional[Tuple[int, str]]:
    for i, tok in enumerate(tokens):
        t = tok.lower()
        if t in PREPOSITIONS:
            return i, t
    return None


def _map_prep_to_role(prep: str) -> str:
    return PREP_TO_ROLE.get(prep, "target")


# =============================================================================
# Main parser
# =============================================================================


def parse_command(
    raw: str,
    context: Optional["GameContext"] = None,
) -> ParseResult:
    if not raw or not raw.strip():
        return ParseResult(
            error_message="You mumble something incomprehensible to yourself."
        )

    # Compound command support (semicolon)
    if ";" in raw:
        parts = [p.strip() for p in raw.split(";") if p.strip()]
        commands = []
        last_object = None  # very basic pronoun carry for v1
        for part in parts:
            # naive pronoun substitution for "it"
            if " it " in f" {part} " or part.strip() == "it":
                if last_object:
                    part = part.replace(" it ", f" {last_object} ").replace(
                        "it", last_object
                    )
            sub_result = parse_command(part, context=context)  # recursive for compounds
            if sub_result.error_message:
                return sub_result  # fail fast on first error
            if sub_result.commands:
                cmd = sub_result.commands[0]
                commands.append(cmd)
                # update last object for next pronoun
                if "object" in cmd.roles:
                    last_object = cmd.roles["object"]
                elif "target" in cmd.roles:
                    last_object = cmd.roles["target"]
        return ParseResult(commands=commands)

    tokens = tokenize(raw)
    if not tokens:
        return ParseResult(
            error_message="You mumble something incomprehensible to yourself."
        )

    # Verb handling
    verb_tok = tokens[0].lower()
    verb = VERB_ALIASES.get(verb_tok, verb_tok)

    # Phrasal verb rewrite (longest first)
    for length in (3, 2):
        if len(tokens) >= length:
            phrase = " ".join(tokens[:length]).lower()
            if phrase in PHRASAL_VERBS:
                verb = PHRASAL_VERBS[phrase]
                tokens = [verb] + tokens[length:]
                break

    # Direction shortcut
    if verb in {
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
    }:
        return ParseResult(
            commands=[ParsedCommand(verb="move", roles={"direction": verb}, raw=raw)]
        )

    rest = tokens[1:]
    prep_info = _find_first_preposition(rest)

    roles: Dict[str, Any] = {}

    if prep_info:
        idx, prep = prep_info
        direct_tokens = rest[:idx]
        indirect_tokens = rest[idx + 1 :]
        direct_phrase = _make_phrase(direct_tokens)
        indirect_phrase = _make_phrase(indirect_tokens)

        # quantity / adjectives on direct
        qty, adjs, noun = _extract_quantity_and_adjectives(direct_phrase)
        if qty is not None:
            roles["quantity"] = qty
        if adjs:
            roles["adjectives"] = adjs
        if noun:
            roles["object"] = noun
        elif direct_phrase:
            roles["object"] = direct_phrase

        role_for_prep = _map_prep_to_role(prep)
        if indirect_phrase:
            roles[role_for_prep] = indirect_phrase
        roles.setdefault("preposition", prep)  # keep raw prep if needed
    else:
        # no preposition - everything is direct object(s)
        direct_phrase = _make_phrase(rest)
        qty, adjs, noun = _extract_quantity_and_adjectives(direct_phrase)
        if qty is not None:
            roles["quantity"] = qty
        if adjs:
            roles["adjectives"] = adjs
        if noun:
            roles["object"] = noun
        elif direct_phrase:
            roles["object"] = direct_phrase

    # Special cases for message / say
    if verb in {"say", "whisper", "shout"} and "object" in roles:
        roles["message"] = roles.pop("object")

    syntactic_cmd = ParsedCommand(verb=verb, roles=roles, raw=raw)

    # Context resolution (optional, v1 basic version)
    if context is not None:
        # TODO(v2): full pronoun history, implicit object inference, deep nesting
        # For v1 we do simple fuzzy match on visible + inventory
        try:
            visible = getattr(context, "get_visible_entities", lambda: [])()
            inventory = getattr(context, "get_inventory", lambda: [])()
            candidates = visible + inventory
        except Exception:
            candidates = []

        def resolve_phrase(
            phrase: Optional[str], role_name: str
        ) -> Tuple[Optional[str], List[str], str]:
            if not phrase:
                return None, [], ""
            matches = []
            for item in candidates:
                # item expected as (id, name, aliases_list)
                if isinstance(item, (list, tuple)) and len(item) >= 2:
                    eid, name = item[0], item[1]
                    aliases = item[2] if len(item) > 2 else []
                else:
                    continue
                score = _score_match(phrase, name, aliases)
                if score > 0.5:
                    matches.append((score, eid, name))
            if not matches:
                suggestions = sorted(
                    [
                        name
                        for _, name, _ in [
                            (_score_match(phrase, n, a), n) for *_, n, a in candidates
                        ]
                    ],
                    key=lambda x: _score_match(phrase, x),
                    reverse=True,
                )[:3]
                return (
                    None,
                    suggestions,
                    f"You don't see any '{phrase}' here that makes sense.",
                )
            matches.sort(reverse=True)
            best_score, best_id, best_name = matches[0]
            close = [m for m in matches[1:] if m[0] > best_score - 0.2]
            if close:
                sugg = [m[2] for m in matches[:4]]
                return None, sugg, f"Which '{phrase}' did you mean?"
            note = (
                f"fuzzy matched '{phrase}' to '{best_name}'"
                if best_score < 0.92
                else ""
            )
            return best_id, [], note

        resolved = {}
        notes = []
        for role_key in [
            "object",
            "target",
            "instrument",
            "recipient",
            "source",
            "destination",
        ]:
            if role_key in roles:
                phrase = roles[role_key]
                rid, sugg, note = resolve_phrase(phrase, role_key)
                if sugg:
                    return ParseResult(error_message=note, suggestions=sugg)
                if rid:
                    resolved[role_key] = rid
                    if note:
                        notes.append(note)

        if resolved or notes:
            syntactic_cmd = ParsedCommand(
                verb=verb,
                roles=roles,
                raw=raw,
                resolved_ids=resolved,
                parse_notes="; ".join(notes),
            )

    return ParseResult(commands=[syntactic_cmd])


def _score_match(query: str, name: str, aliases: List[str] = None) -> float:
    q = normalize(query)
    n = normalize(name)
    if not q:
        return 0.0
    if q == n:
        return 1.0
    if q in n or n in q:
        return 0.9
    qw = set(q.split())
    nw = set(n.split())
    if qw and nw:
        overlap = len(qw & nw) / max(len(qw), len(nw))
        if overlap > 0.4:
            return 0.6 + 0.3 * overlap
    ratio = difflib.SequenceMatcher(None, q, n).ratio()
    best_alias = max((_score_match(q, a) for a in (aliases or [])), default=0.0)
    return max(ratio * 0.8, best_alias)


# =============================================================================
# Diagnostic mode
# =============================================================================


def diagnose_command(
    raw: str, context: Optional["GameContext"] = None, verbose: bool = True
) -> ParseDiagnostics:
    diag = ParseDiagnostics(raw=raw)
    diag.normalized = normalize(raw)
    diag.tokens = tokenize(diag.normalized)

    diag.steps.append(
        ParseStep(
            "normalize_tokenize", {"normalized": diag.normalized, "tokens": diag.tokens}
        )
    )

    # Run the real parser
    result = parse_command(raw, context=context)
    diag.final_result = result

    if result.commands:
        diag.steps.append(
            ParseStep(
                "final_commands",
                {
                    "count": len(result.commands),
                    "verbs": [c.verb for c in result.commands],
                    "roles": [c.roles for c in result.commands],
                },
            )
        )
    else:
        diag.error = result.error_message
        diag.steps.append(
            ParseStep(
                "error",
                {"message": result.error_message, "suggestions": result.suggestions},
            )
        )

    if verbose:
        _print_diagnostics(diag)
    return diag


def _print_diagnostics(diag: ParseDiagnostics):
    print(f"\n{'=' * 60}")
    print("LORECRAFT PARSER DIAGNOSTICS")
    print(f"Raw input : {diag.raw!r}")
    print(f"Normalized: {diag.normalized}")
    print(f"Tokens    : {diag.tokens}")
    print("-" * 60)
    for step in diag.steps:
        print(f"\n[ {step.name} ]")
        for k, v in step.details.items():
            print(f"  {k}: {v}")
    if diag.final_result:
        print("\n--- FINAL RESULT ---")
        if diag.final_result.commands:
            for i, cmd in enumerate(diag.final_result.commands):
                print(f"Command {i + 1}: verb={cmd.verb}")
                print(f"  roles: {cmd.roles}")
                if cmd.resolved_ids:
                    print(f"  resolved: {cmd.resolved_ids}")
                if cmd.parse_notes:
                    print(f"  notes: {cmd.parse_notes}")
        if diag.final_result.error_message:
            print(f"Error (in-character): {diag.final_result.error_message}")
            if diag.final_result.suggestions:
                print(f"Suggestions: {diag.final_result.suggestions}")
    print("=" * 60 + "\n")


# Placeholder for type checking - real GameContext lives in your project
class GameContext:
    """Minimal stub for standalone testing / diagnostics."""

    def get_visible_entities(self):
        return []

    def get_inventory(self):
        return []
