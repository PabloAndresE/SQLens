"""Abstract base for enrichment modules.

Each enricher adds one category of metadata to the catalog. Enrichers are
composable (run in any order) and idempotent (running twice = same result).
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from sqlens.catalog.models import Catalog
from sqlens.connectors.base import ConnectorProtocol


class EnricherProtocol(ABC):
    """Protocol for enrichment modules.

    Each enricher receives the current catalog state and a connector (for
    querying the database if needed) and returns an enriched catalog.
    """

    @abstractmethod
    def enrich(self, catalog: Catalog, connector: ConnectorProtocol) -> Catalog:
        """Enrich the catalog with additional metadata.

        Must be idempotent — running twice produces the same result.
        Must not modify the connector or its underlying database.
        """
        ...

    @abstractmethod
    def name(self) -> str:
        """Unique enricher identifier (e.g., 'descriptions', 'stats').

        This value is recorded in catalog.enrichers_applied.
        """
        ...
