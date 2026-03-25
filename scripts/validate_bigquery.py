"""
sqlens validation script — BigQuery public dataset.

Run this locally to validate the full pipeline against real data:

    1. pip install -e ".[bigquery,dev]"
    2. gcloud auth application-default login
    3. python scripts/validate_bigquery.py --billing-project YOUR_GCP_PROJECT

Uses bigquery-public-data.thelook_ecommerce (free, no setup needed).
You need a GCP project for billing even though the data is public.
"""

import argparse
import json
import sys
import time
from pathlib import Path

# ─── Config ───────────────────────────────────────────────────────────
DATA_PROJECT = "bigquery-public-data"
DATASET = "thelook_ecommerce"
OUTPUT_PATH = Path("./validation_output")
# ──────────────────────────────────────────────────────────────────────


def step(n: int, title: str) -> None:
    print(f"\n{'='*60}")
    print(f"  Step {n}: {title}")
    print(f"{'='*60}\n")


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate sqlens against BigQuery public data")
    parser.add_argument(
        "--billing-project",
        required=True,
        help="Your GCP project ID (for billing). The data is free but BQ needs a project.",
    )
    args = parser.parse_args()

    OUTPUT_PATH.mkdir(exist_ok=True)

    # ── Step 1: Connect and introspect ────────────────────────────
    step(1, "Connect to BigQuery and introspect schema")

    try:
        from sqlens import SQLens
    except ImportError:
        print("ERROR: sqlens not installed. Run: pip install -e '.[bigquery,dev]'")
        sys.exit(1)

    t0 = time.time()
    try:
        ctx = SQLens.from_bigquery(
            project=DATA_PROJECT,
            dataset=DATASET,
            billing_project=args.billing_project,
        )
    except Exception as e:
        print(f"ERROR connecting to BigQuery: {e}")
        print("\nMake sure you have:")
        print("  1. pip install sqlens[bigquery]")
        print("  2. gcloud auth application-default login")
        print("     OR set GOOGLE_APPLICATION_CREDENTIALS")
        sys.exit(1)

    elapsed = time.time() - t0
    print(f"Introspected {ctx.table_count} tables in {elapsed:.1f}s")
    print(f"Tables: {', '.join(ctx.tables)}")

    for table_name in ctx.tables:
        table = ctx.get_table(table_name)
        cols = [c.name for c in table.columns]
        pks = [c.name for c in table.columns if c.is_primary_key]
        fp = ctx.fingerprint(table_name)
        print(f"\n  {table_name} ({table.row_count or '?'} rows, fingerprint: {fp})")
        print(f"    Columns ({len(cols)}): {', '.join(cols[:8])}{'...' if len(cols) > 8 else ''}")
        if pks:
            print(f"    PKs: {', '.join(pks)}")

    # ── Step 2: Enrich descriptions + relations + domains ─────────
    step(2, "Enrich: descriptions (rules) + relations + domains")

    t0 = time.time()
    ctx.enrich(descriptions=True, relations=True, domains=True)
    elapsed = time.time() - t0
    print(f"Enriched in {elapsed:.1f}s")
    print(f"Enrichers applied: {ctx.enrichers_applied}")

    for table_name in ctx.tables:
        table = ctx.get_table(table_name)
        print(f"\n  {table_name}")
        if table.description:
            print(f"    Description: {table.description}")
        if table.domains:
            print(f"    Domains: {', '.join(table.domains)}")
        inferred = [r for r in table.relationships if r.type == "inferred"]
        if inferred:
            for r in inferred:
                print(f"    Inferred FK: {r.source_column} -> {r.target_table}.{r.target_column} (conf: {r.confidence})")
        described_cols = [c for c in table.columns if c.description]
        undescribed = [c for c in table.columns if not c.description]
        print(f"    Columns described: {len(described_cols)}/{len(table.columns)}")
        if undescribed:
            print(f"    Undescribed: {', '.join(c.name for c in undescribed[:5])}")

    # ── Step 3: Enrich stats ──────────────────────────────────────
    step(3, "Enrich: stats (queries against BigQuery)")

    t0 = time.time()
    try:
        ctx.enrich(stats=True)
        elapsed = time.time() - t0
        print(f"Stats collected in {elapsed:.1f}s")

        for table_name in ctx.tables[:3]:  # show first 3
            table = ctx.get_table(table_name)
            print(f"\n  {table_name} ({table.row_count:,} rows)" if table.row_count else f"\n  {table_name}")
            for col in table.columns[:5]:  # show first 5 columns
                if col.stats:
                    s = col.stats
                    parts = []
                    if s.cardinality is not None:
                        parts.append(f"cardinality={s.cardinality:,}")
                    if s.null_pct is not None:
                        parts.append(f"nulls={s.null_pct:.1%}")
                    if s.min_value is not None:
                        parts.append(f"min={s.min_value}")
                    if s.max_value is not None:
                        parts.append(f"max={s.max_value}")
                    if s.top_values:
                        parts.append(f"top={s.top_values[:3]}")
                    print(f"    {col.name}: {', '.join(parts)}")
                else:
                    print(f"    {col.name}: no stats")
    except Exception as e:
        print(f"WARNING: Stats enrichment failed: {e}")
        print("This might be a permissions issue or query format problem.")
        print("Continuing without stats...")

    # ── Step 4: Enrich samples ────────────────────────────────────
    step(4, "Enrich: samples (3 rows per table)")

    t0 = time.time()
    try:
        ctx.enrich(samples=3)
        elapsed = time.time() - t0
        print(f"Samples collected in {elapsed:.1f}s")

        for table_name in ctx.tables[:2]:  # show first 2
            table = ctx.get_table(table_name)
            if table.sample_data:
                print(f"\n  {table_name} ({len(table.sample_data)} sample rows):")
                for row in table.sample_data[:2]:
                    truncated = {k: str(v)[:40] for k, v in list(row.items())[:5]}
                    print(f"    {truncated}")
            else:
                print(f"\n  {table_name}: no samples")
    except Exception as e:
        print(f"WARNING: Samples enrichment failed: {e}")
        print("Continuing without samples...")

    # ── Step 5: Save catalog ──────────────────────────────────────
    step(5, "Save catalog to disk")

    catalog_path = OUTPUT_PATH / "thelook_catalog.json"
    ctx.save(str(catalog_path))
    size_kb = catalog_path.stat().st_size / 1024
    print(f"Saved to {catalog_path} ({size_kb:.1f} KB)")

    # ── Step 6: Load and verify round-trip ────────────────────────
    step(6, "Load catalog and verify round-trip")

    ctx2 = SQLens.load(str(catalog_path))
    assert ctx2.table_count == ctx.table_count, "Table count mismatch!"
    assert ctx2.tables == ctx.tables, "Table names mismatch!"
    assert ctx2.enrichers_applied == ctx.enrichers_applied, "Enrichers mismatch!"
    print(f"Round-trip OK: {ctx2.table_count} tables, {ctx2.enrichers_applied}")

    # ── Step 7: Retrieval tests ───────────────────────────────────
    step(7, "Retrieval tests")

    test_queries = [
        ("total revenue by country", None),
        ("most popular product categories", None),
        ("user registration over time", None),
        ("ventas en Ecuador", "auto"),
        ("order items shipped", "sales"),
    ]

    for query, domain in test_queries:
        result = ctx.get_context(query, max_tables=3, domain=domain)
        table_names = [t.name for t in result.tables]
        domain_info = f" [domain={result.domain_filter_applied}]" if result.domain_filter_applied else ""
        print(f"\n  Query: \"{query}\"{domain_info}")
        print(f"  Results: {', '.join(table_names)}")
        if result.scores:
            for name, score in list(result.scores.items())[:3]:
                print(f"    {name}: {score:.4f}")

    # ── Step 8: .to_prompt() output ───────────────────────────────
    step(8, "Generate .to_prompt() output")

    result = ctx.get_context("total revenue by product category", max_tables=4)
    prompt = result.to_prompt(level="standard")

    prompt_path = OUTPUT_PATH / "sample_prompt.txt"
    with open(prompt_path, "w") as f:
        f.write(prompt)

    print(f"Saved to {prompt_path}")
    print(f"Prompt length: {len(prompt):,} chars (~{len(prompt)//4:,} tokens)")
    print(f"\nFirst 500 chars:")
    print("-" * 40)
    print(prompt[:500])
    print("-" * 40)

    # ── Step 9: Merge test (refresh) ──────────────────────────────
    step(9, "Test incremental merge (refresh)")

    old_descriptions = {}
    for t in ctx.catalog.tables:
        old_descriptions[t.name] = t.description

    ctx.refresh()

    all_preserved = True
    for t in ctx.catalog.tables:
        if t.name in old_descriptions and old_descriptions[t.name] != t.description:
            print(f"  WARNING: Description changed for {t.name}")
            all_preserved = False

    if all_preserved:
        print("All enrichment data preserved after refresh (fingerprints matched)")

    # ── Summary ───────────────────────────────────────────────────
    step(10, "SUMMARY")

    total_cols = sum(len(t.columns) for t in ctx.catalog.tables)
    described_cols = sum(
        sum(1 for c in t.columns if c.description) for t in ctx.catalog.tables
    )
    coverage_pct = described_cols / total_cols * 100 if total_cols else 0

    print(f"  Tables introspected:     {ctx.table_count}")
    print(f"  Enrichers applied:       {', '.join(ctx.enrichers_applied)}")
    print(f"  Domains detected:        {', '.join(ctx.domains)}")
    print(f"  Description coverage:    {described_cols}/{total_cols} columns ({coverage_pct:.0f}%)")
    print(f"  Catalog size on disk:    {size_kb:.1f} KB")
    print(f"  Prompt output length:    {len(prompt):,} chars")
    print(f"  Output files in:         {OUTPUT_PATH.absolute()}")
    print()

    # Check what failed
    issues = []
    if "stats" not in ctx.enrichers_applied:
        issues.append("Stats enrichment failed — check query format for BigQuery")
    if "samples" not in ctx.enrichers_applied:
        issues.append("Samples enrichment failed — check query format for BigQuery")

    for t in ctx.catalog.tables:
        undescribed = [c for c in t.columns if not c.description]
        if len(undescribed) > len(t.columns) * 0.5:
            issues.append(f"  {t.name}: {len(undescribed)}/{len(t.columns)} columns undescribed")

    if issues:
        print("  ISSUES TO FIX:")
        for issue in issues:
            print(f"    - {issue}")
    else:
        print("  No issues detected!")

    print(f"\n{'='*60}")
    print("  Validation complete")
    print(f"{'='*60}\n")


if __name__ == "__main__":
    main()
