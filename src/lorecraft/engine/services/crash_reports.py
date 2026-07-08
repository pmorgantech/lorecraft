"""Persist unhandled command-pipeline exceptions (Sprint 57.3).

Deliberately a plain function, not a `GameContext`-based service like
`AuditService`: the whole point is to work even when `GameContext`
construction itself is what failed, so this only needs a raw audit `Session`.
"""

from __future__ import annotations

import time
import traceback

from sqlmodel import Session

from lorecraft.engine.models.audit import CrashReport


def record_crash(
    audit_session: Session,
    *,
    transaction_id: str,
    correlation_id: str,
    player_id: str,
    command_text: str,
    exc: BaseException,
) -> None:
    """Persist one `CrashReport` row and commit it immediately.

    Rolls back `audit_session` first to discard any half-written audit rows
    from the failed command (e.g. a `_record_blocked` call that ran before
    the crash) — a crash report should never accidentally smuggle in other
    pending, unrelated writes. Commits on its own rather than deferring to
    the caller, since a crash report is the one thing that must survive even
    when the rest of the command's session can't be trusted.
    """
    audit_session.rollback()
    audit_session.add(
        CrashReport(
            transaction_id=transaction_id,
            correlation_id=correlation_id,
            player_id=player_id,
            command_text=command_text,
            stack_trace="".join(
                traceback.format_exception(type(exc), exc, exc.__traceback__)
            ),
            real_time=time.time(),
        )
    )
    audit_session.commit()
