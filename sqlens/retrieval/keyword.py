"""Keyword retriever: TF-IDF-based table matching with zero external deps.

This is the always-available fallback retriever. It tokenizes table
descriptions and column names, builds a simple TF-IDF index, and matches
queries against it using cosine similarity on term frequency vectors.
"""

from __future__ import annotations

import math
import re
from collections import Counter
from typing import Optional

from sqlens.catalog.models import Catalog, RetrievalResult, Table
from sqlens.retrieval.base import RetrieverProtocol


def _tokenize(text: str) -> list[str]:
    """Simple tokenizer: lowercase, split on non-alphanumeric, drop short tokens."""
    tokens = re.findall(r"[a-z0-9]+", text.lower())
    return [t for t in tokens if len(t) > 1]


def _build_table_document(table: Table) -> str:
    """Build a text document from all available table metadata."""
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


class KeywordRetriever(RetrieverProtocol):
    """TF-IDF based retriever with zero external dependencies.

    Builds an inverted index over table documents (name + description +
    column names + column descriptions + domains). Retrieval uses cosine
    similarity between the query TF-IDF vector and each document vector.
    """

    def __init__(self) -> None:
        self._catalog: Optional[Catalog] = None
        self._documents: dict[str, list[str]] = {}  # table_name → tokens
        self._idf: dict[str, float] = {}
        self._doc_tfidf: dict[str, dict[str, float]] = {}

    def is_available(self) -> bool:
        return True  # always available

    def build_index(self, catalog: Catalog) -> None:
        self._catalog = catalog
        self._documents = {}

        for table in catalog.tables:
            doc = _build_table_document(table)
            self._documents[table.name] = _tokenize(doc)

        # Compute IDF
        n_docs = len(self._documents)
        doc_freq: Counter[str] = Counter()
        for tokens in self._documents.values():
            unique = set(tokens)
            for token in unique:
                doc_freq[token] += 1

        self._idf = {
            token: math.log(n_docs / (1 + count))
            for token, count in doc_freq.items()
        }

        # Pre-compute TF-IDF vectors for each document
        self._doc_tfidf = {}
        for table_name, tokens in self._documents.items():
            tf = Counter(tokens)
            total = len(tokens) or 1
            self._doc_tfidf[table_name] = {
                token: (count / total) * self._idf.get(token, 0)
                for token, count in tf.items()
            }

    def retrieve(
        self,
        query: str,
        max_tables: int = 5,
        candidate_tables: Optional[list[str]] = None,
    ) -> RetrievalResult:
        if self._catalog is None:
            raise RuntimeError("Call build_index() before retrieve()")

        query_tokens = _tokenize(query)
        query_tf = Counter(query_tokens)
        total = len(query_tokens) or 1
        query_vec = {
            token: (count / total) * self._idf.get(token, 0)
            for token, count in query_tf.items()
        }

        candidates = candidate_tables or list(self._doc_tfidf.keys())
        scores: dict[str, float] = {}

        for table_name in candidates:
            doc_vec = self._doc_tfidf.get(table_name, {})
            score = self._cosine_similarity(query_vec, doc_vec)
            scores[table_name] = score

        if candidate_tables is not None:
            # Domain filter active: return candidates sorted by score, even if score is 0.
            # The domain filter already narrowed the search space — we should not return
            # nothing just because keyword tokens don't overlap.
            sorted_tables = sorted(
                [t for t in candidates if t in self._doc_tfidf],
                key=lambda t: scores.get(t, 0.0),
                reverse=True,
            )[:max_tables]
        else:
            # No domain filter: only return tables with a positive score.
            sorted_tables = sorted(
                [t for t in candidates if scores.get(t, 0.0) > 0],
                key=lambda t: scores.get(t, 0.0),
                reverse=True,
            )[:max_tables]

        tables = []
        for name in sorted_tables:
            table = self._catalog.get_table(name)
            if table:
                tables.append(table)

        return RetrievalResult(
            tables=tables,
            query=query,
            retrieval_method="keyword",
            total_tables_in_catalog=self._catalog.table_count,
            scores={name: scores[name] for name in sorted_tables},
        )

    @staticmethod
    def _cosine_similarity(a: dict[str, float], b: dict[str, float]) -> float:
        """Compute cosine similarity between two sparse TF-IDF vectors."""
        common = set(a) & set(b)
        if not common:
            return 0.0

        dot = sum(a[k] * b[k] for k in common)
        norm_a = math.sqrt(sum(v * v for v in a.values()))
        norm_b = math.sqrt(sum(v * v for v in b.values()))

        if norm_a == 0 or norm_b == 0:
            return 0.0
        return dot / (norm_a * norm_b)
