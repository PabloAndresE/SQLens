# Changelog

All notable changes to sqlens are documented here.

## [0.6.0] — 2026-03-26

### Added
- CLI tool (`sqlens inspect`, `sqlens enrich`, `sqlens context`) with `--verbose` flag
- `sqlens/cli.py` — three subcommands via argparse, no extra dependencies

### Changed
- Updated README with PostgreSQL quickstart, CLI section, cosine retrieval section, Gemini LLM example, PK heuristic documentation
- Updated ARCHITECTURE.md with decisions #13–15, PK heuristic section, dialect-aware stats section, updated test counts

---

## [0.5.0] — 2026-03-25

### Added
- `PostgreSQLConnector` — full connector using `information_schema` views and psycopg2
- `SQLens.from_postgresql(connection_string, schema)` factory method
- `get_column_stats()` optional method on `ConnectorProtocol` (non-abstract, returns `None` by default)
- PostgreSQL dialect-aware stats: `COUNT(DISTINCT …)` with standard SQL casts
- 11 new unit tests for `PostgreSQLConnector` using psycopg2 mocking

### Changed
- `StatsEnricher` now calls `connector.get_column_stats()` first; falls back to BigQuery queries only if `None` is returned
- `RelationsEnricher._find_target_pk()` now accepts any PK (not just single-PK tables)
- `pyproject.toml`: added `psycopg2-binary` to `[postgresql]` and `[all]` extras

---

## [0.4.0] — 2026-03-22

### Added
- PK heuristic fallback in `IntrospectionEngine` for databases without PK constraints (e.g., BigQuery)
  - Rule 1: column named exactly `id`
  - Rule 2: column named `{singular_table}_id`
  - Rule 3: first NOT NULL column with `_id` suffix
- `table.metadata["pk_source"]` — `"database"` vs `"inferred"` provenance tracking
- `scripts/test_llm_descriptions.py` — validates LLM descriptions via Google Gemini API

### Changed
- `IntrospectionEngine._singularize()` handles `-ies`, `-ses/-xes/-zes`, and `-s` patterns

---

## [0.3.5] — 2026-03-20

### Added
- Embedding model caching on `SQLens` instance (`self._embedding_fn`, `self._retriever_method`)
- `_resolve_retriever()` returns cached retriever via identity check — eliminates per-call model reloads (~4x speedup on `compare_retrievers.py`)
- 18 new unit tests for `NumpyCosineRetriever` and retrieval cascade

### Fixed
- `NumpyCosineRetriever` candidate filter: changed sentinel from `-1.0` to `-np.inf`; non-candidate tables are now skipped with `continue` instead of `break`, fixing domain-scoped retrieval with cosine

---

## [0.3.0] — 2026-03-18

### Added
- `KeywordRetriever` — TF-IDF token matching, zero dependencies
- `NumpyCosineRetriever` — cosine similarity using numpy + optional sentence-transformers
- `VectorDBRetriever` — chromadb/lancedb semantic search (lazy import)
- Auto-detect cascade: VectorDB → Numpy cosine → Keyword
- `DomainFilter` — pre-filter tables by business domain before retrieval
- `domain="auto"` classifier — keyword matching + optional LLM tier
- `scripts/compare_retrievers.py` — benchmarks all three strategies

---

## [0.2.0] — 2026-03-10

### Added
- `DescriptionsEnricher` — rule-based heuristics + optional LLM callable
- `StatsEnricher` — cardinality, null%, min/max, top values
- `RelationsEnricher` — infers implicit foreign keys from naming patterns
- `SamplesEnricher` — N representative rows per table
- `DomainsEnricher` — auto-tags tables by business domain using name + column patterns + relationship propagation
- `EnricherProtocol` (ABC) — standard interface for all enrichers
- Fingerprinting: SHA-256 hash of table structure for incremental enrichment

---

## [0.1.0] — 2026-03-01

### Added
- `BigQueryConnector` — introspects BigQuery using `information_schema`
- `IntrospectionEngine` — parallel table introspection via `ThreadPoolExecutor`
- `Catalog` — JSON persistence with fingerprints
- `ConnectorProtocol` (ABC) — standard interface for database connectors
- `Table`, `Column`, `Relationship`, `RetrievalResult` dataclasses
- `.to_dict()`, `.to_prompt()` serializers with compact/standard/full level filtering
- `MemoryConnector` for unit testing
- `scripts/validate_bigquery.py` — end-to-end validation against thelook_ecommerce
