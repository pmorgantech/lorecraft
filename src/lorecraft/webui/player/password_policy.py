"""Password complexity policy for new local-account creation.

Requirements are configuration with defaults (``Settings.password_*``, see
``docs/project/wishlist.md`` — Player Creation): length bounds plus optional
mixed-case / number / symbol requirements. ``validate_password`` returns a list
of human-readable failures (empty means the password is acceptable) so both the
server (as the authoritative backstop) and the browser (for live feedback) can
describe exactly what's wrong. The policy is applied only when a *new*
credential is set, never when verifying an existing account's login.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from lorecraft.config import Settings

_SYMBOLS = set("!@#$%^&*()-_=+[]{};:,.<>?/|\\`~'\"")


@dataclass(frozen=True)
class PasswordPolicy:
    min_length: int = 8
    max_length: int = 32
    require_mixed_case: bool = True
    require_symbol: bool = False
    require_number: bool = True

    @classmethod
    def from_settings(cls, settings: Settings) -> PasswordPolicy:
        return cls(
            min_length=settings.password_min_length,
            max_length=settings.password_max_length,
            require_mixed_case=settings.password_require_mixed_case,
            require_symbol=settings.password_require_symbol,
            require_number=settings.password_require_number,
        )

    def requirements(self) -> list[str]:
        """Human-readable requirement list, for showing in the create form."""
        reqs = [f"{self.min_length}–{self.max_length} characters"]
        if self.require_mixed_case:
            reqs.append("upper- and lower-case letters")
        if self.require_number:
            reqs.append("at least one number")
        if self.require_symbol:
            reqs.append("at least one symbol")
        return reqs


def validate_password(password: str, policy: PasswordPolicy) -> list[str]:
    """Return a list of human-readable failures; an empty list means valid."""
    failures: list[str] = []
    if len(password) < policy.min_length:
        failures.append(f"Must be at least {policy.min_length} characters.")
    if len(password) > policy.max_length:
        failures.append(f"Must be at most {policy.max_length} characters.")
    if policy.require_mixed_case and not (
        any(c.islower() for c in password) and any(c.isupper() for c in password)
    ):
        failures.append("Must include both upper- and lower-case letters.")
    if policy.require_number and not any(c.isdigit() for c in password):
        failures.append("Must include at least one number.")
    if policy.require_symbol and not any(c in _SYMBOLS for c in password):
        failures.append("Must include at least one symbol.")
    return failures
