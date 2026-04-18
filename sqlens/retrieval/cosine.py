"""Numpy cosine retriever: semantic search using pre-computed embeddings.

Requires numpy. Uses cosine similarity on embedding vectors stored in a
simple numpy array. No external vector DB needed — works well up to ~500 tables.
"""

from __future__ import annotations

from collections.abc import Callable

from sqlens.catalog.models import Catalog, RetrievalResult, Table
from sqlens.retrieval.base import RetrieverProtocol


class NumpyCosineRetriever(RetrieverProtocol):
    """Cosine similarity retriever using numpy arrays.

    Stores one embedding per table (built from name + description + column info).
    At retrieval time, computes cosine similarity between the query embedding
    and all table embeddings.

    Args:
        embedding_fn: Function that takes a string and returns a list of floats
            (the embedding vector). User provides this — sqlens is model-agnostic.
    """

    def __init__(self, embedding_fn: Callable[[str], list[float]]) -> None:
        self._embed = embedding_fn
        self._catalog: Catalog | None = None
        self._table_names: list[str] = []
        self._embeddings = None  # numpy array, set in build_index

    def is_available(self) -> bool:
        try:
            import numpy  # noqa: F401
            return True
        except ImportError:
            return False

    def build_index(self, catalog: Catalog) -> None:
        import numpy as np

        self._catalog = catalog
        self._table_names = []
        vectors = []

        for table in catalog.tables:
            doc = self._table_to_text(table)
            vec = self._embed(doc)
            self._table_names.append(table.name)
            vectors.append(vec)

        self._embeddings = np.array(vectors, dtype=np.float32)  # type: ignore[assignment]
        # Normalize for cosine similarity
        norms = np.linalg.norm(self._embeddings, axis=1, keepdims=True)  # type: ignore[call-overload]
        norms = np.where(norms == 0, 1, norms)
        self._embeddings = self._embeddings / norms

    def retrieve(
        self,
        query: str,
        max_tables: int = 5,
        candidate_tables: list[str] | None = None,
    ) -> RetrievalResult:
        import numpy as np

        if self._catalog is None or self._embeddings is None:
            raise RuntimeError("Call build_index() before retrieve()")

        query_vec = np.array(self._embed(query), dtype=np.float32)
        query_norm = np.linalg.norm(query_vec)
        if query_norm > 0:
            query_vec = query_vec / query_norm

        # Cosine similarity = dot product (vectors are pre-normalized)
        similarities = self._embeddings @ query_vec

        # Apply candidate filter
        candidate_set: set[str] | None = None
        if candidate_tables is not None:
            candidate_set = set(candidate_tables)
            mask = np.array([
                name in candidate_set for name in self._table_names
            ])
            similarities = np.where(mask, similarities, -np.inf)

        # Get top-N indices
        top_indices = np.argsort(similarities)[::-1][:max_tables]

        tables: list[Table] = []
        scores: dict[str, float] = {}
        for idx in top_indices:
            score = float(similarities[idx])
            name = self._table_names[idx]

            # Skip non-candidates (masked to -inf)
            if candidate_set is not None and name not in candidate_set:
                continue

            # Skip zero/negative scores only when no domain filter is active
            if score <= 0 and candidate_set is None:
                break

            table = self._catalog.get_table(name)
            if table:
                tables.append(table)
                scores[name] = score

        return RetrievalResult(
            tables=tables,
            query=query,
            retrieval_method="cosine",
            total_tables_in_catalog=self._catalog.table_count,
            scores=scores,
        )

    @staticmethod
    def _table_to_text(table: Table) -> str:
        """Build embedding input from table metadata."""
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


import re  # noqa: E402


def _numpy_hash_embedding(text: str, dim: int = 256) -> list[float]:
    """Hash-based embedding using numpy only. Deterministic, no downloads.

    Maps each token to a random unit vector seeded by its hash, then averages.
    Not semantically meaningful (no synonym detection), but produces consistent
    dense vectors — better than pure keyword for partial-match scenarios.
    """
    import hashlib

    import numpy as np

    tokens = re.findall(r"[a-z0-9]+", text.lower())
    if not tokens:
        return [0.0] * dim

    vec = np.zeros(dim, dtype=np.float32)
    for token in tokens:
        seed = int(hashlib.md5(token.encode()).hexdigest(), 16) % (2**31)
        rng = np.random.RandomState(seed)
        vec += rng.randn(dim).astype(np.float32)

    vec = vec / len(tokens)
    norm = np.linalg.norm(vec)
    return (vec / norm if norm > 0 else vec).tolist()  # type: ignore[no-any-return]


def _build_default_embedding_fn() -> Callable[[str], list[float]]:
    """Return the best available embedding function.

    Priority:
    1. sentence-transformers (sqlens[vector]) — semantic quality
    2. numpy hash embedding (sqlens[numpy]) — deterministic, zero ML deps

    Raises ImportError if numpy is not installed.
    """
    # Try sentence-transformers first
    try:
        from sentence_transformers import SentenceTransformer
        model = SentenceTransformer("all-MiniLM-L6-v2")
        return lambda text: model.encode(text, show_progress_bar=False).tolist()
    except ImportError:
        pass

    # Fallback: numpy hash embedding
    try:
        import numpy as np  # noqa: F401 — just checking it's installed
        return _numpy_hash_embedding
    except ImportError:
        raise ImportError(
            "Cosine retriever requires numpy. Install with: pip install sqlens[numpy]"
        )
