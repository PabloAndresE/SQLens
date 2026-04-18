"""Domains enricher: tags tables with business domain labels.

Auto-detects domains using table name patterns, column signatures, and
relationship propagation. Supports manual overrides.
"""

from __future__ import annotations

from collections.abc import Callable

from sqlens.catalog.models import Catalog
from sqlens.connectors.base import ConnectorProtocol
from sqlens.enrichment.base import EnricherProtocol

# Table name → domain mappings
TABLE_NAME_PATTERNS: dict[str, list[str]] = {
    "sales": ["order", "invoice", "payment", "purchase", "sale", "transaction", "checkout"],
    "finance": ["revenue", "billing", "refund", "ledger", "account_balance", "expense"],
    "users": ["user", "account", "profile", "auth", "login", "session", "credential"],
    "marketing": ["campaign", "ad_", "click", "impression", "email_campaign", "promo"],
    "products": ["product", "catalog", "item", "sku", "inventory", "stock", "category"],
    "ops": ["log", "audit", "monitor", "alert", "metric", "health", "error"],
    "config": ["config", "setting", "feature_flag", "permission", "role"],
    "analytics": ["event", "tracking", "funnel", "cohort", "segment"],
}

# Column presence → domain hints
COLUMN_SIGNATURE_PATTERNS: dict[str, list[str]] = {
    "sales": ["amount", "price", "total", "revenue", "discount", "tax"],
    "finance": ["debit", "credit", "balance", "ledger"],
    "users": ["email", "phone", "address", "password_hash", "first_name", "last_name"],
    "marketing": ["click", "impression", "ctr", "conversion", "utm_"],
    "analytics": ["event_type", "session_id", "page_view", "referrer"],
}


def _detect_domains_by_name(table_name: str) -> list[str]:
    """Detect domains based on table name patterns."""
    lower = table_name.lower()
    domains: list[str] = []
    for domain, patterns in TABLE_NAME_PATTERNS.items():
        if any(
            lower.startswith(p) or lower.endswith(p)
            or f"_{p}_" in f"_{lower}_"
            for p in patterns
        ):
            domains.append(domain)
    return domains


def _detect_domains_by_columns(column_names: list[str]) -> list[str]:
    """Detect domains based on column name signatures."""
    lower_cols = {c.lower() for c in column_names}
    domains: list[str] = []
    for domain, signatures in COLUMN_SIGNATURE_PATTERNS.items():
        matches = sum(
            1 for sig in signatures
            if any(sig in col for col in lower_cols)
        )
        if matches >= 2:  # require at least 2 matching columns
            domains.append(domain)
    return domains


class DomainsEnricher(EnricherProtocol):
    """Enricher that tags tables with business domain labels.

    Detection strategy (layered):
    1. Table name patterns (e.g., order* → "sales")
    2. Column signature detection (e.g., amount+price → "sales")
    3. Relationship propagation (FK targets inherit parent domains)
    4. Manual overrides (always take precedence)
    5. LLM fallback (optional, for unclassified tables)

    Args:
        overrides: Dict of table_name → list of domain tags (manual).
        llm_callable: Optional LLM for classifying unresolved tables.
    """

    def __init__(
        self,
        overrides: dict[str, list[str]] | None = None,
        llm_callable: Callable[[str], str] | None = None,
    ) -> None:
        self._overrides = overrides or {}
        self._llm = llm_callable

    def name(self) -> str:
        return "domains"

    def enrich(self, catalog: Catalog, connector: ConnectorProtocol) -> Catalog:
        # Phase 1: Auto-detect by name and columns
        for table in catalog.tables:
            if table.name in self._overrides:
                table.domains = list(self._overrides[table.name])
                continue

            domains: set[str] = set()
            domains.update(_detect_domains_by_name(table.name))
            domains.update(_detect_domains_by_columns([c.name for c in table.columns]))
            table.domains = sorted(domains)

        # Phase 2: Propagate through relationships
        changed = True
        while changed:
            changed = False
            for table in catalog.tables:
                for rel in table.relationships:
                    target = catalog.get_table(rel.target_table)
                    if target is None:
                        continue
                    for domain in target.domains:
                        if domain not in table.domains:
                            table.domains.append(domain)
                            table.domains.sort()
                            changed = True

        # Phase 3: LLM fallback for untagged tables
        if self._llm is not None:
            all_domains = catalog.domains
            untagged = [t for t in catalog.tables if not t.domains]
            for table in untagged:
                prompt = (
                    f"Classify the database table '{table.name}' with columns "
                    f"{', '.join(c.name for c in table.columns)} "
                    f"into one or more of these domains: {', '.join(all_domains)}. "
                    f"Return only the domain name(s), comma-separated."
                )
                try:
                    response = self._llm(prompt).strip().lower()
                    detected = [d.strip() for d in response.split(",") if d.strip() in all_domains]
                    if detected:
                        table.domains = sorted(detected)
                except Exception:
                    pass

        if "domains" not in catalog.enrichers_applied:
            catalog.enrichers_applied.append("domains")
        return catalog
