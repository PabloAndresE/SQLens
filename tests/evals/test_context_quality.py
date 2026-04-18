"""Tier 2 -- Context quality evaluation.

Structural comparison between raw and enriched SQLens contexts.
These tests verify that the enrichment pipeline adds meaningful metadata
to the catalog rather than testing retrieval accuracy.
"""

from __future__ import annotations

from sqlens import SQLens


class TestContextQuality:
    """Structural quality checks on the enriched catalog."""

    def test_description_coverage(self, enriched_ctx: SQLens) -> None:
        """Enriched catalog should have >80% column descriptions."""
        total_cols = 0
        described_cols = 0
        for table_name in enriched_ctx.tables:
            table = enriched_ctx.get_table(table_name)
            assert table is not None
            for col in table.columns:
                total_cols += 1
                if col.description:
                    described_cols += 1

        assert total_cols > 0
        coverage = described_cols / total_cols
        assert coverage > 0.80, (
            f"Description coverage {coverage:.1%} is below 80% "
            f"({described_cols}/{total_cols} columns described)"
        )

    def test_relationship_density(
        self, raw_ctx: SQLens, enriched_ctx: SQLens
    ) -> None:
        """Enriched should have more relationships than raw."""
        raw_rels = 0
        for name in raw_ctx.tables:
            table = raw_ctx.get_table(name)
            if table:
                raw_rels += len(table.relationships)

        enriched_rels = 0
        for name in enriched_ctx.tables:
            table = enriched_ctx.get_table(name)
            if table:
                enriched_rels += len(table.relationships)

        assert enriched_rels > raw_rels, (
            f"Enriched relationships ({enriched_rels}) should exceed "
            f"raw relationships ({raw_rels})"
        )

    def test_domain_coverage(self, enriched_ctx: SQLens) -> None:
        """Most tables should have at least one domain tag."""
        total = enriched_ctx.table_count
        with_domain = sum(
            1
            for name in enriched_ctx.tables
            if enriched_ctx.get_table(name) and enriched_ctx.get_table(name).domains
        )

        coverage = with_domain / total if total else 0
        assert coverage > 0.70, (
            f"Domain coverage {coverage:.1%} is below 70% "
            f"({with_domain}/{total} tables tagged)"
        )

    def test_enriched_beats_raw_info_density(
        self, raw_ctx: SQLens, enriched_ctx: SQLens
    ) -> None:
        """Enriched prompt output should be more informative than raw."""
        raw_prompt = raw_ctx.to_prompt(level="standard")
        enriched_prompt = enriched_ctx.to_prompt(level="standard")

        # The enriched prompt should be strictly longer because it includes
        # descriptions, relationships, domain tags, row counts, and stats.
        assert len(enriched_prompt) > len(raw_prompt), (
            f"Enriched prompt ({len(enriched_prompt)} chars) should be "
            f"longer than raw prompt ({len(raw_prompt)} chars)"
        )

    def test_enrichers_applied(self, enriched_ctx: SQLens) -> None:
        """All enrichers should be recorded in the catalog."""
        expected = {"descriptions", "stats", "relations", "samples", "domains"}
        applied = set(enriched_ctx.enrichers_applied)
        assert expected.issubset(applied), (
            f"Expected enrichers {expected} but only found {applied}"
        )

    def test_inferred_relationships_have_confidence(
        self, enriched_ctx: SQLens
    ) -> None:
        """Inferred relationships should carry a confidence score."""
        for name in enriched_ctx.tables:
            table = enriched_ctx.get_table(name)
            if table is None:
                continue
            for rel in table.relationships:
                if rel.type == "inferred":
                    assert rel.confidence is not None, (
                        f"Inferred rel {table.name}.{rel.source_column} -> "
                        f"{rel.target_table} missing confidence"
                    )
                    assert 0.0 <= rel.confidence <= 1.0
