# Development

Contributor setup, project layout, testing, and quality checks for pythermacell.
See the root [CONTRIBUTING.md](../CONTRIBUTING.md) for the full contribution
workflow (branching, commits, PRs, release process).

## Setup

This project uses [uv](https://docs.astral.sh/uv/) and targets Python 3.13+.

```bash
git clone https://github.com/joyfulhouse/pythermacell.git
cd pythermacell
uv sync
```

`uv sync` installs the package with its development dependencies into a local
virtual environment.

## Project Structure

```
pythermacell/
├── src/pythermacell/         # Main package
│   ├── __init__.py           # Public API exports
│   ├── api.py                # Low-level HTTP API layer
│   ├── client.py             # Device manager / coordinator
│   ├── auth.py               # Authentication handler
│   ├── devices.py            # Stateful device objects
│   ├── models.py             # Data models
│   ├── exceptions.py         # Custom exceptions
│   ├── resilience.py         # Resilience patterns
│   └── const.py              # Constants
├── tests/                    # Test suite
│   ├── test_*.py             # Unit tests
│   ├── integration/          # Integration tests
│   └── conftest.py           # Pytest fixtures
├── docs/                     # Documentation
├── examples/                 # Usage examples
├── pyproject.toml            # Project configuration
├── README.md
└── LICENSE                   # MIT License
```

## Testing

```bash
# Run all tests
uv run pytest

# Run with coverage report
uv run pytest --cov=pythermacell --cov-report=term-missing

# Run only unit tests (fast)
uv run pytest -m "not integration"

# Run only integration tests (requires credentials)
uv run pytest -m integration

# Run a specific test file
uv run pytest tests/test_client.py -v

# Stop on first failure
uv run pytest -x
```

### Integration Tests

Integration tests require real API credentials. Create a `.env` file in the
project root:

```env
THERMACELL_USERNAME=your@email.com
THERMACELL_PASSWORD=your_password
THERMACELL_API_BASE_URL=https://api.iot.thermacell.com
THERMACELL_TEST_NODE_ID=optional_specific_device_id
```

Then run:

```bash
uv run pytest -m integration
```

The `.env` file is gitignored and must never be committed. See
[testing/TESTING.md](testing/TESTING.md) for the comprehensive testing guide and
[testing/INTEGRATION_TEST_RESULTS.md](testing/INTEGRATION_TEST_RESULTS.md) for
live-API results.

## Code Quality

```bash
# Format code
uv run ruff format src/ tests/

# Lint code
uv run ruff check src/ tests/

# Fix auto-fixable issues
uv run ruff check --fix src/ tests/

# Type checking (strict mypy)
uv run mypy src/pythermacell/
```

### Standards

- **Type safety:** 100% coverage with strict mypy.
- **Code style:** Ruff with a comprehensive rule set.
- **Line length:** 120 characters.
- **Python version:** 3.13+.
- **Docstrings:** Google-style format.
- **Import sorting:** Automated with ruff.

Linters and type checks are never disabled to silence a finding; fix the root
cause. See
[development/CODE_REVIEW_PYTHON_BEST_PRACTICES.md](development/CODE_REVIEW_PYTHON_BEST_PRACTICES.md)
for the project's Python best-practices review notes.

## CI/CD

GitHub Actions runs lint, type checks, and unit tests on every PR
([.github/workflows/ci.yml](../.github/workflows/ci.yml)); integration tests run
on `main`; and tagged releases publish to PyPI
([.github/workflows/publish.yml](../.github/workflows/publish.yml)). Internal
pipeline notes are kept in [claude/CI_CD.md](claude/CI_CD.md).
