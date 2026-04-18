"""Session-scoped fixtures for the SQLens evaluation suite.

Provides the techmart database path, ground-truth queries, and
pre-built raw / enriched SQLens instances.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

from sqlens import SQLens

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
FIXTURES_DIR = Path(__file__).parent / "fixtures"
DB_PATH = FIXTURES_DIR / "techmart.db"
GROUND_TRUTH_PATH = FIXTURES_DIR / "techmart_ground_truth.json"
CREATE_SCRIPT = Path(__file__).parent.parent.parent / "scripts" / "create_eval_fixture.py"


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="session")
def techmart_db() -> Path:
    """Path to techmart.db.  Create it if missing."""
    if not DB_PATH.exists():
        subprocess.check_call(
            [sys.executable, str(CREATE_SCRIPT)],
            cwd=str(CREATE_SCRIPT.parent.parent),
        )
    assert DB_PATH.exists(), f"techmart.db not found at {DB_PATH}"
    return DB_PATH


@pytest.fixture(scope="session")
def ground_truth() -> list[dict[str, Any]]:
    """Load techmart_ground_truth.json."""
    with open(GROUND_TRUTH_PATH) as f:
        data: list[dict[str, Any]] = json.load(f)
    return data


@pytest.fixture(scope="session")
def raw_ctx(techmart_db: Path) -> SQLens:
    """SQLens instance with NO enrichment (raw DDL only)."""
    ctx = SQLens.from_sqlite(techmart_db)
    return ctx


@pytest.fixture(scope="session")
def enriched_ctx(techmart_db: Path) -> SQLens:
    """SQLens instance with FULL enrichment (descriptions, relations, domains)."""
    ctx = SQLens.from_sqlite(techmart_db)
    ctx.enrich(
        descriptions=True,
        stats=True,
        relations=True,
        samples=3,
        domains=True,
    )
    return ctx


# ---------------------------------------------------------------------------
# Aggregate metric collector
# ---------------------------------------------------------------------------
# We collect per-query metrics during the session and print a summary at the
# end.  Tests append results into these dicts via the ``metric_collector``
# fixture.

_METRIC_STORE: dict[str, list[dict[str, Any]]] = {}


@pytest.fixture(scope="session")
def metric_collector() -> dict[str, list[dict[str, Any]]]:
    """Session-wide dict that tests append metrics into.

    Keys are retriever names (e.g. ``"raw_keyword"``, ``"enriched_keyword"``).
    Values are lists of per-query metric dicts.
    """
    return _METRIC_STORE


def pytest_sessionfinish(session: pytest.Session, exitstatus: int) -> None:
    """Print aggregate metric summary at end of session."""
    if not _METRIC_STORE:
        return

    print("\n\n" + "=" * 72)
    print("SQLENS EVALUATION SUMMARY")
    print("=" * 72)

    header = (
        f"{'Retriever':<25} {'Recall':<10} {'Precision':<10} "
        f"{'MRR':<10} {'HitRate':<10} {'N':>5}"
    )
    print(header)
    print("-" * 72)

    for name, records in sorted(_METRIC_STORE.items()):
        n = len(records)
        if n == 0:
            continue
        avg_recall = sum(r.get("recall", 0.0) for r in records) / n
        avg_prec = sum(r.get("precision", 0.0) for r in records) / n
        avg_mrr = sum(r.get("mrr", 0.0) for r in records) / n
        avg_hit = sum(r.get("hit_rate", 0.0) for r in records) / n
        print(
            f"{name:<25} {avg_recall:<10.3f} {avg_prec:<10.3f} "
            f"{avg_mrr:<10.3f} {avg_hit:<10.3f} {n:>5}"
        )

    print("=" * 72)
