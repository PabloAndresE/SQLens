"""Integration tests: full SQLite pipeline (inspect → enrich → save → load → retrieve).

These tests use a real SQLite database with 10 tables and FKs.
No external infrastructure required — runs anywhere Python runs.

Marker: @pytest.mark.integration
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from sqlens import SQLens
from sqlens.connectors.sqlite import SQLiteConnector

FIXTURE_DB = Path(__file__).parent.parent / "fixtures" / "ecommerce.db"


def _ensure_fixture() -> Path:
    """Create the fixture if it doesn't exist (CI-friendly)."""
    if not FIXTURE_DB.exists():
        import subprocess
        import sys

        script = Path(__file__).parent.parent.parent / "scripts" / "create_sqlite_fixture.py"
        subprocess.check_call(
            [sys.executable, str(script)]
        )
    return FIXTURE_DB


# ---------------------------------------------------------------------------
# SQLiteConnector unit-level tests (with real DB)
# ---------------------------------------------------------------------------

@pytest.mark.integration
class TestSQLiteConnector:

    @pytest.fixture(autouse=True)
    def setup(self):
        self.db_path = _ensure_fixture()
        self.connector = SQLiteConnector(self.db_path)

    def test_get_tables(self):
        tables = self.connector.get_tables()
        assert len(tables) == 10
        assert "users" in tables
        assert "orders" in tables
        assert "order_items" in tables

    def test_get_columns(self):
        cols = self.connector.get_columns("users")
        col_names = [c.name for c in cols]
        assert "id" in col_names
        assert "email" in col_names
        assert "country_id" in col_names

    def test_get_primary_keys(self):
        pks = self.connector.get_primary_keys("users")
        assert pks == ["id"]

    def test_get_foreign_keys(self):
        fks = self.connector.get_foreign_keys("orders")
        assert len(fks) == 1
        assert fks[0].source_column == "user_id"
        assert fks[0].target_table == "users"
        assert fks[0].target_column == "id"

    def test_get_foreign_keys_multiple(self):
        fks = self.connector.get_foreign_keys("order_items")
        assert len(fks) == 2
        target_tables = {fk.target_table for fk in fks}
        assert "orders" in target_tables
        assert "products" in target_tables

    def test_get_table_metadata(self):
        meta = self.connector.get_table_metadata("users")
        assert meta["row_count"] == 5

    def test_execute_query(self):
        rows = self.connector.execute_query("SELECT COUNT(*) AS cnt FROM users")
        assert rows[0]["cnt"] == 5

    def test_qualify_table_name(self):
        assert self.connector.qualify_table_name("users") == '"users"'

    def test_get_column_stats(self):
        stats = self.connector.get_column_stats("users", "email", "TEXT")
        assert stats is not None
        assert stats.cardinality == 5
        assert stats.null_pct == 0.0

    def test_column_stats_with_nulls(self):
        stats = self.connector.get_column_stats("audit_log", "user_id", "INTEGER")
        assert stats is not None
        assert stats.cardinality is not None

    def test_column_stats_numeric_min_max(self):
        stats = self.connector.get_column_stats("products", "price", "REAL")
        assert stats is not None
        assert stats.min_value is not None
        assert stats.max_value is not None
        assert float(stats.min_value) < float(stats.max_value)


# ---------------------------------------------------------------------------
# Full pipeline: inspect → enrich → save → load → retrieve
# ---------------------------------------------------------------------------

@pytest.mark.integration
class TestSQLiteEndToEnd:

    @pytest.fixture(autouse=True)
    def setup(self):
        self.db_path = _ensure_fixture()

    def test_from_sqlite_factory(self):
        ctx = SQLens.from_sqlite(self.db_path)
        assert ctx.table_count == 10
        assert "users" in ctx.tables
        assert "orders" in ctx.tables
        assert "order_items" in ctx.tables

    def test_source_identifier(self):
        ctx = SQLens.from_sqlite(self.db_path)
        assert "sqlite://" in ctx.catalog.source

    def test_fingerprints_computed(self):
        ctx = SQLens.from_sqlite(self.db_path)
        fp = ctx.fingerprint("users")
        assert fp is not None
        assert len(fp) == 16

    def test_fingerprints_stable(self):
        ctx1 = SQLens.from_sqlite(self.db_path)
        ctx2 = SQLens.from_sqlite(self.db_path)
        assert ctx1.fingerprint("users") == ctx2.fingerprint("users")

    def test_explicit_foreign_keys_detected(self):
        ctx = SQLens.from_sqlite(self.db_path)
        orders = ctx.get_table("orders")
        explicit_fks = [r for r in orders.relationships if r.type == "explicit"]
        assert len(explicit_fks) == 1
        assert explicit_fks[0].target_table == "users"

    def test_enrich_descriptions(self):
        ctx = SQLens.from_sqlite(self.db_path)
        ctx.enrich(descriptions=True)
        assert "descriptions" in ctx.enrichers_applied
        users = ctx.get_table("users")
        email_col = next(c for c in users.columns if c.name == "email")
        assert email_col.description is not None

    def test_enrich_stats(self):
        ctx = SQLens.from_sqlite(self.db_path)
        ctx.enrich(stats=True)
        assert "stats" in ctx.enrichers_applied
        users = ctx.get_table("users")
        email_col = next(c for c in users.columns if c.name == "email")
        assert email_col.stats is not None
        assert email_col.stats.cardinality == 5

    def test_enrich_relations(self):
        ctx = SQLens.from_sqlite(self.db_path)
        ctx.enrich(relations=True)
        assert "relations" in ctx.enrichers_applied
        # order_items has explicit FKs + possibly inferred ones
        order_items = ctx.get_table("order_items")
        assert len(order_items.relationships) >= 2

    def test_enrich_samples(self):
        ctx = SQLens.from_sqlite(self.db_path)
        ctx.enrich(samples=2)
        assert "samples" in ctx.enrichers_applied
        users = ctx.get_table("users")
        assert users.sample_data is not None
        assert len(users.sample_data) <= 2

    def test_enrich_domains(self):
        ctx = SQLens.from_sqlite(self.db_path)
        ctx.enrich(domains=True)
        assert "domains" in ctx.enrichers_applied
        orders = ctx.get_table("orders")
        assert "sales" in orders.domains

    def test_full_enrichment_pipeline(self):
        ctx = SQLens.from_sqlite(self.db_path)
        ctx.enrich(
            descriptions=True,
            stats=True,
            relations=True,
            samples=3,
            domains=True,
        )
        assert len(ctx.enrichers_applied) == 5
        assert len(ctx.domains) > 0

    def test_save_and_load_roundtrip(self):
        ctx = SQLens.from_sqlite(self.db_path)
        ctx.enrich(descriptions=True, relations=True, domains=True)

        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
            path = f.name

        ctx.save(path)
        loaded = SQLens.load(path)

        assert loaded.table_count == ctx.table_count
        assert loaded.tables == ctx.tables
        assert loaded.enrichers_applied == ctx.enrichers_applied
        assert loaded.domains == ctx.domains

        Path(path).unlink()

    def test_retrieval_keyword(self):
        ctx = SQLens.from_sqlite(self.db_path)
        ctx.enrich(descriptions=True)

        result = ctx.get_context("user email country", max_tables=3, retrieval="keyword")
        assert len(result.tables) > 0
        assert result.retrieval_method == "keyword"
        table_names = [t.name for t in result.tables]
        assert "users" in table_names

    def test_retrieval_with_domain_filter(self):
        ctx = SQLens.from_sqlite(self.db_path)
        ctx.enrich(descriptions=True, domains=True)

        result = ctx.get_context("order total amount", max_tables=5, domain="sales")
        assert result.domain_filter_applied == "sales"
        table_names = [t.name for t in result.tables]
        assert "audit_log" not in table_names

    def test_to_prompt_output(self):
        ctx = SQLens.from_sqlite(self.db_path)
        ctx.enrich(descriptions=True)

        prompt = ctx.to_prompt()
        assert "DATABASE SCHEMA CONTEXT" in prompt
        assert "users" in prompt
        assert "orders" in prompt

    def test_retrieval_result_to_prompt(self):
        ctx = SQLens.from_sqlite(self.db_path)
        ctx.enrich(descriptions=True)

        result = ctx.get_context("products price category", max_tables=3)
        prompt = result.to_prompt()
        assert "DATABASE SCHEMA CONTEXT" in prompt

    def test_refresh_preserves_enrichment(self):
        ctx = SQLens.from_sqlite(self.db_path)
        ctx.enrich(descriptions=True)

        # Refresh should re-introspect and merge with fingerprints
        ctx.refresh()
        assert ctx.table_count == 10
        users = ctx.get_table("users")
        email_col = next(c for c in users.columns if c.name == "email")
        # Descriptions should be preserved since structure didn't change
        assert email_col.description is not None
