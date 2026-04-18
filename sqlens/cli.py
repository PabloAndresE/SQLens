"""sqlens CLI — command line interface.

Commands:
    sqlens inspect  --bigquery PROJECT.DATASET [-o catalog.json]
    sqlens inspect  --postgresql "postgresql://..." [-o catalog.json]
    sqlens inspect  --mysql "mysql://..." [-o catalog.json]
    sqlens inspect  --sqlite path/to/db.sqlite [-o catalog.json]
    sqlens enrich   catalog.json --descriptions --stats --relations --samples 3 --domains
    sqlens context  catalog.json "query" [--max-tables 5] [--level standard] [--domain auto]
"""

from __future__ import annotations

import argparse
import json
import sys
import time

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _log(msg: str, verbose: bool = False) -> None:
    if verbose:
        print(f"[sqlens] {msg}", file=sys.stderr)


def _err(msg: str) -> None:
    print(f"error: {msg}", file=sys.stderr)
    sys.exit(1)


# ---------------------------------------------------------------------------
# Sub-commands
# ---------------------------------------------------------------------------

def cmd_inspect(args: argparse.Namespace) -> None:
    """Connect to a database, introspect the schema, and save the catalog."""
    from sqlens import SQLens

    t0 = time.time()

    if args.bigquery:
        # Parse "project.dataset" or "project.dataset.billing"
        parts = args.bigquery.split(".")
        if len(parts) < 2:
            _err("--bigquery expects PROJECT.DATASET (e.g. my-project.analytics)")
        project, dataset = parts[0], parts[1]
        billing = args.billing_project or project
        _log(f"connecting to BigQuery {project}.{dataset} (billing: {billing})", args.verbose)
        try:
            ctx = SQLens.from_bigquery(
                project=project,
                dataset=dataset,
                billing_project=billing,
            )
        except Exception as e:
            _err(str(e))

    elif args.postgresql:
        schema = args.schema or "public"
        _log(f"connecting to PostgreSQL schema={schema}", args.verbose)
        try:
            ctx = SQLens.from_postgresql(
                connection_string=args.postgresql,
                schema=schema,
            )
        except Exception as e:
            _err(str(e))

    elif args.mysql:
        database = args.database or None
        _log(f"connecting to MySQL database={database or '(from URI)'}", args.verbose)
        try:
            ctx = SQLens.from_mysql(
                connection_string=args.mysql,
                database=database,
            )
        except Exception as e:
            _err(str(e))

    elif args.sqlite:
        _log(f"connecting to SQLite {args.sqlite}", args.verbose)
        try:
            ctx = SQLens.from_sqlite(path=args.sqlite)
        except Exception as e:
            _err(str(e))

    else:
        _err(
            "specify --bigquery PROJECT.DATASET, --postgresql DSN, "
            "--mysql URI, or --sqlite PATH"
        )

    elapsed = time.time() - t0
    output = args.output or "catalog.json"

    ctx.save(output)
    print(f"introspected {ctx.table_count} tables in {elapsed:.1f}s → {output}")
    _log(f"tables: {', '.join(ctx.tables)}", args.verbose)


def cmd_enrich(args: argparse.Namespace) -> None:
    """Load a catalog and run enrichers, then save the result."""
    from sqlens import SQLens

    _log(f"loading {args.catalog}", args.verbose)
    try:
        ctx = SQLens.load(args.catalog)
    except Exception as e:
        _err(f"could not load catalog: {e}")

    before_desc = 0
    for t_name in ctx.tables:
        tbl = ctx.get_table(t_name)
        if tbl is None:
            continue
        before_desc += sum(1 for col in tbl.columns if col.description is not None)
    before_rel = 0
    for t_name in ctx.tables:
        tbl = ctx.get_table(t_name)
        if tbl is None:
            continue
        before_rel += len([r for r in tbl.relationships if r.type == "inferred"])

    kwargs: dict = {}
    if args.descriptions:
        kwargs["descriptions"] = True
    if args.stats:
        kwargs["stats"] = True
    if args.relations:
        kwargs["relations"] = True
    if args.samples is not None:
        kwargs["samples"] = args.samples
    if args.domains:
        kwargs["domains"] = True

    if not kwargs:
        _err(
            "specify at least one enricher: --descriptions,"
            " --stats, --relations, --samples N, --domains"
        )

    t0 = time.time()
    ctx.enrich(**kwargs)
    elapsed = time.time() - t0

    output = args.output or args.catalog
    ctx.save(output)

    # Summary
    total_cols = 0
    for t_name in ctx.tables:
        tbl = ctx.get_table(t_name)
        if tbl is None:
            continue
        total_cols += len(tbl.columns)
    after_desc = 0
    for t_name in ctx.tables:
        tbl = ctx.get_table(t_name)
        if tbl is None:
            continue
        after_desc += sum(1 for col in tbl.columns if col.description is not None)
    after_rel = 0
    for t_name in ctx.tables:
        tbl = ctx.get_table(t_name)
        if tbl is None:
            continue
        after_rel += len([r for r in tbl.relationships if r.type == "inferred"])

    print(f"enriched {ctx.table_count} tables in {elapsed:.1f}s → {output}")
    print(f"  enrichers applied : {', '.join(ctx.enrichers_applied)}")
    if args.descriptions:
        print(f"  column descriptions: {before_desc}/{total_cols} → {after_desc}/{total_cols}")
    if args.relations:
        print(f"  inferred relations : {before_rel} → {after_rel}")
    if args.domains:
        print(f"  domains detected   : {', '.join(ctx.domains) or '(none)'}")


def cmd_context(args: argparse.Namespace) -> None:
    """Load a catalog and retrieve context for a natural language query."""
    from sqlens import SQLens

    _log(f"loading {args.catalog}", args.verbose)
    try:
        ctx = SQLens.load(args.catalog)
    except Exception as e:
        _err(f"could not load catalog: {e}")

    domain = args.domain or None
    retrieval = args.retrieval or None

    try:
        result = ctx.get_context(
            args.query,
            max_tables=args.max_tables,
            level=args.level,
            domain=domain,
            retrieval=retrieval,
        )
    except NotImplementedError as e:
        _err(str(e))
    except Exception as e:
        _err(f"retrieval failed: {e}")

    if args.json:
        print(json.dumps(result.to_dict(args.level), indent=2, default=str))
    else:
        print(result.to_prompt(args.level))

    # Diagnostics to stderr so they don't pollute stdout
    method = result.retrieval_method
    n = len(result.tables)
    total = result.total_tables_in_catalog
    domain_info = (
        f", domain={result.domain_filter_applied}"
        if result.domain_filter_applied else ""
    )
    _log(
        f"retrieved {n}/{total} tables via {method}{domain_info}",
        verbose=True,  # always print diagnostics to stderr when context runs
    )


# ---------------------------------------------------------------------------
# Argument parser
# ---------------------------------------------------------------------------

def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="sqlens",
        description="Schema intelligence layer for LLMs.",
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="print debug output to stderr",
    )

    sub = parser.add_subparsers(dest="command", metavar="COMMAND")

    # ── inspect ──────────────────────────────────────────────────
    p_inspect = sub.add_parser(
        "inspect",
        help="introspect a database and save the catalog",
    )
    src = p_inspect.add_mutually_exclusive_group(required=True)
    src.add_argument(
        "--bigquery",
        metavar="PROJECT.DATASET",
        help='BigQuery source, e.g. "my-project.analytics"',
    )
    src.add_argument(
        "--postgresql",
        metavar="DSN",
        help='PostgreSQL DSN, e.g. "postgresql://user:pass@host/db"',
    )
    src.add_argument(
        "--mysql",
        metavar="URI",
        help='MySQL URI, e.g. "mysql://user:pass@host/db"',
    )
    src.add_argument(
        "--sqlite",
        metavar="PATH",
        help="path to a SQLite database file",
    )
    p_inspect.add_argument(
        "--billing-project",
        metavar="PROJECT",
        help="GCP billing project (BigQuery only, defaults to source project)",
    )
    p_inspect.add_argument(
        "--schema",
        metavar="SCHEMA",
        default="public",
        help="PostgreSQL schema to introspect (default: public)",
    )
    p_inspect.add_argument(
        "--database",
        metavar="DATABASE",
        default=None,
        help="MySQL database name (overrides the one in the URI)",
    )
    p_inspect.add_argument(
        "-o", "--output",
        metavar="FILE",
        default="catalog.json",
        help="output catalog file (default: catalog.json)",
    )

    # ── enrich ───────────────────────────────────────────────────
    p_enrich = sub.add_parser(
        "enrich",
        help="load a catalog and run enrichers",
    )
    p_enrich.add_argument("catalog", metavar="CATALOG", help="path to catalog JSON")
    p_enrich.add_argument(
        "--descriptions",
        action="store_true",
        help="generate rule-based column and table descriptions",
    )
    p_enrich.add_argument(
        "--stats",
        action="store_true",
        help="collect column-level statistics (requires DB connection)",
    )
    p_enrich.add_argument(
        "--relations",
        action="store_true",
        help="infer implicit foreign key relationships",
    )
    p_enrich.add_argument(
        "--samples",
        metavar="N",
        type=int,
        nargs="?",
        const=3,
        default=None,
        help="collect N sample rows per table (default N=3)",
    )
    p_enrich.add_argument(
        "--domains",
        action="store_true",
        help="auto-tag tables with business domain labels",
    )
    p_enrich.add_argument(
        "-o", "--output",
        metavar="FILE",
        default=None,
        help="output file (default: overwrite input catalog)",
    )

    # ── context ───────────────────────────────────────────────────
    p_context = sub.add_parser(
        "context",
        help="retrieve schema context for a natural language query",
    )
    p_context.add_argument("catalog", metavar="CATALOG", help="path to catalog JSON")
    p_context.add_argument("query", metavar="QUERY", help="natural language query")
    p_context.add_argument(
        "--max-tables",
        metavar="N",
        type=int,
        default=5,
        help="maximum number of tables to return (default: 5)",
    )
    p_context.add_argument(
        "--level",
        choices=["compact", "standard", "full"],
        default="standard",
        help="output detail level (default: standard)",
    )
    p_context.add_argument(
        "--domain",
        metavar="DOMAIN",
        default=None,
        help='domain filter: a domain name or "auto" for auto-detect',
    )
    p_context.add_argument(
        "--retrieval",
        choices=["keyword", "cosine", "vector"],
        default=None,
        help="force a specific retrieval method (default: auto-detect)",
    )
    p_context.add_argument(
        "--json",
        action="store_true",
        help="output JSON instead of the LLM prompt text",
    )

    return parser


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    parser = _build_parser()
    args = parser.parse_args()

    if args.command == "inspect":
        cmd_inspect(args)
    elif args.command == "enrich":
        cmd_enrich(args)
    elif args.command == "context":
        cmd_context(args)
    else:
        parser.print_help()
        sys.exit(0)


if __name__ == "__main__":
    main()
