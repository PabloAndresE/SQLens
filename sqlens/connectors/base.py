"""Abstract base for database connectors.

Every supported database engine implements this protocol. The connector's job
is to extract raw schema metadata — it does not interpret, enrich, or format.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Optional

from sqlens.catalog.models import ColumnStats, RawColumn, RawForeignKey


class ConnectorProtocol(ABC):
    """Protocol that every database connector must implement.

    Connectors are thin wrappers around database-specific SDKs. They extract
    raw metadata (tables, columns, types, keys) and expose a read-only query
    interface used by enrichers for stats and sample collection.
    """

    @abstractmethod
    def get_tables(self) -> list[str]:
        """Return all table names in the target dataset/schema."""
        ...

    @abstractmethod
    def get_columns(self, table: str) -> list[RawColumn]:
        """Return column metadata for a specific table."""
        ...

    @abstractmethod
    def get_primary_keys(self, table: str) -> list[str]:
        """Return primary key column names for a table."""
        ...

    @abstractmethod
    def get_foreign_keys(self, table: str) -> list[RawForeignKey]:
        """Return explicit foreign key constraints for a table."""
        ...

    @abstractmethod
    def execute_query(self, sql: str) -> list[dict[str, Any]]:
        """Execute a read-only SQL query and return results as list of dicts.

        Used by the stats enricher (COUNT DISTINCT, MIN/MAX) and the samples
        enricher (SELECT with diversity logic). Implementations should enforce
        read-only access or at minimum refuse DDL/DML.
        """
        ...

    @abstractmethod
    def get_table_metadata(self, table: str) -> dict[str, Any]:
        """Return engine-specific metadata for a table.

        This is a catch-all for metadata that doesn't fit the standard
        protocol methods — row count, partitioning scheme, clustering
        columns, table description from DB comments, etc.

        The returned dict is stored as-is in Table.metadata.
        """
        ...

    def qualify_table_name(self, table: str) -> str:
        """Return the fully qualified table name for use in SQL queries.

        Default implementation returns the table name as-is. Connectors
        for engines that require qualified names (e.g., BigQuery) should
        override this.
        """
        return table

    def get_column_stats(
        self,
        table: str,
        column_name: str,
        data_type: str,
        include_top_values: bool = False,
        top_n: int = 5,
    ) -> Optional[ColumnStats]:
        """Return column stats using connector-specific SQL, or None to use defaults.

        Override in connectors to provide dialect-specific stats collection
        (e.g., COUNT(DISTINCT) vs APPROX_COUNT_DISTINCT, TEXT vs STRING cast).
        Returning None causes StatsEnricher to fall back to its built-in queries.
        """
        return None
