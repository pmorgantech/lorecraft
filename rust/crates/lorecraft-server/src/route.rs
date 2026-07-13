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

/// A verb whose command pipeline Rust owns this phase.
///
/// A closed enum (no catch-all) so adding a migrated verb — movement lands at
/// 4c — forces every dispatch site ([`crate::execute`]) to handle it. For 4a the
/// only variant is [`MigratedVerb::Look`].
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum MigratedVerb {
    /// The read-only `look` verb (Phase 2 port, [`lorecraft_feature_look`]).
    Look,
}

impl MigratedVerb {
    /// The canonical verb string this variant routes for (the allow-list key).
    pub fn verb(self) -> &'static str {
        match self {
            MigratedVerb::Look => "look",
        }
    }

    /// Resolve a canonical (already normalized) verb to its migrated variant, or
    /// `None` if Rust does not own that verb this phase.
    fn from_verb(verb: &str) -> Option<Self> {
        match verb {
            "look" => Some(MigratedVerb::Look),
            _ => None,
        }
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
    fn go_north_is_not_migrated_in_4a_and_falls_back_to_python() {
        // Movement is not a migrated verb this phase; `go north` also carries an
        // argument. Even if the allow-list were mis-set to include `go`, `go north`
        // has two tokens and `go` is not a migrated verb, so it stays Python.
        assert_eq!(
            decide("go north", &allow(&["look", "go"])),
            RouteDecision::Python
        );
        // A bare movement alias is a single token, but movement is not migrated in
        // 4a, so it still routes to Python.
        assert_eq!(decide("north", &allow(&["look"])), RouteDecision::Python);
        assert_eq!(decide("n", &allow(&["look"])), RouteDecision::Python);
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
        assert_eq!(MigratedVerb::from_verb("go"), None);
    }
}
