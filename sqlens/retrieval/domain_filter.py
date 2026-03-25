"""Domain filter: pre-filters the catalog by business domain before retrieval.

Sits between the catalog and the retriever. When domain filtering is active,
the retriever only searches within the relevant subset of tables.
"""

from __future__ import annotations

from typing import Callable, Optional

from sqlens.catalog.models import Catalog

# Keyword → domain mappings for auto-detect (multilingual: en + es)
DOMAIN_KEYWORDS: dict[str, list[str]] = {
    "sales": [
        "sales", "revenue", "orders", "sold", "purchase", "checkout",
        "ventas", "ingresos", "pedidos", "compras", "facturación",
    ],
    "finance": [
        "finance", "billing", "refund", "expense", "budget", "accounting",
        "finanzas", "factura", "reembolso", "gastos", "presupuesto", "contabilidad",
    ],
    "users": [
        "users", "accounts", "customers", "registration", "signup", "profiles",
        "usuarios", "cuentas", "clientes", "registro", "perfiles",
    ],
    "marketing": [
        "marketing", "campaigns", "ads", "clicks", "conversions", "email",
        "campañas", "anuncios", "clics", "conversiones",
    ],
    "products": [
        "products", "catalog", "inventory", "stock", "items", "categories",
        "productos", "catálogo", "inventario", "artículos", "categorías",
    ],
    "ops": [
        "logs", "monitoring", "alerts", "errors", "health", "incidents",
        "registros", "monitoreo", "alertas", "errores", "incidentes",
    ],
    "analytics": [
        "analytics", "events", "tracking", "funnel", "metrics", "sessions",
        "analítica", "eventos", "seguimiento", "métricas", "sesiones",
    ],
}


def classify_query_domain(
    query: str,
    available_domains: list[str],
    llm_callable: Optional[Callable[[str], str]] = None,
) -> Optional[str]:
    """Classify a query into a business domain.

    Tier 1: keyword matching (zero deps).
    Tier 2: LLM classification (if callable provided).

    Returns the domain name, or None if no domain could be detected.
    """
    lower = query.lower()

    # Tier 1: keyword matching
    scores: dict[str, int] = {}
    for domain, keywords in DOMAIN_KEYWORDS.items():
        if domain not in available_domains:
            continue
        score = sum(1 for kw in keywords if kw in lower)
        if score > 0:
            scores[domain] = score

    if scores:
        return max(scores, key=scores.get)  # type: ignore[arg-type]

    # Tier 2: LLM classification
    if llm_callable is not None:
        prompt = (
            f"Classify this database query into one of these domains: "
            f"{', '.join(available_domains)}.\n"
            f"Query: \"{query}\"\n"
            f"Return only the domain name, nothing else."
        )
        try:
            response = llm_callable(prompt).strip().lower()
            if response in available_domains:
                return response
        except Exception:
            pass

    return None


def filter_catalog_by_domain(catalog: Catalog, domain: str) -> list[str]:
    """Return table names that belong to the given domain."""
    return [t.name for t in catalog.tables if domain in t.domains]
