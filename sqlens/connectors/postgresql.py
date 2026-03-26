"""PostgreSQL connector.

Implements ConnectorProtocol using psycopg2.
Requires: pip install sqlens[postgresql]
"""

from __future__ import annotations

from typing import Any, Optional

from sqlens.catalog.models import ColumnStats, RawColumn, RawForeignKey
from sqlens.connectors.base import ConnectorProtocol


class PostgreSQLConnector(ConnectorProtocol):
    """Connector for PostgreSQL databases.

    Uses information_schema views for metadata extraction (schema-level queries,
    no superuser privileges required) and pg_stat_user_tables for row count
    estimates.

    Args:
        connection_string: A libpq connection string.
            e.g. "postgresql://user:pass@host:5432/dbname"
            or   "host=localhost dbname=mydb user=postgres"
        schema: PostgreSQL schema to introspect. Defaults to 'public'.
    """

    def __init__(self, connection_string: str, schema: str = "public") -> None:
        try:
            import psycopg2
        except ImportError:
            raise ImportError(
                "PostgreSQL connector requires psycopg2. "
                "Install it with: pip install sqlens[postgresql]"
            )
        self._schema = schema
        self.source = self._build_source(connection_string, schema)
        self._conn = psycopg2.connect(connection_string)
        self._conn.autocommit = True

    # ------------------------------------------------------------------
    # Protocol implementation
    # ------------------------------------------------------------------

    def qualify_table_name(self, table: str) -> str:
        """Return double-quoted, schema-qualified table name for use in SQL."""
        return f'"{self._schema}"."{table}"'

    def get_tables(self) -> list[str]:
        rows = self._execute(
            """
            SELECT table_name
            FROM information_schema.tables
            WHERE table_schema = %s
              AND table_type = 'BASE TABLE'
            ORDER BY table_name
            """,
            (self._schema,),
        )
        return [r["table_name"] for r in rows]

    def get_columns(self, table: str) -> list[RawColumn]:
        rows = self._execute(
            """
            SELECT
                column_name,
                data_type,
                is_nullable,
                ordinal_position
            FROM information_schema.columns
            WHERE table_schema = %s
              AND table_name   = %s
            ORDER BY ordinal_position
            """,
            (self._schema, table),
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
            """
            SELECT kcu.column_name
            FROM information_schema.table_constraints  tc
            JOIN information_schema.key_column_usage   kcu
              ON  tc.constraint_name = kcu.constraint_name
              AND tc.table_schema    = kcu.table_schema
            WHERE tc.table_schema    = %s
              AND tc.table_name      = %s
              AND tc.constraint_type = 'PRIMARY KEY'
            ORDER BY kcu.ordinal_position
            """,
            (self._schema, table),
        )
        return [r["column_name"] for r in rows]

    def get_foreign_keys(self, table: str) -> list[RawForeignKey]:
        rows = self._execute(
            """
            SELECT
                kcu.column_name  AS source_column,
                ccu.table_name   AS target_table,
                ccu.column_name  AS target_column
            FROM information_schema.table_constraints       tc
            JOIN information_schema.key_column_usage        kcu
              ON  tc.constraint_name = kcu.constraint_name
              AND tc.table_schema    = kcu.table_schema
            JOIN information_schema.constraint_column_usage ccu
              ON  tc.constraint_name = ccu.constraint_name
            WHERE tc.table_schema    = %s
              AND tc.table_name      = %s
              AND tc.constraint_type = 'FOREIGN KEY'
            """,
            (self._schema, table),
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
            """
            SELECT
                n_live_tup AS row_count,
                pg_total_relation_size(
                    quote_ident(schemaname) || '.' || quote_ident(relname)
                ) AS size_bytes
            FROM pg_stat_user_tables
            WHERE schemaname = %s
              AND relname    = %s
            """,
            (self._schema, table),
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
    ) -> Optional[ColumnStats]:
        """Return column stats using standard PostgreSQL SQL.

        Uses COUNT(DISTINCT …), CAST(… AS TEXT), and double-quoted identifiers
        instead of the BigQuery-specific APPROX_COUNT_DISTINCT / STRING syntax
        used by StatsEnricher's built-in queries.
        """
        fqn = self.qualify_table_name(table)
        col = f'"{column_name}"'
        stats = ColumnStats()

        # Cardinality and null percentage
        rows = self._execute(f"""
            SELECT
                COUNT(DISTINCT {col}) AS cardinality,
                COUNT(CASE WHEN {col} IS NULL THEN 1 END)::float
                    / NULLIF(COUNT(*), 0) AS null_pct
            FROM {fqn}
        """)
        if rows:
            stats.cardinality = rows[0].get("cardinality")
            null_pct = rows[0].get("null_pct")
            if null_pct is not None:
                stats.null_pct = round(float(null_pct), 4)

        # Min/max for numeric and temporal types
        upper = data_type.upper()
        if any(t in upper for t in (
            "INT", "FLOAT", "NUMERIC", "REAL", "DOUBLE", "DECIMAL",
            "DATE", "TIMESTAMP", "TIME",
        )):
            rows = self._execute(f"""
                SELECT
                    CAST(MIN({col}) AS TEXT) AS min_val,
                    CAST(MAX({col}) AS TEXT) AS max_val
                FROM {fqn}
            """)
            if rows:
                stats.min_value = rows[0].get("min_val")
                stats.max_value = rows[0].get("max_val")

        # Top values for low-cardinality columns
        if include_top_values and stats.cardinality and stats.cardinality <= 1000:
            rows = self._execute(f"""
                SELECT CAST({col} AS TEXT) AS val, COUNT(*) AS cnt
                FROM {fqn}
                WHERE {col} IS NOT NULL
                GROUP BY val
                ORDER BY cnt DESC
                LIMIT {top_n}
            """)
            if rows:
                stats.top_values = [r["val"] for r in rows]

        return stats

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _execute(self, sql: str, params: tuple | None = None) -> list[dict[str, Any]]:
        """Execute SQL with optional positional params and return rows as dicts."""
        with self._conn.cursor() as cur:
            cur.execute(sql, params)
            if cur.description is None:
                return []
            col_names = [desc[0] for desc in cur.description]
            return [dict(zip(col_names, row)) for row in cur.fetchall()]

    @staticmethod
    def _build_source(connection_string: str, schema: str) -> str:
        """Derive a credential-free source identifier from a connection string."""
        if connection_string.startswith(("postgresql://", "postgres://")):
            try:
                from urllib.parse import urlparse
                parsed = urlparse(connection_string)
                host = parsed.hostname or "unknown"
                db = (parsed.path or "/").lstrip("/") or "unknown"
                return f"postgresql://{host}/{db}?schema={schema}"
            except Exception:
                pass
        return f"postgresql://unknown?schema={schema}"
