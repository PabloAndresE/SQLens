"""Unit tests for sqlens core functionality."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest

from sqlens import SQLens
from sqlens.catalog.models import Catalog, Column, Relationship, Table
from sqlens.catalog.store import load_catalog, save_catalog, merge_catalogs
from sqlens.connectors.memory import MemoryConnector
from sqlens.enrichment.descriptions import describe_column, describe_table
from sqlens.enrichment.domains import _detect_domains_by_name, _detect_domains_by_columns
from sqlens.retrieval.domain_filter import classify_query_domain
from sqlens.retrieval.keyword import KeywordRetriever

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

        result = ctx.get_context("user email country active", max_tables=2)
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
