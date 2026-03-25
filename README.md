# sqlens

**Schema intelligence layer for LLMs.** Enriched database context, not SQL generation.

sqlens introspects your database schema, enriches it with descriptions, statistics, inferred relationships, sample data, and business domain tags, then retrieves only the relevant tables for any natural language query — formatted and optimized for an LLM's context window.

## Why?

Most NL-to-SQL tools fail not because of the LLM, but because of the garbage context they feed it. A raw DDL dump tells a model nothing about what `usr_acct_bal_dt` means, which tables relate to each other implicitly, or what values `country_code` actually contains.

sqlens solves the **context problem** and stays out of the **generation problem**. It's the R+A in RAG — retrieval and augmentation — without the G. You bring your own LLM.

## Install

```bash
pip install sqlens                   # core (keyword retrieval only)
pip install sqlens[bigquery]         # + BigQuery connector
pip install sqlens[numpy]            # + cosine similarity retrieval
pip install sqlens[vector]           # + chromadb vector search
pip install sqlens[all]              # everything
```

## Quick start

```python
from sqlens import SQLens

# Connect and introspect
ctx = SQLens.from_bigquery(project="my-project", dataset="analytics")

# Enrich the schema (one-time, ~2-3 min for 80 tables)
ctx.enrich(
    descriptions=True,    # rule-based column/table descriptions
    stats=True,           # cardinality, null%, min/max, top values
    relations=True,       # infer implicit foreign keys
    samples=3,            # 3 representative rows per table
    domains=True,         # auto-tag tables by business domain
)

# Save to disk (don't re-enrich every time)
ctx.save("./catalog.json")

# Later: load and retrieve context for a query
ctx = SQLens.load("./catalog.json")

context = ctx.get_context(
    "monthly active users by country",
    max_tables=5,
    level="standard",
    domain="auto",        # auto-detect relevant domain, pre-filter
)

# Use with any LLM
print(context.to_prompt())   # LLM-optimized text
print(context.to_dict())     # structured dict/JSON
```

## How it works

```
Database → Introspect → Enrich → Catalog (JSON)
                                      ↓
                              Domain Filter (optional)
                                      ↓
                              Retrieval (keyword/cosine/vector)
                                      ↓
                              Context Output → .to_dict() / .to_prompt()
```

**Enrichment** adds metadata the LLM needs: human-readable descriptions (via heuristics or optional LLM), column statistics, inferred relationships, sample data, and business domain tags.

**Retrieval** finds the relevant tables for a query. Three tiers auto-detected by what's installed: keyword/TF-IDF (zero deps), numpy cosine similarity, or chromadb vector search.

**Domain-scoped retrieval** pre-filters tables by business domain before search. On an 83-table schema, this reduces the search space from 83 to ~12 tables, dramatically improving precision.

## Domain-scoped retrieval

```python
# Explicit domain
ctx.get_context("revenue Q1", domain="sales")

# Auto-detect from query (supports English + Spanish)
ctx.get_context("ventas en Ecuador", domain="auto")

# Manual domain tagging
ctx.set_domain("orders", ["sales", "finance"])
ctx.set_domain("campaign_clicks", ["marketing"])
```

## LLM descriptions

By default, descriptions use rule-based heuristics (`usr_acct_bal_dt` → "user account balance date"). For higher quality, pass any LLM as a callable:

```python
import anthropic
client = anthropic.Anthropic()

ctx.enrich(
    descriptions=lambda prompt: client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=200,
        messages=[{"role": "user", "content": prompt}],
    ).content[0].text,
)
```

## Incremental updates

sqlens fingerprints each table's structure. When you re-introspect, only tables that changed get re-enriched:

```python
ctx = SQLens.load("./catalog.json")
ctx.set_connector(BigQueryConnector(...))
ctx.refresh()  # only re-enriches changed tables
ctx.save("./catalog.json")
```

## License

MIT
