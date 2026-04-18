# SQLens Full Repo Cleanup — Design Spec

## Context

SQLens is preparing for public visibility (LinkedIn launch post). The core library is solid (118 tests, clean architecture), but the repo has open-source hygiene gaps that would undermine credibility with developers evaluating whether to star/use it.

## Goal

Make the repo withstand scrutiny from developers clicking through from a LinkedIn post. Fix broken metadata, remove tracked artifacts, add CI/CD, improve documentation, add CLI test coverage, and provide integration examples.

## Approach

Sequential commits on master, one per logical category. No branches — these are independent, low-risk fixes.

---

## 1. Hygiene Fixes

**Commit message:** `fix: version mismatch, project URL, and tracked artifacts`

### 1.1 Version mismatch
- `sqlens/__init__.py` line 427: change `__version__ = "0.1.0"` to `__version__ = "0.7.0"`
- Single source of truth is `pyproject.toml` (already says 0.7.0)

### 1.2 GitHub URL
- `pyproject.toml` lines 50-53: change all occurrences of `pabloandr/sqlens` to `PabloAndresE/SQLens`

### 1.3 Remove tracked artifacts
- Run `git rm --cached -r` on:
  - `.idea/`
  - All `__pycache__/` directories (sqlens/, tests/)
  - `validation_output/`
- Verify `.gitignore` already covers these patterns (it does)

---

## 2. CI/CD — GitHub Actions

**Commit message:** `ci: add GitHub Actions workflow for tests and type checking`

### File: `.github/workflows/ci.yml`

- **Trigger:** push to master, pull requests to master
- **Matrix:** Python 3.10, 3.11, 3.12
- **Steps:**
  1. Checkout
  2. Setup Python
  3. Install: `pip install -e ".[dev]"`
  4. Lint: `ruff check .` (if ruff is in dev deps, otherwise skip)
  5. Type check: `mypy sqlens/`
  6. Test: `pytest tests/unit/ -v`
- **Note:** Integration tests excluded (require real databases). Unit tests only.

### README badge
- Add CI status badge at top of README.md linking to the workflow

---

## 3. Documentation Updates

**Commit message:** `docs: update ARCHITECTURE.md, add CONTRIBUTING.md and templates`

### 3.1 ARCHITECTURE.md updates
- Update test count (68 → 118)
- Add `sqlite.py` and `mysql.py` to connector module tree
- Add MySQL to dependencies section
- Fix any other stale references found during review

### 3.2 CONTRIBUTING.md (new file)
Sections:
- Development setup (`git clone`, `pip install -e ".[dev]"`)
- Running tests (`pytest tests/unit/`, `pytest tests/integration/`)
- Type checking (`mypy sqlens/`)
- PR process (fork, branch, test, PR)
- Code style (existing patterns, no formal style guide beyond ruff/mypy)

### 3.3 GitHub templates (new files)
- `.github/ISSUE_TEMPLATE/bug_report.md` — minimal: description, steps to reproduce, expected/actual, environment
- `.github/pull_request_template.md` — minimal: what changed, why, testing done

---

## 4. CLI Tests

**Commit message:** `test: add CLI smoke tests`

### File: `tests/unit/test_cli.py`

Tests:
- `test_inspect_help` — `inspect --help` exits 0 and shows usage
- `test_enrich_help` — `enrich --help` exits 0 and shows usage
- `test_context_help` — `context --help` exits 0 and shows usage
- `test_inspect_sqlite` — `inspect` with ecommerce.db fixture produces table output
- `test_invalid_connection` — bad connection string produces readable error, not traceback

Use `click.testing.CliRunner` (if click) or `subprocess` depending on CLI framework.

---

## 5. Integration Examples

**Commit message:** `docs: add LangChain and LlamaIndex integration examples`

### File: `examples/langchain_integration.py`
- Uses SQLens to enrich a SQLite schema (ecommerce.db fixture or inline demo)
- Passes enriched context to a LangChain LLM chain for text-to-SQL
- Fully commented, runnable with `pip install sqlens langchain langchain-openai`
- Includes note about setting OPENAI_API_KEY (or whatever LLM provider)

### File: `examples/llamaindex_integration.py`
- Same pattern but with LlamaIndex
- Uses SQLens context output as part of a LlamaIndex query engine
- Fully commented, runnable with `pip install sqlens llama-index`

### File: `examples/README.md`
- Brief description of each example
- Prerequisites and how to run

---

## Verification

After all commits:
1. `pytest tests/unit/ -v` — all tests pass including new CLI tests
2. `mypy sqlens/` — no new type errors
3. `git status` — clean working tree, no tracked artifacts
4. `git ls-files | grep -E '__pycache__|\.idea|validation_output'` — returns empty
5. Check `sqlens.__version__` matches `pyproject.toml`
6. Verify README badge URL points to correct repo
