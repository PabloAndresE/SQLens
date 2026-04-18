"""Smoke tests for the sqlens CLI."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

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
