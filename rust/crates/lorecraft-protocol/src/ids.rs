//! Identifier newtypes for protocol entities.
//!
//! Each ID is a transparent wrapper over `String` so its JSON representation is a
//! bare string — the Python mirror uses plain `str` aliases for the same wire shape.

use serde::{Deserialize, Serialize};

/// Identifies a world (a self-contained game universe / shard).
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
#[serde(transparent)]
pub struct WorldId(pub String);

/// Identifies an actor (a player-controlled or NPC entity that issues commands).
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
#[serde(transparent)]
pub struct ActorId(pub String);

/// Identifies a player account.
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
#[serde(transparent)]
pub struct PlayerId(pub String);

/// Identifies a connection/session for a player.
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
#[serde(transparent)]
pub struct SessionId(pub String);

/// Identifies a single command submission (an idempotency key).
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
#[serde(transparent)]
pub struct CommandId(pub String);
