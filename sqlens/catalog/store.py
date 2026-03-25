"""Catalog store: JSON persistence with fingerprint-based incremental updates.

Handles saving/loading catalogs to disk and merging new introspection results
with cached enrichment data based on structural fingerprints.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sqlens.catalog.models import (
    Catalog,
    Column,
    ColumnStats,
    Relationship,
    Table,
)


def save_catalog(catalog: Catalog, path: str | Path) -> None:
    """Save a catalog to a JSON file."""
    data = _catalog_to_serializable(catalog)
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False, default=str)


def load_catalog(path: str | Path) -> Catalog:
    """Load a catalog from a JSON file."""
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    return _catalog_from_serializable(data)


def merge_catalogs(old: Catalog, new: Catalog) -> Catalog:
    """Merge a new introspection result with a cached catalog.

    Uses fingerprints to determine which tables changed:
    - Unchanged tables: keep the old enrichment data
    - Changed tables: use the new structure, discard old enrichment
    - New tables: add them without enrichment
    - Deleted tables: remove them

    Returns a new Catalog with the merged result.
    """
    old_map = {t.name: t for t in old.tables}
    merged_tables: list[Table] = []

    for new_table in new.tables:
        old_table = old_map.get(new_table.name)

        if old_table is None:
            # New table — no cached data
            merged_tables.append(new_table)
        elif old_table.fingerprint == new_table.fingerprint:
            # Unchanged structure — keep enrichment from old
            merged_tables.append(old_table)
        else:
            # Structure changed — use new structure, lose enrichment
            merged_tables.append(new_table)

    merged_tables.sort(key=lambda t: t.name)

    return Catalog(
        source=new.source,
        tables=merged_tables,
        extracted_at=new.extracted_at,
        enrichers_applied=old.enrichers_applied,
        version=old.version,
    )


# ---------------------------------------------------------------------------
# Serialization helpers
# ---------------------------------------------------------------------------

def _catalog_to_serializable(catalog: Catalog) -> dict[str, Any]:
    """Convert a Catalog to a JSON-serializable dict (full fidelity)."""
    return {
        "version": catalog.version,
        "source": catalog.source,
        "extracted_at": catalog.extracted_at.isoformat() if catalog.extracted_at else None,
        "enrichers_applied": catalog.enrichers_applied,
        "tables": [_table_to_serializable(t) for t in catalog.tables],
    }


def _table_to_serializable(table: Table) -> dict[str, Any]:
    d: dict[str, Any] = {
        "name": table.name,
        "fingerprint": table.fingerprint,
    }
    if table.description is not None:
        d["description"] = table.description
    if table.row_count is not None:
        d["row_count"] = table.row_count
    if table.domains:
        d["domains"] = table.domains
    if table.metadata:
        d["metadata"] = table.metadata

    d["columns"] = [_column_to_serializable(c) for c in table.columns]

    if table.relationships:
        d["relationships"] = [_rel_to_serializable(r) for r in table.relationships]
    if table.sample_data is not None:
        d["sample_data"] = table.sample_data

    return d


def _column_to_serializable(col: Column) -> dict[str, Any]:
    d: dict[str, Any] = {
        "name": col.name,
        "data_type": col.data_type,
        "nullable": col.nullable,
        "is_primary_key": col.is_primary_key,
        "ordinal_position": col.ordinal_position,
    }
    if col.description is not None:
        d["description"] = col.description
    if col.stats is not None:
        d["stats"] = _stats_to_serializable(col.stats)
    return d


def _stats_to_serializable(stats: ColumnStats) -> dict[str, Any]:
    d: dict[str, Any] = {}
    for field_name in ("cardinality", "null_pct", "min_value", "max_value",
                       "top_values", "distribution"):
        val = getattr(stats, field_name)
        if val is not None:
            d[field_name] = val
    return d


def _rel_to_serializable(rel: Relationship) -> dict[str, Any]:
    d: dict[str, Any] = {
        "source_table": rel.source_table,
        "source_column": rel.source_column,
        "target_table": rel.target_table,
        "target_column": rel.target_column,
        "type": rel.type,
    }
    if rel.confidence is not None:
        d["confidence"] = rel.confidence
    return d


# ---------------------------------------------------------------------------
# Deserialization helpers
# ---------------------------------------------------------------------------

def _catalog_from_serializable(data: dict[str, Any]) -> Catalog:
    extracted_at = None
    if data.get("extracted_at"):
        extracted_at = datetime.fromisoformat(data["extracted_at"])

    tables = [_table_from_serializable(t) for t in data.get("tables", [])]

    return Catalog(
        source=data.get("source", "unknown"),
        tables=tables,
        extracted_at=extracted_at,
        enrichers_applied=data.get("enrichers_applied", []),
        version=data.get("version", "1.0"),
    )


def _table_from_serializable(data: dict[str, Any]) -> Table:
    columns = [_column_from_serializable(c) for c in data.get("columns", [])]
    relationships = [_rel_from_serializable(r) for r in data.get("relationships", [])]

    return Table(
        name=data["name"],
        columns=columns,
        description=data.get("description"),
        row_count=data.get("row_count"),
        relationships=relationships,
        sample_data=data.get("sample_data"),
        domains=data.get("domains", []),
        fingerprint=data.get("fingerprint"),
        metadata=data.get("metadata", {}),
    )


def _column_from_serializable(data: dict[str, Any]) -> Column:
    stats = None
    if "stats" in data:
        stats = ColumnStats(**data["stats"])

    return Column(
        name=data["name"],
        data_type=data.get("data_type", "STRING"),
        nullable=data.get("nullable", True),
        is_primary_key=data.get("is_primary_key", False),
        ordinal_position=data.get("ordinal_position", 0),
        description=data.get("description"),
        stats=stats,
    )


def _rel_from_serializable(data: dict[str, Any]) -> Relationship:
    return Relationship(
        source_table=data["source_table"],
        source_column=data["source_column"],
        target_table=data["target_table"],
        target_column=data["target_column"],
        type=data.get("type", "explicit"),
        confidence=data.get("confidence"),
    )
