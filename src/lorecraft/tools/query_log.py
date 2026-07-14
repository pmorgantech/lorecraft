"""Analyze SQL query-span JSONL logs.

The log is intentionally outside the database so operators can inspect query
shape and timing before adding schema/index changes.
"""

from __future__ import annotations

import argparse
import json
import re
import sqlite3
from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path
from statistics import mean
from typing import Any

_COLUMN_PATTERN = re.compile(
    r'(?:(?P<table>"?[A-Za-z_][\w]*"?)\.)?"?(?P<column>[A-Za-z_][\w]*)"?\s*'
    r"(?:=|<|>|<=|>=|IN\b|LIKE\b|IS\b)",
    re.IGNORECASE,
)
_FROM_JOIN_PATTERN = re.compile(
    r'\b(?:FROM|JOIN)\s+"?(?P<table>[A-Za-z_][\w]*)"?'
    r'(?:\s+(?:AS\s+)?"?(?P<alias>[A-Za-z_][\w]*)"?)?',
    re.IGNORECASE,
)
_ORDER_BY_PATTERN = re.compile(
    r"\bORDER\s+BY\s+(?P<columns>.+?)(?:\s+LIMIT\b|\s+OFFSET\b|$)",
    re.IGNORECASE,
)
_SQL_KEYWORDS = {
    "WHERE",
    "JOIN",
    "ON",
    "GROUP",
    "ORDER",
    "LIMIT",
    "OFFSET",
    "INNER",
    "LEFT",
    "RIGHT",
    "FULL",
    "CROSS",
}


@dataclass(frozen=True)
class QuerySpan:
    duration_ms: float
    statement_hash: str
    statement: str
    statement_type: str
    engine_role: str = ""
    rowcount: int | None = None
    slow: bool = False


@dataclass
class StatementSummary:
    statement_hash: str
    statement: str
    count: int = 0
    total_ms: float = 0.0
    max_ms: float = 0.0

    @property
    def avg_ms(self) -> float:
        return self.total_ms / self.count if self.count else 0.0


@dataclass
class IndexCandidate:
    table: str
    column: str
    count: int = 0
    total_ms: float = 0.0
    max_ms: float = 0.0
    statement_hashes: Counter[str] = field(default_factory=Counter)
    indexed: bool | None = None

    @property
    def avg_ms(self) -> float:
        return self.total_ms / self.count if self.count else 0.0


@dataclass
class QueryLogAnalysis:
    total_statements: int
    total_ms: float
    avg_ms: float
    max_ms: float
    slow_statements: list[QuerySpan]
    frequent_statements: list[StatementSummary]
    index_candidates: list[IndexCandidate]


def load_query_spans(paths: Sequence[Path]) -> list[QuerySpan]:
    spans: list[QuerySpan] = []
    for path in paths:
        if not path.exists():
            continue
        for line_number, line in enumerate(path.read_text().splitlines(), start=1):
            if not line.strip():
                continue
            try:
                raw = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"{path}:{line_number}: invalid JSONL") from exc
            spans.append(_span_from_record(raw, path=path, line_number=line_number))
    return spans


def analyze_query_spans(
    spans: Sequence[QuerySpan],
    *,
    limit: int = 10,
    indexed_columns: set[tuple[str, str]] | None = None,
) -> QueryLogAnalysis:
    if not spans:
        return QueryLogAnalysis(0, 0.0, 0.0, 0.0, [], [], [])

    by_hash: dict[str, StatementSummary] = {}
    candidates: dict[tuple[str, str], IndexCandidate] = {}

    for span in spans:
        summary = by_hash.setdefault(
            span.statement_hash,
            StatementSummary(span.statement_hash, span.statement),
        )
        summary.count += 1
        summary.total_ms += span.duration_ms
        summary.max_ms = max(summary.max_ms, span.duration_ms)

        for table, column in _extract_index_candidate_columns(span.statement):
            key = (table, column)
            candidate = candidates.setdefault(key, IndexCandidate(table, column))
            candidate.count += 1
            candidate.total_ms += span.duration_ms
            candidate.max_ms = max(candidate.max_ms, span.duration_ms)
            candidate.statement_hashes[span.statement_hash] += 1

    if indexed_columns is not None:
        for candidate in candidates.values():
            candidate.indexed = (candidate.table, candidate.column) in indexed_columns

    index_candidates = sorted(
        candidates.values(),
        key=lambda candidate: (
            candidate.indexed is True,
            -candidate.count,
            -candidate.total_ms,
            candidate.table,
            candidate.column,
        ),
    )[:limit]
    frequent = sorted(
        by_hash.values(),
        key=lambda summary: (-summary.count, -summary.total_ms, summary.statement_hash),
    )[:limit]
    slowest = sorted(spans, key=lambda span: span.duration_ms, reverse=True)[:limit]
    durations = [span.duration_ms for span in spans]
    return QueryLogAnalysis(
        total_statements=len(spans),
        total_ms=sum(durations),
        avg_ms=mean(durations),
        max_ms=max(durations),
        slow_statements=slowest,
        frequent_statements=frequent,
        index_candidates=index_candidates,
    )


def sqlite_indexed_columns(database_path: Path) -> set[tuple[str, str]]:
    indexed: set[tuple[str, str]] = set()
    with sqlite3.connect(database_path) as connection:
        tables = connection.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table'"
        ).fetchall()
        for (table_name,) in tables:
            for column in connection.execute(f'PRAGMA table_info("{table_name}")'):
                if column[5]:
                    indexed.add((table_name, str(column[1])))
            for index in connection.execute(f'PRAGMA index_list("{table_name}")'):
                index_name = str(index[1])
                for column in connection.execute(f'PRAGMA index_info("{index_name}")'):
                    indexed.add((table_name, str(column[2])))
    return indexed


def format_analysis(analysis: QueryLogAnalysis, *, database_checked: bool) -> str:
    lines = [
        "Query log summary",
        f"  total_statements: {analysis.total_statements}",
        f"  total_ms: {analysis.total_ms:.3f}",
        f"  avg_ms: {analysis.avg_ms:.3f}",
        f"  max_ms: {analysis.max_ms:.3f}",
    ]
    lines.append("")
    lines.append("Slowest statements")
    for span in analysis.slow_statements:
        lines.append(
            f"  {span.duration_ms:9.3f} ms {span.statement_hash} "
            f"{_ellipsize(span.statement)}"
        )
    lines.append("")
    lines.append("Most frequent statement fingerprints")
    for summary in analysis.frequent_statements:
        lines.append(
            f"  {summary.count:6d}x avg={summary.avg_ms:.3f} ms "
            f"max={summary.max_ms:.3f} ms {summary.statement_hash} "
            f"{_ellipsize(summary.statement)}"
        )
    lines.append("")
    lines.append("Index candidates from WHERE/JOIN/ORDER BY usage")
    if not database_checked:
        lines.append("  database not checked; candidates may already be indexed")
    for candidate in analysis.index_candidates:
        state = (
            "indexed"
            if candidate.indexed is True
            else "missing"
            if candidate.indexed is False
            else "unverified"
        )
        hashes = ", ".join(
            statement_hash
            for statement_hash, _count in candidate.statement_hashes.most_common(3)
        )
        lines.append(
            f"  {candidate.table}.{candidate.column} {state} "
            f"count={candidate.count} avg={candidate.avg_ms:.3f} ms "
            f"max={candidate.max_ms:.3f} ms hashes={hashes}"
        )
    return "\n".join(lines)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Analyze Lorecraft SQL query logs.")
    parser.add_argument(
        "--log",
        action="append",
        default=[],
        help="Query JSONL log path. May be passed more than once.",
    )
    parser.add_argument(
        "--database",
        type=Path,
        help="Optional SQLite database path used to mark candidates already indexed.",
    )
    parser.add_argument("--limit", type=int, default=10)
    args = parser.parse_args(argv)

    log_paths = [Path(path) for path in args.log] or [Path("logs/sql_queries.log")]
    spans = load_query_spans(log_paths)
    indexed_columns = (
        sqlite_indexed_columns(args.database) if args.database is not None else None
    )
    analysis = analyze_query_spans(
        spans, limit=args.limit, indexed_columns=indexed_columns
    )
    print(format_analysis(analysis, database_checked=indexed_columns is not None))
    return 0


def _span_from_record(raw: Any, *, path: Path, line_number: int) -> QuerySpan:
    if not isinstance(raw, dict):
        raise ValueError(f"{path}:{line_number}: expected JSON object")
    return QuerySpan(
        duration_ms=float(raw["duration_ms"]),
        statement_hash=str(raw["statement_hash"]),
        statement=str(raw["statement"]),
        statement_type=str(raw.get("statement_type", "")),
        engine_role=str(raw.get("engine_role", "")),
        rowcount=raw.get("rowcount") if isinstance(raw.get("rowcount"), int) else None,
        slow=bool(raw.get("slow", False)),
    )


def _extract_index_candidate_columns(statement: str) -> set[tuple[str, str]]:
    statement_type = statement.partition(" ")[0].upper()
    if statement_type not in {"SELECT", "UPDATE", "DELETE"}:
        return set()

    alias_map = _table_aliases(statement)
    tables = set(alias_map.values())
    candidates: set[tuple[str, str]] = set()

    for match in _COLUMN_PATTERN.finditer(statement):
        table_ref = _strip_identifier(match.group("table") or "")
        column = _strip_identifier(match.group("column"))
        table = _resolve_table(table_ref, alias_map, tables)
        if table:
            candidates.add((table, column))

    for match in _ORDER_BY_PATTERN.finditer(statement):
        raw_columns = match.group("columns")
        for raw_column in raw_columns.split(","):
            table, column = _split_order_column(raw_column, alias_map, tables)
            if table and column:
                candidates.add((table, column))

    return candidates


def _table_aliases(statement: str) -> dict[str, str]:
    aliases: dict[str, str] = {}
    for match in _FROM_JOIN_PATTERN.finditer(statement):
        table = _strip_identifier(match.group("table"))
        alias = _strip_identifier(match.group("alias") or "")
        aliases[table] = table
        if alias and alias.upper() not in _SQL_KEYWORDS:
            aliases[alias] = table
    return aliases


def _resolve_table(
    table_ref: str, alias_map: dict[str, str], tables: set[str]
) -> str | None:
    if table_ref:
        return alias_map.get(table_ref, table_ref)
    if len(tables) == 1:
        return next(iter(tables))
    return None


def _split_order_column(
    raw_column: str, alias_map: dict[str, str], tables: set[str]
) -> tuple[str | None, str | None]:
    cleaned = raw_column.strip()
    if not cleaned:
        return None, None
    first = cleaned.split()[0]
    first = first.strip('"')
    if "." in first:
        table_ref, column = first.split(".", 1)
        return _resolve_table(table_ref.strip('"'), alias_map, tables), column.strip(
            '"'
        )
    return _resolve_table("", alias_map, tables), first


def _strip_identifier(value: str) -> str:
    return value.strip().strip('"')


def _ellipsize(value: str, *, length: int = 120) -> str:
    if len(value) <= length:
        return value
    return value[: length - 3] + "..."


if __name__ == "__main__":
    raise SystemExit(main())
