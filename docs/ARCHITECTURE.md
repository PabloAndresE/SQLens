# sqlens — Architecture Document

## Vision

sqlens is a Python library that generates enriched schema context for LLMs. It does **not** generate SQL — it produces the highest-quality representation of a database schema so that any LLM can generate better SQL on its own.

The core insight: most NL-to-SQL tools fail not because of the LLM, but because of the garbage context they feed it. sqlens solves the context problem and stays out of the generation problem.

---

## Architecture decisions

| # | Decision | Choice |
|---|----------|--------|
| 1 | Scope | Schema context layer — no SQL generation |
| 2 | Output format | Data pura (dict/JSON) + `.to_prompt()` convenience method |
| 3 | Granularity | Two axes: enrichers control what metadata exists, levels (compact/standard/full) control how much |
| 4 | Prompt hints | No — output is pure data, user builds their own prompt |
| 5 | LLM for descriptions | Rule-based heuristics as default + optional LLM via callable |
| 6 | Caching | Fingerprint per table (structure hash) — only re-enriches what changed |
| 7 | Vector store | Hybrid: auto-detect cascade (keyword → numpy cosine → vector DB) + installable extras |
| 8 | Priority DB | BigQuery first, abstract connector protocol for extension |
| 9 | License | Open-source (MIT) |
| 10 | Concurrency | Sync-first API + ThreadPoolExecutor for internal parallelism |
| 11 | Testing | MemoryConnector + JSON fixtures + retrieval eval set |
| 12 | Domain-scoped retrieval | Tables tagged by business domain; retrieval pre-filters by domain before vector search to reduce noise and improve precision on large schemas |

---

## Pipeline overview

```
┌─────────────┐  ┌─────────────┐  ┌─────────────┐
│  BigQuery    │  │ PostgreSQL  │  │   Custom     │
│  Connector   │  │ Connector   │  │  Connector   │
└──────┬───────┘  └──────┬──────┘  └──────┬───────┘
       │                 │                 │
       └────────────┬────┴─────────────────┘
                    ▼
        ┌───────────────────────┐
        │  Introspection Engine │
        │  DDL, types, PKs, FKs │
        └───────────┬───────────┘
                    ▼
   ┌────────────────────────────────────────────┐
   │           Enrichment Pipeline              │
   │  ┌─────────┬────────┬────────┬───────────┐ │
   │  │Descript.│ Stats  │Relat.  │  Samples  │ │
   │  │Rules+LLM│Card/null│Inferred│  Smart    │ │
   │  └─────────┴────────┴────────┴───────────┘ │
   │  ┌─────────────────────────────────────┐   │
   │  │ Domains (auto-tag by name/columns)  │   │
   │  └─────────────────────────────────────┘   │
   └────────────────┬───────────────────────────┘
                    ▼
        ┌───────────────────────┐
        │  Catalog (JSON)       │
        │  Fingerprints + cache │
        └───────────┬───────────┘
                    ▼
        ┌───────────────────────┐
        │  Domain Filter        │
        │  83 tables → 12       │
        │  (optional pre-filter)│
        └───────────┬───────────┘
                    ▼
   ┌────────────────────────────────────────┐
   │     Retrieval (auto-detect cascade)    │
   │  ┌──────────┬──────────┬─────────────┐ │
   │  │ Keyword/ │ Numpy    │ Vector DB   │ │
   │  │ TF-IDF   │ Cosine   │ [extra]     │ │
   │  └──────────┴──────────┴─────────────┘ │
   └────────────────┬───────────────────────┘
                    ▼
        ┌───────────────────────┐
        │  Context Output       │
        │  .to_dict()           │
        │  .to_prompt()         │
        │  compact/standard/full│
        └───────────────────────┘
```

---

## Module structure

```
sqlens/
├── __init__.py                  # SQLens main class
├── connectors/
│   ├── base.py                  # ConnectorProtocol (ABC)
│   ├── bigquery.py              # BigQueryConnector
│   └── postgresql.py            # PostgreSQLConnector (v0.5)
├── introspection/
│   └── engine.py                # IntrospectionEngine
├── enrichment/
│   ├── base.py                  # EnricherProtocol (ABC)
│   ├── descriptions.py          # RuleBasedDescriber + LLMDescriber
│   ├── stats.py                 # StatsCollector
│   ├── relations.py             # RelationInferrer
│   ├── samples.py               # SampleSelector
│   └── domains.py               # DomainsEnricher (auto-tag + manual)
├── catalog/
│   ├── models.py                # Dataclasses: Table, Column, Relationship, etc.
│   ├── store.py                 # Catalog (JSON persistence + fingerprints)
│   └── serializers.py           # .to_dict(), .to_prompt(), level filtering
├── retrieval/
│   ├── base.py                  # RetrieverProtocol (ABC)
│   ├── domain_filter.py         # DomainFilter (pre-filter before retrieval)
│   ├── keyword.py               # KeywordRetriever (zero deps)
│   ├── cosine.py                # NumpyCosineRetriever (numpy only)
│   └── vector.py                # VectorDBRetriever (lazy import chromadb/lancedb)
└── cli.py                       # CLI tool (v0.6)
```

---

## Core protocols

### ConnectorProtocol

What every database connector must implement.

```python
from abc import ABC, abstractmethod
from sqlens.catalog.models import RawSchema

class ConnectorProtocol(ABC):
    """Protocol for database connectors."""

    @abstractmethod
    def get_tables(self) -> list[str]:
        """Return list of table names in the target dataset/schema."""
        ...

    @abstractmethod
    def get_columns(self, table: str) -> list[RawColumn]:
        """Return column metadata for a table."""
        ...

    @abstractmethod
    def get_primary_keys(self, table: str) -> list[str]:
        """Return primary key column names."""
        ...

    @abstractmethod
    def get_foreign_keys(self, table: str) -> list[RawForeignKey]:
        """Return explicit foreign key relationships."""
        ...

    @abstractmethod
    def execute_query(self, sql: str) -> list[dict]:
        """Execute a read-only query and return results as dicts.
        Used by stats/samples enrichers."""
        ...

    @abstractmethod
    def get_table_metadata(self, table: str) -> dict:
        """Return engine-specific metadata (row count, partitioning, etc.)."""
        ...
```

### EnricherProtocol

What every enrichment module must implement.

```python
from abc import ABC, abstractmethod
from sqlens.catalog.models import Catalog

class EnricherProtocol(ABC):
    """Protocol for enrichment modules. Each enricher receives the
    current catalog state and returns an enriched version."""

    @abstractmethod
    def enrich(self, catalog: Catalog, connector: ConnectorProtocol) -> Catalog:
        """Enrich the catalog with additional metadata.
        Must be idempotent — running twice produces the same result."""
        ...

    @abstractmethod
    def name(self) -> str:
        """Unique enricher identifier (e.g., 'descriptions', 'stats')."""
        ...
```

### RetrieverProtocol

What every retrieval strategy must implement.

```python
from abc import ABC, abstractmethod
from sqlens.catalog.models import Catalog, RetrievalResult

class RetrieverProtocol(ABC):
    """Protocol for retrieval strategies."""

    @abstractmethod
    def build_index(self, catalog: Catalog) -> None:
        """Build/rebuild the search index from catalog data."""
        ...

    @abstractmethod
    def retrieve(self, query: str, max_tables: int = 5,
                 candidate_tables: Optional[list[str]] = None) -> RetrievalResult:
        """Given a natural language query, return the most relevant tables
        with their enriched metadata. If candidate_tables is provided,
        only search within that subset (used by domain filter)."""
        ...

    @abstractmethod
    def is_available(self) -> bool:
        """Check if this retriever's dependencies are installed."""
        ...
```

---

## Data models

### Core dataclasses

```python
from dataclasses import dataclass, field
from typing import Any, Optional
from datetime import datetime

@dataclass
class Column:
    name: str
    data_type: str
    nullable: bool = True
    is_primary_key: bool = False
    description: Optional[str] = None          # from descriptions enricher
    stats: Optional[dict] = None               # from stats enricher
    # stats shape: {cardinality, null_pct, min, max, top_values, distribution}

@dataclass
class Relationship:
    source_table: str
    source_column: str
    target_table: str
    target_column: str
    type: str = "explicit"                     # "explicit" | "inferred"
    confidence: Optional[float] = None         # 0.0-1.0 for inferred

@dataclass
class Table:
    name: str
    columns: list[Column] = field(default_factory=list)
    description: Optional[str] = None
    row_count: Optional[int] = None
    relationships: list[Relationship] = field(default_factory=list)
    sample_data: Optional[list[dict]] = None
    domains: list[str] = field(default_factory=list)   # from domains enricher
    fingerprint: Optional[str] = None          # hash of structure for caching
    metadata: dict = field(default_factory=dict)  # engine-specific extras

@dataclass
class Catalog:
    source: str                                # e.g. "bigquery://project.dataset"
    tables: list[Table] = field(default_factory=list)
    extracted_at: Optional[datetime] = None
    enrichers_applied: list[str] = field(default_factory=list)
    version: str = "1.0"

@dataclass
class RetrievalResult:
    tables: list[Table]
    query: str
    retrieval_method: str                      # "keyword" | "cosine" | "vector_db"
    total_tables_in_catalog: int
    domain_filter_applied: Optional[str] = None  # domain used for pre-filtering
    tables_after_domain_filter: Optional[int] = None  # how many tables remained
    scores: Optional[dict[str, float]] = None  # table_name → relevance score
```

---

## Output format

### Level filtering matrix

| Enricher active | compact | standard | full |
|----------------|---------|----------|------|
| Base (always)  | table + columns + types | + PKs, explicit FKs | + partitions, indices |
| descriptions   | table descriptions only | + column descriptions | + relationship descriptions |
| stats          | row_count, null_pct | + cardinality, min/max | + top_values, distribution |
| relations      | explicit FKs only | + inferred (conf > 0.8) | + all inferred + confidence score |
| samples        | — | 2 rows per table | N rows (configurable) |
| domains        | domain tags as list | same | + auto-detect confidence scores |

### Example output (standard level)

```json
{
  "metadata": {
    "source": "bigquery://my-project.analytics",
    "extracted_at": "2026-03-19T14:30:00Z",
    "total_tables": 47,
    "tables_included": 3,
    "query": "monthly active users by country",
    "retrieval_method": "cosine",
    "level": "standard",
    "enrichers_applied": ["descriptions", "stats", "relations", "samples", "domains"]
  },
  "tables": [
    {
      "name": "users",
      "description": "Core user accounts with registration and profile data",
      "row_count": 1240000,
      "domains": ["sales", "users", "marketing"],
      "columns": [
        {
          "name": "id",
          "type": "STRING",
          "is_primary_key": true,
          "nullable": false,
          "description": "Unique user identifier (UUID)",
          "stats": {"cardinality": 1240000, "null_pct": 0.0}
        },
        {
          "name": "country_code",
          "type": "STRING",
          "nullable": true,
          "description": "ISO 3166-1 alpha-2 country code",
          "stats": {"cardinality": 89, "null_pct": 0.02, "min": "AR", "max": "ZW"}
        },
        {
          "name": "last_active_at",
          "type": "TIMESTAMP",
          "nullable": true,
          "description": "Last login or API activity timestamp",
          "stats": {"null_pct": 0.05, "min": "2023-01-01", "max": "2026-03-18"}
        }
      ],
      "relationships": [
        {
          "source_column": "id",
          "target_table": "events",
          "target_column": "user_id",
          "type": "inferred",
          "confidence": 0.95
        }
      ],
      "sample_data": [
        {"id": "abc-123", "country_code": "EC", "last_active_at": "2026-03-17T10:30:00Z"},
        {"id": "def-456", "country_code": "US", "last_active_at": "2026-03-10T08:15:00Z"}
      ]
    }
  ]
}
```

### .to_prompt() output (standard level, same data)

```
DATABASE SCHEMA CONTEXT
Source: bigquery://my-project.analytics
Tables included: 3 of 47 (filtered by relevance to: "monthly active users by country")

TABLE: users
Description: Core user accounts with registration and profile data
Row count: 1,240,000
Domains: sales, users, marketing

Columns:
  - id (STRING, PK, NOT NULL): Unique user identifier (UUID) [cardinality: 1,240,000]
  - country_code (STRING, NULLABLE): ISO 3166-1 alpha-2 country code [cardinality: 89, 2% nulls]
  - last_active_at (TIMESTAMP, NULLABLE): Last login or API activity timestamp [5% nulls, range: 2023-01-01 to 2026-03-18]

Relationships:
  - users.id → events.user_id (inferred, confidence: 0.95)

Sample rows:
  | id      | country_code | last_active_at           |
  | abc-123 | EC           | 2026-03-17T10:30:00Z     |
  | def-456 | US           | 2026-03-10T08:15:00Z     |
```

---

## Public API

```python
from sqlens import SQLens

# --- Initialize from a connector ---
ctx = SQLens.from_bigquery(project="my-project", dataset="analytics")
# Future: SQLens.from_postgresql(connection_string="...")

# --- Enrich (composable, incremental) ---
ctx.enrich(
    descriptions=True,     # rule-based default
    stats=True,            # column-level stats
    relations=True,        # inferred FKs
    samples=5,             # N rows per table
    domains=True,          # auto-tag tables by business domain
)

# With LLM for descriptions:
ctx.enrich(
    descriptions=lambda prompt: anthropic_client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=200,
        messages=[{"role": "user", "content": prompt}]
    ).content[0].text,
)

# Manual domain overrides:
ctx.set_domain("orders", ["sales", "finance"])
ctx.set_domain("users", ["sales", "users", "marketing"])
ctx.set_domain("campaign_clicks", ["marketing"])
ctx.set_domain("audit_log", ["ops", "security"])

# --- Persist / Load ---
ctx.save("./catalog.json")
ctx = SQLens.load("./catalog.json")

# --- Retrieve context for a query ---
context = ctx.get_context(
    "monthly active users by country",
    max_tables=5,
    level="standard",      # compact | standard | full
)

# Domain-scoped retrieval (pre-filter before vector search):
context = ctx.get_context(
    "revenue by product category",
    max_tables=5,
    domain="sales",        # only search within "sales" domain tables
)

# Auto-detect domain from query (classify then filter):
context = ctx.get_context(
    "ventas en Ecuador último trimestre",
    max_tables=5,
    domain="auto",         # auto-classify query → domain → filter → search
)

# Output as dict
data = context.to_dict()

# Output as LLM-optimized text
prompt_text = context.to_prompt()

# Inspect retrieval metadata
print(context.metadata["retrieval_method"])       # "keyword" | "cosine" | "vector_db"
print(context.metadata["domain_filter_applied"])  # "sales" | None
print(context.metadata["tables_after_domain_filter"])  # 12

# Force a specific retrieval method
context = ctx.get_context(query, retrieval="vector")

# --- Domain inspection ---
print(ctx.domains)                     # ["sales", "users", "marketing", "ops", ...]
print(ctx.tables_in_domain("sales"))   # ["orders", "order_items", "products", ...]

# --- Full catalog (small schemas) ---
full = ctx.to_dict(level="full")
full_prompt = ctx.to_prompt(level="compact")

# --- Inspect catalog state ---
print(ctx.table_count)             # 47
print(ctx.enrichers_applied)       # ["descriptions", "stats", "relations", "samples", "domains"]
print(ctx.tables)                  # list of table names
print(ctx.fingerprint("users"))    # "a3f8c2d1..."
```

---

## Retrieval cascade

The retrieval pipeline has two stages: an optional domain pre-filter, followed by the auto-detected search strategy.

### Stage 1 — Domain filter (optional)

When `domain` is specified in `get_context()`, the catalog is pre-filtered before any vector/keyword search happens:

```
domain=None     → skip filter, search all tables (default)
domain="sales"  → filter catalog to only tables tagged with "sales"
domain="auto"   → classify the query to detect domain, then filter
```

The `domain="auto"` classifier works in two tiers:
1. Keyword matching against domain names (zero deps): "ventas"/"revenue"/"sales" → "sales"
2. If an LLM callable is available, a short classification prompt (optional, higher accuracy)

### Stage 2 — Search strategy (auto-detected)

The retriever auto-detects the best available strategy on the (possibly filtered) table set:

```
1. Check: chromadb or lancedb installed?
   YES → VectorDBRetriever (semantic search, ANN index)
   NO  ↓

2. Check: numpy installed?
   YES → NumpyCosineRetriever (cosine similarity on pre-computed embeddings)
   NO  ↓

3. Fallback → KeywordRetriever (TF-IDF token matching, zero deps)
```

### Full cascade example

```
Query: "ventas en Ecuador último trimestre"
domain="auto"
                    ▼
Domain classifier: "ventas" → domain "sales"
                    ▼
Catalog: 83 tables → filter to "sales" → 12 tables
                    ▼
Vector search on 12 tables (not 83)
                    ▼
Top 5: orders, order_items, users, products, payments
                    ▼
Context output (enriched metadata for these 5 tables)
```

Installation shortcuts:

```bash
pip install sqlens                        # keyword only
pip install sqlens[vector]                # + chromadb + sentence-transformers
pip install sqlens[numpy]                 # + numpy (cosine retrieval)
pip install sqlens[all]                   # everything
```

---

## Fingerprinting & caching

Each table gets a fingerprint = hash of its structure (column names + types + PKs + FKs).

```python
import hashlib, json

def compute_fingerprint(table: Table) -> str:
    structure = {
        "name": table.name,
        "columns": [(c.name, c.data_type, c.nullable, c.is_primary_key)
                     for c in table.columns],
        "explicit_fks": [(r.source_column, r.target_table, r.target_column)
                          for r in table.relationships if r.type == "explicit"]
    }
    return hashlib.sha256(json.dumps(structure, sort_keys=True).encode()).hexdigest()[:16]
```

On re-enrichment:
1. Introspect current schema
2. Compare fingerprints with cached catalog
3. Only re-enrich tables where fingerprint changed or is new
4. Remove tables that no longer exist
5. Preserve enrichment data for unchanged tables

---

## Description heuristics (rule-based)

The default describer uses a layered approach:

1. **Abbreviation dictionary**: `usr` → user, `acct` → account, `bal` → balance, `dt` → date, `amt` → amount, `qty` → quantity, `desc` → description, `addr` → address, `num` → number, `pct` → percent, `ts` → timestamp, `txn` → transaction, etc.

2. **Naming pattern detection**: `created_at` → "creation timestamp", `is_active` → "boolean flag for active status", `*_id` → "foreign key reference to [table]", `*_count` → "count of [entity]"

3. **Type-based inference**: TIMESTAMP → "timestamp", BOOLEAN → "boolean flag", FLOAT/NUMERIC → "numeric value", ARRAY → "list of values"

4. **Combination**: `usr_acct_bal_dt` → split by `_` → expand abbreviations → "user account balance date"

5. **Fallback**: if no heuristic matches, leave description as null. The LLM callable fills in remaining nulls if provided.

---

## Domain-scoped retrieval

### Problem

On large schemas (80+ tables), vector search across all tables produces noise. A query about "sales in Ecuador" might return `audit_log` (which has an `amount` column) alongside `orders`. The more tables in the search space, the lower the precision.

### Solution

Tables are tagged with business domains during enrichment. At retrieval time, an optional domain filter reduces the search space before vector/keyword search runs. This is not intent detection for routing (that belongs in the application layer) — it is a retrieval optimization that narrows the candidate set.

### Domain tagging (enrichment phase)

The `DomainsEnricher` auto-tags tables using a layered heuristic:

1. **Table name patterns**: `order*`, `invoice*`, `payment*` → "sales"; `user*`, `account*` → "users"; `campaign*`, `ad_*` → "marketing"; `log_*`, `audit_*` → "ops"

2. **Column signature detection**: tables with `amount`/`price`/`total`/`revenue` columns → "finance"; tables with `click`/`impression`/`ctr` → "marketing"; tables with `email`/`phone`/`address` → "users"

3. **Relationship propagation**: if `order_items` has a FK to `orders`, it inherits the "sales" domain. If `user_preferences` has a FK to `users`, it inherits "users".

4. **Manual overrides**: the user can set, add, or remove domains per table. Manual assignments always take precedence over auto-detected ones.

5. **LLM fallback** (optional): if a callable is available, tables that couldn't be classified by heuristics get a short LLM classification prompt.

Tables can belong to multiple domains — `users` might be tagged with both "sales" and "marketing" because it's relevant to queries in both areas.

### Domain filter (retrieval phase)

The `DomainFilter` sits between the catalog and the retriever. It accepts three modes via the `domain` parameter in `get_context()`:

```python
# No filter — search all tables (default, backwards compatible)
ctx.get_context("revenue by region", domain=None)

# Explicit domain — user knows which domain to search
ctx.get_context("revenue by region", domain="sales")

# Auto-detect — classify the query, then filter
ctx.get_context("revenue by region", domain="auto")
```

The auto-detect classifier has two tiers:

**Tier 1 — Keyword matching (zero deps):** A dictionary maps common terms to domains. "ventas", "revenue", "orders", "sales", "compras" → "sales". "usuarios", "accounts", "signup" → "users". "campaigns", "ads", "clicks" → "marketing". Multilingual mappings are included (Spanish + English at minimum). If multiple domains match, all are included (union).

**Tier 2 — LLM classifier (optional):** If an LLM callable was provided during enrichment, the classifier sends a short prompt: "Given these domains: [sales, users, marketing, ops, finance]. Which domain(s) is this query about: '{query}'. Return only the domain name(s)." This is a single, cheap LLM call (~50 tokens) that runs before the heavier vector search.

### Impact by schema size

| Schema size | Without domain filter | With domain filter |
|-------------|----------------------|--------------------|
| < 30 tables | Minimal difference | Not needed |
| 30-100 tables | Some noise in results | Reduces search space by ~70-80% |
| 100-500 tables | Significant precision loss | Critical for usable results |
| 500+ tables | Vector search struggles | Essential — makes retrieval viable |

### Output metadata

The `RetrievalResult` includes domain filter diagnostics so the consumer can inspect what happened:

```json
{
  "metadata": {
    "retrieval_method": "cosine",
    "domain_filter_applied": "sales",
    "total_tables_in_catalog": 83,
    "tables_after_domain_filter": 12,
    "tables_included": 5
  }
}
```

---

## Testing strategy

```
tests/
├── fixtures/
│   └── ecommerce_catalog.json     # 10-15 table e-commerce schema
├── unit/
│   ├── test_introspection.py      # MemoryConnector-based
│   ├── test_descriptions.py       # rule-based heuristics
│   ├── test_stats.py              # stats collector
│   ├── test_relations.py          # relationship inference
│   ├── test_samples.py            # sample selector
│   ├── test_domains.py            # domain auto-tagging + manual overrides
│   ├── test_domain_filter.py      # domain filter + auto-detect classifier
│   ├── test_catalog.py            # persistence, fingerprinting, levels
│   ├── test_retrieval.py          # all 3 retriever tiers
│   └── test_serializers.py        # to_dict, to_prompt, level filtering
├── integration/
│   └── test_bigquery.py           # real BQ, CI only (@pytest.mark.integration)
└── evals/
    ├── retrieval_accuracy.py      # (query, expected_tables) eval set
    └── domain_classification.py   # (query, expected_domain) eval set
```

---

## Roadmap

| Version | Scope | Estimated time |
|---------|-------|---------------|
| v0.1 | BigQuery connector + introspection + catalog (JSON) + fingerprinting | 2-3 weeks |
| v0.2 | Enrichment pipeline: stats, samples, relations, rule-based descriptions | 2-3 weeks |
| v0.3 | Retrieval: keyword + numpy cosine + vector DB cascade | 2 weeks |
| v0.3.5 | Domain-scoped retrieval: domain tagging enricher + domain filter + auto-detect classifier | 1-2 weeks |
| v0.4 | LLM descriptions (callable) + .to_prompt() serializer | 1-2 weeks |
| v0.5 | PostgreSQL connector (validate abstraction works) | 2 weeks |
| v0.6 | CLI tool, documentation, PyPI publish | 1-2 weeks |

---

## Dependencies

### Core (zero heavy deps)
- Python >= 3.10
- Standard library only for keyword retrieval

### Connector extras
- `sqlens[bigquery]` → google-cloud-bigquery
- `sqlens[postgresql]` → psycopg2-binary (v0.5)

### Retrieval extras
- `sqlens[numpy]` → numpy
- `sqlens[vector]` → chromadb or lancedb + sentence-transformers

### Development
- pytest, pytest-asyncio
- ruff (linting)
- mypy (type checking)
