//! Lorecraft core — entities, effects, rules, validation, and transaction model.

#![warn(missing_docs)]

pub use lorecraft_protocol;

pub mod rng;

pub use rng::derive_stream;

/// A placeholder for core game entities and logic.
pub struct Entity {
    /// Entity identifier
    pub id: String,
}

impl Entity {
    /// Create a new entity.
    pub fn new(id: String) -> Self {
        Self { id }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn entity_creation() {
        let entity = Entity::new("player_1".to_string());
        assert_eq!(entity.id, "player_1");
    }
}
