"""Compare keyword vs cosine (hash embedding) retrieval on thelook catalog.

Usage:
    python3 scripts/compare_retrievers.py
"""

from __future__ import annotations

import sys
from pathlib import Path

# Allow running from repo root
sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlens import SQLens

CATALOG_PATH = Path(__file__).parent.parent / "validation_output" / "thelook_catalog.json"

QUERIES: list[tuple[str, str | None]] = [
    ("total revenue by country", None),
    ("most popular product categories", None),
    ("user registration over time", None),
    ("order items shipped", None),
    ("ventas en Ecuador", "sales"),
    ("how many users signed up last month", None),
    ("average order value by brand", None),
    ("inventory stock levels", None),
    ("shipping delays by region", None),
    ("customer lifetime value", None),
]

TOP_N = 3
COL_W = 40  # width for each retriever column


def fmt_table_score(name: str, score: float) -> str:
    return f"{name} ({score:.3f})"


def run() -> None:
    if not CATALOG_PATH.exists():
        print(f"ERROR: catalog not found at {CATALOG_PATH}")
        print("Run scripts/validate_bigquery.py first to generate it.")
        sys.exit(1)

    print(f"Loading catalog from {CATALOG_PATH} …")
    ctx = SQLens.load(CATALOG_PATH)
    print(f"  {ctx.table_count} tables, domains: {ctx.domains}\n")

    differing = 0
    keyword_unique = 0
    cosine_unique = 0

    separator = "-" * (COL_W * 2 + 45)

    print(
        f"{'QUERY':<35} {'DOMAIN':<10} "
        f"{'KEYWORD top-3':<{COL_W}} {'COSINE top-3':<{COL_W}} DIFF?"
    )
    print(separator)

    for query, domain in QUERIES:
        kw_result = ctx.get_context(query, max_tables=TOP_N, domain=domain, retrieval="keyword")
        co_result = ctx.get_context(query, max_tables=TOP_N, domain=domain, retrieval="cosine")

        kw_tables = [t.name for t in kw_result.tables]
        co_tables = [t.name for t in co_result.tables]

        kw_items = [
            fmt_table_score(t.name, kw_result.scores.get(t.name, 0.0))
            for t in kw_result.tables
        ]
        co_items = [
            fmt_table_score(t.name, co_result.scores.get(t.name, 0.0))
            for t in co_result.tables
        ]

        differs = kw_tables != co_tables
        if differs:
            differing += 1
            only_in_kw = set(kw_tables) - set(co_tables)
            only_in_co = set(co_tables) - set(kw_tables)
            if only_in_kw:
                keyword_unique += 1
            if only_in_co:
                cosine_unique += 1

        diff_marker = "YES" if differs else "   "
        domain_str = domain or "-"

        # Print header row
        print(
            f"{query:<35} {domain_str:<10} "
            f"{', '.join(kw_items) or '(none)':<{COL_W}} "
            f"{', '.join(co_items) or '(none)':<{COL_W}} "
            f"{diff_marker}"
        )

        # Print per-table diff detail when results differ
        if differs:
            only_in_kw = set(kw_tables) - set(co_tables)
            only_in_co = set(co_tables) - set(kw_tables)
            if only_in_kw:
                print(f"  keyword-only : {', '.join(sorted(only_in_kw))}")
            if only_in_co:
                print(f"  cosine-only  : {', '.join(sorted(only_in_co))}")

    print(separator)
    print("\nSUMMARY")
    print(f"  Total queries         : {len(QUERIES)}")
    print(f"  Different results     : {differing} / {len(QUERIES)}")
    print(f"  Queries where keyword found unique tables : {keyword_unique}")
    print(f"  Queries where cosine  found unique tables : {cosine_unique}")

    if cosine_unique > keyword_unique:
        print("\n  → Cosine found more unique tables across differing queries.")
    elif keyword_unique > cosine_unique:
        print("\n  → Keyword found more unique tables across differing queries.")
    else:
        print("\n  → Both retrievers found the same number of unique tables overall.")


if __name__ == "__main__":
    run()
