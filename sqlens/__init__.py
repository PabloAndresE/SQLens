"""sqlens — Schema intelligence layer for LLMs.

Generate enriched database context, not SQL. sqlens introspects your schema,
enriches it with descriptions, stats, relationships, samples, and domain tags,
then retrieves only the relevant tables for any natural language query.

Usage:
    from sqlens import SQLens

    ctx = SQLens.from_bigquery(project="my-project", dataset="analytics")
    ctx.enrich(descriptions=True, stats=True, relations=True, samples=3, domains=True)
    ctx.save("./catalog.json")

    context = ctx.get_context("monthly active users by country", max_tables=5)
    print(context.to_prompt())
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

from sqlens.catalog.models import Catalog, RetrievalResult
from sqlens.catalog.serializers import catalog_to_prompt
from sqlens.catalog.store import load_catalog, merge_catalogs, save_catalog
from sqlens.connectors.base import ConnectorProtocol
from sqlens.enrichment.base import EnricherProtocol
from sqlens.enrichment.descriptions import DescriptionsEnricher
from sqlens.enrichment.domains import DomainsEnricher
from sqlens.enrichment.relations import RelationsEnricher
from sqlens.enrichment.samples import SamplesEnricher
from sqlens.enrichment.stats import StatsEnricher
from sqlens.introspection.engine import IntrospectionEngine
from sqlens.retrieval.base import RetrieverProtocol
from sqlens.retrieval.domain_filter import classify_query_domain, filter_catalog_by_domain
from sqlens.retrieval.keyword import KeywordRetriever


class SQLens:
    """Main entry point for sqlens.

    Orchestrates the full pipeline: introspection → enrichment → persistence
    → retrieval → context output.
    """

    def __init__(self, catalog: Catalog, connector: ConnectorProtocol | None = None) -> None:
        self._catalog = catalog
        self._connector = connector
        self._retriever: RetrieverProtocol | None = None
        self._retriever_method: str | None = None  # effective method of cached retriever
        self._embedding_fn: Callable[[str], list[float]] | None = None  # cached model instance
        self._llm_callable: Callable[[str], str] | None = None

    # ------------------------------------------------------------------
    # Factory methods
    # ------------------------------------------------------------------

    @classmethod
    def from_bigquery(
        cls,
        project: str,
        dataset: str,
        billing_project: str | None = None,
        credentials: Any = None,
    ) -> SQLens:
        """Create a SQLens instance connected to BigQuery.

        Args:
            project: GCP project where the data lives.
            dataset: BigQuery dataset name.
            billing_project: GCP project for billing. Required for public datasets.
            credentials: Optional google.auth credentials.
        """
        from sqlens.connectors.bigquery import BigQueryConnector

        connector = BigQueryConnector(
            project=project,
            dataset=dataset,
            billing_project=billing_project,
            credentials=credentials,
        )
        engine = IntrospectionEngine(connector)
        catalog = engine.introspect(source=connector.source)
        return cls(catalog=catalog, connector=connector)

    @classmethod
    def from_postgresql(
        cls,
        connection_string: str,
        schema: str = "public",
    ) -> SQLens:
        """Create a SQLens instance connected to a PostgreSQL database.

        Args:
            connection_string: A libpq connection string.
                e.g. "postgresql://user:pass@host:5432/dbname"
                or   "host=localhost dbname=mydb user=postgres"
            schema: PostgreSQL schema to introspect. Defaults to 'public'.
        """
        from sqlens.connectors.postgresql import PostgreSQLConnector

        connector = PostgreSQLConnector(
            connection_string=connection_string,
            schema=schema,
        )
        engine = IntrospectionEngine(connector)
        catalog = engine.introspect(source=connector.source)
        return cls(catalog=catalog, connector=connector)

    @classmethod
    def from_sqlite(cls, path: str | Path) -> SQLens:
        """Create a SQLens instance connected to a SQLite database.

        Args:
            path: Path to the SQLite database file. Use ":memory:" for in-memory DBs.
        """
        from sqlens.connectors.sqlite import SQLiteConnector

        connector = SQLiteConnector(path=path)
        engine = IntrospectionEngine(connector)
        catalog = engine.introspect(source=connector.source)
        return cls(catalog=catalog, connector=connector)

    @classmethod
    def from_mysql(
        cls,
        connection_string: str,
        database: str | None = None,
    ) -> SQLens:
        """Create a SQLens instance connected to a MySQL / MariaDB database.

        Args:
            connection_string: A MySQL connection URI.
                e.g. "mysql://user:pass@host:3306/dbname"
            database: Database name to introspect. If None, extracted from the URI.
        """
        from sqlens.connectors.mysql import MySQLConnector

        connector = MySQLConnector(
            connection_string=connection_string,
            database=database,
        )
        engine = IntrospectionEngine(connector)
        catalog = engine.introspect(source=connector.source)
        return cls(catalog=catalog, connector=connector)

    @classmethod
    def from_connector(cls, connector: ConnectorProtocol, source: str = "") -> SQLens:
        """Create a SQLens instance from any ConnectorProtocol implementation."""
        src = source or getattr(connector, "source", "custom://unknown")
        engine = IntrospectionEngine(connector)
        catalog = engine.introspect(source=src)
        return cls(catalog=catalog, connector=connector)

    @classmethod
    def load(cls, path: str | Path) -> SQLens:
        """Load a previously saved catalog from disk.

        Note: no connector is attached — enrichment that requires DB queries
        won't work until a connector is provided via .set_connector().
        """
        catalog = load_catalog(path)
        return cls(catalog=catalog)

    # ------------------------------------------------------------------
    # Enrichment
    # ------------------------------------------------------------------

    def enrich(
        self,
        descriptions: bool | Callable[[str], str] = False,
        stats: bool = False,
        relations: bool = False,
        samples: int | bool = False,
        domains: bool | dict[str, list[str]] = False,
    ) -> SQLens:
        """Run enrichment pipeline on the catalog.

        Args:
            descriptions: True for rule-based, or a callable (str)->str for LLM.
            stats: Collect column-level statistics.
            relations: Infer implicit foreign key relationships.
            samples: Number of sample rows per table, or False to skip.
            domains: True for auto-detect, or a dict of manual overrides.

        Returns:
            self (for chaining).
        """
        enrichers: list[EnricherProtocol] = []

        if descriptions is not False:
            llm = descriptions if callable(descriptions) else None
            self._llm_callable = llm
            enrichers.append(DescriptionsEnricher(llm_callable=llm))

        if stats:
            enrichers.append(StatsEnricher())

        if relations:
            enrichers.append(RelationsEnricher())

        if samples is not False:
            n = samples if isinstance(samples, int) else 3
            enrichers.append(SamplesEnricher(n=n))

        if domains is not False:
            overrides = domains if isinstance(domains, dict) else None
            enrichers.append(DomainsEnricher(
                overrides=overrides,
                llm_callable=self._llm_callable,
            ))

        connector = self._connector
        for enricher in enrichers:
            if connector is None and enricher.name() in ("stats", "samples"):
                continue  # skip DB-dependent enrichers if no connector
            self._catalog = enricher.enrich(
                self._catalog,
                connector,  # type: ignore[arg-type]
            )

        # Rebuild retriever index after enrichment
        self._retriever = None
        self._retriever_method = None

        return self

    # ------------------------------------------------------------------
    # Domain management
    # ------------------------------------------------------------------

    def set_domain(self, table_name: str, domains: list[str]) -> SQLens:
        """Manually set domain tags for a table."""
        table = self._catalog.get_table(table_name)
        if table is None:
            raise ValueError(f"Table '{table_name}' not found in catalog")
        table.domains = sorted(domains)
        return self

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def save(self, path: str | Path) -> None:
        """Save the catalog to a JSON file."""
        save_catalog(self._catalog, path)

    def refresh(self) -> SQLens:
        """Re-introspect the database and merge with cached enrichment.

        Only re-enriches tables whose structure (fingerprint) changed.
        Requires a connector to be attached.
        """
        if self._connector is None:
            raise RuntimeError("No connector attached. Use set_connector() first.")

        engine = IntrospectionEngine(self._connector)
        source = getattr(self._connector, "source", self._catalog.source)
        new_catalog = engine.introspect(source=source)
        self._catalog = merge_catalogs(old=self._catalog, new=new_catalog)
        self._retriever = None
        return self

    def set_connector(self, connector: ConnectorProtocol) -> SQLens:
        """Attach a connector to a loaded catalog."""
        self._connector = connector
        return self

    # ------------------------------------------------------------------
    # Retrieval
    # ------------------------------------------------------------------

    def get_context(
        self,
        query: str,
        max_tables: int = 5,
        level: str = "standard",
        domain: str | None = None,
        retrieval: str | None = None,
    ) -> RetrievalResult:
        """Retrieve relevant schema context for a natural language query.

        Args:
            query: Natural language query (e.g., "revenue by country").
            max_tables: Maximum number of tables to return.
            level: Detail level — "compact", "standard", or "full".
            domain: Domain filter — None (no filter), a domain name, or "auto".
            retrieval: Force a retrieval method — "keyword", "cosine", "vector".
                If None, auto-detects the best available.

        Returns:
            RetrievalResult with enriched metadata for the relevant tables.
        """
        retriever = self._resolve_retriever(retrieval)

        # Build index if needed (retriever is a new instance, not the cached one)
        if retriever is not self._retriever:
            retriever.build_index(self._catalog)
            self._retriever = retriever
            try:
                from sqlens.retrieval.cosine import NumpyCosineRetriever
                self._retriever_method = (
                    "cosine" if isinstance(retriever, NumpyCosineRetriever)
                    else "keyword"
                )
            except ImportError:
                self._retriever_method = "keyword"

        # Domain filtering
        candidate_tables = None
        domain_applied = None
        tables_after_filter = None

        if domain is not None:
            resolved_domain: str | None = domain
            if domain == "auto":
                resolved_domain = classify_query_domain(
                    query,
                    self._catalog.domains,
                    llm_callable=self._llm_callable,
                )

            if resolved_domain and resolved_domain != "auto":
                candidate_tables = filter_catalog_by_domain(self._catalog, resolved_domain)
                domain_applied = resolved_domain
                tables_after_filter = len(candidate_tables)

        result = retriever.retrieve(
            query=query,
            max_tables=max_tables,
            candidate_tables=candidate_tables,
        )

        # Attach domain filter metadata
        result.domain_filter_applied = domain_applied
        result.tables_after_domain_filter = tables_after_filter

        return result

    def _resolve_retriever(self, forced: str | None = None) -> RetrieverProtocol:
        """Resolve the best available retriever (auto-detect cascade).

        Cascade order:
          1. NumpyCosineRetriever (sentence-transformers) — semantic search
          2. KeywordRetriever — always available, zero deps

        forced="keyword"  → always keyword
        forced="cosine"   → cosine or ImportError if sentence-transformers missing
        forced="vector"   → must use set_retriever() (requires user-configured embed fn)
        """
        if forced == "vector":
            raise NotImplementedError(
                "Vector retriever requires a configured embedding function. "
                "Use SQLens.set_retriever(VectorDBRetriever(embedding_fn=...)) to configure it."
            )

        # Reuse cached retriever: no forced override, or forced matches cached method
        if self._retriever is not None:
            if forced is None or forced == self._retriever_method:
                return self._retriever

        if forced == "keyword":
            return KeywordRetriever()

        # forced="cosine" or auto-detect
        try:
            from sqlens.retrieval.cosine import NumpyCosineRetriever, _build_default_embedding_fn
            # Cache the embedding fn so the model is only loaded once per SQLens instance
            if self._embedding_fn is None:
                self._embedding_fn = _build_default_embedding_fn()
            retriever = NumpyCosineRetriever(embedding_fn=self._embedding_fn)
            if retriever.is_available():
                return retriever
        except ImportError:
            if forced == "cosine":
                raise  # surface the error when user explicitly asked for cosine
            # else: fall through to keyword

        return KeywordRetriever()

    def set_retriever(self, retriever: RetrieverProtocol) -> SQLens:
        """Manually set the retriever (e.g., with a configured embedding function)."""
        retriever.build_index(self._catalog)
        self._retriever = retriever
        return self

    # ------------------------------------------------------------------
    # Convenience accessors
    # ------------------------------------------------------------------

    @property
    def table_count(self) -> int:
        return self._catalog.table_count

    @property
    def tables(self) -> list[str]:
        return self._catalog.table_names

    @property
    def enrichers_applied(self) -> list[str]:
        return self._catalog.enrichers_applied

    @property
    def domains(self) -> list[str]:
        return self._catalog.domains

    @property
    def catalog(self) -> Catalog:
        return self._catalog

    def tables_in_domain(self, domain: str) -> list[str]:
        return self._catalog.tables_in_domain(domain)

    def get_table(self, name: str) -> Any | None:
        return self._catalog.get_table(name)

    def fingerprint(self, table_name: str) -> str | None:
        table = self._catalog.get_table(table_name)
        return table.fingerprint if table else None

    def to_dict(self, level: str = "standard") -> dict[str, Any]:
        return self._catalog.to_dict(level)

    def to_prompt(self, level: str = "standard") -> str:
        return catalog_to_prompt(self._catalog, level)


__all__ = ["SQLens"]
__version__ = "0.7.0"
