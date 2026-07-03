#!/usr/bin/env python3
"""Create a Lorecraft audit SQLite database.

Usage:
    python scripts/create_audit_db.py [--db PATH] [--fresh]

Options:
    --db PATH    Path to the SQLite audit DB (default: configured audit DB).
    --fresh      Remove the existing audit DB before creating tables.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from urllib.parse import unquote

repo_root = Path(__file__).parent.parent
sys.path.insert(0, str(repo_root / "src"))

from sqlmodel import create_engine  # noqa: E402

from lorecraft.config import load_settings  # noqa: E402
from lorecraft.db import create_audit_tables, database_url  # noqa: E402


def _sqlite_file_path(database_path_or_url: str) -> Path | None:
    url = database_url(database_path_or_url)
    if url == "sqlite://":
        return None
    if url.startswith("sqlite:///"):
        return Path(unquote(url.removeprefix("sqlite:///")))
    return None


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "--db", default=None, help="Path to SQLite audit DB (overrides settings)"
    )
    parser.add_argument(
        "--fresh", action="store_true", help="Remove existing audit DB first"
    )
    args = parser.parse_args()

    audit_db = args.db or load_settings().audit_database_path
    db_path = _sqlite_file_path(audit_db)

    if db_path is not None:
        db_path.parent.mkdir(parents=True, exist_ok=True)
        if args.fresh and db_path.exists():
            db_path.unlink()
    elif args.fresh:
        sys.exit("--fresh is only supported for SQLite file paths.")

    audit_url = database_url(audit_db)
    print(f"Audit database: {audit_url}")

    audit_engine = create_engine(audit_url, connect_args={"check_same_thread": False})
    create_audit_tables(audit_engine)

    print("Done.")


if __name__ == "__main__":
    main()
