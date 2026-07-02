"""Game domain errors — typed, machine-readable, with codes."""


class GameError(Exception):
    """Base exception for all game logic errors."""

    def __init__(self, message: str, code: str | None = None) -> None:
        self.message = message
        self.code = code or "unknown_error"
        super().__init__(message)

    def __str__(self) -> str:
        return f"{self.code}: {self.message}"


class ValidationError(GameError):
    """User input validation failed. Code: validation_*."""

    def __init__(self, message: str, code: str = "validation_failed") -> None:
        super().__init__(message, code)


class NotFoundError(GameError):
    """Entity not found. Code: not_found_*."""

    def __init__(self, message: str, code: str = "not_found") -> None:
        super().__init__(message, code)


class PermissionError(GameError):
    """User lacks permission. Code: permission_denied."""

    def __init__(self, message: str, code: str = "permission_denied") -> None:
        super().__init__(message, code)


class ConflictError(GameError):
    """Concurrent modification or state conflict. Code: conflict_*."""

    def __init__(self, message: str, code: str = "conflict") -> None:
        super().__init__(message, code)
