"""Protocol version constant — mirrors the Rust `PROTOCOL_VERSION`.

Kept in agreement with `rust/crates/lorecraft-protocol` (the constant there and the
checked-in `schema/version.json`) by `tests/unit/test_protocol_version_parity.py`.
"""

from __future__ import annotations

PROTOCOL_VERSION: int = 1
