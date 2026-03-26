"""Validate LLM-enriched descriptions using Google Gemini.

Loads the existing thelook catalog, runs DescriptionsEnricher with a Gemini
callable, then prints a before/after comparison and sample prompts.

Usage:
    GEMINI_API_KEY=<key> python3 scripts/test_llm_descriptions.py
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlens import SQLens

CATALOG_PATH = Path(__file__).parent.parent / "validation_output" / "thelook_catalog.json"
OUTPUT_PATH = Path(__file__).parent.parent / "validation_output" / "thelook_catalog_gemini.json"

TEST_QUERIES = [
    "total revenue by country",
    "most popular product categories",
    "user registration funnel by traffic source",
    "shipping delays and inventory levels",
]


# ---------------------------------------------------------------------------
# Gemini callable
# ---------------------------------------------------------------------------

def make_gemini_callable():
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        print("ERROR: GEMINI_API_KEY environment variable not set.")
        sys.exit(1)

    try:
        import google.generativeai as genai
    except ImportError:
        print("ERROR: google-generativeai not installed. Run: pip install google-generativeai")
        sys.exit(1)

    genai.configure(api_key=api_key)
    model = genai.GenerativeModel("gemini-2.0-flash")

    def gemini_describe(prompt: str) -> str:
        response = model.generate_content(prompt)
        return response.text

    return gemini_describe


# ---------------------------------------------------------------------------
# Snapshot helpers
# ---------------------------------------------------------------------------

def snapshot_descriptions(ctx: SQLens) -> dict[str, dict]:
    """Capture current description state for all tables and columns."""
    state: dict[str, dict] = {}
    for table_name in ctx.tables:
        table = ctx.get_table(table_name)
        state[table_name] = {
            "table_description": table.description,
            "columns": {c.name: c.description for c in table.columns},
        }
    return state


def print_diff(before: dict, after: dict) -> tuple[int, int]:
    """Print before/after diff. Returns (new_col_descs, new_table_descs)."""
    new_col = 0
    new_table = 0

    print("\n── Description changes ──────────────────────────────────────────")
    for table_name in sorted(before):
        b = before[table_name]
        a = after[table_name]

        # Table description
        if b["table_description"] is None and a["table_description"] is not None:
            print(f"\n  [{table_name}] table description:")
            print(f"    before: (none)")
            print(f"    after:  {a['table_description']}")
            new_table += 1

        # Column descriptions
        changed_cols = []
        for col_name, b_desc in b["columns"].items():
            a_desc = a["columns"].get(col_name)
            if b_desc is None and a_desc is not None:
                changed_cols.append((col_name, a_desc))
                new_col += 1

        if changed_cols:
            print(f"\n  [{table_name}] new column descriptions:")
            for col_name, desc in changed_cols:
                print(f"    {col_name}: {desc}")

    if new_col == 0 and new_table == 0:
        print("  (no changes — all descriptions were already filled in)")

    return new_col, new_table


def count_descriptions(ctx: SQLens) -> tuple[int, int]:
    """Return (described_cols, total_cols)."""
    described = 0
    total = 0
    for table_name in ctx.tables:
        table = ctx.get_table(table_name)
        for col in table.columns:
            total += 1
            if col.description is not None:
                described += 1
    return described, total


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    if not CATALOG_PATH.exists():
        print(f"ERROR: catalog not found at {CATALOG_PATH}")
        print("Run scripts/validate_bigquery.py first.")
        sys.exit(1)

    gemini_callable = make_gemini_callable()

    # ── Load catalog ──────────────────────────────────────────────
    print(f"Loading catalog from {CATALOG_PATH} …")
    ctx = SQLens.load(str(CATALOG_PATH))
    print(f"  {ctx.table_count} tables, enrichers: {ctx.enrichers_applied}")

    # ── Snapshot before state ─────────────────────────────────────
    before = snapshot_descriptions(ctx)
    described_before, total_cols = count_descriptions(ctx)

    undescribed_before: dict[str, list[str]] = {}
    for table_name, state in before.items():
        missing = [c for c, d in state["columns"].items() if d is None]
        if missing:
            undescribed_before[table_name] = missing
    tables_without_desc = [t for t, s in before.items() if s["table_description"] is None]

    print(f"\nBEFORE enrichment:")
    print(f"  Column descriptions : {described_before}/{total_cols}")
    print(f"  Table descriptions  : {ctx.table_count - len(tables_without_desc)}/{ctx.table_count}")
    if undescribed_before:
        print(f"  Undescribed columns :")
        for table_name, cols in undescribed_before.items():
            print(f"    {table_name}: {', '.join(cols)}")
    if tables_without_desc:
        print(f"  Tables without desc : {', '.join(tables_without_desc)}")

    # ── Enrich with Gemini ────────────────────────────────────────
    print(f"\nRunning enrich(descriptions=gemini_callable) …")
    import time
    t0 = time.time()
    ctx.enrich(descriptions=gemini_callable)
    elapsed = time.time() - t0
    print(f"  Done in {elapsed:.1f}s")

    # ── Snapshot after and print diff ─────────────────────────────
    after = snapshot_descriptions(ctx)
    new_col, new_table = print_diff(before, after)

    described_after, _ = count_descriptions(ctx)
    tables_with_desc_after = sum(
        1 for t_name in ctx.tables if ctx.get_table(t_name).description is not None
    )

    # Check for remaining gaps
    still_undescribed: dict[str, list[str]] = {}
    for table_name, state in after.items():
        missing = [c for c, d in state["columns"].items() if d is None]
        if missing:
            still_undescribed[table_name] = missing

    # ── Sample prompts ────────────────────────────────────────────
    print("\n── Sample prompts (with Gemini descriptions) ────────────────────")
    for query in TEST_QUERIES:
        result = ctx.get_context(query, max_tables=3)
        prompt = result.to_prompt(level="standard")
        token_est = len(prompt) // 4
        print(f"\n  Query: \"{query}\"  (~{token_est} tokens)")
        print("  " + "-" * 60)
        # Print first 600 chars of prompt
        preview = prompt[:600]
        for line in preview.split("\n"):
            print(f"  {line}")
        if len(prompt) > 600:
            print(f"  … ({len(prompt):,} chars total)")

    # ── Save enriched catalog ─────────────────────────────────────
    ctx.save(str(OUTPUT_PATH))
    size_kb = OUTPUT_PATH.stat().st_size / 1024
    print(f"\nSaved enriched catalog to {OUTPUT_PATH} ({size_kb:.1f} KB)")

    # ── Summary ───────────────────────────────────────────────────
    print("\n── SUMMARY ──────────────────────────────────────────────────────")
    print(f"  Column descriptions : {described_before}/{total_cols} → {described_after}/{total_cols}")
    print(f"  Table descriptions  : {ctx.table_count - len(tables_without_desc)}/{ctx.table_count} → {tables_with_desc_after}/{ctx.table_count}")
    print(f"  New col descriptions: {new_col}")
    print(f"  New table descs     : {new_table}")
    print(f"  LLM time            : {elapsed:.1f}s")

    if still_undescribed:
        print(f"\n  Still undescribed (LLM failed or returned nothing):")
        for table_name, cols in still_undescribed.items():
            print(f"    {table_name}: {', '.join(cols)}")
    else:
        print(f"\n  All columns now have descriptions.")

    # Full prompt token estimate for a broad query
    result_full = ctx.get_context("schema overview", max_tables=ctx.table_count)
    full_prompt = result_full.to_prompt(level="standard")
    print(f"\n  Full catalog prompt : {len(full_prompt):,} chars (~{len(full_prompt)//4:,} tokens)")


if __name__ == "__main__":
    main()
