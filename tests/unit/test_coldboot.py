"""Unit tests for the cold-boot runtime-DB reset (Sprint 72.3)."""

from __future__ import annotations

from pathlib import Path

from lorecraft.ops.coldboot import prepare_runtime_dbs, reset_runtime_db


def test_reset_copies_seed_over_runtime(tmp_path: Path) -> None:
    seed = tmp_path / "seed.db"
    runtime = tmp_path / "runtime.db"
    seed.write_bytes(b"SEED")
    runtime.write_bytes(b"MUTATED")

    reset_runtime_db(seed, runtime)

    assert runtime.read_bytes() == b"SEED"


def test_reset_clears_stale_wal_and_shm(tmp_path: Path) -> None:
    seed = tmp_path / "seed.db"
    runtime = tmp_path / "runtime.db"
    seed.write_bytes(b"SEED")
    runtime.write_bytes(b"OLD")
    (tmp_path / "runtime.db-wal").write_bytes(b"WAL")
    (tmp_path / "runtime.db-shm").write_bytes(b"SHM")

    reset_runtime_db(seed, runtime)

    assert not (tmp_path / "runtime.db-wal").exists()
    assert not (tmp_path / "runtime.db-shm").exists()


def test_reset_creates_missing_runtime_dir(tmp_path: Path) -> None:
    seed = tmp_path / "seed.db"
    seed.write_bytes(b"SEED")
    runtime = tmp_path / "nested" / "runtime.db"

    reset_runtime_db(seed, runtime)

    assert runtime.read_bytes() == b"SEED"


def test_prepare_runtime_dbs_handles_multiple_pairs(tmp_path: Path) -> None:
    game_seed = tmp_path / "game-seed.db"
    audit_seed = tmp_path / "audit-seed.db"
    game_seed.write_bytes(b"GAME")
    audit_seed.write_bytes(b"AUDIT")
    game_runtime = tmp_path / "game.db"
    audit_runtime = tmp_path / "audit.db"

    prepare_runtime_dbs([(game_seed, game_runtime), (audit_seed, audit_runtime)])

    assert game_runtime.read_bytes() == b"GAME"
    assert audit_runtime.read_bytes() == b"AUDIT"
