# SQLens

<p align="center">
  <b>Schema intelligence layer for LLMs.</b><br>
  Enriched database context.
</p>

<p align="center">
  <a href="https://github.com/PabloAndresE/SQLens/actions/workflows/ci.yml"><img src="https://github.com/PabloAndresE/SQLens/actions/workflows/ci.yml/badge.svg" alt="CI"></a>
  <img src="https://img.shields.io/badge/python-3.10%2B-blue" alt="Python 3.10+">
  <img src="https://img.shields.io/badge/version-0.7.0-green" alt="version">
  <img src="https://img.shields.io/badge/license-MIT-lightgrey" alt="MIT License">
</p>

**Better SQL starts with better context, not a better prompt.**

SQLens introspects your database schema, enriches it with descriptions, statistics, inferred relationships, sample data, and business domain tags, then retrieves only the relevant tables for any natural language query — formatted and optimized for an LLM's context window.

## Why?

Most NL-to-SQL tools fail not because of the LLM, but because of the garbage context they feed it. A raw DDL dump tells a model nothing about what `usr_acct_bal_dt` means, which tables relate to each other implicitly, or what values `country_code` actually contains.

SQLens solves the **context problem** and stays out of the **generation problem**. It's the R+A in RAG — retrieval and augmentation — without the G. You bring your own LLM.


---

## Contents

- [Install](#install)
- [Quick start](#quick-start)
- [How it works](#how-it-works)
- [Enrichment](#enrichment)
- [Retrieval](#retrieval)
- [Domain-scoped retrieval](#domain-scoped-retrieval)
- [Output levels](#output-levels)
- [Primary key inference](#primary-key-inference)
- [Incremental updates](#incremental-updates)
- [CLI](#cli)
- [Catalog inspection](#catalog-inspection)

---

## Install

```bash
pip install sqlens                   # core — keyword retrieval, SQLite built-in
pip install sqlens[bigquery]         # + BigQuery connector
pip install sqlens[postgresql]       # + PostgreSQL connector
pip install sqlens[mysql]            # + MySQL / MariaDB connector
pip install sqlens[numpy]            # + cosine similarity retrieval
pip install sqlens[vector]           # + chromadb vector search
pip install sqlens[all]              # everything
```

SQLite support requires **zero extra dependencies** — `sqlite3` ships with Python.

---

## Quick start

```python
from sqlens import SQLens

# 1. Connect and introspect — pick your database
ctx = SQLens.from_sqlite("./my_database.db")
# ctx = SQLens.from_bigquery(project="my-project", dataset="analytics")
# ctx = SQLens.from_postgresql("postgresql://user:pass@localhost:5432/mydb")
# ctx = SQLens.from_mysql("mysql://user:pass@localhost:3306/mydb")

# 2. Enrich once, save to disk
ctx.enrich(
    descriptions=True,   # human-readable column and table descriptions
    stats=True,          # cardinality, null %, min/max, top values
    relations=True,      # infer implicit foreign keys
    samples=3,           # representative rows per table
    domains=True,        # auto-tag tables by business domain
)
ctx.save("./catalog.json")

# 3. Load and query
ctx = SQLens.load("./catalog.json")

context = ctx.get_context(
    "monthly active users by country",
    max_tables=5,
    level="standard",    # compact | standard | full
    domain="auto",       # classify query → filter by domain → retrieve
)

# 4. Feed to any LLM
print(context.to_prompt())  # optimized text block
print(context.to_dict())    # structured dict / JSON
```

---

## How it works

```
┌──────────────────────────────────────────────────────────────────────┐
│  Database  (SQLite · PostgreSQL · MySQL · BigQuery · custom)         │
└──────────────────────────────────┬───────────────────────────────────┘
                            │
                            ▼
              ┌─────────────────────────┐
              │     Introspection       │
              │  tables · columns ·     │
              │  types · PKs · FKs      │
              │  PK heuristic fallback  │
              └────────────┬────────────┘
                           │
                           ▼
        ┌──────────────────────────────────────┐
        │          Enrichment Pipeline          │
        │                                       │
        │  descriptions  rule-based + LLM       │
        │  stats         cardinality · nulls    │
        │  relations     inferred foreign keys  │
        │  samples       representative rows    │
        │  domains       business domain tags   │
        └──────────────────┬───────────────────┘
                           │
                           ▼
              ┌─────────────────────────┐
              │   Catalog  (JSON)       │
              │   fingerprinted ·       │
              │   incremental cache     │
              └────────────┬────────────┘
                           │
              ┌────────────▼────────────┐
              │     Domain Filter       │  optional
              │   83 tables → ~12       │
              └────────────┬────────────┘
                           │
        ┌──────────────────▼───────────────────┐
        │       Retrieval  (auto-detected)      │
        │                                       │
        │  keyword   TF-IDF · zero deps         │
        │  cosine    numpy + sentence-transformers│
        │  vector    chromadb / lancedb         │
        └──────────────────┬───────────────────┘
                           │
                           ▼
              ┌─────────────────────────┐
              │    Context Output       │
              │  .to_dict()             │
              │  .to_prompt()           │
              └─────────────────────────┘
```

---

## Enrichment

Each enricher is optional and composable. Run them once, save the catalog, reuse forever.

### Descriptions

Rule-based heuristics expand abbreviations and detect naming patterns automatically:

| Input | Output |
|-------|--------|
| `usr_acct_bal_dt` | "user account balance date" |
| `is_active` | "boolean flag for active status" |
| `created_at` | "creation timestamp" |
| `order_id` | "foreign key reference to orders" |

For higher quality, pass any LLM as a callable — it fills in what the rules miss:

```python
# Anthropic Claude
import anthropic
client = anthropic.Anthropic()

ctx.enrich(
    descriptions=lambda prompt: client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=200,
        messages=[{"role": "user", "content": prompt}],
    ).content[0].text
)

# Google Gemini
import google.generativeai as genai
genai.configure(api_key="YOUR_KEY")
model = genai.GenerativeModel("gemini-2.0-flash")

ctx.enrich(descriptions=lambda prompt: model.generate_content(prompt).text)
```

### Stats

Column-level statistics collected per table. Dialect-aware: each connector runs native SQL (`COUNT(DISTINCT …)` on PostgreSQL/SQLite/MySQL, `APPROX_COUNT_DISTINCT` on BigQuery).

```python
ctx.enrich(stats=True)
# → cardinality, null_pct, min, max per column
# → top_values for string / low-cardinality columns
```

### Relations

Infers implicit foreign keys from naming patterns — finds joins that don't exist in `INFORMATION_SCHEMA`:

```python
ctx.enrich(relations=True)
# "user_id" in "orders" → inferred FK to "users.id"  (confidence: 0.9)
# "product_id" in "order_items" → inferred FK to "products.id"  (confidence: 0.9)
```

### Samples

Stratified representative rows per table:

```python
ctx.enrich(samples=3)
```

### Domains

Auto-tags tables using name patterns, column signatures, and FK propagation. Manual overrides always win:

```python
ctx.enrich(domains=True)
# orders, payments       → ["sales", "finance"]
# users, accounts        → ["users"]
# campaign_clicks        → ["marketing"]
# audit_log              → ["ops"]

# Manual overrides
ctx.set_domain("orders", ["sales", "finance"])
ctx.set_domain("dim_date", ["finance", "ops"])
```

---

## Retrieval

### Auto-detect cascade

SQLens picks the best available retriever at runtime — no configuration required:

```
sentence-transformers installed? →  NumpyCosineRetriever (semantic search)
fallback                         →  KeywordRetriever     (TF-IDF, zero deps)
```

With `sentence-transformers` installed, the cosine retriever uses a semantic embedding model (all-MiniLM-L6-v2). The model loads once per `SQLens` instance and is cached — repeated `get_context()` calls pay zero reload cost.

```bash
pip install sqlens                                 # keyword retrieval (zero deps)
pip install "sqlens[numpy]" sentence-transformers  # + cosine semantic search
pip install sqlens[vector]                         # + vector DB (chromadb)
```

> **Note:** The auto-detect cascade covers keyword and cosine retrieval. Vector DB retrieval requires explicit setup via `set_retriever()` because it needs a configured embedding function and persistence path.

### Force a specific retriever

```python
ctx.get_context(query, retrieval="keyword")
ctx.get_context(query, retrieval="cosine")
ctx.get_context(query, retrieval="vector")
```

### Inspect retrieval metadata

```python
context = ctx.get_context("monthly active users by country", domain="auto")

context.metadata["retrieval_method"]            # "cosine"
context.metadata["domain_filter_applied"]       # "users"
context.metadata["total_tables_in_catalog"]     # 83
context.metadata["tables_after_domain_filter"]  # 11
context.metadata["tables_included"]             # 5
```

---

## Domain-scoped retrieval

On large schemas, vector search across all tables introduces noise. A query about "sales in Ecuador" might surface `audit_log` (which has an `amount` column) ahead of `orders`. Domain filtering narrows the candidate set before retrieval runs.

```python
# Explicit domain
ctx.get_context("revenue Q1", domain="sales")

# Auto-detect from query — keyword classifier + optional LLM tier
# Supports English and Spanish out of the box
ctx.get_context("ventas en Ecuador último trimestre", domain="auto")
# → "ventas" matches "sales" → 83 tables filtered to 12 → cosine on 12

# No filter (default, backwards compatible)
ctx.get_context("revenue Q1")
```

**Impact by schema size:**

| Schema size | Without domain filter | With domain filter |
|---|---|---|
| < 30 tables | Minimal difference | Not needed |
| 30–100 tables | Some noise | ~70–80% smaller search space |
| 100–500 tables | Significant precision loss | Critical |
| 500+ tables | Vector search struggles | Essential |

---

## Output levels

Three levels control how much metadata is included:

| Level | Includes |
|-------|----------|
| `compact` | Table names, columns, types, explicit FKs |
| `standard` | + descriptions, stats (cardinality/nulls), inferred FKs, 2 sample rows |
| `full` | + all stats, all samples, all inferred FKs with confidence scores |

```python
context = ctx.get_context(query, level="standard")  # default
context.to_prompt()   # text block ready to paste into a system prompt
context.to_dict()     # structured dict for programmatic use
```

**Example `.to_prompt()` output** (standard level):

```
DATABASE SCHEMA CONTEXT
Source: bigquery://my-project.analytics
Tables included: 3 of 83  ·  query: "monthly active users by country"

TABLE: users
Description: Core user accounts with registration and profile data
Row count: 1,240,000  ·  Domains: sales, users

Columns:
  - id             STRING  PK  NOT NULL   Unique user identifier  [cardinality: 1,240,000]
  - country_code   STRING  NULLABLE       ISO 3166-1 alpha-2 country code  [cardinality: 89, 2% nulls]
  - last_active_at TIMESTAMP  NULLABLE    Last login or API activity  [5% nulls · 2023-01-01 → 2026-03-18]

Relationships:
  - users.id → events.user_id  (inferred · confidence 0.95)

Sample rows:
  | id      | country_code | last_active_at           |
  | abc-123 | EC           | 2026-03-17T10:30:00Z     |
  | def-456 | US           | 2026-03-10T08:15:00Z     |
```

---

## Primary key inference

Some databases (BigQuery, Redshift) don't enforce or expose primary key constraints. sqlens infers them automatically so the relation inferrer and context output still work correctly.

Three rules, applied in order — first match wins:

| Rule | Pattern | Example |
|------|---------|---------|
| 1 | Column named exactly `id` | `id` in any table |
| 2 | Column named `{singular_table}_id` | `user_id` in `users` |
| 3 | First NOT NULL column with `_id` suffix | `account_id` if rules 1–2 don't match |

Inferred keys are marked `pk_source: "inferred"` in the catalog metadata, distinguishable from `"database"` (declared constraints).

---

## Incremental updates

SQLens SHA-256 fingerprints each table's structure (column names, types, PKs, FKs). On re-introspection, only tables where the fingerprint changed are re-enriched — unchanged tables keep their existing metadata.

```python
ctx = SQLens.load("./catalog.json")
ctx.set_connector(BigQueryConnector(...))
ctx.refresh()   # re-enriches only changed or new tables
ctx.save("./catalog.json")
```

---

## CLI

```bash
# Introspect a database and save the catalog
sqlens inspect --sqlite ./my_database.db -o catalog.json
sqlens inspect --postgresql "postgresql://user:pass@host/db" -o catalog.json
sqlens inspect --mysql "mysql://user:pass@host/db" -o catalog.json
sqlens inspect --bigquery my-project.analytics -o catalog.json

# PostgreSQL with custom schema / MySQL with database override
sqlens inspect --postgresql "..." --schema reporting -o catalog.json
sqlens inspect --mysql "mysql://user@host/db" --database other_db -o catalog.json

# Enrich (any combination of flags)
sqlens enrich catalog.json --descriptions --stats --relations --samples 3 --domains

# Retrieve context for a natural language query
sqlens context catalog.json "monthly active users by country"
sqlens context catalog.json "revenue by region" --domain auto --level full --max-tables 8
sqlens context catalog.json "orders last week" --json     # structured JSON output
```

Add `-v` / `--verbose` to any command for diagnostic output.

---

## Catalog inspection

```python
ctx = SQLens.load("./catalog.json")

ctx.table_count                  # 83
ctx.tables                       # ["users", "orders", "order_items", ...]
ctx.enrichers_applied            # ["descriptions", "stats", "relations", "samples", "domains"]
ctx.domains                      # ["sales", "users", "marketing", "finance", "ops"]
ctx.tables_in_domain("sales")    # ["orders", "order_items", "payments", ...]
ctx.fingerprint("users")         # "a3f8c2d1..."

# Full catalog output without query filtering
ctx.to_dict(level="compact")
ctx.to_prompt(level="full")
```

---

## License

MIT
