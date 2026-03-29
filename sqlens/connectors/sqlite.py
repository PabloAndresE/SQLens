"""SQLite connector.

Implements ConnectorProtocol using Python's built-in sqlite3 module.
Zero external dependencies — sqlite3 ships with CPython.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any, Optional

from sqlens.catalog.models import ColumnStats, RawColumn, RawForeignKey
from sqlens.connectors.base import ConnectorProtocol


class SQLiteConnector(ConnectorProtocol):
    """Connector for SQLite databases.

    Uses PRAGMA commands for metadata extraction (table_info, foreign_key_list)
    and standard SQL for stats collection.

    Args:
        path: Path to the SQLite database file. Use ":memory:" for in-memory DBs.
    """

    def __init__(self, path: str | Path) -> None:
        self._path = str(path)
        self.source = f"sqlite://{self._path}"
        # check_same_thread=False is required because the introspection engine
        # uses ThreadPoolExecutor for parallel table introspection. SQLite
        # serializes writes internally, and we only read during introspection.
        self._conn = sqlite3.connect(self._path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        # Enable foreign key support (off by default in SQLite)
        self._conn.execute("PRAGMA foreign_keys = ON")

    # ------------------------------------------------------------------
    # Protocol implementation
    # ------------------------------------------------------------------

    def get_tables(self) -> list[str]:
        rows = self._conn.execute(
            "SELECT name FROM sqlite_master "
            "WHERE type = 'table' AND name NOT LIKE 'sqlite_%' "
            "ORDER BY name"
        ).fetchall()
        return [r["name"] for r in rows]

    def get_columns(self, table: str) -> list[RawColumn]:
        rows = self._conn.execute(f"PRAGMA table_info(\"{table}\")").fetchall()
        return [
            RawColumn(
                name=r["name"],
                data_type=r["type"].upper() if r["type"] else "TEXT",
                nullable=not r["notnull"],
                is_primary_key=bool(r["pk"]),
                ordinal_position=r["cid"],
            )
            for r in rows
        ]

    def get_primary_keys(self, table: str) -> list[str]:
        rows = self._conn.execute(f"PRAGMA table_info(\"{table}\")").fetchall()
        return [r["name"] for r in rows if r["pk"]]

    def get_foreign_keys(self, table: str) -> list[RawForeignKey]:
        rows = self._conn.execute(f"PRAGMA foreign_key_list(\"{table}\")").fetchall()
        return [
            RawForeignKey(
                source_column=r["from"],
                target_table=r["table"],
                target_column=r["to"],
            )
            for r in rows
        ]

    def get_table_metadata(self, table: str) -> dict[str, Any]:
        # Row count via COUNT(*) — SQLite has no stats table
        row = self._conn.execute(
            f"SELECT COUNT(*) AS cnt FROM \"{table}\""
        ).fetchone()
        row_count = row["cnt"] if row else 0
        return {"row_count": row_count}

    def execute_query(self, sql: str) -> list[dict[str, Any]]:
        rows = self._conn.execute(sql).fetchall()
        if not rows:
            return []
        return [dict(r) for r in rows]

    def qualify_table_name(self, table: str) -> str:
        return f'"{table}"'

    def get_column_stats(
        self,
        table: str,
        column_name: str,
        data_type: str,
        include_top_values: bool = False,
        top_n: int = 5,
    ) -> Optional[ColumnStats]:
        """Return column stats using SQLite-compatible SQL."""
        fqn = self.qualify_table_name(table)
        col = f'"{column_name}"'
        stats = ColumnStats()

        # Cardinality and null percentage
        rows = self._conn.execute(
            f"SELECT COUNT(DISTINCT {col}) AS cardinality, "
            f"CAST(SUM(CASE WHEN {col} IS NULL THEN 1 ELSE 0 END) AS REAL) "
            f"/ MAX(COUNT(*), 1) AS null_pct "
            f"FROM {fqn}"
        ).fetchall()
        if rows:
            r = dict(rows[0])
            stats.cardinality = r.get("cardinality")
            null_pct = r.get("null_pct")
            if null_pct is not None:
                stats.null_pct = round(float(null_pct), 4)

        # Min/max for numeric and temporal types
        upper = data_type.upper()
        if any(t in upper for t in (
            "INT", "FLOAT", "NUMERIC", "REAL", "DOUBLE", "DECIMAL",
            "DATE", "TIMESTAMP", "TIME",
        )):
            rows = self._conn.execute(
                f"SELECT CAST(MIN({col}) AS TEXT) AS min_val, "
                f"CAST(MAX({col}) AS TEXT) AS max_val "
                f"FROM {fqn}"
            ).fetchall()
            if rows:
                r = dict(rows[0])
                stats.min_value = r.get("min_val")
                stats.max_value = r.get("max_val")

        # Top values for low-cardinality columns
        if include_top_values and stats.cardinality and stats.cardinality <= 1000:
            rows = self._conn.execute(
                f"SELECT CAST({col} AS TEXT) AS val, COUNT(*) AS cnt "
                f"FROM {fqn} WHERE {col} IS NOT NULL "
                f"GROUP BY val ORDER BY cnt DESC LIMIT {top_n}"
            ).fetchall()
            if rows:
                stats.top_values = [dict(r)["val"] for r in rows]

        return stats

    def close(self) -> None:
        """Close the database connection."""
        self._conn.close()
