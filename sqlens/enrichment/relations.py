"""Relations enricher: infers implicit foreign key relationships.

Uses naming conventions (e.g., orders.user_id → users.id) and optionally
value co-occurrence to detect relationships not declared in the schema.
"""

from __future__ import annotations

from sqlens.catalog.models import Catalog, Relationship
from sqlens.connectors.base import ConnectorProtocol
from sqlens.enrichment.base import EnricherProtocol


class RelationsEnricher(EnricherProtocol):
    """Enricher that infers implicit foreign key relationships.

    Detection strategies (applied in order):
    1. Naming convention: column_name matches pattern `{other_table}_id`
       or `{other_table_singular}_id`
    2. Naming convention: column_name is `{other_table}_{pk_column}`
    3. (Future) Value co-occurrence sampling

    Args:
        min_confidence: Minimum confidence threshold for including a
            relationship (0.0-1.0). Default 0.5.
    """

    def __init__(self, min_confidence: float = 0.5) -> None:
        self._min_confidence = min_confidence

    def name(self) -> str:
        return "relations"

    def enrich(self, catalog: Catalog, connector: ConnectorProtocol) -> Catalog:
        table_names = {t.name for t in catalog.tables}
        pk_map = self._build_pk_map(catalog)

        for table in catalog.tables:
            existing_fks = {
                (r.source_column, r.target_table, r.target_column)
                for r in table.relationships
            }

            for col in table.columns:
                if col.is_primary_key:
                    continue

                inferred = self._infer_relationship(
                    table.name, col.name, table_names, pk_map,
                )
                if inferred is None:
                    continue

                key = (inferred.source_column, inferred.target_table, inferred.target_column)
                if key in existing_fks:
                    continue

                if inferred.confidence is not None and inferred.confidence >= self._min_confidence:
                    table.relationships.append(inferred)

        if "relations" not in catalog.enrichers_applied:
            catalog.enrichers_applied.append("relations")
        return catalog

    def _build_pk_map(self, catalog: Catalog) -> dict[str, list[str]]:
        """Build a map of table_name → list of primary key column names."""
        pk_map: dict[str, list[str]] = {}
        for table in catalog.tables:
            pks = [c.name for c in table.columns if c.is_primary_key]
            if pks:
                pk_map[table.name] = pks
        return pk_map

    def _infer_relationship(
        self,
        source_table: str,
        column_name: str,
        table_names: set[str],
        pk_map: dict[str, list[str]],
    ) -> Relationship | None:
        """Try to infer a FK relationship for a single column."""
        lower = column_name.lower()

        # Pattern: {table}_id → table.id
        if lower.endswith("_id"):
            candidate = lower[:-3]  # strip _id
            return self._try_match(source_table, column_name, candidate, table_names, pk_map)

        return None

    def _try_match(
        self,
        source_table: str,
        column_name: str,
        candidate: str,
        table_names: set[str],
        pk_map: dict[str, list[str]],
    ) -> Relationship | None:
        """Try to match a candidate table name against known tables."""
        # Direct match: user_id → users
        for table_name in table_names:
            if table_name == source_table:
                continue

            # Exact match (e.g., candidate="user", table="user")
            if candidate == table_name:
                target_col = self._find_target_pk(table_name, pk_map)
                return Relationship(
                    source_table=source_table,
                    source_column=column_name,
                    target_table=table_name,
                    target_column=target_col,
                    type="inferred",
                    confidence=0.95,
                )

            # Singular → plural (e.g., candidate="user", table="users")
            if candidate + "s" == table_name or candidate + "es" == table_name:
                target_col = self._find_target_pk(table_name, pk_map)
                return Relationship(
                    source_table=source_table,
                    source_column=column_name,
                    target_table=table_name,
                    target_column=target_col,
                    type="inferred",
                    confidence=0.9,
                )

            # Plural → singular (e.g., candidate="users", table="user")
            if (
                candidate.endswith("s")
                and candidate[:-1] == table_name
            ):
                target_col = self._find_target_pk(table_name, pk_map)
                return Relationship(
                    source_table=source_table,
                    source_column=column_name,
                    target_table=table_name,
                    target_column=target_col,
                    type="inferred",
                    confidence=0.85,
                )

        return None

    def _find_target_pk(self, table_name: str, pk_map: dict[str, list[str]]) -> str:
        """Find the primary key column for the target table, defaulting to 'id'."""
        pks = pk_map.get(table_name, [])
        if len(pks) == 1:
            return pks[0]
        return "id"
