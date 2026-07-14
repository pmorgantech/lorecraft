//! `route.rs` — verb-level routing at gateway ingress (Phase 4, decision 3).
//!
//! Phase 4 makes Rust the authority for a *slice* of gameplay: a small allow-list
//! of migrated verbs executes through the Rust pipeline
//! ([`crate::execute`]) while every other command continues down the unchanged
//! Phase 3 forward-to-Python path. This module owns the **routing decision only**:
//! given a raw command line, decide whether Rust owns it this request.
//!
//! ## The decision (conservative by construction — decision 3)
//!
//! Full parsing and disambiguation stay in Python this phase; Rust parses only the
//! *minimum* needed to route. A line is dispatched to Rust when it is either
//!
//! - a single bare migrated verb (`look`, or a bare cardinal `north`/`n`) whose
//!   (normalized) verb is in the allow-list, **or**
//! - the explicit two-token movement form `go <direction>` (`go north`, `go n`)
//!   whose direction is a recognized cardinal in the allow-list (4c live cutover).
//!
//! Everything else falls back to Python:
//!
//! - a multi-command line (`look;go north`) — the `;` separator is Python's,
//! - a non-movement line carrying arguments (`look at rock`) — more than one token,
//! - `go <non-direction>` (`go home`) or `go` with extra tokens (`go north now`) —
//!   only a lone recognized direction is a migrated move,
//! - a bare disambiguation number (`5`) — not a migrated verb,
//! - any verb (or direction) not in the (env-populated) allow-list.
//!
//! ## Rollback is a routing toggle
//!
//! The allow-list defaults **empty** ([`crate::gateway::GatewayConfig::rust_verbs`]),
//! so with no configuration **every** command routes to Python — byte-identical to
//! the pure Phase 3 path. Enabling a verb is an operational config change
//! (`LORECRAFT_RUST_VERBS=look`); disabling it (empty list) is the rollback, exactly
//! as Phase 3 decision 8 established. The allow-list is an *operational* dial, not a
//! game-balance one, so it is static config — not the live-tunable `WorldClock`
//! pattern (decision 12 / the Phase 4 tunables note).

use std::collections::HashSet;

use lorecraft_feature_move::Direction;

/// A verb whose command pipeline Rust owns this phase.
///
/// A closed enum (no catch-all) so adding a migrated verb forces every dispatch
/// site ([`crate::execute`]) to handle it. As of 4c the variants are
/// [`MigratedVerb::Look`] (read-only) and [`MigratedVerb::Move`] (a cardinal
/// direction, carrying the parsed [`Direction`]).
///
/// **Movement is live as of the 4c cutover.** A `Move` variant is produced whenever
/// the allow-list contains the direction word; the library-level
/// [`GatewayConfig`](crate::gateway::GatewayConfig) default is still empty (safe
/// pure-Phase-3 default), but the deployed gateway binary's `DEFAULT_RUST_VERBS`
/// now opts the four cardinal moves in, so a real client's bare `north` (or
/// `go north`) is Rust-executed by default. Rollback stays the `LORECRAFT_RUST_VERBS=`
/// toggle.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum MigratedVerb {
    /// The read-only `look` verb (Phase 2 port, [`lorecraft_feature_look`]).
    Look,
    /// A movement in a cardinal direction (`north`, `n`, …), 4c port
    /// ([`lorecraft_feature_move`]). Carries the resolved [`Direction`]. Produced for
    /// both the bare-direction form (`north`) and the explicit `go <direction>` form
    /// (`go north`); both resolve to the same registered move Python-side, so routing
    /// either to Rust is byte-identical.
    Move(Direction),
}

impl MigratedVerb {
    /// The canonical verb string this variant routes for (the allow-list key). For
    /// [`MigratedVerb::Move`] this is the canonical direction word (`"north"`, …),
    /// which is what an operator lists in `LORECRAFT_RUST_VERBS` to enable it.
    pub fn verb(self) -> &'static str {
        match self {
            MigratedVerb::Look => "look",
            MigratedVerb::Move(direction) => direction.as_str(),
        }
    }

    /// Resolve a canonical (already normalized) verb to its migrated variant, or
    /// `None` if Rust does not own that verb this phase. A bare direction word maps
    /// to [`MigratedVerb::Move`]; a bare `go` (with no direction) is *not* migrated
    /// and falls back to Python (matching the Python service's `"Go where?"`).
    fn from_verb(verb: &str) -> Option<Self> {
        if verb == "look" {
            return Some(MigratedVerb::Look);
        }
        Direction::from_canonical(verb).map(MigratedVerb::Move)
    }
}

/// Where an incoming command line is dispatched this request.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum RouteDecision {
    /// Rust owns this command: run it through [`crate::execute`] with the resolved
    /// migrated verb.
    RustExecute(MigratedVerb),
    /// Python owns this command: forward it via the unchanged Phase 3 path.
    Python,
}

/// Normalize a single raw verb token: lowercase, then apply the direction-alias
/// table mirrored from Python's `DIRECTION_ALIASES`
/// (`engine/game/grammar.py`). For 4a `look` has no alias and normalizes to
/// itself; the table is here so movement aliases (`n` → `north`, …) slot in at 4c
/// with no structural change.
fn normalize_verb(token: &str) -> String {
    let lower = token.to_ascii_lowercase();
    // Mirror of DIRECTION_ALIASES — kept as an explicit match (no map allocation)
    // so it is trivially auditable against the Python source.
    let canonical = match lower.as_str() {
        "n" => "north",
        "s" => "south",
        "e" => "east",
        "w" => "west",
        "ne" => "northeast",
        "nw" => "northwest",
        "se" => "southeast",
        "sw" => "southwest",
        "u" => "up",
        "d" => "down",
        other => other,
    };
    canonical.to_owned()
}

/// Parse the comma-separated `LORECRAFT_RUST_VERBS` value into a normalized
/// allow-list. Blank entries are dropped; each surviving verb is normalized the
/// same way an incoming line's verb is (so `LORECRAFT_RUST_VERBS=n` and a typed
/// `n` agree at 4c). An empty/blank string yields the empty set — the rollback
/// default.
pub fn parse_allow_list(raw: &str) -> HashSet<String> {
    raw.split(',')
        .map(str::trim)
        .filter(|entry| !entry.is_empty())
        .map(normalize_verb)
        .collect()
}

/// Decide whether `raw` routes to Rust or Python, consulting the normalized
/// `allow_list` (see the module docs for the conservative fallback rules).
pub fn decide(raw: &str, allow_list: &HashSet<String>) -> RouteDecision {
    let trimmed = raw.trim();
    // Multi-command lines are Python's to split (the `;` grammar is not migrated).
    if trimmed.contains(';') {
        return RouteDecision::Python;
    }
    match trimmed.split_whitespace().collect::<Vec<_>>().as_slice() {
        // A single whitespace-delimited token: a *bare* migrated verb (`look`, or a
        // bare cardinal direction). Anything not in the allow-list falls to Python.
        [only] => resolve(&normalize_verb(only), allow_list),
        // The explicit two-token movement form `go <direction>` (4c cutover): only a
        // lone recognized direction is a migrated move. `go` alone, `go <non-dir>`,
        // and any extra token stay Python. The allow-list key is the direction word
        // (so opting in `north` enables both `north` and `go north`).
        [go, dir] if go.eq_ignore_ascii_case("go") => {
            match resolve(&normalize_verb(dir), allow_list) {
                // Guard the arm to a `Move` so `go look` (or any non-move verb) is not
                // mistaken for a migrated command — only directions ride the `go` form.
                RouteDecision::RustExecute(MigratedVerb::Move(direction)) => {
                    RouteDecision::RustExecute(MigratedVerb::Move(direction))
                }
                _ => RouteDecision::Python,
            }
        }
        // Zero tokens (blank), a non-movement argument line (`look at rock`), or any
        // other multi-token line is Python's to parse this phase.
        _ => RouteDecision::Python,
    }
}

/// Resolve an already-normalized `verb` against the `allow_list` to a route decision:
/// [`RouteDecision::RustExecute`] when Rust owns the verb *and* it is opted in, else
/// [`RouteDecision::Python`]. Shared by the bare-verb and `go <direction>` forms.
fn resolve(verb: &str, allow_list: &HashSet<String>) -> RouteDecision {
    match MigratedVerb::from_verb(verb) {
        Some(migrated) if allow_list.contains(verb) => RouteDecision::RustExecute(migrated),
        _ => RouteDecision::Python,
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn allow(verbs: &[&str]) -> HashSet<String> {
        verbs.iter().map(|v| (*v).to_owned()).collect()
    }

    #[test]
    fn look_routes_to_rust_when_allow_listed() {
        let decision = decide("look", &allow(&["look"]));
        assert_eq!(decision, RouteDecision::RustExecute(MigratedVerb::Look));
    }

    #[test]
    fn look_routes_to_python_when_not_allow_listed() {
        // Empty allow-list is the rollback default: every command goes to Python.
        assert_eq!(decide("look", &HashSet::new()), RouteDecision::Python);
        // A non-empty list that omits `look` also routes it to Python.
        assert_eq!(decide("look", &allow(&["north"])), RouteDecision::Python);
    }

    #[test]
    fn look_is_case_and_whitespace_insensitive() {
        assert_eq!(
            decide("  LOOK  ", &allow(&["look"])),
            RouteDecision::RustExecute(MigratedVerb::Look)
        );
    }

    #[test]
    fn look_with_arguments_falls_back_to_python() {
        // A noun argument means Python still owns parse/disambiguation this phase.
        assert_eq!(
            decide("look at rock", &allow(&["look"])),
            RouteDecision::Python
        );
    }

    #[test]
    fn multi_command_line_falls_back_to_python() {
        assert_eq!(decide("look;go", &allow(&["look"])), RouteDecision::Python);
        assert_eq!(
            decide("look; go north", &allow(&["look"])),
            RouteDecision::Python
        );
    }

    #[test]
    fn bare_disambiguation_number_falls_back_to_python() {
        assert_eq!(decide("5", &allow(&["look"])), RouteDecision::Python);
    }

    #[test]
    fn bare_direction_routes_to_rust_move_when_allow_listed() {
        // A bare cardinal direction is a single token and — with its canonical word
        // in the allow-list — routes to the Rust movement feature.
        assert_eq!(
            decide("north", &allow(&["north"])),
            RouteDecision::RustExecute(MigratedVerb::Move(Direction::North))
        );
        // Aliases normalize before both the typed token and the allow-list entry, so
        // a typed `n` matches an allow-listed `north`.
        assert_eq!(
            decide("n", &allow(&["north"])),
            RouteDecision::RustExecute(MigratedVerb::Move(Direction::North))
        );
    }

    #[test]
    fn movement_is_not_in_the_default_allow_list() {
        // Headless-only this phase: with the default (empty) allow-list, and even
        // with a `look`-only list, a bare direction routes to Python.
        assert_eq!(decide("north", &HashSet::new()), RouteDecision::Python);
        assert_eq!(decide("north", &allow(&["look"])), RouteDecision::Python);
        assert_eq!(decide("n", &allow(&["look"])), RouteDecision::Python);
    }

    #[test]
    fn go_direction_routes_to_rust_move_when_allow_listed() {
        // 4c cutover, decision (b): the explicit `go <direction>` form is migrated —
        // it resolves to the SAME move as the bare direction, so it routes to Rust
        // when the direction word is opted in. The allow-list key is the direction.
        assert_eq!(
            decide("go north", &allow(&["north"])),
            RouteDecision::RustExecute(MigratedVerb::Move(Direction::North))
        );
        // A direction alias in the second token normalizes before the allow-list
        // check, so `go n` matches an allow-listed `north` too.
        assert_eq!(
            decide("go n", &allow(&["north"])),
            RouteDecision::RustExecute(MigratedVerb::Move(Direction::North))
        );
        // Case-insensitive on the `go` keyword.
        assert_eq!(
            decide("GO north", &allow(&["north"])),
            RouteDecision::RustExecute(MigratedVerb::Move(Direction::North))
        );
    }

    #[test]
    fn go_direction_falls_back_to_python_when_not_allow_listed() {
        // The direction must be opted in — `go north` with an empty or `look`-only
        // list still routes to Python (rollback / not-yet-migrated).
        assert_eq!(decide("go north", &HashSet::new()), RouteDecision::Python);
        assert_eq!(decide("go north", &allow(&["look"])), RouteDecision::Python);
    }

    #[test]
    fn go_non_movement_and_extra_tokens_fall_back_to_python() {
        // Only a lone recognized direction rides the `go` form. A non-direction
        // argument, extra tokens, or a bare `go` all stay Python.
        assert_eq!(
            decide("go home", &allow(&["north", "look"])),
            RouteDecision::Python
        );
        assert_eq!(
            decide("go north now", &allow(&["north"])),
            RouteDecision::Python
        );
        // A bare `go` (no direction) is not a migrated verb: Python says "Go where?".
        assert_eq!(
            decide("go", &allow(&["go", "north"])),
            RouteDecision::Python
        );
        // `go look` must not be mistaken for the migrated `look` verb — the `go` form
        // is directions-only.
        assert_eq!(
            decide("go look", &allow(&["look", "north"])),
            RouteDecision::Python
        );
    }

    #[test]
    fn blank_line_falls_back_to_python() {
        assert_eq!(decide("   ", &allow(&["look"])), RouteDecision::Python);
        assert_eq!(decide("", &allow(&["look"])), RouteDecision::Python);
    }

    #[test]
    fn parse_allow_list_normalizes_trims_and_drops_blanks() {
        let set = parse_allow_list(" look , , n ");
        assert!(set.contains("look"));
        // `n` normalizes to its canonical direction so it agrees with a typed `n`.
        assert!(set.contains("north"));
        assert_eq!(set.len(), 2);
    }

    #[test]
    fn parse_allow_list_empty_is_the_rollback_default() {
        assert!(parse_allow_list("").is_empty());
        assert!(parse_allow_list("  ").is_empty());
    }

    #[test]
    fn migrated_verb_round_trips_its_verb_string() {
        assert_eq!(MigratedVerb::Look.verb(), "look");
        assert_eq!(MigratedVerb::from_verb("look"), Some(MigratedVerb::Look));
        // A bare direction is a migrated Move whose allow-list key is its word.
        assert_eq!(
            MigratedVerb::from_verb("north"),
            Some(MigratedVerb::Move(Direction::North))
        );
        assert_eq!(MigratedVerb::Move(Direction::North).verb(), "north");
        // `go` (bare, no direction) is not migrated.
        assert_eq!(MigratedVerb::from_verb("go"), None);
    }
}
