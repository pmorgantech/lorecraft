"""Cold-boot runtime-DB reset — the reseed step, isolated so it runs *once*.

``start.sh`` seeds runtime SQLite DBs by copying the committed seed DBs
(``test_dbs/lorecraft-dev-*.db``) over the runtime paths (``/tmp/lorecraft-dev-*.db``)
*before* launching the server. That wipes all live runtime state (player
positions, sessions, world mutations) back to seed — exactly what a fresh cold
boot wants, and exactly what a supervisor-triggered *relaunch* must never do
(docs/roadmap.md, Sprint 72.3 "the critical footgun").

Keeping the reseed here — importable, testable, single-sourced — lets the
regression guard (72.3c) exercise the *real* reset path and assert the
supervisor's relaunch loop, which never calls this, leaves the runtime DB
untouched. The supervisor module deliberately does not import this.

Pure stdlib (see ``lorecraft.ops`` package docstring).
"""

from __future__ import annotations

import shutil
from pathlib import Path

# SQLite WAL mode leaves sidecar files beside the DB. A stale runtime WAL can be
# replayed against a freshly copied DB and make startup report corruption.
_WAL_SUFFIXES = ("-wal", "-shm")


def reset_runtime_db(seed_db: str | Path, runtime_db: str | Path) -> None:
    """Copy ``seed_db`` over ``runtime_db``, clearing stale WAL/SHM sidecars.

    This is the reseed footgun: calling it on a relaunch wipes live state. It is
    intended for cold boot only.
    """
    seed = Path(seed_db)
    runtime = Path(runtime_db)
    for suffix in ("", *_WAL_SUFFIXES):
        target = runtime.with_name(runtime.name + suffix)
        target.unlink(missing_ok=True)
    runtime.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(seed, runtime)


def prepare_runtime_dbs(pairs: list[tuple[str | Path, str | Path]]) -> None:
    """Reset each ``(seed, runtime)`` pair for a cold boot."""
    for seed, runtime in pairs:
        reset_runtime_db(seed, runtime)


def main(argv: list[str] | None = None) -> int:
    """CLI entry so ``start.sh``'s cold-boot section can single-source the reseed.

    Usage: ``python -m lorecraft.ops.coldboot --pair SEED RUNTIME [--pair ...]``
    """
    import argparse

    parser = argparse.ArgumentParser(description="Reset runtime DBs for a cold boot.")
    parser.add_argument(
        "--pair",
        nargs=2,
        action="append",
        metavar=("SEED", "RUNTIME"),
        default=[],
        help="A seed DB path and the runtime DB path to (over)write from it.",
    )
    args = parser.parse_args(argv)
    prepare_runtime_dbs([(seed, runtime) for seed, runtime in args.pair])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
