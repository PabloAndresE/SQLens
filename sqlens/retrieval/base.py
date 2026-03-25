"""Abstract base for retrieval strategies.

All retrieval implementations (keyword, cosine, vector DB) implement this
protocol. The domain filter sits upstream and feeds a filtered candidate
list into whichever retriever is active.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Optional

from sqlens.catalog.models import Catalog, RetrievalResult


class RetrieverProtocol(ABC):
    """Protocol for retrieval strategies."""

    @abstractmethod
    def build_index(self, catalog: Catalog) -> None:
        """Build or rebuild the search index from catalog data.

        Called once after enrichment or when the catalog changes. The index
        is kept in memory for fast retrieval.
        """
        ...

    @abstractmethod
    def retrieve(
        self,
        query: str,
        max_tables: int = 5,
        candidate_tables: Optional[list[str]] = None,
    ) -> RetrievalResult:
        """Given a natural language query, return the most relevant tables.

        Args:
            query: Natural language query (e.g., "monthly active users by country").
            max_tables: Maximum number of tables to return.
            candidate_tables: If provided, only search within this subset.
                Used by the domain filter to restrict the search space.

        Returns:
            RetrievalResult with the top-N most relevant tables and their
            enriched metadata.
        """
        ...

    @abstractmethod
    def is_available(self) -> bool:
        """Check if this retriever's dependencies are installed.

        Used by the auto-detect cascade to determine which retriever to use.
        """
        ...
