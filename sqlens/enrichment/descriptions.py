"""Description enricher: generates human-readable descriptions for tables and columns.

Uses a layered heuristic approach (abbreviation expansion, naming patterns,
type inference) with an optional LLM fallback for unresolved cases.
"""

from __future__ import annotations

from collections.abc import Callable

from sqlens.catalog.models import Catalog
from sqlens.connectors.base import ConnectorProtocol
from sqlens.enrichment.base import EnricherProtocol

# Common abbreviations found in database column names
ABBREVIATIONS: dict[str, str] = {
    "acct": "account",
    "addr": "address",
    "amt": "amount",
    "avg": "average",
    "bal": "balance",
    "cat": "category",
    "cd": "code",
    "cnt": "count",
    "crt": "created",
    "crtd": "created",
    "curr": "currency",
    "cust": "customer",
    "del": "deleted",
    "desc": "description",
    "dt": "date",
    "dur": "duration",
    "emp": "employee",
    "fst": "first",
    "grp": "group",
    "id": "identifier",
    "img": "image",
    "inv": "invoice",
    "lst": "last",
    "max": "maximum",
    "min": "minimum",
    "msg": "message",
    "nm": "name",
    "num": "number",
    "org": "organization",
    "pct": "percent",
    "prd": "product",
    "qty": "quantity",
    "ref": "reference",
    "seq": "sequence",
    "src": "source",
    "stat": "status",
    "tel": "telephone",
    "tmp": "temporary",
    "tot": "total",
    "ts": "timestamp",
    "txn": "transaction",
    "typ": "type",
    "upd": "updated",
    "usr": "user",
    "val": "value",
}

# Naming patterns that map to descriptions
SUFFIX_PATTERNS: dict[str, str] = {
    "_id": "foreign key reference",
    "_at": "timestamp",
    "_on": "date",
    "_by": "actor reference",
    "_count": "count",
    "_total": "total amount",
    "_pct": "percentage",
    "_url": "URL",
    "_flag": "boolean flag",
    "_name": "name",
    "_code": "code",
    "_number": "number",
    "_address": "address",
    "_price": "price",
    "_type": "type",
    "_date": "date",
    "_time": "time",
    "_status": "status",
    "_category": "category",
    "_brand": "brand",
    "_email": "email address",
    "_phone": "phone number",
    "_key": "key",
    "_hash": "hash value",
    "_token": "token",
    "_slug": "URL slug",
    "_score": "score",
    "_rank": "rank",
    "_rating": "rating",
    "_weight": "weight",
    "_size": "size",
    "_currency": "currency code",
    "_country": "country",
    "_city": "city",
    "_state": "state",
    "_region": "region",
}

PREFIX_PATTERNS: dict[str, str] = {
    "is_": "boolean flag indicating",
    "has_": "boolean flag indicating presence of",
    "can_": "boolean flag indicating ability to",
    "num_": "count of",
    "total_": "total",
    "avg_": "average",
    "max_": "maximum",
    "min_": "minimum",
}

# Direct name → description for common plain-English column names
# that don't match suffix/prefix patterns or abbreviations.
DIRECT_NAMES: dict[str, str] = {
    "id": "unique identifier",
    "name": "name",
    "email": "email address",
    "cost": "cost",
    "price": "price",
    "status": "status",
    "gender": "gender",
    "brand": "brand",
    "category": "category",
    "age": "age",
    "city": "city",
    "state": "state",
    "country": "country",
    "latitude": "latitude coordinate",
    "longitude": "longitude coordinate",
    "phone": "phone number",
    "address": "address",
    "zip": "postal code",
    "type": "type",
    "date": "date",
    "time": "time",
    "code": "code",
    "key": "key",
    "value": "value",
    "title": "title",
    "text": "text content",
    "body": "body text",
    "note": "note",
    "tag": "tag",
    "label": "label",
    "color": "color",
    "image": "image URL",
    "url": "URL",
    "path": "file path",
    "hash": "hash value",
    "token": "authentication token",
    "slug": "URL slug",
    "rank": "rank",
    "score": "score",
    "rating": "rating",
    "weight": "weight",
    "size": "size",
    "quantity": "quantity",
    "amount": "amount",
    "total": "total",
    "tax": "tax amount",
    "discount": "discount amount",
    "revenue": "revenue",
    "profit": "profit",
    "currency": "currency code",
    "locale": "locale",
    "language": "language code",
    "region": "region",
    "timezone": "timezone",
    "ip": "IP address",
    "host": "hostname",
    "port": "port number",
    "version": "version",
    "message": "message",
    "error": "error message",
    "level": "level",
    "priority": "priority",
    "source": "source",
    "target": "target",
    "action": "action",
    "event": "event type",
    "method": "method",
    "format": "format",
    "mode": "mode",
    "department": "department",
    "sku": "stock keeping unit (SKU)",
    "street": "street",
    "traffic": "traffic source",
    "browser": "browser",
    "os": "operating system",
    "device": "device type",
    "platform": "platform",
    "channel": "channel",
    "medium": "marketing medium",
    "campaign": "campaign",
    "referrer": "referrer URL",
    "session": "session identifier",
    "sequence": "sequence number",
    "index": "index",
    "order": "order",
    "bucket": "bucket",
    "partition": "partition key",
    "geom": "geographic geometry",
    "geometry": "geographic geometry",
    "location": "location",
    "coordinates": "geographic coordinates",
}


def _expand_abbreviations(name: str) -> str:
    """Expand known abbreviations in a snake_case name."""
    parts = name.lower().split("_")
    expanded = [ABBREVIATIONS.get(p, p) for p in parts]
    return " ".join(expanded)


def _describe_column_by_pattern(name: str) -> str | None:
    """Try to describe a column based on naming patterns."""
    lower = name.lower()

    for prefix, desc in PREFIX_PATTERNS.items():
        if lower.startswith(prefix):
            rest = _expand_abbreviations(lower[len(prefix):])
            return f"{desc} {rest}"

    for suffix, desc in SUFFIX_PATTERNS.items():
        if lower.endswith(suffix):
            rest = _expand_abbreviations(lower[: -len(suffix)])
            return f"{rest} {desc}"

    return None


def _describe_column_by_type(data_type: str) -> str | None:
    """Infer a generic description from the column's data type."""
    upper = data_type.upper()
    if "TIMESTAMP" in upper or "DATETIME" in upper:
        return "timestamp"
    if "BOOL" in upper:
        return "boolean flag"
    if "JSON" in upper:
        return "JSON data"
    if "ARRAY" in upper:
        return "list of values"
    return None


def describe_column(name: str, data_type: str) -> str | None:
    """Generate a description for a column using heuristics.

    Tries pattern matching first, then abbreviation expansion, then direct
    name lookup, then type inference. Returns None if no heuristic matches.
    """
    # Try naming patterns
    by_pattern = _describe_column_by_pattern(name)
    if by_pattern:
        return by_pattern

    # Try abbreviation expansion (only if it actually expanded something)
    expanded = _expand_abbreviations(name)
    original_joined = " ".join(name.lower().split("_"))
    if expanded != original_joined:
        return expanded

    # Try direct name lookup for common plain-English column names
    lower = name.lower()
    if lower in DIRECT_NAMES:
        return DIRECT_NAMES[lower]

    # Try type-based inference
    return _describe_column_by_type(data_type)


def describe_table(name: str, column_names: list[str]) -> str | None:
    """Generate a description for a table based on its name and columns."""
    expanded = _expand_abbreviations(name)
    original_joined = " ".join(name.lower().split("_"))
    if expanded != original_joined:
        return expanded.title()
    return None


class DescriptionsEnricher(EnricherProtocol):
    """Enricher that generates natural language descriptions for tables and columns.

    Args:
        llm_callable: Optional function (str) -> str that takes a prompt and
            returns a description. Used as fallback for columns that can't be
            described by heuristics. Pass None for rule-based only.
    """

    def __init__(self, llm_callable: Callable[[str], str] | None = None) -> None:
        self._llm = llm_callable

    def name(self) -> str:
        return "descriptions"

    def enrich(self, catalog: Catalog, connector: ConnectorProtocol) -> Catalog:
        for table in catalog.tables:
            # Table description
            if table.description is None:
                table.description = describe_table(
                    table.name,
                    [c.name for c in table.columns],
                )

            # Column descriptions
            for col in table.columns:
                if col.description is None:
                    col.description = describe_column(col.name, col.data_type)

            # LLM fallback for unresolved descriptions
            if self._llm is not None:
                undescribed = [c for c in table.columns if c.description is None]
                if undescribed:
                    prompt = self._build_llm_prompt(table.name, undescribed)
                    try:
                        response = self._llm(prompt)
                        self._parse_llm_response(response, undescribed)
                    except Exception as e:
                        import warnings
                        warnings.warn(
                            f"LLM description failed for table '{table.name}': {e}",
                            RuntimeWarning,
                            stacklevel=2,
                        )

                if table.description is None:
                    prompt = (
                        f"Describe the database table '{table.name}' with columns: "
                        f"{', '.join(c.name for c in table.columns)}. "
                        "One sentence, no markdown."
                    )
                    try:
                        table.description = self._llm(prompt).strip()
                    except Exception as e:
                        import warnings
                        warnings.warn(
                            f"LLM table description failed for '{table.name}': {e}",
                            RuntimeWarning,
                            stacklevel=2,
                        )

        if "descriptions" not in catalog.enrichers_applied:
            catalog.enrichers_applied.append("descriptions")
        return catalog

    def _build_llm_prompt(self, table_name: str, columns: list) -> str:
        col_list = "\n".join(f"  - {c.name} ({c.data_type})" for c in columns)
        return (
            f"For the database table '{table_name}', describe each column "
            f"in one short sentence. Return one line per column in the format "
            f"'column_name: description'. No markdown.\n\n{col_list}"
        )

    def _parse_llm_response(self, response: str, columns: list) -> None:
        col_map = {c.name: c for c in columns}
        for line in response.strip().split("\n"):
            if ":" in line:
                name, desc = line.split(":", 1)
                name = name.strip().lower()
                if name in col_map:
                    col_map[name].description = desc.strip()
