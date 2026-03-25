"""BigQuery connector.

Implements ConnectorProtocol using the google-cloud-bigquery SDK.
Requires: pip install sqlens[bigquery]
"""

from __future__ import annotations

from typing import Any

from sqlens.catalog.models import RawColumn, RawForeignKey
from sqlens.connectors.base import ConnectorProtocol


class BigQueryConnector(ConnectorProtocol):
    """Connector for Google BigQuery.

    Uses INFORMATION_SCHEMA views for metadata extraction (free, no slot cost)
    and the BigQuery client for stats/sample queries.

    Args:
        project: GCP project ID where the data lives.
        dataset: BigQuery dataset name.
        billing_project: GCP project for billing/running queries. Defaults to
            `project`. Required when querying public datasets (e.g.,
            bigquery-public-data) from your own project.
        credentials: Optional google.auth credentials. If None, uses
            Application Default Credentials.
    """

    def __init__(
        self,
        project: str,
        dataset: str,
        billing_project: str | None = None,
        credentials: Any = None,
    ) -> None:
        try:
            from google.cloud import bigquery
        except ImportError:
            raise ImportError(
                "BigQuery connector requires google-cloud-bigquery. "
                "Install it with: pip install sqlens[bigquery]"
            )

        self.project = project
        self.dataset = dataset
        self.source = f"bigquery://{project}.{dataset}"
        self._client = bigquery.Client(
            project=billing_project or project,
            credentials=credentials,
        )

    @property
    def _dataset_ref(self) -> str:
        return f"`{self.project}.{self.dataset}`"

    def qualify_table_name(self, table: str) -> str:
        """Return fully qualified BigQuery table name."""
        return f"`{self.project}.{self.dataset}.{table}`"

    def get_tables(self) -> list[str]:
        query = f"""
            SELECT table_name
            FROM `{self.project}.{self.dataset}.INFORMATION_SCHEMA.TABLES`
            WHERE table_type = 'BASE TABLE'
            ORDER BY table_name
        """
        rows = self._client.query(query).result()
        return [row.table_name for row in rows]

    def get_columns(self, table: str) -> list[RawColumn]:
        query = f"""
            SELECT
                column_name,
                data_type,
                is_nullable,
                ordinal_position,
                column_default
            FROM `{self.project}.{self.dataset}.INFORMATION_SCHEMA.COLUMNS`
            WHERE table_name = '{table}'
            ORDER BY ordinal_position
        """
        rows = self._client.query(query).result()
        return [
            RawColumn(
                name=row.column_name,
                data_type=row.data_type,
                nullable=row.is_nullable == "YES",
                ordinal_position=row.ordinal_position,
            )
            for row in rows
        ]

    def get_primary_keys(self, table: str) -> list[str]:
        query = f"""
            SELECT kcu.column_name
            FROM `{self.project}.{self.dataset}.INFORMATION_SCHEMA.KEY_COLUMN_USAGE` kcu
            JOIN `{self.project}.{self.dataset}.INFORMATION_SCHEMA.TABLE_CONSTRAINTS` tc
                ON kcu.constraint_name = tc.constraint_name
            WHERE tc.table_name = '{table}'
                AND tc.constraint_type = 'PRIMARY KEY'
            ORDER BY kcu.ordinal_position
        """
        rows = self._client.query(query).result()
        return [row.column_name for row in rows]

    def get_foreign_keys(self, table: str) -> list[RawForeignKey]:
        query = f"""
            SELECT
                kcu.column_name AS source_column,
                ccu.table_name AS target_table,
                ccu.column_name AS target_column
            FROM `{self.project}.{self.dataset}.INFORMATION_SCHEMA.KEY_COLUMN_USAGE` kcu
            JOIN `{self.project}.{self.dataset}.INFORMATION_SCHEMA.TABLE_CONSTRAINTS` tc
                ON kcu.constraint_name = tc.constraint_name
            JOIN `{self.project}.{self.dataset}.INFORMATION_SCHEMA.CONSTRAINT_COLUMN_USAGE` ccu
                ON tc.constraint_name = ccu.constraint_name
            WHERE tc.table_name = '{table}'
                AND tc.constraint_type = 'FOREIGN KEY'
        """
        try:
            rows = self._client.query(query).result()
            return [
                RawForeignKey(
                    source_column=row.source_column,
                    target_table=row.target_table,
                    target_column=row.target_column,
                )
                for row in rows
            ]
        except Exception:
            # BigQuery doesn't enforce FKs on all datasets
            return []

    def execute_query(self, sql: str) -> list[dict[str, Any]]:
        rows = self._client.query(sql).result()
        return [dict(row.items()) for row in rows]

    def get_table_metadata(self, table: str) -> dict[str, Any]:
        query = f"""
            SELECT
                row_count,
                size_bytes,
                TIMESTAMP_MILLIS(last_modified_time) AS last_modified
            FROM `{self.project}.{self.dataset}.__TABLES__`
            WHERE table_id = '{table}'
        """
        rows = list(self._client.query(query).result())
        if not rows:
            return {}
        row = rows[0]
        return {
            "row_count": row.row_count,
            "size_bytes": row.size_bytes,
            "last_modified": str(row.last_modified),
        }
