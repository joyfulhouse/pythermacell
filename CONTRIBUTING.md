# Contributing to pythermacell

Thank you for your interest in contributing to pythermacell! This document provides guidelines and instructions for contributing to the project.

## Table of Contents

- [Code of Conduct](#code-of-conduct)
- [Getting Started](#getting-started)
- [Development Setup](#development-setup)
- [Making Changes](#making-changes)
- [Testing](#testing)
- [Code Quality](#code-quality)
- [Submitting Changes](#submitting-changes)
- [CI/CD Pipeline](#cicd-pipeline)
- [Release Process](#release-process)

## Code of Conduct

This project follows a code of conduct that we expect all contributors to adhere to:

- Be respectful and inclusive
- Welcome newcomers and help them learn
- Focus on constructive feedback
- Respect differing viewpoints and experiences

## Getting Started

1. **Fork the repository** on GitHub
2. **Clone your fork** locally:
   ```bash
   git clone https://github.com/YOUR_USERNAME/pythermacell.git
   cd pythermacell
   ```

3. **Add upstream remote**:
   ```bash
   git remote add upstream https://github.com/joyfulhouse/pythermacell.git
   ```

## Development Setup

### Prerequisites

- Python 3.13 or higher
- Git
- A Thermacell account (for integration testing)

### Install Development Dependencies

```bash
# Create virtual environment
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate

# Install package in development mode with dev dependencies
pip install -e ".[dev]"
```

### Configure Integration Tests

Create a `.env` file in the project root:

```env
THERMACELL_USERNAME=your@email.com
THERMACELL_PASSWORD=your_password
THERMACELL_API_BASE_URL=https://api.iot.thermacell.com
THERMACELL_TEST_NODE_ID=optional_device_id
```

**Important**: Never commit the `.env` file (it's in `.gitignore`).

## Making Changes

### 1. Create a Branch

```bash
git checkout -b feature/your-feature-name
```

Branch naming conventions:
- `feature/` - New features
- `fix/` - Bug fixes
- `docs/` - Documentation changes
- `refactor/` - Code refactoring
- `test/` - Test additions/changes

### 2. Write Code

Follow these guidelines:

#### Code Style
- **Line length**: 120 characters maximum
- **Imports**: Sorted with ruff (automatic)
- **Formatting**: Use ruff format
- **Docstrings**: Google-style format
- **Type hints**: Required for all functions

#### Architecture
- **Async/await**: All I/O operations must be async
- **Error handling**: Use custom exceptions from `exceptions.py`
- **Separation of concerns**: Keep modules focused on single responsibilities

#### Example:

```python
async def get_device_status(node_id: str) -> DeviceStatus | None:
    """Get device status from API.

    Args:
        node_id: Unique device identifier.

    Returns:
        DeviceStatus if successful, None otherwise.

    Raises:
        DeviceError: If device cannot be found.
        ThermacellConnectionError: If connection fails.
    """
    # Implementation
    ...
```

### 3. Add Tests

All new code must include tests:

#### Unit Tests
- Add tests to `tests/test_*.py`
- Mock external API calls
- Aim for >90% coverage

#### Integration Tests
- Add tests to `tests/integration/test_*.py`
- Test against real API (optional)
- Mark with `@pytest.mark.integration`

Example:

```python
import pytest
from pythermacell import ThermacellClient

@pytest.mark.asyncio
async def test_get_devices():
    """Test getting devices from API."""
    async with ThermacellClient("user", "pass") as client:
        devices = await client.get_devices()
        assert isinstance(devices, list)
```

## Testing

### Run All Tests

```bash
# Unit tests only (fast)
pytest tests/ -m "not integration and not manual"

# With coverage
pytest tests/ -m "not integration and not manual" --cov=pythermacell --cov-report=term-missing

# Integration tests (requires credentials)
pytest tests/integration/ -v

# All tests
pytest tests/ -v
```

### Run Specific Tests

```bash
# Specific file
pytest tests/test_client.py -v

# Specific test
pytest tests/test_client.py::test_get_devices -v

# Stop on first failure
pytest tests/ -x
```

## Code Quality

### Automated Checks

Run these before committing:

```bash
# Format code
ruff format src/ tests/

# Lint code
ruff check src/ tests/

# Fix auto-fixable issues
ruff check --fix src/ tests/

# Type checking
mypy src/pythermacell/
```

### Quality Standards

- **Type safety**: 100% (strict mypy)
- **Test coverage**: >90%
- **Linting**: 0 errors
- **Complexity**: Avoid C/D rated functions (use radon to check)

### Pre-commit Checklist

Before committing, ensure:

- [ ] All tests pass
- [ ] Code is formatted (`ruff format`)
- [ ] No linting errors (`ruff check`)
- [ ] No type errors (`mypy`)
- [ ] Coverage >90%
- [ ] Documentation updated
- [ ] CHANGELOG.md updated (if applicable)

## Submitting Changes

### 1. Commit Your Changes

```bash
git add .
git commit -m "feat: Add device grouping support

- Implement group creation API
- Add group update and delete methods
- Include comprehensive tests

Closes #123"
```

Commit message format:
- `feat:` - New feature
- `fix:` - Bug fix
- `docs:` - Documentation changes
- `test:` - Test additions/changes
- `refactor:` - Code refactoring
- `chore:` - Maintenance tasks

### 2. Push to Your Fork

```bash
git push origin feature/your-feature-name
```

### 3. Create Pull Request

1. Go to https://github.com/joyfulhouse/pythermacell
2. Click "New Pull Request"
3. Select your fork and branch
4. Fill in the PR template:
   - Description of changes
   - Related issues
   - Testing performed
   - Screenshots (if UI changes)

### 4. PR Requirements

Your PR must:
- ✅ Pass all CI checks (linting, type checking, tests)
- ✅ Include tests for new functionality
- ✅ Update documentation if needed
- ✅ Have a clear description
- ✅ Follow code style guidelines

## CI/CD Pipeline

### Automated Checks

Every PR triggers:

1. **Linting & Type Checking**
   - Ruff formatting check
   - Ruff linting
   - Mypy type checking

2. **Unit Tests**
   - Runs on Python 3.13 and 3.14
   - Must pass with >90% coverage

3. **Integration Tests** (main branch only)
   - Requires admin approval
   - Uses GitHub Secrets for credentials
   - Tests against real API

### Pipeline Stages

```
Pull Request → Lint → Unit Tests → Merge
                                     ↓
Main Branch → Lint → Unit Tests → Integration Tests*
                                     ↓
Tag (v*.*.*)  → Lint → Unit Tests → Integration Tests* → TestPyPI → PyPI

* Requires manual approval
```

### Environment Protection

- **integration-tests**: Requires manual approval
- **testpypi**: Automatic on version tags
- **pypi**: Requires manual approval after TestPyPI

## Release Process

### 1. Update Version

Update version in `pyproject.toml` and `src/pythermacell/__init__.py`:

```python
__version__ = "0.2.0"
```

### 2. Update CHANGELOG

Add release notes to `docs/CHANGELOG.md`:

```markdown
## [0.2.0] - 2025-01-19

### Added
- Device grouping support
- Multi-device control

### Fixed
- LED saturation parameter crash

### Changed
- Improved error handling
```

### 3. Create Tag

```bash
git add pyproject.toml src/pythermacell/__init__.py docs/CHANGELOG.md
git commit -m "chore: Bump version to 0.2.0"
git tag -a v0.2.0 -m "Release version 0.2.0"
git push origin main --tags
```

### 4. Automated Publishing

The CI pipeline will:
1. Run all tests
2. Publish to TestPyPI
3. Wait for manual approval
4. Publish to PyPI

### 5. Create GitHub Release

1. Go to https://github.com/joyfulhouse/pythermacell/releases
2. Click "Create a new release"
3. Select the tag (v0.2.0)
4. Copy CHANGELOG entry
5. Publish release

## Project Structure

```
pythermacell/
├── .github/
│   └── workflows/
│       └── ci.yml              # CI/CD pipeline
├── src/pythermacell/
│   ├── __init__.py            # Public API
│   ├── client.py              # Main client
│   ├── auth.py                # Authentication
│   ├── devices.py             # Device management
│   ├── models.py              # Data models
│   ├── exceptions.py          # Custom exceptions
│   ├── resilience.py          # Resilience patterns
│   ├── const.py               # Constants
│   └── py.typed               # PEP 561 marker
├── tests/
│   ├── test_*.py              # Unit tests
│   └── integration/           # Integration tests
├── docs/                      # Documentation
├── examples/                  # Usage examples
├── pyproject.toml             # Package configuration
├── README.md                  # Main documentation
└── CONTRIBUTING.md            # This file
```

## Getting Help

- **Questions**: Open a [Discussion](https://github.com/joyfulhouse/pythermacell/discussions)
- **Bugs**: Open an [Issue](https://github.com/joyfulhouse/pythermacell/issues)
- **Security**: Email bryan.li@gmail.com

## License

By contributing, you agree that your contributions will be licensed under the MIT License.

---

Thank you for contributing to pythermacell! 🎉
