"""Serializers for converting catalog/retrieval data to LLM-friendly formats.

The primary serializer is `to_prompt()` which produces a text representation
optimized for inclusion in an LLM prompt context window.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from sqlens.catalog.models import Catalog, RetrievalResult, Table


def _format_column_prompt(col_dict: dict, level: str) -> str:
    """Format a single column for the prompt output."""
    parts = [f"  - {col_dict['name']} ({col_dict['type']}"]

    flags = []
    if col_dict.get("is_primary_key"):
        flags.append("PK")
    if not col_dict.get("nullable", True):
        flags.append("NOT NULL")
    elif col_dict.get("nullable"):
        flags.append("NULLABLE")

    if flags:
        parts[0] += f", {', '.join(flags)}"
    parts[0] += ")"

    if col_dict.get("description"):
        parts[0] += f": {col_dict['description']}"

    stats_parts = []
    stats = col_dict.get("stats", {})
    if "cardinality" in stats:
        stats_parts.append(f"cardinality: {stats['cardinality']:,}")
    if "null_pct" in stats and stats["null_pct"] > 0:
        stats_parts.append(f"{stats['null_pct']:.0%} nulls")
    if "min_value" in stats and "max_value" in stats:
        stats_parts.append(f"range: {stats['min_value']} to {stats['max_value']}")
    if "top_values" in stats:
        top = ", ".join(f'"{v}"' for v in stats["top_values"][:4])
        stats_parts.append(f"top: {top}")

    if stats_parts:
        parts[0] += f" [{', '.join(stats_parts)}]"

    return parts[0]


def _format_table_prompt(table_dict: dict, level: str) -> str:
    """Format a single table for the prompt output."""
    lines = [f"TABLE: {table_dict['name']}"]

    if table_dict.get("description"):
        lines.append(f"Description: {table_dict['description']}")
    if table_dict.get("row_count"):
        lines.append(f"Row count: {table_dict['row_count']:,}")
    if table_dict.get("domains"):
        lines.append(f"Domains: {', '.join(table_dict['domains'])}")

    lines.append("")
    lines.append("Columns:")
    for col in table_dict.get("columns", []):
        lines.append(_format_column_prompt(col, level))

    rels = table_dict.get("relationships", [])
    if rels:
        lines.append("")
        lines.append("Relationships:")
        for rel in rels:
            rel_str = f"  - {table_dict['name']}.{rel['source_column']} → {rel['target_table']}.{rel['target_column']}"
            if rel.get("type") == "inferred":
                rel_str += f" (inferred"
                if rel.get("confidence"):
                    rel_str += f", confidence: {rel['confidence']:.2f}"
                rel_str += ")"
            lines.append(rel_str)

    samples = table_dict.get("sample_data", [])
    if samples:
        lines.append("")
        lines.append("Sample rows:")
        if samples:
            headers = list(samples[0].keys())
            lines.append("  | " + " | ".join(headers) + " |")
            for row in samples:
                vals = [str(row.get(h, "")) for h in headers]
                lines.append("  | " + " | ".join(vals) + " |")

    return "\n".join(lines)


def to_prompt(result: RetrievalResult, level: str = "standard") -> str:
    """Convert a RetrievalResult to an LLM-optimized text format.

    This is the primary serialization target — designed to be included
    directly in an LLM prompt as schema context.
    """
    result_dict = result.to_dict(level)
    meta = result_dict["metadata"]

    lines = ["DATABASE SCHEMA CONTEXT"]
    lines.append(f"Tables included: {meta['tables_included']} of {meta['total_tables_in_catalog']}")

    if meta.get("domain_filter_applied"):
        lines.append(
            f"Domain filter: {meta['domain_filter_applied']} "
            f"({meta.get('tables_after_domain_filter', '?')} tables in domain)"
        )

    lines.append(f"Filtered by relevance to: \"{meta['query']}\"")
    lines.append("")

    for table_dict in result_dict["tables"]:
        lines.append(_format_table_prompt(table_dict, level))
        lines.append("")

    return "\n".join(lines).strip()


def catalog_to_prompt(catalog: Catalog, level: str = "standard") -> str:
    """Convert an entire Catalog to prompt format (for small schemas)."""
    catalog_dict = catalog.to_dict(level)

    lines = ["DATABASE SCHEMA CONTEXT"]
    lines.append(f"Source: {catalog_dict['metadata']['source']}")
    lines.append(f"Total tables: {catalog_dict['metadata']['total_tables']}")
    lines.append("")

    for table_dict in catalog_dict["tables"]:
        lines.append(_format_table_prompt(table_dict, level))
        lines.append("")

    return "\n".join(lines).strip()
