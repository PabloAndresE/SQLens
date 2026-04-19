#!/usr/bin/env python3
"""Run SQLens evaluation suite and print results.

Usage:
    python scripts/run_eval.py
"""

from __future__ import annotations

import json
import subprocess
import sys
import time
from pathlib import Path

# Ensure repo root is on the path
REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from sqlens import SQLens  # noqa: E402
from tests.evals.metrics import (  # noqa: E402
    compute_hit_rate,
    compute_mrr,
    compute_precision_at_k,
    compute_recall_at_k,
)

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
FIXTURES_DIR = REPO_ROOT / "tests" / "evals" / "fixtures"
DB_PATH = FIXTURES_DIR / "techmart.db"
GT_PATH = FIXTURES_DIR / "techmart_ground_truth.json"
CREATE_SCRIPT = REPO_ROOT / "scripts" / "create_eval_fixture.py"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _ensure_db() -> Path:
    if not DB_PATH.exists():
        print(f"Creating techmart.db via {CREATE_SCRIPT} ...")
        subprocess.check_call([sys.executable, str(CREATE_SCRIPT)])
    return DB_PATH


def _load_ground_truth() -> list[dict]:
    with open(GT_PATH) as f:
        return json.load(f)


def _avg(values: list[float]) -> float:
    return sum(values) / len(values) if values else 0.0


# ---------------------------------------------------------------------------
# Evaluation
# ---------------------------------------------------------------------------

def run_evaluation(
    ctx: SQLens,
    ground_truth: list[dict],
    retrieval: str,
    label: str,
) -> dict[str, float]:
    """Run all queries and return aggregate metrics."""
    recalls: list[float] = []
    precisions: list[float] = []
    mrrs: list[float] = []
    hit_rates: list[float] = []

    for q in ground_truth:
        k = q.get("max_tables", 5)
        result = ctx.get_context(q["nl"], max_tables=k, retrieval=retrieval)
        retrieved = [t.name for t in result.tables]

        recalls.append(compute_recall_at_k(retrieved, q["expected_tables"]))
        precisions.append(
            compute_precision_at_k(retrieved, q["acceptable_tables"], k)
        )
        mrrs.append(compute_mrr(retrieved, q["expected_tables"]))
        hit_rates.append(compute_hit_rate(retrieved, q["expected_tables"]))

    return {
        "label": label,
        "recall": _avg(recalls),
        "precision": _avg(precisions),
        "mrr": _avg(mrrs),
        "hit_rate": _avg(hit_rates),
        "n": len(ground_truth),
    }


def main() -> None:
    print("=" * 72)
    print("  SQLens Evaluation Suite")
    print("=" * 72)

    # 1. Ensure DB exists
    db_path = _ensure_db()
    print(f"\nDatabase: {db_path}")

    # 2. Load ground truth
    gt = _load_ground_truth()
    print(f"Ground truth: {len(gt)} queries")

    # 3. Build raw context
    print("\nBuilding raw context (no enrichment) ...")
    t0 = time.time()
    raw_ctx = SQLens.from_sqlite(db_path)
    print(f"  Done in {time.time() - t0:.1f}s  ({raw_ctx.table_count} tables)")

    # 4. Build enriched context
    print("Building enriched context ...")
    t0 = time.time()
    enriched_ctx = SQLens.from_sqlite(db_path)
    enriched_ctx.enrich(
        descriptions=True,
        stats=True,
        relations=True,
        samples=3,
        domains=True,
    )
    print(f"  Done in {time.time() - t0:.1f}s  (enrichers: {enriched_ctx.enrichers_applied})")

    # 5. Run evaluations
    results: list[dict[str, float]] = []

    print("\nRunning raw keyword retrieval ...")
    results.append(run_evaluation(raw_ctx, gt, "keyword", "Raw Keyword"))

    print("Running enriched keyword retrieval ...")
    results.append(run_evaluation(enriched_ctx, gt, "keyword", "Enriched Keyword"))

    try:
        import numpy  # noqa: F401

        print("Running enriched cosine retrieval ...")
        try:
            results.append(
                run_evaluation(enriched_ctx, gt, "cosine", "Enriched Cosine")
            )
        except Exception as e:
            # sentence-transformers may fail (network). Fall back to hash.
            print(f"  Semantic model failed ({e}), falling back to hash embedding...")
            from sqlens.retrieval.cosine import _numpy_hash_embedding

            enriched_ctx._embedding_fn = _numpy_hash_embedding
            enriched_ctx._retriever = None
            results.append(
                run_evaluation(
                    enriched_ctx, gt, "cosine", "Enriched Cosine (hash)"
                )
            )
    except ImportError:
        print("Skipping cosine retrieval (numpy not installed)")

    # Domain-scoped retrieval
    print("Running enriched keyword + domain filter ...")
    domain_recalls: list[float] = []
    domain_precisions: list[float] = []
    domain_mrrs: list[float] = []
    domain_hits: list[float] = []
    for q in gt:
        k = q.get("max_tables", 5)
        try:
            result = enriched_ctx.get_context(
                q["nl"], max_tables=k, retrieval="keyword", domain="auto"
            )
            retrieved = [t.name for t in result.tables]
        except Exception:
            retrieved = []
        domain_recalls.append(compute_recall_at_k(retrieved, q["expected_tables"]))
        domain_precisions.append(
            compute_precision_at_k(retrieved, q["acceptable_tables"], k)
        )
        domain_mrrs.append(compute_mrr(retrieved, q["expected_tables"]))
        domain_hits.append(compute_hit_rate(retrieved, q["expected_tables"]))
    results.append({
        "label": "Enriched Keyword+Domain",
        "recall": _avg(domain_recalls),
        "precision": _avg(domain_precisions),
        "mrr": _avg(domain_mrrs),
        "hit_rate": _avg(domain_hits),
        "n": len(gt),
    })

    # 6. Print results
    print("\n")
    print("## Retrieval Quality Results")
    print()
    hdr = (
        f"| {'Retriever':<22} | {'Recall':>8} | {'Precision':>9} "
        f"| {'MRR':>6} | {'Hit Rate':>8} |  N  |"
    )
    print(hdr)
    sep = f"|{'-' * 24}|{'-' * 10}|{'-' * 11}|{'-' * 8}|{'-' * 10}|{'-' * 5}|"
    print(sep)
    for r in results:
        print(
            f"| {r['label']:<22} "
            f"| {r['recall']:>8.3f} "
            f"| {r['precision']:>9.3f} "
            f"| {r['mrr']:>6.3f} "
            f"| {r['hit_rate']:>8.3f} "
            f"| {int(r['n']):>3} |"
        )
    print()

    # 7. Delta analysis
    raw_recall = results[0]["recall"]
    enriched_recall = results[1]["recall"]
    delta = enriched_recall - raw_recall
    pct = (delta / raw_recall * 100) if raw_recall > 0 else float("inf")
    print(
        f"Recall improvement (enriched keyword vs raw): "
        f"+{delta:.3f} ({pct:+.1f}%)"
    )

    if len(results) > 2:
        cosine_recall = results[2]["recall"]
        delta_c = cosine_recall - raw_recall
        pct_c = (delta_c / raw_recall * 100) if raw_recall > 0 else float("inf")
        print(
            f"Recall improvement (enriched cosine  vs raw): "
            f"+{delta_c:.3f} ({pct_c:+.1f}%)"
        )

    print("\nDone.")


if __name__ == "__main__":
    main()
