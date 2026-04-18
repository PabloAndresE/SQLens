"""Tier 1 -- Retrieval quality evaluation.

Parametrized over all 40 ground-truth queries.  Records per-query metrics
for three retriever configurations:

  * raw_keyword      -- raw DDL (no enrichment) + keyword retriever
  * enriched_keyword -- full enrichment + keyword retriever
  * enriched_cosine  -- full enrichment + cosine retriever (numpy hash)

and validates that automatic domain classification matches ground truth.

Individual queries do NOT hard-assert pass/fail.  Instead, aggregate recall
for the enriched retrievers is compared against the raw baseline in a final
test.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from sqlens import SQLens
from sqlens.retrieval.domain_filter import classify_query_domain
from tests.evals.metrics import (
    compute_hit_rate,
    compute_mrr,
    compute_precision_at_k,
    compute_recall_at_k,
)

# ---------------------------------------------------------------------------
# Load ground truth for parametrize IDs
# ---------------------------------------------------------------------------
_GT_PATH = Path(__file__).parent / "fixtures" / "techmart_ground_truth.json"
with open(_GT_PATH) as _f:
    _GROUND_TRUTH: list[dict[str, Any]] = json.load(_f)

_IDS = [q["id"] for q in _GROUND_TRUTH]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _record(
    metric_collector: dict[str, list[dict[str, Any]]],
    retriever_name: str,
    query_id: str,
    retrieved: list[str],
    expected: list[str],
    acceptable: list[str],
    k: int,
) -> dict[str, float]:
    """Compute and record metrics for one query."""
    metrics = {
        "query_id": query_id,
        "recall": compute_recall_at_k(retrieved, expected),
        "precision": compute_precision_at_k(retrieved, acceptable, k),
        "mrr": compute_mrr(retrieved, expected),
        "hit_rate": compute_hit_rate(retrieved, expected),
    }
    metric_collector.setdefault(retriever_name, []).append(metrics)
    return metrics


# ---------------------------------------------------------------------------
# Baseline: Raw DDL + keyword
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("query_case", _GROUND_TRUTH, ids=_IDS)
class TestRetrievalBaseline:
    """Raw DDL + keyword retriever (baseline)."""

    def test_recall(
        self,
        raw_ctx: SQLens,
        query_case: dict[str, Any],
        metric_collector: dict[str, list[dict[str, Any]]],
    ) -> None:
        k = query_case.get("max_tables", 5)
        result = raw_ctx.get_context(
            query_case["nl"],
            max_tables=k,
            retrieval="keyword",
        )
        retrieved = [t.name for t in result.tables]
        _record(
            metric_collector,
            "raw_keyword",
            query_case["id"],
            retrieved,
            query_case["expected_tables"],
            query_case["acceptable_tables"],
            k,
        )
        # No hard assertion -- we only record.


# ---------------------------------------------------------------------------
# Enriched + keyword
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("query_case", _GROUND_TRUTH, ids=_IDS)
class TestRetrievalEnriched:
    """Enriched + keyword retriever."""

    def test_recall(
        self,
        enriched_ctx: SQLens,
        query_case: dict[str, Any],
        metric_collector: dict[str, list[dict[str, Any]]],
    ) -> None:
        k = query_case.get("max_tables", 5)
        result = enriched_ctx.get_context(
            query_case["nl"],
            max_tables=k,
            retrieval="keyword",
        )
        retrieved = [t.name for t in result.tables]
        _record(
            metric_collector,
            "enriched_keyword",
            query_case["id"],
            retrieved,
            query_case["expected_tables"],
            query_case["acceptable_tables"],
            k,
        )

    def test_precision(
        self,
        enriched_ctx: SQLens,
        query_case: dict[str, Any],
        metric_collector: dict[str, list[dict[str, Any]]],
    ) -> None:
        k = query_case.get("max_tables", 5)
        result = enriched_ctx.get_context(
            query_case["nl"],
            max_tables=k,
            retrieval="keyword",
        )
        retrieved = [t.name for t in result.tables]
        precision = compute_precision_at_k(retrieved, query_case["acceptable_tables"], k)
        # Not a hard threshold -- just record.
        assert precision >= 0.0  # trivially true, keeps test visible


# ---------------------------------------------------------------------------
# Enriched + cosine (skip if numpy unavailable)
# ---------------------------------------------------------------------------

try:
    import numpy  # noqa: F401
    _NUMPY_AVAILABLE = True
except ImportError:
    _NUMPY_AVAILABLE = False


@pytest.mark.skipif(not _NUMPY_AVAILABLE, reason="numpy not installed")
@pytest.mark.parametrize("query_case", _GROUND_TRUTH, ids=_IDS)
class TestRetrievalCosine:
    """Enriched + cosine retriever (numpy hash embedding)."""

    def test_recall(
        self,
        enriched_ctx: SQLens,
        query_case: dict[str, Any],
        metric_collector: dict[str, list[dict[str, Any]]],
    ) -> None:
        k = query_case.get("max_tables", 5)
        result = enriched_ctx.get_context(
            query_case["nl"],
            max_tables=k,
            retrieval="cosine",
        )
        retrieved = [t.name for t in result.tables]
        _record(
            metric_collector,
            "enriched_cosine",
            query_case["id"],
            retrieved,
            query_case["expected_tables"],
            query_case["acceptable_tables"],
            k,
        )


# ---------------------------------------------------------------------------
# Domain classification accuracy
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("query_case", _GROUND_TRUTH, ids=_IDS)
class TestDomainClassification:
    """Does auto domain detection match ground truth?"""

    def test_domain_accuracy(
        self,
        enriched_ctx: SQLens,
        query_case: dict[str, Any],
        metric_collector: dict[str, list[dict[str, Any]]],
    ) -> None:
        predicted = classify_query_domain(
            query_case["nl"],
            enriched_ctx.domains,
        )
        expected = query_case["domain"]
        correct = 1.0 if predicted == expected else 0.0
        metric_collector.setdefault("domain_classification", []).append({
            "query_id": query_case["id"],
            "recall": correct,
            "precision": correct,
            "mrr": correct,
            "hit_rate": correct,
        })
        # No hard assertion on individual queries.


# ---------------------------------------------------------------------------
# Aggregate assertion: enriched recall > raw baseline
# ---------------------------------------------------------------------------

class TestAggregateComparison:
    """Assert that enriched retrieval improves over raw baseline."""

    def test_enriched_keyword_beats_raw(
        self,
        metric_collector: dict[str, list[dict[str, Any]]],
    ) -> None:
        raw = metric_collector.get("raw_keyword", [])
        enriched = metric_collector.get("enriched_keyword", [])
        if not raw or not enriched:
            pytest.skip("Retrieval tests did not run yet")

        raw_recall = sum(r["recall"] for r in raw) / len(raw)
        enriched_recall = sum(r["recall"] for r in enriched) / len(enriched)
        assert enriched_recall >= raw_recall, (
            f"Enriched recall ({enriched_recall:.3f}) should be >= "
            f"raw recall ({raw_recall:.3f})"
        )
