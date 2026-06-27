"""Transaction context for commands, scheduler work, and admin actions."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from uuid import uuid4


class TransactionSource(StrEnum):
    PLAYER_COMMAND = "PLAYER_COMMAND"
    SCHEDULER = "SCHEDULER"
    ADMIN = "ADMIN"
    SYSTEM = "SYSTEM"


@dataclass(frozen=True)
class TransactionContext:
    transaction_id: str
    correlation_id: str
    parent_transaction_ids: list[str] = field(default_factory=list)
    source_type: TransactionSource = TransactionSource.PLAYER_COMMAND
    actor_id: str = "system"

    @classmethod
    def create(
        cls,
        *,
        actor_id: str,
        source_type: TransactionSource = TransactionSource.PLAYER_COMMAND,
        correlation_id: str | None = None,
        parent_transaction_ids: list[str] | None = None,
    ) -> "TransactionContext":
        return cls(
            transaction_id=str(uuid4()),
            correlation_id=correlation_id or str(uuid4()),
            parent_transaction_ids=list(parent_transaction_ids or []),
            source_type=source_type,
            actor_id=actor_id,
        )
