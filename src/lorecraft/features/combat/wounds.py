"""Combat wound derivation policy for Sprint 88."""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256


BODY_LOCATIONS: tuple[str, ...] = (
    "head",
    "torso",
    "left_arm",
    "right_arm",
    "left_leg",
    "right_leg",
)


@dataclass(frozen=True)
class WoundDescriptor:
    body_location: str
    severity: str


def derive_wound(*, action_id: str, target_id: str, damage: float) -> WoundDescriptor:
    """Derive stable wound metadata from a resolved damaging action.

    This avoids adding another random draw after resolution while still making
    body-location records deterministic and reproducible from persisted action
    data.
    """
    digest = sha256(f"{action_id}:{target_id}:{damage:.2f}".encode("utf-8")).digest()
    location = BODY_LOCATIONS[digest[0] % len(BODY_LOCATIONS)]
    return WoundDescriptor(body_location=location, severity=_severity(damage))


def _severity(damage: float) -> str:
    if damage >= 18:
        return "critical"
    if damage >= 10:
        return "major"
    if damage >= 4:
        return "minor"
    return "bruise"
