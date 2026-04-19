"""Core data models for sqlens.

These dataclasses define the shape of all data flowing through the pipeline:
connectors produce RawColumn/RawForeignKey, the introspection engine assembles
them into Table/Column/Relationship objects, enrichers augment them, and
serializers export them.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

# ---------------------------------------------------------------------------
# Raw types (produced by connectors, consumed by introspection engine)
# ---------------------------------------------------------------------------

@dataclass
class RawColumn:
    """Column metadata as returned by a database connector."""

    name: str
    data_type: str
    nullable: bool = True
    is_primary_key: bool = False
    ordinal_position: int = 0
    description: str | None = None  # from DB comments if available


@dataclass
class RawForeignKey:
    """Explicit foreign key as declared in the database."""

    source_column: str
    target_table: str
    target_column: str


# ---------------------------------------------------------------------------
# Enriched types (built by introspection, augmented by enrichers)
# ---------------------------------------------------------------------------

@dataclass
class ColumnStats:
    """Statistics for a single column, produced by the stats enricher."""

    cardinality: int | None = None
    null_pct: float | None = None
    min_value: str | None = None
    max_value: str | None = None
    top_values: list[str] | None = None
    distribution: dict[str, Any] | None = None


@dataclass
class Column:
    """Enriched column metadata."""

    name: str
    data_type: str
    nullable: bool = True
    is_primary_key: bool = False
    ordinal_position: int = 0
    description: str | None = None
    stats: ColumnStats | None = None

    def to_dict(self, level: str = "standard") -> dict[str, Any]:
        """Serialize column to dict, respecting the detail level."""
        d: dict[str, Any] = {
            "name": self.name,
            "type": self.data_type,
            "nullable": self.nullable,
        }
        if level in ("standard", "full"):
            d["is_primary_key"] = self.is_primary_key
        if self.description is not None:
            d["description"] = self.description

        if self.stats is not None:
            stats_d: dict[str, Any] = {}
            if level == "compact":
                if self.stats.null_pct is not None:
                    stats_d["null_pct"] = self.stats.null_pct
            elif level == "standard":
                for k in ("cardinality", "null_pct", "min_value", "max_value"):
                    v = getattr(self.stats, k)
                    if v is not None:
                        stats_d[k] = v
            else:  # full
                for k in ("cardinality", "null_pct", "min_value", "max_value",
                          "top_values", "distribution"):
                    v = getattr(self.stats, k)
                    if v is not None:
                        stats_d[k] = v
            if stats_d:
                d["stats"] = stats_d

        return d


@dataclass
class Relationship:
    """A relationship between two tables (explicit FK or inferred)."""

    source_table: str
    source_column: str
    target_table: str
    target_column: str
    type: str = "explicit"  # "explicit" | "inferred"
    confidence: float | None = None  # 0.0-1.0, only for inferred

    def to_dict(self, level: str = "standard") -> dict[str, Any]:
        d: dict[str, Any] = {
            "source_column": self.source_column,
            "target_table": self.target_table,
            "target_column": self.target_column,
            "type": self.type,
        }
        if level == "full" and self.confidence is not None:
            d["confidence"] = self.confidence
        if level == "standard" and self.type == "inferred" and self.confidence is not None:
            if self.confidence >= 0.8:
                d["confidence"] = self.confidence
        return d


@dataclass
class Table:
    """Enriched table metadata — the core unit of the catalog."""

    name: str
    columns: list[Column] = field(default_factory=list)
    description: str | None = None
    row_count: int | None = None
    relationships: list[Relationship] = field(default_factory=list)
    sample_data: list[dict[str, Any]] | None = None
    domains: list[str] = field(default_factory=list)
    fingerprint: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def compute_fingerprint(self) -> str:
        """Compute a structural fingerprint for change detection.

        The fingerprint is based only on structure (columns, types, PKs, FKs),
        not on enrichment data. This means enrichment is preserved when the
        structure hasn't changed.
        """
        structure = {
            "name": self.name,
            "columns": [
                (c.name, c.data_type, c.nullable, c.is_primary_key)
                for c in sorted(self.columns, key=lambda c: c.name)
            ],
            "explicit_fks": sorted(
                [
                    (r.source_column, r.target_table, r.target_column)
                    for r in self.relationships
                    if r.type == "explicit"
                ]
            ),
        }
        raw = json.dumps(structure, sort_keys=True).encode()
        return hashlib.sha256(raw).hexdigest()[:16]

    def to_dict(self, level: str = "standard") -> dict[str, Any]:
        """Serialize table to dict, respecting the detail level."""
        d: dict[str, Any] = {"name": self.name}

        if self.description is not None:
            d["description"] = self.description
        if self.row_count is not None:
            d["row_count"] = self.row_count
        if self.domains:
            d["domains"] = self.domains

        d["columns"] = [c.to_dict(level) for c in self.columns]

        # Relationships: compact = explicit only, standard = inferred conf>0.8, full = all
        rels = self.relationships
        if level == "compact":
            rels = [r for r in rels if r.type == "explicit"]
        elif level == "standard":
            rels = [
                r for r in rels
                if r.type == "explicit" or (r.confidence is not None and r.confidence >= 0.8)
            ]
        if rels:
            d["relationships"] = [r.to_dict(level) for r in rels]

        # Samples: compact = none, standard = 2, full = all
        if self.sample_data is not None:
            if level == "standard":
                d["sample_data"] = self.sample_data[:2]
            elif level == "full":
                d["sample_data"] = self.sample_data

        if level == "full" and self.metadata:
            d["metadata"] = self.metadata

        return d


# ---------------------------------------------------------------------------
# Catalog (top-level container)
# ---------------------------------------------------------------------------

@dataclass
class Catalog:
    """The complete enriched schema catalog."""

    source: str  # e.g. "bigquery://project.dataset"
    tables: list[Table] = field(default_factory=list)
    extracted_at: datetime | None = None
    enrichers_applied: list[str] = field(default_factory=list)
    version: str = "1.0"

    def __post_init__(self) -> None:
        self._table_index: dict[str, Table] = {}
        self._index_dirty: bool = True

    def _ensure_index(self) -> None:
        """Rebuild the index if it is stale or out of sync with self.tables."""
        if self._index_dirty or len(self._table_index) != len(self.tables):
            self._table_index = {t.name: t for t in self.tables}
            self._index_dirty = False

    def get_table(self, name: str) -> Table | None:
        """Look up a table by name (O(1) via dict index)."""
        self._ensure_index()
        return self._table_index.get(name)

    @property
    def table_names(self) -> list[str]:
        return [t.name for t in self.tables]

    @property
    def table_count(self) -> int:
        return len(self.tables)

    @property
    def domains(self) -> list[str]:
        """Return all unique domains across all tables."""
        all_domains: set[str] = set()
        for t in self.tables:
            all_domains.update(t.domains)
        return sorted(all_domains)

    def tables_in_domain(self, domain: str) -> list[str]:
        """Return table names tagged with the given domain."""
        return [t.name for t in self.tables if domain in t.domains]

    def to_dict(self, level: str = "standard") -> dict[str, Any]:
        return {
            "metadata": {
                "source": self.source,
                "extracted_at": self.extracted_at.isoformat() if self.extracted_at else None,
                "total_tables": self.table_count,
                "level": level,
                "enrichers_applied": self.enrichers_applied,
                "version": self.version,
            },
            "tables": [t.to_dict(level) for t in self.tables],
        }


# ---------------------------------------------------------------------------
# Retrieval result
# ---------------------------------------------------------------------------

@dataclass
class RetrievalResult:
    """Result of a context retrieval operation."""

    tables: list[Table]
    query: str
    retrieval_method: str  # "keyword" | "cosine" | "vector_db"
    total_tables_in_catalog: int
    domain_filter_applied: str | None = None
    tables_after_domain_filter: int | None = None
    scores: dict[str, float] | None = None

    def to_dict(self, level: str = "standard") -> dict[str, Any]:
        return {
            "metadata": {
                "query": self.query,
                "retrieval_method": self.retrieval_method,
                "total_tables_in_catalog": self.total_tables_in_catalog,
                "tables_included": len(self.tables),
                "domain_filter_applied": self.domain_filter_applied,
                "tables_after_domain_filter": self.tables_after_domain_filter,
                "level": level,
            },
            "tables": [t.to_dict(level) for t in self.tables],
        }

    def to_prompt(self, level: str = "standard") -> str:
        """Serialize to LLM-optimized text format."""
        from sqlens.catalog.serializers import to_prompt
        return to_prompt(self, level)
