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
//! *minimum* needed to route. A line is dispatched to Rust **only** when it is a
//! single bare migrated verb whose (normalized) verb is in the allow-list.
//! Everything else falls back to Python:
//!
//! - a multi-command line (`look;go north`) — the `;` separator is Python's,
//! - a line carrying arguments (`look at rock`, `go north`) — more than one token,
//! - a bare disambiguation number (`5`) — not a migrated verb,
//! - any verb not in the (env-populated) allow-list — including, this phase,
//!   movement, which is not yet a Rust-migrated verb.
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
/// [`MigratedVerb::Look`] (read-only) and [`MigratedVerb::Move`] (a bare cardinal
/// direction, carrying the parsed [`Direction`]).
///
/// **Movement is headless-only this phase.** A `Move` variant is only ever produced
/// when the allow-list explicitly contains the direction word; the default
/// allow-list is empty ([`crate::gateway::GatewayConfig`]) and no direction is added
/// to it, so no real client routes a move to Rust until the later live-cutover task
/// — only a test/harness that sets `LORECRAFT_RUST_VERBS` to include a direction
/// exercises the movement path.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum MigratedVerb {
    /// The read-only `look` verb (Phase 2 port, [`lorecraft_feature_look`]).
    Look,
    /// A movement in a bare cardinal direction (`north`, `n`, …), 4c port
    /// ([`lorecraft_feature_move`]). Carries the resolved [`Direction`]; a `go <dir>`
    /// line (two tokens) still falls back to Python via the argument rule.
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
    // Exactly one whitespace-delimited token and nothing more: a *bare* verb.
    // Zero tokens (blank) or any argument (a second token) falls back to Python.
    let mut tokens = trimmed.split_whitespace();
    let (Some(first), None) = (tokens.next(), tokens.next()) else {
        return RouteDecision::Python;
    };
    let verb = normalize_verb(first);
    match MigratedVerb::from_verb(&verb) {
        Some(migrated) if allow_list.contains(&verb) => RouteDecision::RustExecute(migrated),
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
    fn go_with_argument_falls_back_to_python() {
        // `go north` carries an argument (two tokens), so — like `look at rock` —
        // Python still owns parse/disambiguation this phase, regardless of the list.
        assert_eq!(
            decide("go north", &allow(&["look", "north", "go"])),
            RouteDecision::Python
        );
        // A bare `go` (no direction) is not a migrated verb: Python says "Go where?".
        assert_eq!(
            decide("go", &allow(&["go", "north"])),
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
