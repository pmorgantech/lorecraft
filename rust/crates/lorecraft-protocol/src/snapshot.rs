//! Opaque entity snapshots handed to scripts and effect logic.

use serde::{Deserialize, Serialize};
use std::collections::BTreeMap;

/// An immutable, opaque view of a game entity for script/effect evaluation.
///
/// The mechanism layer knows only that an entity has an `id`, a `kind`, and a bag
/// of `attributes` — it deliberately does **not** type feature-specific fields
/// (e.g. a room's `exits` or a player's HP). Those are Tier 2 policy the feature
/// fills into `attributes`; adding a typed feature field here would leak policy
/// into the mechanism layer and is the signal to reject in review.
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct EntitySnapshot {
    /// Stable identifier of the entity within its world.
    pub id: String,
    /// Category of entity, e.g. `"room"`, `"player"`, `"item"`.
    pub kind: String,
    /// Opaque attribute map — arbitrary JSON values keyed by feature-defined names.
    pub attributes: BTreeMap<String, serde_json::Value>,
}
