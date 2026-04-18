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
