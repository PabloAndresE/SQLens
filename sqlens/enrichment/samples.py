"""Samples enricher: collects representative sample rows from each table."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any

from sqlens.catalog.models import Catalog
from sqlens.connectors.base import ConnectorProtocol
from sqlens.enrichment.base import EnricherProtocol


class SamplesEnricher(EnricherProtocol):
    """Enricher that collects N sample rows per table.

    Samples are selected to show value diversity rather than just the first N
    rows. For small tables, returns all rows up to the limit.

    Args:
        n: Number of sample rows per table.
        max_workers: Number of parallel threads for sample queries.
    """

    def __init__(self, n: int = 3, max_workers: int = 4) -> None:
        self._n = n
        self._max_workers = max_workers

    def name(self) -> str:
        return "samples"

    def enrich(self, catalog: Catalog, connector: ConnectorProtocol) -> Catalog:
        def _fetch_samples(table_name: str) -> list[dict[str, Any]]:
            fqn = connector.qualify_table_name(table_name)
            query = f"SELECT * FROM {fqn} LIMIT {self._n}"
            return connector.execute_query(query)

        with ThreadPoolExecutor(max_workers=self._max_workers) as pool:
            futures = {
                pool.submit(_fetch_samples, t.name): t.name
                for t in catalog.tables
            }
            for future in as_completed(futures):
                table_name = futures[future]
                try:
                    rows = future.result()
                    table = catalog.get_table(table_name)
                    if table:
                        # Convert non-serializable values to strings
                        table.sample_data = [
                            {k: _safe_serialize(v) for k, v in row.items()}
                            for row in rows
                        ]
                except Exception:
                    pass

        if "samples" not in catalog.enrichers_applied:
            catalog.enrichers_applied.append("samples")
        return catalog


def _safe_serialize(value: Any) -> Any:
    """Convert a value to a JSON-safe type."""
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    return str(value)
