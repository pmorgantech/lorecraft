//! Deterministic RNG stream derivation.
//!
//! A world has a single `world_seed`; each named stream (`stream_id`) draws from an
//! independent, reproducible [`ChaCha8Rng`] derived from `(world_seed, stream_id)`.
//! Deriving a stream is a pure function of its identity, so two derivations of the
//! same stream produce identical draw sequences, and per-stream state is isolated —
//! interleaving draws across streams never perturbs any one stream's own sequence.
//!
//! Cross-language RNG parity with Python's `random.Random` (Mersenne Twister) is
//! explicitly **not** a goal here (deferred to a later phase); this proves
//! Rust-internal determinism only.

use rand::SeedableRng;
use rand_chacha::ChaCha8Rng;
use sha2::{Digest, Sha256};

/// Derive an independent, reproducible RNG stream from a world seed and stream id.
///
/// The 32-byte ChaCha seed is `SHA-256(world_seed_le_bytes || stream_id_utf8)`, so
/// the seed — and therefore the entire draw sequence — is a deterministic function
/// of the stream's identity alone.
pub fn derive_stream(world_seed: u64, stream_id: &str) -> ChaCha8Rng {
    let mut hasher = Sha256::new();
    hasher.update(world_seed.to_le_bytes());
    // A length-prefix would be needed only to disambiguate multi-field identities;
    // with a fixed 8-byte seed prefix followed by the id, the boundary is
    // unambiguous and the id's own bytes cannot collide with the seed bytes.
    hasher.update(stream_id.as_bytes());
    let seed: [u8; 32] = hasher.finalize().into();
    ChaCha8Rng::from_seed(seed)
}

#[cfg(test)]
mod tests {
    use super::*;
    use rand::RngCore;

    fn draw_n(rng: &mut ChaCha8Rng, n: usize) -> Vec<u64> {
        (0..n).map(|_| rng.next_u64()).collect()
    }

    #[test]
    fn same_identity_produces_identical_sequences() {
        let mut a = derive_stream(1, "combat");
        let mut b = derive_stream(1, "combat");
        assert_eq!(draw_n(&mut a, 8), draw_n(&mut b, 8));
    }

    #[test]
    fn different_stream_id_produces_different_sequence() {
        let mut a = derive_stream(1, "combat");
        let mut b = derive_stream(1, "loot");
        assert_ne!(draw_n(&mut a, 8), draw_n(&mut b, 8));
    }

    #[test]
    fn different_world_seed_produces_different_sequence() {
        let mut a = derive_stream(1, "combat");
        let mut b = derive_stream(2, "combat");
        assert_ne!(draw_n(&mut a, 8), draw_n(&mut b, 8));
    }

    #[test]
    fn streams_are_order_independent_and_isolated() {
        // Derive A then B, draw A-then-B.
        let mut a1 = derive_stream(7, "alpha");
        let mut b1 = derive_stream(7, "beta");
        let a1_draws = draw_n(&mut a1, 5);
        let b1_draws = draw_n(&mut b1, 5);

        // Fresh derivation, draw B-then-A (reversed derive/draw order).
        let mut b2 = derive_stream(7, "beta");
        let mut a2 = derive_stream(7, "alpha");
        let b2_draws = draw_n(&mut b2, 5);
        let a2_draws = draw_n(&mut a2, 5);

        // Each stream's own draws are identical regardless of interleaving —
        // proving per-stream state isolation, not shared/global RNG interference.
        assert_eq!(a1_draws, a2_draws);
        assert_eq!(b1_draws, b2_draws);
    }
}
