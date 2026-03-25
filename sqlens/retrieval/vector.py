"""Vector DB retriever: semantic search using chromadb or lancedb.

Requires: pip install sqlens[vector]
This is the highest-tier retriever, suitable for schemas with 500+ tables.
"""

from __future__ import annotations

from typing import Callable, Optional

from sqlens.catalog.models import Catalog, RetrievalResult
from sqlens.retrieval.base import RetrieverProtocol


class VectorDBRetriever(RetrieverProtocol):
    """Vector database retriever using chromadb.

    Args:
        embedding_fn: Function that takes a string and returns a list of floats.
        collection_name: Name of the chromadb collection.
        persist_directory: Optional directory for persistent storage.
    """

    def __init__(
        self,
        embedding_fn: Callable[[str], list[float]],
        collection_name: str = "sqlens_tables",
        persist_directory: Optional[str] = None,
    ) -> None:
        self._embed = embedding_fn
        self._collection_name = collection_name
        self._persist_directory = persist_directory
        self._catalog: Optional[Catalog] = None
        self._collection = None

    def is_available(self) -> bool:
        try:
            import chromadb  # noqa: F401
            return True
        except ImportError:
            return False

    def build_index(self, catalog: Catalog) -> None:
        import chromadb

        self._catalog = catalog

        if self._persist_directory:
            client = chromadb.PersistentClient(path=self._persist_directory)
        else:
            client = chromadb.Client()

        # Delete existing collection if it exists
        try:
            client.delete_collection(self._collection_name)
        except Exception:
            pass

        self._collection = client.create_collection(
            name=self._collection_name,
            metadata={"hnsw:space": "cosine"},
        )

        documents = []
        ids = []
        embeddings = []

        for table in catalog.tables:
            doc = self._table_to_text(table)
            vec = self._embed(doc)
            documents.append(doc)
            ids.append(table.name)
            embeddings.append(vec)

        if documents:
            self._collection.add(
                documents=documents,
                ids=ids,
                embeddings=embeddings,
            )

    def retrieve(
        self,
        query: str,
        max_tables: int = 5,
        candidate_tables: Optional[list[str]] = None,
    ) -> RetrievalResult:
        if self._catalog is None or self._collection is None:
            raise RuntimeError("Call build_index() before retrieve()")

        query_embedding = self._embed(query)

        where_filter = None
        if candidate_tables is not None:
            where_filter = {"$or": [{"id": name} for name in candidate_tables]}

        results = self._collection.query(
            query_embeddings=[query_embedding],
            n_results=max_tables,
            where=where_filter if candidate_tables and len(candidate_tables) > 1 else None,
        )

        tables = []
        scores: dict[str, float] = {}

        if results["ids"] and results["distances"]:
            for name, distance in zip(results["ids"][0], results["distances"][0]):
                if candidate_tables and name not in candidate_tables:
                    continue
                table = self._catalog.get_table(name)
                if table:
                    tables.append(table)
                    scores[name] = 1 - distance  # convert distance to similarity

        return RetrievalResult(
            tables=tables[:max_tables],
            query=query,
            retrieval_method="vector_db",
            total_tables_in_catalog=self._catalog.table_count,
            scores=scores,
        )

    @staticmethod
    def _table_to_text(table) -> str:
        parts = [table.name]
        if table.description:
            parts.append(table.description)
        for col in table.columns:
            parts.append(col.name)
            if col.description:
                parts.append(col.description)
        for domain in table.domains:
            parts.append(domain)
        return " ".join(parts)
