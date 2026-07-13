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

use serde::Serialize;
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
}
