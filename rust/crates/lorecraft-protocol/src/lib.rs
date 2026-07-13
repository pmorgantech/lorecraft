//! Lorecraft protocol types — IDs, envelopes, versioning, and scripting boundaries.
//!
//! This crate defines the value-oriented contracts between engine, persistence, and
//! scripting layers. Types are versioned and serializable for replay, audit, and
//! cross-process communication.

#![warn(missing_docs)]

use serde::{Deserialize, Serialize};
use std::fmt;

/// Protocol version for this release.
pub const PROTOCOL_VERSION: u32 = 1;

/// A placeholder error type for protocol operations.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub enum ProtocolError {
    /// Serialization or deserialization error
    SerializationError(String),
    /// Version mismatch
    VersionMismatch { expected: u32, got: u32 },
    /// Invalid command envelope
    InvalidEnvelope(String),
}

impl fmt::Display for ProtocolError {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            ProtocolError::SerializationError(msg) => write!(f, "Serialization error: {}", msg),
            ProtocolError::VersionMismatch { expected, got } => {
                write!(f, "Version mismatch: expected {}, got {}", expected, got)
            }
            ProtocolError::InvalidEnvelope(msg) => write!(f, "Invalid envelope: {}", msg),
        }
    }
}

impl std::error::Error for ProtocolError {}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn protocol_version_is_stable() {
        assert_eq!(PROTOCOL_VERSION, 1);
    }
}
