"""Metric computation functions for the SQLens evaluation suite.

Provides precision@k, recall@k, MRR, and hit-rate over retrieved table lists.
"""

from __future__ import annotations


def compute_precision_at_k(
    retrieved_tables: list[str],
    acceptable_tables: list[str],
    k: int,
) -> float:
    """Fraction of retrieved tables (up to *k*) that are acceptable.

    Args:
        retrieved_tables: Ordered list of retrieved table names.
        acceptable_tables: Set of table names considered correct.
        k: Cut-off depth.

    Returns:
        Precision in [0.0, 1.0].
    """
    top_k = retrieved_tables[:k]
    if not top_k:
        return 0.0
    acceptable_set = set(acceptable_tables)
    hits = sum(1 for t in top_k if t in acceptable_set)
    return hits / len(top_k)


def compute_recall_at_k(
    retrieved_tables: list[str],
    expected_tables: list[str],
) -> float:
    """Fraction of *expected* tables that appear in retrieved.

    Args:
        retrieved_tables: Ordered list of retrieved table names.
        expected_tables: Minimal set of tables required to answer the query.

    Returns:
        Recall in [0.0, 1.0].
    """
    if not expected_tables:
        return 1.0
    retrieved_set = set(retrieved_tables)
    hits = sum(1 for t in expected_tables if t in retrieved_set)
    return hits / len(expected_tables)


def compute_mrr(
    retrieved_tables: list[str],
    expected_tables: list[str],
) -> float:
    """Mean Reciprocal Rank -- 1/rank of the first expected table found.

    Args:
        retrieved_tables: Ordered list of retrieved table names.
        expected_tables: Minimal set of tables required to answer the query.

    Returns:
        MRR in [0.0, 1.0].  0.0 if no expected table is found.
    """
    expected_set = set(expected_tables)
    for rank, table in enumerate(retrieved_tables, start=1):
        if table in expected_set:
            return 1.0 / rank
    return 0.0


def compute_hit_rate(
    retrieved_tables: list[str],
    expected_tables: list[str],
) -> float:
    """1.0 if ALL expected tables are in retrieved, else 0.0.

    Args:
        retrieved_tables: Ordered list of retrieved table names.
        expected_tables: Minimal set of tables required to answer the query.

    Returns:
        1.0 or 0.0.
    """
    if not expected_tables:
        return 1.0
    retrieved_set = set(retrieved_tables)
    return 1.0 if all(t in retrieved_set for t in expected_tables) else 0.0
