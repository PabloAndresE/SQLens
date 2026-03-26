"""Introspection engine: extracts raw schema metadata via a connector.

Converts raw connector output (RawColumn, RawForeignKey) into enriched
model objects (Table, Column, Relationship) and assembles the initial Catalog.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone

from sqlens.catalog.models import (
    Catalog,
    Column,
    Relationship,
    Table,
)
from sqlens.connectors.base import ConnectorProtocol


class IntrospectionEngine:
    """Extracts schema metadata from a database connector.

    Uses ThreadPoolExecutor to parallelize per-table introspection when
    the connector supports it.

    Args:
        connector: A ConnectorProtocol implementation.
        max_workers: Number of parallel threads for introspection queries.
    """

    def __init__(self, connector: ConnectorProtocol, max_workers: int = 4) -> None:
        self._connector = connector
        self._max_workers = max_workers

    def introspect(self, source: str) -> Catalog:
        """Run full introspection and return a Catalog.

        Args:
            source: Source identifier (e.g., "bigquery://project.dataset").

        Returns:
            A Catalog with tables, columns, PKs, FKs, and basic metadata.
            No enrichment is applied — the catalog is "raw".
        """
        table_names = self._connector.get_tables()

        def _introspect_table(name: str) -> Table:
            raw_columns = self._connector.get_columns(name)
            pk_names = set(self._connector.get_primary_keys(name))
            raw_fks = self._connector.get_foreign_keys(name)
            metadata = self._connector.get_table_metadata(name)

            columns = [
                Column(
                    name=rc.name,
                    data_type=rc.data_type,
                    nullable=rc.nullable,
                    is_primary_key=rc.name in pk_names,
                    ordinal_position=rc.ordinal_position,
                    description=rc.description,
                )
                for rc in raw_columns
            ]

            relationships = [
                Relationship(
                    source_table=name,
                    source_column=fk.source_column,
                    target_table=fk.target_table,
                    target_column=fk.target_column,
                    type="explicit",
                )
                for fk in raw_fks
            ]

            row_count = metadata.get("row_count")

            table = Table(
                name=name,
                columns=columns,
                relationships=relationships,
                row_count=row_count,
                metadata=metadata,
            )

            if pk_names:
                table.metadata["pk_source"] = "database"
            else:
                IntrospectionEngine._infer_primary_keys(table)

            table.fingerprint = table.compute_fingerprint()
            return table

        tables: list[Table] = []
        with ThreadPoolExecutor(max_workers=self._max_workers) as pool:
            futures = {pool.submit(_introspect_table, n): n for n in table_names}
            for future in as_completed(futures):
                try:
                    tables.append(future.result())
                except Exception as e:
                    table_name = futures[future]
                    raise RuntimeError(f"Introspection failed for table '{table_name}': {e}") from e

        tables.sort(key=lambda t: t.name)
        tables = [t for t in tables if t.columns]  # skip tables with no columns

        return Catalog(
            source=source,
            tables=tables,
            extracted_at=datetime.now(timezone.utc),
        )

    @staticmethod
    def _singularize(name: str) -> str:
        """Return a simple singular form of an English table name."""
        if name.endswith("ies"):
            return name[:-3] + "y"
        if name.endswith("ses") or name.endswith("xes") or name.endswith("zes"):
            return name[:-2]
        if name.endswith("s") and not name.endswith("ss"):
            return name[:-1]
        return name

    @staticmethod
    def _infer_primary_keys(table: Table) -> None:
        """Infer PKs by naming convention when the database didn't expose them.

        Priority (first match wins):
        1. Column named exactly 'id' → is_primary_key = True
        2. Column named '{singular_table_name}_id' → is_primary_key = True
        3. First NOT NULL column ending with '_id' by ordinal position

        Sets table.metadata['pk_source'] = 'inferred' on a match.
        """
        # Rule 1: exact 'id' column
        for col in table.columns:
            if col.name.lower() == "id":
                col.is_primary_key = True
                table.metadata["pk_source"] = "inferred"
                return

        # Rule 2: {singular_table_name}_id
        singular = IntrospectionEngine._singularize(table.name)
        candidate = f"{singular}_id"
        for col in table.columns:
            if col.name.lower() == candidate:
                col.is_primary_key = True
                table.metadata["pk_source"] = "inferred"
                return

        # Rule 3: first NOT NULL column ending with '_id' by ordinal position
        sorted_cols = sorted(table.columns, key=lambda c: c.ordinal_position)
        for col in sorted_cols:
            if col.name.lower().endswith("_id") and not col.nullable:
                col.is_primary_key = True
                table.metadata["pk_source"] = "inferred"
                return
