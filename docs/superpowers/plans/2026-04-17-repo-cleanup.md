# SQLens Full Repo Cleanup — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the SQLens repo professional and open-source-ready before public launch.

**Architecture:** Five independent commits — hygiene fixes, CI/CD, docs, CLI tests, integration examples. All on master, sequential.

**Tech Stack:** Python 3.10+, pytest, argparse, GitHub Actions, LangChain, LlamaIndex

---

### Task 1: Fix version mismatch and project URL

**Files:**
- Modify: `sqlens/__init__.py:427`
- Modify: `pyproject.toml:50-53`

- [ ] **Step 1: Fix `__version__` in `__init__.py`**

Change line 427 of `sqlens/__init__.py`:

```python
__version__ = "0.7.0"
```

- [ ] **Step 2: Fix GitHub URLs in `pyproject.toml`**

Replace lines 50-53 of `pyproject.toml`:

```toml
[project.urls]
Homepage = "https://github.com/PabloAndresE/SQLens"
Documentation = "https://github.com/PabloAndresE/SQLens#readme"
Issues = "https://github.com/PabloAndresE/SQLens/issues"
```

- [ ] **Step 3: Verify version matches**

Run: `python -c "import sqlens; print(sqlens.__version__)"`
Expected: `0.7.0`

---

### Task 2: Remove tracked artifacts from git

**Files:**
- Modify: git index (no file edits)

These files are already in `.gitignore` but were committed before the ignore rules existed.

- [ ] **Step 1: Remove `.idea/` from tracking**

```bash
git rm --cached -r .idea/
```

- [ ] **Step 2: Remove all `__pycache__/` from tracking**

```bash
git rm --cached -r sqlens/__pycache__/ sqlens/catalog/__pycache__/ sqlens/connectors/__pycache__/ sqlens/enrichment/__pycache__/ sqlens/introspection/__pycache__/ sqlens/retrieval/__pycache__/ tests/__pycache__/ tests/unit/__pycache__/
```

- [ ] **Step 3: Remove `validation_output/` from tracking**

```bash
git rm --cached -r validation_output/
```

- [ ] **Step 4: Verify no artifacts remain tracked**

Run: `git ls-files | grep -E '__pycache__|\.idea|validation_output'`
Expected: empty output

- [ ] **Step 5: Commit hygiene fixes (Tasks 1 + 2)**

```bash
git add sqlens/__init__.py pyproject.toml
git commit -m "fix: version mismatch, project URL, and remove tracked artifacts"
```

---

### Task 3: Add GitHub Actions CI

**Files:**
- Create: `.github/workflows/ci.yml`
- Modify: `README.md:9` (add badge)

- [ ] **Step 1: Create CI workflow file**

Create `.github/workflows/ci.yml`:

```yaml
name: CI

on:
  push:
    branches: [master]
  pull_request:
    branches: [master]

jobs:
  test:
    runs-on: ubuntu-latest
    strategy:
      matrix:
        python-version: ["3.10", "3.11", "3.12"]

    steps:
      - uses: actions/checkout@v4

      - name: Set up Python ${{ matrix.python-version }}
        uses: actions/setup-python@v5
        with:
          python-version: ${{ matrix.python-version }}

      - name: Install dependencies
        run: pip install -e ".[dev,numpy]"

      - name: Lint
        run: ruff check .

      - name: Type check
        run: mypy sqlens/

      - name: Unit tests
        run: pytest tests/unit/ -v --tb=short
```

- [ ] **Step 2: Add CI badge to README.md**

Add after line 9 (inside the `<p align="center">` badges block) of `README.md`:

```html
  <a href="https://github.com/PabloAndresE/SQLens/actions/workflows/ci.yml"><img src="https://github.com/PabloAndresE/SQLens/actions/workflows/ci.yml/badge.svg" alt="CI"></a>
```

- [ ] **Step 3: Commit CI**

```bash
git add .github/workflows/ci.yml README.md
git commit -m "ci: add GitHub Actions workflow for tests and type checking"
```

---

### Task 4: Update ARCHITECTURE.md

**Files:**
- Modify: `docs/ARCHITECTURE.md`

- [ ] **Step 1: Add SQLite and MySQL connectors to pipeline diagram**

Replace lines 37-41 of `docs/ARCHITECTURE.md`:

```
┌─────────────┐  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐
│  BigQuery    │  │ PostgreSQL  │  │   MySQL     │  │   SQLite    │  │   Custom    │
│  Connector   │  │ Connector   │  │  Connector  │  │  Connector  │  │  Connector  │
└──────┬───────┘  └──────┬──────┘  └──────┬──────┘  └──────┬──────┘  └──────┬──────┘
       │                 │                 │                 │                │
       └────────────┬────┴────────────┬────┴─────────────────┘────────────────┘
```

- [ ] **Step 2: Add SQLite and MySQL to module tree**

Replace lines 93-96 of `docs/ARCHITECTURE.md` (the connectors section):

```
├── connectors/
│   ├── base.py                  # ConnectorProtocol (ABC)
│   ├── bigquery.py              # BigQueryConnector
│   ├── postgresql.py            # PostgreSQLConnector (v0.5)
│   ├── mysql.py                 # MySQLConnector (v0.7)
│   ├── sqlite.py                # SQLiteConnector (v0.7)
│   └── memory.py                # MemoryConnector (testing)
```

- [ ] **Step 3: Update test count**

Replace line 695 of `docs/ARCHITECTURE.md`:

```
The test suite has **118 tests** across `tests/unit/test_core.py` and `tests/integration/`, organized into classes:
```

- [ ] **Step 4: Update test file structure**

Replace lines 716-720 of `docs/ARCHITECTURE.md`:

```
tests/
├── unit/
│   └── test_core.py               # 68 unit tests — all connectors, enrichers, retrievers
│   └── test_cli.py                # CLI smoke tests
├── integration/
│   ├── test_bigquery.py           # real BQ (@pytest.mark.integration)
│   ├── test_sqlite_integration.py # real SQLite (ecommerce.db fixture)
│   └── test_mysql_integration.py  # real MySQL (@pytest.mark.integration)
├── fixtures/
│   ├── ecommerce.db               # SQLite test fixture
│   └── ecommerce_catalog.json     # Pre-built catalog fixture
└── evals/
```

- [ ] **Step 5: Update dependencies section**

Replace lines 746-751 of `docs/ARCHITECTURE.md`:

```
### Connector extras
- `sqlens[bigquery]` → google-cloud-bigquery
- `sqlens[postgresql]` → psycopg2-binary (v0.5)
- `sqlens[mysql]` → mysql-connector-python (v0.7)
- SQLite → built-in (zero deps, v0.7)
```

- [ ] **Step 6: Update roadmap**

Add after the v0.6 row in the roadmap table:

```
| v0.7 | SQLite + MySQL connectors, integration tests | completed |
```

---

### Task 5: Add CONTRIBUTING.md

**Files:**
- Create: `CONTRIBUTING.md`

- [ ] **Step 1: Create CONTRIBUTING.md**

Create `CONTRIBUTING.md` at project root:

```markdown
# Contributing to SQLens

Thanks for your interest in contributing to SQLens!

## Development Setup

```bash
git clone https://github.com/PabloAndresE/SQLens.git
cd SQLens
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev,numpy]"
```

## Running Tests

```bash
# Unit tests (no external dependencies)
pytest tests/unit/ -v

# Integration tests (requires real databases)
pytest tests/integration/ -v -m integration

# Type checking
mypy sqlens/

# Linting
ruff check .
```

## Pull Request Process

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/my-feature`)
3. Write tests for your changes
4. Ensure all tests pass and type checking is clean
5. Submit a pull request with a clear description of the change

## Adding a New Connector

Implement the `ConnectorProtocol` ABC in `sqlens/connectors/base.py`. See `sqlens/connectors/sqlite.py` for a minimal example. Your connector must implement:

- `get_tables()` — list table names
- `get_columns(table)` — column metadata
- `get_primary_keys(table)` — PK column names
- `get_foreign_keys(table)` — explicit FK relationships
- `execute_query(sql)` — run read-only queries (used by stats/samples)
- `get_table_metadata(table)` — engine-specific metadata

Optionally implement `get_column_stats(table, column)` for dialect-aware statistics.

## Code Style

- We use [ruff](https://docs.astral.sh/ruff/) for linting and formatting
- [mypy](https://mypy-lang.org/) for type checking with `disallow_untyped_defs = true`
- Line length: 100 characters
- Target: Python 3.10+
```

---

### Task 6: Add GitHub issue and PR templates

**Files:**
- Create: `.github/ISSUE_TEMPLATE/bug_report.md`
- Create: `.github/pull_request_template.md`

- [ ] **Step 1: Create bug report template**

Create `.github/ISSUE_TEMPLATE/bug_report.md`:

```markdown
---
name: Bug Report
about: Report a bug in SQLens
labels: bug
---

## Description

A clear description of the bug.

## Steps to Reproduce

1. ...
2. ...
3. ...

## Expected Behavior

What you expected to happen.

## Actual Behavior

What actually happened. Include error messages or tracebacks if applicable.

## Environment

- Python version:
- SQLens version:
- Database type:
- OS:
```

- [ ] **Step 2: Create PR template**

Create `.github/pull_request_template.md`:

```markdown
## What changed

Brief description of the change.

## Why

Motivation or issue reference.

## Testing

How you tested this change.
```

- [ ] **Step 3: Commit docs (Tasks 4 + 5 + 6)**

```bash
git add docs/ARCHITECTURE.md CONTRIBUTING.md .github/ISSUE_TEMPLATE/bug_report.md .github/pull_request_template.md
git commit -m "docs: update ARCHITECTURE.md, add CONTRIBUTING.md and templates"
```

---

### Task 7: CLI smoke tests

**Files:**
- Create: `tests/unit/test_cli.py`

The CLI uses `argparse` (not click), so we test via `subprocess` calling `main()` or by invoking the arg parser directly.

- [ ] **Step 1: Write CLI test file**

Create `tests/unit/test_cli.py`:

```python
"""Smoke tests for the sqlens CLI."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

FIXTURES = Path(__file__).parent.parent / "fixtures"
ECOMMERCE_DB = FIXTURES / "ecommerce.db"


def run_cli(*args: str) -> subprocess.CompletedProcess:
    """Run sqlens CLI as a subprocess and return the result."""
    return subprocess.run(
        [sys.executable, "-m", "sqlens.cli", *args],
        capture_output=True,
        text=True,
        timeout=30,
    )


class TestCLIHelp:
    """Each subcommand responds to --help."""

    def test_main_help(self):
        result = run_cli("--help")
        assert result.returncode == 0
        assert "sqlens" in result.stdout.lower()

    def test_inspect_help(self):
        result = run_cli("inspect", "--help")
        assert result.returncode == 0
        assert "--sqlite" in result.stdout

    def test_enrich_help(self):
        result = run_cli("enrich", "--help")
        assert result.returncode == 0
        assert "--descriptions" in result.stdout

    def test_context_help(self):
        result = run_cli("context", "--help")
        assert result.returncode == 0
        assert "--level" in result.stdout


class TestCLIInspect:
    """Inspect subcommand with real SQLite fixture."""

    def test_inspect_sqlite(self, tmp_path):
        output = tmp_path / "catalog.json"
        result = run_cli(
            "inspect",
            "--sqlite", str(ECOMMERCE_DB),
            "-o", str(output),
        )
        assert result.returncode == 0
        assert "introspected" in result.stdout
        assert output.exists()

    def test_inspect_no_source(self):
        result = run_cli("inspect")
        assert result.returncode != 0


class TestCLIErrors:
    """Error cases produce readable messages, not tracebacks."""

    def test_invalid_sqlite_path(self):
        result = run_cli("inspect", "--sqlite", "/nonexistent/path.db")
        assert result.returncode != 0
        assert "error" in result.stderr.lower() or result.returncode != 0

    def test_enrich_missing_catalog(self):
        result = run_cli("enrich", "/nonexistent/catalog.json", "--descriptions")
        assert result.returncode != 0

    def test_no_command(self):
        result = run_cli()
        # Should print help, not crash
        assert result.returncode == 0
```

- [ ] **Step 2: Run CLI tests to verify they pass**

Run: `cd "/Users/pabloencalada/Desktop/Proyectos/SQLens/SQLens V0.1/sqlens" && pytest tests/unit/test_cli.py -v`
Expected: all tests PASS

- [ ] **Step 3: Run full unit test suite to check no regressions**

Run: `pytest tests/unit/ -v --tb=short`
Expected: all existing + new tests PASS

- [ ] **Step 4: Commit CLI tests**

```bash
git add tests/unit/test_cli.py
git commit -m "test: add CLI smoke tests"
```

---

### Task 8: LangChain integration example

**Files:**
- Create: `examples/langchain_integration.py`

- [ ] **Step 1: Create LangChain example**

Create `examples/langchain_integration.py`:

```python
"""SQLens + LangChain integration example.

Shows how to use SQLens to enrich database context and feed it
to a LangChain LLM chain for text-to-SQL generation.

Requirements:
    pip install sqlens langchain langchain-openai

Usage:
    export OPENAI_API_KEY="your-key-here"
    python examples/langchain_integration.py
"""

from __future__ import annotations

import os
import sys

from sqlens import SQLens


def main() -> None:
    # ── Step 1: Enrich schema with SQLens ────────────────────────
    # Use the bundled ecommerce fixture (or replace with your own DB)
    db_path = os.path.join(os.path.dirname(__file__), "..", "tests", "fixtures", "ecommerce.db")

    ctx = SQLens.from_sqlite(db_path)
    ctx.enrich(
        descriptions=True,  # rule-based column descriptions
        relations=True,     # infer implicit foreign keys
        domains=True,       # auto-tag business domains
    )

    # ── Step 2: Retrieve context for a natural-language query ────
    query = "What are the top 5 customers by total order amount?"

    context = ctx.get_context(
        query,
        max_tables=5,
        level="standard",
        domain="auto",
    )

    schema_context = context.to_prompt()

    print("=" * 60)
    print("ENRICHED SCHEMA CONTEXT (from SQLens)")
    print("=" * 60)
    print(schema_context)
    print()

    # ── Step 3: Feed to LangChain ────────────────────────────────
    # This step requires: pip install langchain langchain-openai
    # and OPENAI_API_KEY set in environment.
    try:
        from langchain_openai import ChatOpenAI
        from langchain_core.prompts import ChatPromptTemplate
    except ImportError:
        print("=" * 60)
        print("LangChain not installed. The schema context above is what")
        print("you would pass to your LLM. Install langchain to see the")
        print("full integration:")
        print("  pip install langchain langchain-openai")
        return

    if not os.environ.get("OPENAI_API_KEY"):
        print("=" * 60)
        print("Set OPENAI_API_KEY to run the LangChain integration.")
        print("The schema context above is ready to use with any LLM.")
        return

    llm = ChatOpenAI(model="gpt-4o-mini", temperature=0)

    prompt = ChatPromptTemplate.from_messages([
        ("system", (
            "You are a SQL expert. Given the database schema context below, "
            "write a SQL query that answers the user's question.\n\n"
            "Schema context:\n{schema_context}\n\n"
            "Return ONLY the SQL query, no explanation."
        )),
        ("human", "{question}"),
    ])

    chain = prompt | llm

    response = chain.invoke({
        "schema_context": schema_context,
        "question": query,
    })

    print("=" * 60)
    print("GENERATED SQL (from LangChain + OpenAI)")
    print("=" * 60)
    print(response.content)


if __name__ == "__main__":
    main()
```

---

### Task 9: LlamaIndex integration example

**Files:**
- Create: `examples/llamaindex_integration.py`

- [ ] **Step 1: Create LlamaIndex example**

Create `examples/llamaindex_integration.py`:

```python
"""SQLens + LlamaIndex integration example.

Shows how to use SQLens to enrich database context and feed it
to a LlamaIndex query engine for text-to-SQL generation.

Requirements:
    pip install sqlens llama-index llama-index-llms-openai

Usage:
    export OPENAI_API_KEY="your-key-here"
    python examples/llamaindex_integration.py
"""

from __future__ import annotations

import os
import sys

from sqlens import SQLens


def main() -> None:
    # ── Step 1: Enrich schema with SQLens ────────────────────────
    db_path = os.path.join(os.path.dirname(__file__), "..", "tests", "fixtures", "ecommerce.db")

    ctx = SQLens.from_sqlite(db_path)
    ctx.enrich(
        descriptions=True,
        relations=True,
        domains=True,
    )

    # ── Step 2: Retrieve context for a natural-language query ────
    query = "Which product categories have the highest return rate?"

    context = ctx.get_context(
        query,
        max_tables=5,
        level="standard",
        domain="auto",
    )

    schema_context = context.to_prompt()

    print("=" * 60)
    print("ENRICHED SCHEMA CONTEXT (from SQLens)")
    print("=" * 60)
    print(schema_context)
    print()

    # ── Step 3: Feed to LlamaIndex ───────────────────────────────
    # This step requires: pip install llama-index llama-index-llms-openai
    # and OPENAI_API_KEY set in environment.
    try:
        from llama_index.core.llms import ChatMessage
        from llama_index.llms.openai import OpenAI
    except ImportError:
        print("=" * 60)
        print("LlamaIndex not installed. The schema context above is what")
        print("you would pass to your LLM. Install llama-index to see the")
        print("full integration:")
        print("  pip install llama-index llama-index-llms-openai")
        return

    if not os.environ.get("OPENAI_API_KEY"):
        print("=" * 60)
        print("Set OPENAI_API_KEY to run the LlamaIndex integration.")
        print("The schema context above is ready to use with any LLM.")
        return

    llm = OpenAI(model="gpt-4o-mini", temperature=0)

    messages = [
        ChatMessage(
            role="system",
            content=(
                "You are a SQL expert. Given the database schema context below, "
                "write a SQL query that answers the user's question.\n\n"
                f"Schema context:\n{schema_context}\n\n"
                "Return ONLY the SQL query, no explanation."
            ),
        ),
        ChatMessage(role="user", content=query),
    ]

    response = llm.chat(messages)

    print("=" * 60)
    print("GENERATED SQL (from LlamaIndex + OpenAI)")
    print("=" * 60)
    print(response.message.content)


if __name__ == "__main__":
    main()
```

---

### Task 10: Examples README and final commit

**Files:**
- Create: `examples/README.md`

- [ ] **Step 1: Create examples README**

Create `examples/README.md`:

```markdown
# SQLens Integration Examples

These examples show how to use SQLens with popular LLM frameworks.

## LangChain

```bash
pip install sqlens langchain langchain-openai
export OPENAI_API_KEY="your-key"
python examples/langchain_integration.py
```

## LlamaIndex

```bash
pip install sqlens llama-index llama-index-llms-openai
export OPENAI_API_KEY="your-key"
python examples/llamaindex_integration.py
```

Both examples work without API keys — they will show the enriched schema context that SQLens generates, which is the core value. The LLM call is optional to demonstrate the full pipeline.
```

- [ ] **Step 2: Commit examples**

```bash
git add examples/
git commit -m "docs: add LangChain and LlamaIndex integration examples"
```

---

### Task 11: Final verification

- [ ] **Step 1: Run full unit test suite**

Run: `pytest tests/unit/ -v --tb=short`
Expected: all tests PASS (68 existing + new CLI tests)

- [ ] **Step 2: Run type checker**

Run: `mypy sqlens/`
Expected: no new errors

- [ ] **Step 3: Verify no tracked artifacts**

Run: `git ls-files | grep -E '__pycache__|\.idea|validation_output'`
Expected: empty output

- [ ] **Step 4: Verify version consistency**

Run: `python -c "import sqlens; print(sqlens.__version__)"`
Expected: `0.7.0`

- [ ] **Step 5: Verify git log looks clean**

Run: `git log --oneline -6`
Expected: 4 new commits on top of the existing history:
```
<hash> docs: add LangChain and LlamaIndex integration examples
<hash> test: add CLI smoke tests
<hash> docs: update ARCHITECTURE.md, add CONTRIBUTING.md and templates
<hash> ci: add GitHub Actions workflow for tests and type checking
<hash> fix: version mismatch, project URL, and remove tracked artifacts
```
