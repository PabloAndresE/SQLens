"""In-memory connector for testing and prototyping.

Implements ConnectorProtocol using dicts, so tests and examples don't need
a real database connection. Also serves as a reference implementation for
anyone building a custom connector.
"""

from __future__ import annotations

from typing import Any

from sqlens.catalog.models import RawColumn, RawForeignKey
from sqlens.connectors.base import ConnectorProtocol


class MemoryConnector(ConnectorProtocol):
    """Connector backed by in-memory Python dicts.

    Usage:
        connector = MemoryConnector(
            tables={
                "users": {
                    "columns": [
                        {"name": "id", "data_type": "STRING", "is_primary_key": True},
                        {"name": "email", "data_type": "STRING", "nullable": True},
                    ],
                    "foreign_keys": [],
                    "metadata": {"row_count": 1000},
                    "rows": [
                        {"id": "u1", "email": "a@b.com"},
                        {"id": "u2", "email": "c@d.com"},
                    ],
                },
            }
        )
    """

    def __init__(self, tables: dict[str, dict[str, Any]], source: str = "memory://test") -> None:
        self._tables = tables
        self.source = source

    def get_tables(self) -> list[str]:
        return list(self._tables.keys())

    def get_columns(self, table: str) -> list[RawColumn]:
        raw = self._tables[table].get("columns", [])
        return [
            RawColumn(
                name=c["name"],
                data_type=c.get("data_type", "STRING"),
                nullable=c.get("nullable", True),
                is_primary_key=c.get("is_primary_key", False),
                ordinal_position=i,
                description=c.get("description"),
            )
            for i, c in enumerate(raw)
        ]

    def get_primary_keys(self, table: str) -> list[str]:
        return [
            c["name"]
            for c in self._tables[table].get("columns", [])
            if c.get("is_primary_key", False)
        ]

    def get_foreign_keys(self, table: str) -> list[RawForeignKey]:
        raw = self._tables[table].get("foreign_keys", [])
        return [
            RawForeignKey(
                source_column=fk["source_column"],
                target_table=fk["target_table"],
                target_column=fk["target_column"],
            )
            for fk in raw
        ]

    def execute_query(self, sql: str) -> list[dict[str, Any]]:
        """Return stored rows. SQL parsing is not implemented — returns all rows."""
        for table_data in self._tables.values():
            if "rows" in table_data:
                return table_data["rows"]  # type: ignore[no-any-return]
        return []

    def get_table_metadata(self, table: str) -> dict[str, Any]:
        return self._tables[table].get("metadata", {})  # type: ignore[no-any-return]
