"""MySQL connector.

Implements ConnectorProtocol using mysql-connector-python.
Requires: pip install sqlens[mysql]
"""

from __future__ import annotations

from typing import Any

from sqlens.catalog.models import ColumnStats, RawColumn, RawForeignKey
from sqlens.connectors.base import ConnectorProtocol


def _quote_ident(name: str) -> str:
    """Return a backtick-quoted, escape-safe SQL identifier (MySQL/MariaDB style)."""
    return '`' + name.replace('`', '``') + '`'


class MySQLConnector(ConnectorProtocol):
    """Connector for MySQL / MariaDB databases.

    Uses information_schema views for metadata extraction and standard SQL
    for stats collection. No superuser privileges required.

    Args:
        connection_string: A MySQL connection URI.
            e.g. "mysql://user:pass@host:3306/dbname"
            or   "mysql+mysqlconnector://user:pass@host/dbname"
        database: Database name to introspect. If None, extracted from the URI.
    """

    def __init__(self, connection_string: str, database: str | None = None) -> None:
        try:
            import mysql.connector
        except ImportError:
            raise ImportError(
                "MySQL connector requires mysql-connector-python. "
                "Install it with: pip install sqlens[mysql]"
            )
        self._database, connect_args = self._parse_connection(connection_string, database)
        self.source = self._build_source(connection_string, self._database)
        self._conn = mysql.connector.connect(**connect_args)

    # ------------------------------------------------------------------
    # Protocol implementation
    # ------------------------------------------------------------------

    def qualify_table_name(self, table: str) -> str:
        return f"{_quote_ident(self._database)}.{_quote_ident(table)}"

    def get_tables(self) -> list[str]:
        rows = self._execute(
            "SELECT table_name "
            "FROM information_schema.tables "
            "WHERE table_schema = %s "
            "  AND table_type = 'BASE TABLE' "
            "ORDER BY table_name",
            (self._database,),
        )
        return [r["table_name"] for r in rows]

    def get_columns(self, table: str) -> list[RawColumn]:
        rows = self._execute(
            "SELECT column_name, data_type, is_nullable, ordinal_position "
            "FROM information_schema.columns "
            "WHERE table_schema = %s AND table_name = %s "
            "ORDER BY ordinal_position",
            (self._database, table),
        )
        return [
            RawColumn(
                name=r["column_name"],
                data_type=r["data_type"].upper(),
                nullable=r["is_nullable"] == "YES",
                ordinal_position=r["ordinal_position"],
            )
            for r in rows
        ]

    def get_primary_keys(self, table: str) -> list[str]:
        rows = self._execute(
            "SELECT kcu.column_name "
            "FROM information_schema.table_constraints tc "
            "JOIN information_schema.key_column_usage kcu "
            "  ON tc.constraint_name = kcu.constraint_name "
            "  AND tc.table_schema = kcu.table_schema "
            "  AND tc.table_name = kcu.table_name "
            "WHERE tc.table_schema = %s "
            "  AND tc.table_name = %s "
            "  AND tc.constraint_type = 'PRIMARY KEY' "
            "ORDER BY kcu.ordinal_position",
            (self._database, table),
        )
        return [r["column_name"] for r in rows]

    def get_foreign_keys(self, table: str) -> list[RawForeignKey]:
        rows = self._execute(
            "SELECT kcu.column_name AS source_column, "
            "  kcu.referenced_table_name AS target_table, "
            "  kcu.referenced_column_name AS target_column "
            "FROM information_schema.key_column_usage kcu "
            "WHERE kcu.table_schema = %s "
            "  AND kcu.table_name = %s "
            "  AND kcu.referenced_table_name IS NOT NULL",
            (self._database, table),
        )
        return [
            RawForeignKey(
                source_column=r["source_column"],
                target_table=r["target_table"],
                target_column=r["target_column"],
            )
            for r in rows
        ]

    def get_table_metadata(self, table: str) -> dict[str, Any]:
        rows = self._execute(
            "SELECT table_rows AS row_count, "
            "  data_length + index_length AS size_bytes "
            "FROM information_schema.tables "
            "WHERE table_schema = %s AND table_name = %s",
            (self._database, table),
        )
        if not rows:
            return {}
        r = rows[0]
        return {
            "row_count": r.get("row_count"),
            "size_bytes": r.get("size_bytes"),
        }

    def execute_query(self, sql: str) -> list[dict[str, Any]]:
        return self._execute(sql)

    def get_column_stats(
        self,
        table: str,
        column_name: str,
        data_type: str,
        include_top_values: bool = False,
        top_n: int = 5,
    ) -> ColumnStats | None:
        """Return column stats using MySQL-compatible SQL."""
        fqn = self.qualify_table_name(table)
        col = _quote_ident(column_name)
        stats = ColumnStats()

        # Cardinality and null percentage
        rows = self._execute(
            f"SELECT COUNT(DISTINCT {col}) AS cardinality, "
            f"SUM(CASE WHEN {col} IS NULL THEN 1 ELSE 0 END) "
            f"/ GREATEST(COUNT(*), 1) AS null_pct "
            f"FROM {fqn}"
        )
        if rows:
            stats.cardinality = rows[0].get("cardinality")
            null_pct = rows[0].get("null_pct")
            if null_pct is not None:
                stats.null_pct = round(float(null_pct), 4)

        # Min/max for numeric and temporal types
        upper = data_type.upper()
        if any(t in upper for t in (
            "INT", "FLOAT", "NUMERIC", "REAL", "DOUBLE", "DECIMAL",
            "DATE", "TIMESTAMP", "TIME", "DATETIME",
        )):
            rows = self._execute(
                f"SELECT CAST(MIN({col}) AS CHAR) AS min_val, "
                f"CAST(MAX({col}) AS CHAR) AS max_val "
                f"FROM {fqn}"
            )
            if rows:
                stats.min_value = rows[0].get("min_val")
                stats.max_value = rows[0].get("max_val")

        # Top values for low-cardinality columns
        if include_top_values and stats.cardinality and stats.cardinality <= 1000:
            rows = self._execute(
                f"SELECT CAST({col} AS CHAR) AS val, COUNT(*) AS cnt "
                f"FROM {fqn} WHERE {col} IS NOT NULL "
                f"GROUP BY val ORDER BY cnt DESC LIMIT {top_n}"
            )
            if rows:
                stats.top_values = [r["val"] for r in rows]

        return stats

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _execute(self, sql: str, params: tuple | None = None) -> list[dict[str, Any]]:
        """Execute SQL and return rows as dicts."""
        cursor = self._conn.cursor(dictionary=True)
        try:
            cursor.execute(sql, params)  # type: ignore[arg-type]
            return cursor.fetchall()  # type: ignore[return-value]
        finally:
            cursor.close()

    @staticmethod
    def _parse_connection(connection_string: str, database: str | None) -> tuple[str, dict]:
        """Parse a connection URI into (database_name, connect_kwargs)."""
        from urllib.parse import urlparse

        # Normalize scheme: mysql+mysqlconnector:// → mysql://
        normalized = connection_string
        for prefix in ("mysql+mysqlconnector://", "mysql+pymysql://", "mysql://"):
            if connection_string.startswith(prefix):
                normalized = "mysql://" + connection_string[len(prefix):]
                break

        parsed = urlparse(normalized)
        db_name = database or (parsed.path or "/").lstrip("/") or None
        if not db_name:
            raise ValueError(
                "Could not determine database name. "
                "Provide it in the URI path or via the database= parameter."
            )

        connect_args: dict[str, Any] = {
            "database": db_name,
        }
        if parsed.hostname:
            connect_args["host"] = parsed.hostname
        if parsed.port:
            connect_args["port"] = parsed.port
        if parsed.username:
            connect_args["user"] = parsed.username
        if parsed.password:
            connect_args["password"] = parsed.password

        return db_name, connect_args

    @staticmethod
    def _build_source(connection_string: str, database: str) -> str:
        """Derive a credential-free source identifier."""
        try:
            from urllib.parse import urlparse
            parsed = urlparse(connection_string.replace("mysql+mysqlconnector://", "mysql://"))
            host = parsed.hostname or "unknown"
            return f"mysql://{host}/{database}"
        except Exception:
            return f"mysql://unknown/{database}"

    def close(self) -> None:
        """Close the database connection."""
        self._conn.close()
