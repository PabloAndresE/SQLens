"""Stats enricher: collects column-level statistics from the database.

Runs queries against the database (via the connector) to gather cardinality,
null percentages, min/max values, and optionally top values and distribution.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any

from sqlens.catalog.models import Catalog, ColumnStats
from sqlens.connectors.base import ConnectorProtocol
from sqlens.enrichment.base import EnricherProtocol


class StatsEnricher(EnricherProtocol):
    """Enricher that collects column-level statistics.

    Args:
        max_workers: Number of parallel threads for stats queries.
        include_top_values: Whether to collect top N distinct values per column.
        top_n: Number of top values to collect (if enabled).
    """

    def __init__(
        self,
        max_workers: int = 4,
        include_top_values: bool = True,
        top_n: int = 5,
    ) -> None:
        self._max_workers = max_workers
        self._include_top_values = include_top_values
        self._top_n = top_n

    def name(self) -> str:
        return "stats"

    def enrich(self, catalog: Catalog, connector: ConnectorProtocol) -> Catalog:
        def _enrich_table(table_name: str) -> dict[str, ColumnStats]:
            table = catalog.get_table(table_name)
            if table is None:
                return {}
            return self._collect_stats(table.name, table.columns, connector)

        with ThreadPoolExecutor(max_workers=self._max_workers) as pool:
            futures = {
                pool.submit(_enrich_table, t.name): t.name for t in catalog.tables
            }
            for future in as_completed(futures):
                table_name = futures[future]
                try:
                    stats_map = future.result()
                    table = catalog.get_table(table_name)
                    if table:
                        for col in table.columns:
                            if col.name in stats_map:
                                col.stats = stats_map[col.name]
                except Exception:
                    pass  # Stats failure is non-fatal

        # Row counts from table metadata
        for table in catalog.tables:
            if table.row_count is None:
                meta = table.metadata
                if "row_count" in meta:
                    table.row_count = meta["row_count"]

        if "stats" not in catalog.enrichers_applied:
            catalog.enrichers_applied.append("stats")
        return catalog

    def _collect_stats(
        self,
        table_name: str,
        columns: list,
        connector: ConnectorProtocol,
    ) -> dict[str, ColumnStats]:
        """Collect stats for all columns in a single table."""
        results: dict[str, ColumnStats] = {}

        for col in columns:
            try:
                stats = self._collect_column_stats(table_name, col, connector)
                results[col.name] = stats
            except Exception:
                pass

        return results

    def _collect_column_stats(
        self,
        table_name: str,
        col: Any,
        connector: ConnectorProtocol,
    ) -> ColumnStats:
        """Collect stats for a single column.

        Tries connector.get_column_stats() first (dialect-specific SQL).
        Falls back to BigQuery-style queries (APPROX_COUNT_DISTINCT, backtick
        quoting) for connectors that return None.
        """
        # Connector-native path (PostgreSQL, etc.)
        native = connector.get_column_stats(
            table_name, col.name, col.data_type,
            include_top_values=self._include_top_values,
            top_n=self._top_n,
        )
        if native is not None:
            return native

        # BigQuery fallback: APPROX_COUNT_DISTINCT + backtick quoting
        stats = ColumnStats()
        fqn = connector.qualify_table_name(table_name)

        # Basic stats: cardinality and null percentage
        query = f"""
            SELECT
                APPROX_COUNT_DISTINCT(`{col.name}`) AS cardinality,
                COUNTIF(`{col.name}` IS NULL) / COUNT(*) AS null_pct
            FROM {fqn}
        """
        rows = connector.execute_query(query)
        if rows:
            stats.cardinality = rows[0].get("cardinality")
            null_pct = rows[0].get("null_pct")
            if null_pct is not None:
                stats.null_pct = round(float(null_pct), 4)

        # Min/max for sortable types
        upper_type = col.data_type.upper()
        if any(t in upper_type for t in ("INT", "FLOAT", "NUMERIC", "DATE", "TIMESTAMP")):
            query = f"""
                SELECT
                    CAST(MIN(`{col.name}`) AS STRING) AS min_val,
                    CAST(MAX(`{col.name}`) AS STRING) AS max_val
                FROM {fqn}
            """
            rows = connector.execute_query(query)
            if rows:
                stats.min_value = rows[0].get("min_val")
                stats.max_value = rows[0].get("max_val")

        # Top values
        if self._include_top_values and stats.cardinality and stats.cardinality <= 1000:
            query = f"""
                SELECT CAST(`{col.name}` AS STRING) AS val, COUNT(*) AS cnt
                FROM {fqn}
                WHERE `{col.name}` IS NOT NULL
                GROUP BY val
                ORDER BY cnt DESC
                LIMIT {self._top_n}
            """
            rows = connector.execute_query(query)
            if rows:
                stats.top_values = [r["val"] for r in rows]

        return stats
