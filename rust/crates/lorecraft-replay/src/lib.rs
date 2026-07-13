//! lorecraft-replay — canonical JSON serialization + SHA-256 hashing for replay
//! determinism.
//!
//! This is the Rust port of `src/lorecraft/tools/replay_hash.py`'s
//! `canonical_json`/`hash_events` algorithm. The two must agree byte-for-byte so a
//! Python golden hash can be reproduced by the Rust runtime in shadow mode.
//!
//! Canonicalization rules (identical to the Python side):
//! - **Sorted object keys.** We serialize to a [`serde_json::Value`] *first* — its
//!   `Map` is `BTreeMap`-backed (no `preserve_order` feature), so keys sort
//!   automatically. Serializing a `#[derive(Serialize)]` struct directly would
//!   preserve field-declaration order and silently diverge from Python's
//!   `sort_keys=True`.
//! - **No insignificant whitespace.** `serde_json::to_string` on a `Value` is
//!   compact by default (`separators=(",", ":")` in Python terms).
//! - **UTF-8, non-ASCII passed through.** `serde_json` does not `\uXXXX`-escape
//!   non-ASCII, matching Python's `ensure_ascii=False`.
//! - **Floats rejected.** Mirrors Python's `_reject_floats`, which raises on any
//!   `float` (allowing `bool`/`int`), pre-empting cross-language float-formatting
//!   divergence at the boundary.

#![warn(missing_docs)]

use std::fmt::Write;

use serde::{Deserialize, Serialize};
use sha2::{Digest, Sha256};

/// Errors produced while canonicalizing or hashing a value.
#[derive(Debug, thiserror::Error)]
pub enum ReplayError {
    /// A float appeared in the value tree. Canonical JSON rejects floats to
    /// guarantee cross-language byte parity; pre-quantize to int or str first.
    #[error(
        "canonical_json rejects floats to guarantee cross-language byte parity; \
         got {0}. Pre-quantise to int or str before hashing."
    )]
    FloatNotAllowed(f64),

    /// The value could not be serialized to JSON.
    #[error("failed to serialize value to JSON: {0}")]
    Serialization(#[from] serde_json::Error),
}

/// Serialize `value` to canonical UTF-8 JSON (sorted keys, no whitespace, floats
/// rejected).
///
/// Deterministic and stable: the two-step `Serialize -> Value -> String` shape is
/// what fixes key order (via the `BTreeMap`-backed `Value::Object`) to match
/// Python's `sort_keys=True`.
pub fn canonical_json(value: &impl Serialize) -> Result<String, ReplayError> {
    let json = serde_json::to_value(value)?;
    reject_floats(&json)?;
    // `to_string` on a `Value` is already compact; the `BTreeMap`-backed object
    // map means keys emit in sorted order.
    Ok(serde_json::to_string(&json)?)
}

/// Recursively assert no float appears in `value` (bools/ints are fine).
///
/// Mirrors Python's `_reject_floats`: JSON booleans are [`serde_json::Value::Bool`]
/// and integers are non-`f64` numbers, so only genuine floats (`is_f64()`) are
/// rejected — the values that risk cross-language formatting divergence.
fn reject_floats(value: &serde_json::Value) -> Result<(), ReplayError> {
    match value {
        serde_json::Value::Number(n) if n.is_f64() => {
            Err(ReplayError::FloatNotAllowed(n.as_f64().unwrap_or(f64::NAN)))
        }
        serde_json::Value::Array(items) => {
            for item in items {
                reject_floats(item)?;
            }
            Ok(())
        }
        serde_json::Value::Object(map) => {
            for nested in map.values() {
                reject_floats(nested)?;
            }
            Ok(())
        }
        _ => Ok(()),
    }
}

/// Return the lowercase hex SHA-256 digest of raw bytes.
pub fn hash_bytes(bytes: &[u8]) -> String {
    let digest = Sha256::digest(bytes);
    let mut out = String::with_capacity(digest.len() * 2);
    for byte in digest {
        // Infallible for a String sink; format two hex nibbles per byte.
        let _ = write!(out, "{byte:02x}");
    }
    out
}

/// Canonicalize `value` and return the SHA-256 hex digest of its canonical JSON
/// bytes — the composed "canonicalize, then hash" shape used for parity checks.
pub fn hash_canonical(value: &impl Serialize) -> Result<String, ReplayError> {
    let canonical = canonical_json(value)?;
    Ok(hash_bytes(canonical.as_bytes()))
}

/// The canonical post-command player-state snapshot hashed for movement (and
/// future mutating-verb) parity — the Phase-0-deferred `hash_state` shape
/// (migration plan Decision 4).
///
/// It captures exactly the parity-relevant player mutations a movement command
/// makes: the room the player ends in (`current_room_id`) and the accumulated
/// `visited_rooms` list. Both languages produce an identical value, so
/// [`hash_state`] over it is a single cross-language digest to compare (the same
/// discipline as the `look_only` `ScriptResult` hash, extended to a mutating verb).
///
/// **Ordering is load-bearing.** `visited_rooms` preserves the Python engine's
/// insertion order (`ctx.player.visited_rooms = [*visited, target]`): canonical
/// JSON sorts object *keys* but never reorders arrays, so the two sides must build
/// this list in the same order for the hashes to agree. It is deliberately **not**
/// sorted here.
///
/// The field set is intentionally minimal — more parity-relevant fields can be
/// added as later mutating verbs migrate; every addition is a wire/hash change and
/// must land in both languages together.
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct PlayerStateSnapshot {
    /// The room the player is in after the command committed.
    pub current_room_id: String,
    /// The player's visited-rooms list, in insertion order (never re-sorted).
    pub visited_rooms: Vec<String>,
}

/// Hash a post-command [`PlayerStateSnapshot`] to a SHA-256 hex digest over its
/// canonical JSON — the Rust mirror of `replay_hash.hash_state` (Python).
///
/// Reuses [`canonical_json`] + [`hash_bytes`] so it shares the exact
/// canonicalization discipline (sorted keys, compact, floats rejected) as the
/// event-trail hash, guaranteeing byte-for-byte cross-language agreement.
pub fn hash_state(snapshot: &PlayerStateSnapshot) -> Result<String, ReplayError> {
    hash_canonical(snapshot)
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde::Serialize;
    use serde_json::json;

    #[derive(Serialize)]
    struct Sample {
        // Deliberately declared out of alphabetical order to prove key-sorting.
        zeta: u32,
        alpha: String,
        nested: Nested,
    }

    #[derive(Serialize)]
    struct Nested {
        b: bool,
        a: i64,
    }

    #[test]
    fn canonical_json_sorts_keys_and_strips_whitespace() {
        let sample = Sample {
            zeta: 1,
            alpha: "x".into(),
            nested: Nested { b: true, a: -3 },
        };
        // Keys sorted at every level; no whitespace.
        assert_eq!(
            canonical_json(&sample).unwrap(),
            r#"{"alpha":"x","nested":{"a":-3,"b":true},"zeta":1}"#
        );
    }

    #[test]
    fn known_struct_hashes_to_fixed_hex() {
        // Oracle (canonical form {"alpha":"x","nested":{"a":-3,"b":true},"zeta":1}):
        //   python3 -c "import hashlib;print(hashlib.sha256(
        //     b'{\"alpha\":\"x\",\"nested\":{\"a\":-3,\"b\":true},\"zeta\":1}'
        //   ).hexdigest())"
        let sample = Sample {
            zeta: 1,
            alpha: "x".into(),
            nested: Nested { b: true, a: -3 },
        };
        assert_eq!(
            hash_canonical(&sample).unwrap(),
            "57b38b6426c0abd0ecf4c4ff506d3eeb90fc7d3595fea6cabc56b759a93f71e6"
        );
    }

    #[test]
    fn hash_bytes_matches_known_sha256() {
        // sha256("") = e3b0c442... (the standard empty-string digest vector).
        assert_eq!(
            hash_bytes(b""),
            "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
        );
    }

    #[test]
    fn float_containing_value_is_rejected() {
        let value = json!({"ok": 1, "bad": 0.5});
        let err = canonical_json(&value).unwrap_err();
        assert!(matches!(err, ReplayError::FloatNotAllowed(_)));
    }

    #[test]
    fn integer_valued_float_is_still_rejected() {
        // `2.0` is still an f64 in the serde_json::Value tree — `is_f64()` is
        // true regardless of its actual value — so it must be rejected exactly
        // like a fractional float. Mirrors the Python side's equivalent test
        // (`test_canonical_json_rejects_integer_valued_float`), pinning the
        // edge case against a future "optimize by value" regression that would
        // let whole-number floats like `2.0` slip through.
        let value = json!({"a": [1, 2.0]});
        assert!(matches!(
            canonical_json(&value).unwrap_err(),
            ReplayError::FloatNotAllowed(_)
        ));
    }

    #[test]
    fn nested_float_in_array_is_rejected() {
        let value = json!({"list": [1, 2, [3, 4.25]]});
        assert!(matches!(
            canonical_json(&value).unwrap_err(),
            ReplayError::FloatNotAllowed(_)
        ));
    }

    #[test]
    fn bools_and_ints_are_allowed() {
        let value = json!({"b": true, "i": -42, "big": 9_000_000_000_i64});
        assert!(canonical_json(&value).is_ok());
    }

    #[test]
    fn non_ascii_passes_through_as_utf8() {
        let value = json!({"name": "café"});
        // Not \u-escaped, matching Python ensure_ascii=False.
        assert_eq!(canonical_json(&value).unwrap(), r#"{"name":"café"}"#);
    }

    #[test]
    fn player_state_snapshot_canonical_form_is_stable() {
        let snap = PlayerStateSnapshot {
            current_room_id: "village_square".into(),
            visited_rooms: vec!["village_square".into(), "north_road".into()],
        };
        // Object keys sorted; the visited_rooms array order is preserved verbatim.
        assert_eq!(
            canonical_json(&snap).unwrap(),
            r#"{"current_room_id":"village_square","visited_rooms":["village_square","north_road"]}"#
        );
    }

    /// THE CROSS-LANGUAGE hash_state ORACLE: this fixed snapshot must hash to the
    /// same SHA-256 in Rust and Python (`tests/unit/test_replay_hash.py`'s
    /// `test_hash_state_matches_cross_language_oracle`). The constant was captured
    /// from the Python side; if either canonicalizer drifts, one of the two tests
    /// fails. This is the movement analogue of the `look_only` result-hash parity.
    #[test]
    fn hash_state_matches_cross_language_oracle() {
        let snap = PlayerStateSnapshot {
            current_room_id: "village_square".into(),
            visited_rooms: vec!["village_square".into(), "north_road".into()],
        };
        assert_eq!(
            hash_state(&snap).unwrap(),
            "66e04b31205d6a2e01c7058ddcb5421f6c1e24fec1479c59ba19ecb5f586c904"
        );
    }

    #[test]
    fn hash_state_is_order_sensitive_in_visited_rooms() {
        // visited_rooms order changes the digest (arrays are never re-sorted).
        let forward = PlayerStateSnapshot {
            current_room_id: "r".into(),
            visited_rooms: vec!["a".into(), "b".into()],
        };
        let reversed = PlayerStateSnapshot {
            current_room_id: "r".into(),
            visited_rooms: vec!["b".into(), "a".into()],
        };
        assert_ne!(
            hash_state(&forward).unwrap(),
            hash_state(&reversed).unwrap()
        );
    }
}
