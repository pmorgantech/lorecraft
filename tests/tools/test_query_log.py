import json
import sqlite3
from pathlib import Path

from lorecraft.tools.query_log import (
    analyze_query_spans,
    load_query_spans,
    sqlite_indexed_columns,
)


def test_query_log_analysis_groups_slow_frequent_and_index_candidates(
    tmp_path: Path,
) -> None:
    log_path = tmp_path / "queries.log"
    records = [
        {
            "duration_ms": 10.0,
            "statement_hash": "select-player-room",
            "statement_type": "SELECT",
            "statement": "SELECT player.id FROM player WHERE player.room_id = ?",
        },
        {
            "duration_ms": 30.0,
            "statement_hash": "select-player-room",
            "statement_type": "SELECT",
            "statement": "SELECT player.id FROM player WHERE player.room_id = ?",
        },
        {
            "duration_ms": 5.0,
            "statement_hash": "select-room-id",
            "statement_type": "SELECT",
            "statement": "SELECT room.id FROM room WHERE room.id = ?",
        },
    ]
    log_path.write_text("\n".join(json.dumps(record) for record in records) + "\n")

    spans = load_query_spans([log_path])
    analysis = analyze_query_spans(
        spans,
        indexed_columns={("room", "id")},
    )

    assert analysis.total_statements == 3
    assert analysis.slow_statements[0].statement_hash == "select-player-room"
    assert analysis.frequent_statements[0].statement_hash == "select-player-room"
    candidate_by_column = {
        (candidate.table, candidate.column): candidate
        for candidate in analysis.index_candidates
    }
    assert candidate_by_column[("player", "room_id")].indexed is False
    assert candidate_by_column[("player", "room_id")].count == 2
    assert candidate_by_column[("room", "id")].indexed is True


def test_sqlite_indexed_columns_includes_primary_keys_and_indexes(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "game.db"
    with sqlite3.connect(db_path) as connection:
        connection.execute("CREATE TABLE player (id TEXT PRIMARY KEY, room_id TEXT)")
        connection.execute("CREATE INDEX ix_player_room_id ON player (room_id)")

    indexed = sqlite_indexed_columns(db_path)

    assert ("player", "id") in indexed
    assert ("player", "room_id") in indexed
