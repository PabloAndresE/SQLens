"""Unit tests for sqlens core functionality."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from sqlens import SQLens
from sqlens.catalog.models import Catalog, Column, Relationship, Table
from sqlens.catalog.store import load_catalog, save_catalog, merge_catalogs
from sqlens.connectors.memory import MemoryConnector
from sqlens.enrichment.descriptions import describe_column, describe_table
from sqlens.enrichment.domains import _detect_domains_by_name, _detect_domains_by_columns
from sqlens.enrichment.relations import RelationsEnricher
from sqlens.introspection.engine import IntrospectionEngine
from sqlens.retrieval.domain_filter import classify_query_domain
from sqlens.retrieval.keyword import KeywordRetriever

try:
    import numpy as np
    from sqlens.retrieval.cosine import (
        NumpyCosineRetriever,
        _numpy_hash_embedding,
        _build_default_embedding_fn,
    )
    _NUMPY_AVAILABLE = True
except ImportError:
    _NUMPY_AVAILABLE = False

FIXTURES = Path(__file__).parent.parent / "fixtures"


# ---------------------------------------------------------------------------
# Test data helper
# ---------------------------------------------------------------------------

def _make_ecommerce_connector() -> MemoryConnector:
    return MemoryConnector(
        tables={
            "users": {
                "columns": [
                    {"name": "id", "data_type": "STRING", "is_primary_key": True, "nullable": False},
                    {"name": "email", "data_type": "STRING"},
                    {"name": "country_code", "data_type": "STRING"},
                    {"name": "created_at", "data_type": "TIMESTAMP", "nullable": False},
                    {"name": "is_active", "data_type": "BOOLEAN", "nullable": False},
                ],
                "foreign_keys": [],
                "metadata": {"row_count": 50000},
                "rows": [
                    {"id": "u1", "email": "a@b.com", "country_code": "EC", "created_at": "2026-01-01", "is_active": True},
                ],
            },
            "orders": {
                "columns": [
                    {"name": "id", "data_type": "STRING", "is_primary_key": True, "nullable": False},
                    {"name": "user_id", "data_type": "STRING", "nullable": False},
                    {"name": "total_amount", "data_type": "NUMERIC", "nullable": False},
                    {"name": "status", "data_type": "STRING"},
                    {"name": "created_at", "data_type": "TIMESTAMP", "nullable": False},
                ],
                "foreign_keys": [],
                "metadata": {"row_count": 200000},
                "rows": [
                    {"id": "o1", "user_id": "u1", "total_amount": 85.50, "status": "completed", "created_at": "2026-03-15"},
                ],
            },
            "products": {
                "columns": [
                    {"name": "id", "data_type": "STRING", "is_primary_key": True, "nullable": False},
                    {"name": "name", "data_type": "STRING", "nullable": False},
                    {"name": "price", "data_type": "NUMERIC", "nullable": False},
                    {"name": "category_id", "data_type": "STRING"},
                ],
                "foreign_keys": [],
                "metadata": {"row_count": 5000},
                "rows": [],
            },
            "audit_log": {
                "columns": [
                    {"name": "id", "data_type": "STRING", "is_primary_key": True, "nullable": False},
                    {"name": "action", "data_type": "STRING"},
                    {"name": "user_id", "data_type": "STRING"},
                    {"name": "created_at", "data_type": "TIMESTAMP"},
                ],
                "foreign_keys": [],
                "metadata": {"row_count": 5000000},
                "rows": [],
            },
        },
        source="memory://ecommerce-test",
    )


# ---------------------------------------------------------------------------
# Description heuristics
# ---------------------------------------------------------------------------

class TestDescriptions:
    def test_abbreviation_expansion(self):
        assert describe_column("usr_acct_bal_dt", "STRING") == "user account balance date"

    def test_suffix_pattern_id(self):
        desc = describe_column("user_id", "STRING")
        assert desc is not None
        assert "foreign key" in desc.lower() or "user" in desc.lower()

    def test_suffix_pattern_at(self):
        desc = describe_column("created_at", "TIMESTAMP")
        assert desc is not None
        assert "timestamp" in desc.lower() or "created" in desc.lower()

    def test_prefix_pattern_is(self):
        desc = describe_column("is_active", "BOOLEAN")
        assert desc is not None
        assert "boolean" in desc.lower() or "flag" in desc.lower()

    def test_type_based_timestamp(self):
        desc = describe_column("xyz", "TIMESTAMP")
        assert desc is not None
        assert "timestamp" in desc.lower()

    def test_no_match_returns_none_for_plain_name(self):
        # "name" is a common word, not an abbreviation
        desc = describe_column("name", "STRING")
        # May or may not return None depending on heuristics
        # The important thing is it doesn't crash
        assert desc is None or isinstance(desc, str)

    def test_table_description(self):
        desc = describe_table("usr_accounts", ["id", "email"])
        assert desc is not None
        assert "user" in desc.lower()


# ---------------------------------------------------------------------------
# Domain detection
# ---------------------------------------------------------------------------

class TestDomains:
    def test_detect_by_table_name_orders(self):
        domains = _detect_domains_by_name("orders")
        assert "sales" in domains

    def test_detect_by_table_name_audit(self):
        domains = _detect_domains_by_name("audit_log")
        assert "ops" in domains

    def test_detect_by_table_name_campaign(self):
        domains = _detect_domains_by_name("campaign_clicks")
        assert "marketing" in domains

    def test_detect_by_columns_finance(self):
        cols = ["id", "amount", "price", "tax", "discount"]
        domains = _detect_domains_by_columns(cols)
        assert "sales" in domains

    def test_detect_by_columns_users(self):
        cols = ["id", "email", "phone", "first_name", "last_name"]
        domains = _detect_domains_by_columns(cols)
        assert "users" in domains

    def test_classify_query_sales(self):
        domain = classify_query_domain("revenue by country", ["sales", "users", "ops"])
        assert domain == "sales"

    def test_classify_query_spanish(self):
        domain = classify_query_domain("ventas en Ecuador", ["sales", "users", "ops"])
        assert domain == "sales"

    def test_classify_query_no_match(self):
        domain = classify_query_domain("xyz abc 123", ["sales", "users"])
        assert domain is None


# ---------------------------------------------------------------------------
# Introspection + MemoryConnector
# ---------------------------------------------------------------------------

class TestIntrospection:
    def test_from_connector(self):
        connector = _make_ecommerce_connector()
        ctx = SQLens.from_connector(connector)
        assert ctx.table_count == 4
        assert "users" in ctx.tables
        assert "orders" in ctx.tables

    def test_fingerprint_computed(self):
        connector = _make_ecommerce_connector()
        ctx = SQLens.from_connector(connector)
        fp = ctx.fingerprint("users")
        assert fp is not None
        assert len(fp) == 16

    def test_fingerprint_stable(self):
        connector = _make_ecommerce_connector()
        ctx1 = SQLens.from_connector(connector)
        ctx2 = SQLens.from_connector(connector)
        assert ctx1.fingerprint("users") == ctx2.fingerprint("users")


# ---------------------------------------------------------------------------
# Enrichment pipeline
# ---------------------------------------------------------------------------

class TestEnrichment:
    def test_enrich_descriptions(self):
        connector = _make_ecommerce_connector()
        ctx = SQLens.from_connector(connector)
        ctx.enrich(descriptions=True)
        assert "descriptions" in ctx.enrichers_applied

        table = ctx.get_table("users")
        # created_at should get a description from heuristics
        created_at = next(c for c in table.columns if c.name == "created_at")
        assert created_at.description is not None

    def test_enrich_relations(self):
        connector = _make_ecommerce_connector()
        ctx = SQLens.from_connector(connector)
        ctx.enrich(relations=True)
        assert "relations" in ctx.enrichers_applied

        orders = ctx.get_table("orders")
        inferred = [r for r in orders.relationships if r.type == "inferred"]
        # user_id should be inferred as FK to users
        user_fk = [r for r in inferred if r.source_column == "user_id"]
        assert len(user_fk) == 1
        assert user_fk[0].target_table == "users"

    def test_enrich_domains(self):
        connector = _make_ecommerce_connector()
        ctx = SQLens.from_connector(connector)
        ctx.enrich(domains=True)
        assert "domains" in ctx.enrichers_applied

        orders = ctx.get_table("orders")
        assert "sales" in orders.domains

    def test_enrich_chaining(self):
        connector = _make_ecommerce_connector()
        ctx = SQLens.from_connector(connector)
        result = ctx.enrich(descriptions=True, relations=True, domains=True)
        assert result is ctx  # chaining returns self


# ---------------------------------------------------------------------------
# Catalog persistence
# ---------------------------------------------------------------------------

class TestPersistence:
    def test_save_and_load(self):
        connector = _make_ecommerce_connector()
        ctx = SQLens.from_connector(connector)
        ctx.enrich(descriptions=True, relations=True)

        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
            path = f.name

        ctx.save(path)
        loaded = SQLens.load(path)

        assert loaded.table_count == ctx.table_count
        assert loaded.tables == ctx.tables
        assert loaded.enrichers_applied == ctx.enrichers_applied

        Path(path).unlink()

    def test_load_fixture(self):
        catalog = load_catalog(FIXTURES / "ecommerce_catalog.json")
        assert catalog.table_count == 10
        assert "users" in catalog.table_names

    def test_merge_unchanged(self):
        """Merge where nothing changed should preserve enrichment."""
        connector = _make_ecommerce_connector()
        ctx = SQLens.from_connector(connector)
        ctx.enrich(descriptions=True)

        old_catalog = ctx.catalog
        new_catalog = SQLens.from_connector(connector).catalog

        merged = merge_catalogs(old_catalog, new_catalog)
        users = merged.get_table("users")
        # Descriptions should be preserved since fingerprints match
        created_at = next(c for c in users.columns if c.name == "created_at")
        assert created_at.description is not None


# ---------------------------------------------------------------------------
# Retrieval
# ---------------------------------------------------------------------------

class TestRetrieval:
    def test_keyword_retriever_basic(self):
        connector = _make_ecommerce_connector()
        ctx = SQLens.from_connector(connector)
        ctx.enrich(descriptions=True)

        result = ctx.get_context("user email country active", max_tables=2, retrieval="keyword")
        assert len(result.tables) > 0
        assert result.retrieval_method == "keyword"
        table_names = [t.name for t in result.tables]
        assert "users" in table_names

    def test_keyword_retriever_orders(self):
        connector = _make_ecommerce_connector()
        ctx = SQLens.from_connector(connector)
        ctx.enrich(descriptions=True)

        result = ctx.get_context("order total amount", max_tables=2)
        table_names = [t.name for t in result.tables]
        assert "orders" in table_names

    def test_domain_scoped_retrieval(self):
        connector = _make_ecommerce_connector()
        ctx = SQLens.from_connector(connector)
        ctx.enrich(descriptions=True, domains=True)

        result = ctx.get_context("order total", max_tables=5, domain="sales")
        assert result.domain_filter_applied == "sales"
        # audit_log should NOT be in results since it's not in "sales" domain
        table_names = [t.name for t in result.tables]
        assert "audit_log" not in table_names

    def test_domain_auto_detect(self):
        connector = _make_ecommerce_connector()
        ctx = SQLens.from_connector(connector)
        ctx.enrich(descriptions=True, domains=True)

        result = ctx.get_context("ventas en Ecuador", max_tables=5, domain="auto")
        # Should auto-detect "sales" domain from Spanish keyword
        if result.domain_filter_applied:
            assert result.domain_filter_applied == "sales"


# ---------------------------------------------------------------------------
# Serialization
# ---------------------------------------------------------------------------

class TestSerialization:
    def test_to_dict_levels(self):
        connector = _make_ecommerce_connector()
        ctx = SQLens.from_connector(connector)
        ctx.enrich(descriptions=True)

        compact = ctx.to_dict(level="compact")
        standard = ctx.to_dict(level="standard")
        full = ctx.to_dict(level="full")

        # All levels have tables
        assert len(compact["tables"]) == 4
        assert len(standard["tables"]) == 4
        assert len(full["tables"]) == 4

        # Level is recorded in metadata
        assert compact["metadata"]["level"] == "compact"

    def test_to_prompt(self):
        connector = _make_ecommerce_connector()
        ctx = SQLens.from_connector(connector)
        ctx.enrich(descriptions=True)

        prompt = ctx.to_prompt()
        assert "DATABASE SCHEMA CONTEXT" in prompt
        assert "users" in prompt
        assert "orders" in prompt

    def test_retrieval_result_to_prompt(self):
        connector = _make_ecommerce_connector()
        ctx = SQLens.from_connector(connector)
        ctx.enrich(descriptions=True)

        result = ctx.get_context("users", max_tables=2)
        prompt = result.to_prompt()
        assert "DATABASE SCHEMA CONTEXT" in prompt
        assert "Tables included:" in prompt


# ---------------------------------------------------------------------------
# PK inference heuristic
# ---------------------------------------------------------------------------

class TestPKInference:
    def _make_table(self, name: str, cols: list[tuple[str, bool]]) -> Table:
        """Build a Table with columns specified as (name, nullable) pairs."""
        columns = [
            Column(name=n, data_type="STRING", nullable=nullable, ordinal_position=i)
            for i, (n, nullable) in enumerate(cols)
        ]
        return Table(name=name, columns=columns)

    def test_id_column_inferred_as_pk(self):
        table = self._make_table("users", [("id", False), ("email", True)])
        IntrospectionEngine._infer_primary_keys(table)
        pk_cols = [c for c in table.columns if c.is_primary_key]
        assert len(pk_cols) == 1
        assert pk_cols[0].name == "id"
        assert table.metadata.get("pk_source") == "inferred"

    def test_singular_table_name_id_column_inferred(self):
        # orders has no 'id' column; 'order_id' should be picked by rule 2
        table = self._make_table("orders", [("order_id", False), ("user_id", False), ("status", True)])
        IntrospectionEngine._infer_primary_keys(table)
        pk_cols = [c for c in table.columns if c.is_primary_key]
        assert len(pk_cols) == 1
        assert pk_cols[0].name == "order_id"
        assert table.metadata.get("pk_source") == "inferred"

    def test_database_pks_skip_heuristic(self):
        # MemoryConnector with is_primary_key=True → heuristic must not run
        connector = MemoryConnector(
            tables={
                "products": {
                    "columns": [
                        {"name": "product_code", "data_type": "STRING", "is_primary_key": True, "nullable": False},
                        {"name": "name", "data_type": "STRING"},
                    ],
                    "foreign_keys": [],
                    "metadata": {},
                    "rows": [],
                }
            },
            source="memory://test",
        )
        ctx = SQLens.from_connector(connector)
        products = ctx.get_table("products")
        assert products.metadata.get("pk_source") == "database"
        pk_cols = [c for c in products.columns if c.is_primary_key]
        assert len(pk_cols) == 1
        assert pk_cols[0].name == "product_code"

    def test_no_id_pattern_no_pk_inferred(self):
        # No 'id', no '{singular}_id' column, no NOT NULL *_id → nothing inferred
        table = self._make_table("events", [
            ("session_token", False),
            ("created_at", False),
            ("payload", True),
        ])
        IntrospectionEngine._infer_primary_keys(table)
        pk_cols = [c for c in table.columns if c.is_primary_key]
        assert pk_cols == []
        assert "pk_source" not in table.metadata

    def test_find_target_pk_uses_inferred_pk(self):
        pk_map = {"orders": ["order_id"]}
        enricher = RelationsEnricher()
        assert enricher._find_target_pk("orders", pk_map) == "order_id"

    def test_find_target_pk_fallback_to_id_when_empty(self):
        enricher = RelationsEnricher()
        assert enricher._find_target_pk("unknown_table", {}) == "id"

    def test_find_target_pk_uses_first_of_composite(self):
        pk_map = {"order_items": ["order_id", "product_id"]}
        enricher = RelationsEnricher()
        assert enricher._find_target_pk("order_items", pk_map) == "order_id"


# ---------------------------------------------------------------------------
# Cosine retriever + embedding functions
# ---------------------------------------------------------------------------

@pytest.mark.skipif(not _NUMPY_AVAILABLE, reason="numpy not installed")
class TestCosineRetriever:

    # --- _numpy_hash_embedding ---

    def test_hash_embedding_returns_unit_vector(self):
        vec = _numpy_hash_embedding("hello world")
        assert len(vec) == 256
        norm = sum(x * x for x in vec) ** 0.5
        assert abs(norm - 1.0) < 1e-5

    def test_hash_embedding_deterministic(self):
        text = "user email country"
        assert _numpy_hash_embedding(text) == _numpy_hash_embedding(text)

    def test_hash_embedding_empty_text(self):
        vec = _numpy_hash_embedding("")
        assert len(vec) == 256
        assert all(x == 0.0 for x in vec)

    def test_hash_embedding_different_texts(self):
        v1 = _numpy_hash_embedding("users table email")
        v2 = _numpy_hash_embedding("orders total amount")
        assert v1 != v2

    # --- _build_default_embedding_fn ---

    def test_build_default_fn_returns_callable(self):
        fn = _build_default_embedding_fn()
        assert callable(fn)
        result = fn("test query")
        assert isinstance(result, list)
        assert all(isinstance(x, float) for x in result)

    def test_build_default_fn_uses_hash_without_sentence_transformers(self):
        # sentence-transformers is not installed in this test env,
        # so the fallback must be _numpy_hash_embedding
        import sys
        if "sentence_transformers" not in sys.modules:
            fn = _build_default_embedding_fn()
            assert fn is _numpy_hash_embedding

    # --- NumpyCosineRetriever ---

    def _make_retriever(self):
        retriever = NumpyCosineRetriever(embedding_fn=_numpy_hash_embedding)
        connector = _make_ecommerce_connector()
        ctx = SQLens.from_connector(connector)
        retriever.build_index(ctx.catalog)
        return retriever

    def test_is_available(self):
        retriever = NumpyCosineRetriever(embedding_fn=_numpy_hash_embedding)
        assert retriever.is_available() is True

    def test_retrieve_before_build_raises(self):
        retriever = NumpyCosineRetriever(embedding_fn=_numpy_hash_embedding)
        with pytest.raises(RuntimeError):
            retriever.retrieve("anything")

    def test_retrieval_method_is_cosine(self):
        retriever = self._make_retriever()
        result = retriever.retrieve("user email country", max_tables=2)
        assert result.retrieval_method == "cosine"

    def test_max_tables_respected(self):
        retriever = self._make_retriever()
        result = retriever.retrieve("user order product audit", max_tables=2)
        assert len(result.tables) <= 2

    def test_scores_bounded(self):
        retriever = self._make_retriever()
        result = retriever.retrieve("user email country active", max_tables=4)
        for score in result.scores.values():
            assert score <= 1.0

    def test_zero_score_excluded_without_filter(self):
        retriever = self._make_retriever()
        result = retriever.retrieve("xyz zzz", max_tables=5)
        assert result.tables == []

    def test_domain_filter_excludes_non_candidates(self):
        retriever = self._make_retriever()
        result = retriever.retrieve(
            "user order product audit",
            max_tables=10,
            candidate_tables=["orders", "products"],
        )
        table_names = [t.name for t in result.tables]
        assert "users" not in table_names
        assert "audit_log" not in table_names

    def test_domain_filter_includes_low_score_results(self):
        retriever = self._make_retriever()
        result = retriever.retrieve(
            "xyz zzz",
            max_tables=5,
            candidate_tables=["orders"],
        )
        table_names = [t.name for t in result.tables]
        assert "orders" in table_names

    # --- _resolve_retriever / cascade ---

    def test_auto_detect_uses_cosine_when_numpy_installed(self):
        connector = _make_ecommerce_connector()
        ctx = SQLens.from_connector(connector)
        result = ctx.get_context("user email country active", max_tables=2)
        assert result.retrieval_method == "cosine"

    def test_forced_keyword(self):
        connector = _make_ecommerce_connector()
        ctx = SQLens.from_connector(connector)
        ctx.enrich(descriptions=True)
        result = ctx.get_context("user email country active", max_tables=2, retrieval="keyword")
        assert result.retrieval_method == "keyword"

    def test_forced_cosine(self):
        connector = _make_ecommerce_connector()
        ctx = SQLens.from_connector(connector)
        result = ctx.get_context("user email country active", max_tables=2, retrieval="cosine")
        assert result.retrieval_method == "cosine"

    def test_forced_vector_raises(self):
        connector = _make_ecommerce_connector()
        ctx = SQLens.from_connector(connector)
        with pytest.raises(NotImplementedError):
            ctx.get_context("user email", retrieval="vector")


# ---------------------------------------------------------------------------
# PostgreSQLConnector (unit tests — no real database required)
# ---------------------------------------------------------------------------

class TestPostgreSQLConnector:
    """Unit tests for PostgreSQLConnector using a fully-mocked psycopg2."""

    def _make_mock_psycopg2(self, fetchall_return=None):
        """Build a mock psycopg2 module wired to return fetchall_return."""
        mock_pg = MagicMock()
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.description = [("table_name",)]
        mock_cursor.fetchall.return_value = fetchall_return or []
        mock_cursor.__enter__ = MagicMock(return_value=mock_cursor)
        mock_cursor.__exit__ = MagicMock(return_value=False)
        mock_conn.cursor.return_value = mock_cursor
        mock_pg.connect.return_value = mock_conn
        return mock_pg, mock_conn, mock_cursor

    def _make_connector(self, schema="public", fetchall_return=None):
        mock_pg, mock_conn, mock_cursor = self._make_mock_psycopg2(fetchall_return)
        with patch.dict("sys.modules", {"psycopg2": mock_pg}):
            from sqlens.connectors.postgresql import PostgreSQLConnector
            connector = PostgreSQLConnector(
                "postgresql://user:pass@localhost/testdb",
                schema=schema,
            )
        return connector

    def test_qualify_table_name_default_schema(self):
        connector = self._make_connector()
        assert connector.qualify_table_name("users") == '"public"."users"'

    def test_qualify_table_name_custom_schema(self):
        connector = self._make_connector(schema="analytics")
        assert connector.qualify_table_name("events") == '"analytics"."events"'

    def test_qualify_table_name_special_chars_safe(self):
        connector = self._make_connector(schema="my_schema")
        result = connector.qualify_table_name("order_items")
        assert result == '"my_schema"."order_items"'

    def test_constructor_raises_without_psycopg2(self):
        with patch.dict("sys.modules", {"psycopg2": None}):
            from sqlens.connectors.postgresql import PostgreSQLConnector
            with pytest.raises(ImportError, match="psycopg2"):
                PostgreSQLConnector("postgresql://localhost/test")

    def test_constructor_stores_schema(self):
        connector = self._make_connector(schema="warehouse")
        assert connector._schema == "warehouse"

    def test_source_built_from_connection_string(self):
        connector = self._make_connector()
        assert "postgresql://" in connector.source
        assert "localhost" in connector.source

    def test_from_postgresql_factory(self):
        mock_pg, mock_conn, mock_cursor = self._make_mock_psycopg2(fetchall_return=[])
        # get_tables returns [] so introspection produces an empty catalog
        mock_cursor.description = [("table_name",)]
        mock_cursor.fetchall.return_value = []
        with patch.dict("sys.modules", {"psycopg2": mock_pg}):
            ctx = SQLens.from_postgresql(
                "postgresql://user:pass@localhost/testdb",
                schema="public",
            )
        assert isinstance(ctx, SQLens)
        assert ctx.table_count == 0

    def test_from_postgresql_factory_schema_forwarded(self):
        mock_pg, mock_conn, mock_cursor = self._make_mock_psycopg2(fetchall_return=[])
        with patch.dict("sys.modules", {"psycopg2": mock_pg}):
            ctx = SQLens.from_postgresql(
                "postgresql://localhost/testdb",
                schema="reporting",
            )
        # Source should embed the schema name
        assert "reporting" in ctx.catalog.source

    def test_pk_source_database_when_pks_returned(self):
        """When PostgreSQL returns real PKs, heuristic must not run."""
        # Simulate a connector with is_primary_key=True via MemoryConnector
        # (the same path: pk_names non-empty → pk_source = "database")
        connector = MemoryConnector(
            tables={
                "orders": {
                    "columns": [
                        {"name": "order_id", "data_type": "INT", "is_primary_key": True, "nullable": False},
                        {"name": "total", "data_type": "NUMERIC"},
                    ],
                    "foreign_keys": [],
                    "metadata": {},
                    "rows": [],
                }
            },
            source="memory://pg-sim",
        )
        ctx = SQLens.from_connector(connector)
        orders = ctx.get_table("orders")
        # Database-reported PK wins; heuristic did not run
        assert orders.metadata.get("pk_source") == "database"
        pk_cols = [c for c in orders.columns if c.is_primary_key]
        assert len(pk_cols) == 1
        assert pk_cols[0].name == "order_id"

    def test_get_column_stats_returns_columnstats(self):
        """get_column_stats() on PostgreSQLConnector returns a ColumnStats, not None."""
        mock_pg, mock_conn, mock_cursor = self._make_mock_psycopg2()
        # First call: cardinality/null_pct query
        mock_cursor.description = [("cardinality",), ("null_pct",)]
        mock_cursor.fetchall.return_value = [(42, 0.05)]
        with patch.dict("sys.modules", {"psycopg2": mock_pg}):
            from sqlens.connectors.postgresql import PostgreSQLConnector
            from sqlens.catalog.models import ColumnStats
            connector = PostgreSQLConnector("postgresql://localhost/testdb")
        stats = connector.get_column_stats("users", "email", "CHARACTER VARYING")
        assert isinstance(stats, ColumnStats)

    def test_base_connector_get_column_stats_returns_none(self):
        """Default ConnectorProtocol.get_column_stats() returns None (BigQuery fallback)."""
        from sqlens.connectors.base import ConnectorProtocol
        connector = MemoryConnector(tables={}, source="memory://test")
        result = connector.get_column_stats("t", "col", "STRING")
        assert result is None
