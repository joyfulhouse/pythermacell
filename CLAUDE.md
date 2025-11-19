# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**pythermacell** is a Python client library for Thermacell IoT devices, utilizing the ESP RainMaker API platform. The project goal is to create a standalone Python client that can authenticate with and control Thermacell devices through the cloud API at `https://api.iot.thermacell.com/`.

This project is based on extensive research including:
- Reverse-engineered Android APK (`research/com.thermacell.liv/`)
- Existing Home Assistant integration (`research/thermacell_liv/`)
- ESP RainMaker API documentation (https://swaggerapis.rainmaker.espressif.com/)

## Repository Structure

```
pythermacell/
├── research/                    # Research materials and references
│   ├── com.thermacell.liv/      # Decompiled Android APK (14,381 smali files)
│   │   ├── AndroidManifest.xml
│   │   ├── smali/               # Decompiled Java code
│   │   └── res/                 # App resources
│   └── thermacell_liv/          # Reference Home Assistant integration
│       ├── custom_components/thermacell_liv/  # Production HA integration
│       │   ├── api.py          # ESP RainMaker API client implementation
│       │   ├── coordinator.py  # Data coordinator with optimistic updates
│       │   ├── switch.py       # Switch platform (device control)
│       │   ├── light.py        # Light platform (LED control)
│       │   ├── sensor.py       # Sensor platform (status, runtime, refill)
│       │   └── button.py       # Button platform (refill reset, refresh)
│       ├── tests/              # Comprehensive test suite
│       │   ├── integration/    # Real API integration tests
│       │   ├── manual/         # Manual testing scripts
│       │   └── debug/          # Debug and investigation scripts
│       └── docs/               # Integration documentation
├── docs/                       # Project documentation (to be created)
│   └── RESEARCH.md            # Research findings (to be created)
└── pythermacell/              # Main Python package (to be created)
    ├── __init__.py
    ├── client.py              # Main client class
    ├── auth.py                # Authentication handler
    ├── devices.py             # Device management
    └── exceptions.py          # Custom exceptions
```

## API Architecture

### Base API Information
- **Base URL**: `https://api.iot.thermacell.com/`
- **Platform**: ESP RainMaker (Espressif IoT platform)
- **API Documentation**: https://swaggerapis.rainmaker.espressif.com/
- **Authentication**: Username/password → JWT tokens (access + ID token)
- **Protocol**: HTTPS REST API with JSON payloads

### Key API Endpoints

From research/thermacell_liv integration, the following endpoints are validated:

1. **Authentication**: `POST /v1/login2`
   - Request: `{"user_name": str, "password": str}`
   - Response: `{"accesstoken": str, "idtoken": str}`
   - Note: User ID extracted from JWT `idtoken` payload field `custom:user_id`

2. **Device Discovery**: `GET /v1/user/nodes` or `GET /v1/user2/nodes?user_id={user_id}`
   - Headers: `Authorization: {accesstoken}`
   - Response: List of user's devices with IDs and basic info

3. **Device Status**: `GET /v1/user/nodes/status?nodeid={node_id}` or `GET /v1/user2/nodes/status?nodeid={node_id}`
   - Headers: `Authorization: {accesstoken}`
   - Response: Real-time device connectivity status

4. **Device Configuration**: `GET /v1/user/nodes/config?nodeid={node_id}`
   - Headers: `Authorization: {accesstoken}`
   - Response: Device model, firmware version, serial number

5. **Device Parameters**: `GET /v1/user/nodes/params?nodeid={node_id}`
   - Headers: `Authorization: {accesstoken}`
   - Response: Current device state (power, LED, refill life, runtime, etc.)

6. **Control Device**: `PUT /v1/user/nodes/params?nodeid={node_id}`
   - Headers: `Authorization: {accesstoken}`
   - Request: Parameter updates for device control
   - Response: Success/failure confirmation

### JWT Token Handling

The API uses JWT tokens for authentication:
```python
# Decode JWT payload without verification
import base64, json
parts = jwt_token.split(".")
payload = parts[1]
padding = 4 - len(payload) % 4
if padding != 4:
    payload += "=" * padding
decoded = base64.urlsafe_b64decode(payload)
payload_data = json.loads(decoded.decode("utf-8"))
user_id = payload_data.get("custom:user_id")
```

### Device Data Structure

Based on research/thermacell_liv/custom_components/thermacell_liv/api.py:

**Device Parameters** (from `/params` endpoint):
```python
{
    "LIV Hub": {
        "Power": bool,              # Device on/off
        "LED Power": bool,          # LED on/off
        "LED Brightness": int,      # 0-100
        "LED Hue": int,            # 0-360 (HSV color)
        "LED Saturation": int,      # 0-100 (HSV color)
        "Refill Life": float,       # Percentage remaining
        "System Runtime": int,      # Minutes of runtime
        "System Status": int,       # 1=Off, 2=Warming, 3=Protected
        "Error": int,              # Error code (0=no error)
        "Enable Repellers": bool    # Repeller enable state
    }
}
```

## Development Guidelines

### Commands and Workflows

**Testing**:
```bash
# Run all tests (excludes manual/integration by default)
pytest tests/

# Run with coverage
pytest tests/ --cov=pythermacell --cov-report=term-missing

# Run specific test file
pytest tests/test_client.py -v

# Run integration tests (requires credentials in tests/integration/secrets.py)
pytest tests/integration/test_real_api.py -v
```

**Important Testing Guidelines**:
- **ALWAYS use pytest-aiohttp for HTTP/session testing** - Do NOT mock ClientSession directly
- Use `aiohttp.web.Application` with test routes for mocking API endpoints
- Use `aiohttp_client` fixture to create test clients
- Mock the `_auth_handler` instead of trying to mock complex session behavior
- Example pattern:
  ```python
  @pytest.fixture
  def app() -> Application:
      app = web.Application()
      async def mock_endpoint(request: web.Request) -> web.Response:
          return web.json_response({"data": "test"})
      app.router.add_get("/v1/endpoint", mock_endpoint)
      return app

  async def test_method(aiohttp_client, app):
      test_client = await aiohttp_client(app)
      base_url = str(test_client.make_url("/"))

      client = ThermacellClient(username="test", password="test", base_url=base_url.rstrip("/"))
      mock_auth = AsyncMock()
      mock_auth.ensure_authenticated = AsyncMock()
      mock_auth.access_token = "fake-token"
      client._auth_handler = mock_auth

      async with client:
          result = await client.some_method()
  ```

**Code Quality**:
```bash
# Format code with black (line length 120)
black pythermacell/ tests/

# Sort imports with isort
isort pythermacell/ tests/

# Type checking with mypy (strict mode)
mypy pythermacell/

# Linting with ruff
ruff check pythermacell/ tests/
```

**Building**:
```bash
# Install in development mode
pip install -e .

# Build package
python -m build

# Install from built package
pip install dist/pythermacell-*.whl
```

### Code Standards

This project follows strict code quality standards inspired by the Home Assistant Platinum tier quality scale:

1. **Type Hints**: All functions must have complete type annotations
   - Use `from __future__ import annotations` for forward references
   - Enable mypy strict mode (`disallow_untyped_defs = true`)

2. **Async/Await**: All I/O operations must be async
   - Use `aiohttp` for HTTP requests
   - Use `asyncio` for concurrent operations
   - No blocking operations in async code

3. **Error Handling**:
   - Define custom exceptions in `exceptions.py`
   - Use proper exception handling with specific exception types
   - Log errors with appropriate levels (DEBUG, INFO, WARNING, ERROR)

4. **Testing**:
   - Target >90% code coverage
   - Use `pytest` with async support (`pytest-asyncio`)
   - Mock external API calls in unit tests
   - Use `tests/integration/` for real API tests

5. **Documentation**:
   - Docstrings for all public classes and methods
   - Google-style docstring format
   - Keep `docs/RESEARCH.md` updated with API findings

### Research Materials

The `research/` folder contains invaluable reference materials:

**Home Assistant Integration** (`research/thermacell_liv/`):
- Production-quality reference implementation
- Real API endpoint validation in `tests/integration/`
- Comprehensive error handling patterns
- Optimistic update architecture for responsive UX
- Complete entity implementations (switch, light, sensor, button)

**Android APK** (`research/com.thermacell.liv/`):
- 14,381 decompiled smali files
- May contain API endpoint definitions
- Useful for understanding device communication patterns
- Check `AndroidManifest.xml` for app permissions and services

**Using Research Materials**:
1. **API Discovery**: Check `research/thermacell_liv/tests/integration/validate_api.py` for validated endpoints
2. **Error Codes**: Look in `research/thermacell_liv/custom_components/thermacell_liv/sensor.py` for error mappings
3. **Parameter Names**: Reference `api.py` and `coordinator.py` for exact parameter keys
4. **Authentication Flow**: Study `api.py` authenticate() method for JWT handling

**Creating Research Scripts**:
- All research scripts and their output samples must be placed in the `research/` directory
- Research scripts should be named descriptively (e.g., `research_groups.py`, `research_oauth.py`)
- Save API response samples as JSON files in `research/` for documentation purposes

## OpenAPI Specification

As part of the project goals, create an OpenAPI 3.0 specification file:

**Location**: `docs/openapi.yaml`

**Content**: Document all discovered API endpoints with:
- Path parameters, query parameters, headers
- Request/response schemas with examples
- Authentication requirements
- Error responses

**Example structure**:
```yaml
openapi: 3.0.0
info:
  title: Thermacell IoT API
  description: ESP RainMaker API for Thermacell LIV devices
  version: 1.0.0
servers:
  - url: https://api.iot.thermacell.com
paths:
  /v1/login2:
    post:
      summary: Authenticate user
      # ... complete endpoint documentation
```

## Documentation Requirements

**docs/RESEARCH.md** should contain:

1. **API Endpoint Catalog**: Complete list with request/response examples
2. **Authentication Flow**: Step-by-step JWT token acquisition
3. **Device Parameter Mapping**: All known parameters with types and ranges
4. **Error Codes**: Documented error codes and their meanings
5. **Rate Limiting**: Any observed API rate limits or throttling
6. **SDK Comparison**: How this client differs from/improves on HA integration
7. **Testing Methodology**: How API endpoints were discovered and validated

## Environment Setup

**Required Dependencies**:
```bash
# Core dependencies
pip install aiohttp>=3.8.0

# Development dependencies
pip install pytest pytest-asyncio pytest-cov
pip install black isort mypy ruff
pip install build twine  # for package distribution
```

**Credentials for Testing**:
Create `tests/integration/secrets.py`:
```python
THERMACELL_USERNAME = "your_email@example.com"
THERMACELL_PASSWORD = "your_password"
THERMACELL_API_BASE_URL = "https://api.iot.thermacell.com"
```

**Note**: Never commit `secrets.py` - it's in `.gitignore`

## Architecture Principles

The Python client should follow these design principles from the HA integration:

1. **Async-First**: All API calls use async/await
2. **Session Management**: Reuse aiohttp ClientSession
3. **Token Caching**: Cache access tokens, refresh on 401
4. **Retry Logic**: Implement exponential backoff (see api.py:99-120)
5. **Timeout Handling**: 30-second default timeout for API calls
6. **Error Granularity**: Specific exceptions for auth, network, API errors

**Example Client Interface**:
```python
from pythermacell import ThermacellClient, AuthenticationError

async def main():
    async with ThermacellClient(username, password) as client:
        # Authenticate automatically on first call
        devices = await client.get_devices()

        for device in devices:
            print(f"Device: {device.name}")
            await device.turn_on()
            await device.set_led_color(hue=120, saturation=100, brightness=80)
            status = await device.get_status()
            print(f"Status: {status}")
```

## Important Notes

1. **API Base URL**: Always use `https://api.iot.thermacell.com/` - this is hardcoded in the mobile app
2. **Endpoint Versions**: Both `/v1/user/` and `/v1/user2/` endpoints exist - prefer v1 for consistency
3. **Color Handling**: API uses HSV (hue 0-360, saturation 0-100) not RGB
4. **Runtime Tracking**: API returns session runtime, not lifetime runtime (unlike mobile app)
5. **Authentication Lock**: Use asyncio.Lock for thread-safe token refresh
6. **SSL Verification**: Always verify SSL in production (disable only for testing)

## Project Status

**Current Phase**: ✅ **Production Ready (v0.1.0)**

### ✅ Completed Implementation

**Core Package**:
- [x] Main pythermacell package structure (`src/pythermacell/`)
- [x] Client implementation with full auth and device management
- [x] Session injection support for Home Assistant integration
- [x] Resilience patterns (circuit breaker, exponential backoff, rate limiting)
- [x] Comprehensive error handling with custom exceptions
- [x] Type-safe implementation with 100% type coverage

**Code Quality** (Platinum Tier):
- [x] 90.13% test coverage (exceeds 90% target)
  - auth.py: 89.04%
  - client.py: 78.72%
  - devices.py: 94.59%
  - resilience.py: 94.79%
  - exceptions.py: 100%
  - models.py: 100%
  - const.py: 100%
- [x] Zero linting violations (ruff)
- [x] Zero type errors (mypy strict mode)
- [x] 212 comprehensive tests (161 unit, 51 integration)

**Documentation**:
- [x] Comprehensive README with usage examples
- [x] CHANGELOG.md with version history
- [x] Inline code comments for complex logic
- [x] Google-style docstrings throughout
- [x] API reference in README
- [x] Architecture documentation via comments

**Package Infrastructure**:
- [x] pyproject.toml with modern Python packaging
- [x] Development dependencies configured
- [x] Constants centralized in const.py
- [x] Proper module exports in __init__.py

### 🚧 To Be Created (Optional Enhancements)

**Future Enhancements**:
- [ ] OpenAPI specification (docs/openapi.yaml)
- [ ] Standalone ARCHITECTURE.md document
- [ ] Standalone API.md reference
- [ ] Standalone TESTING.md guide
- [ ] CI/CD pipeline (GitHub Actions)
- [ ] Example scripts directory
- [ ] PyPI package publication

### 📊 Quality Metrics

| Metric | Target | Actual | Status |
|--------|--------|--------|--------|
| Test Coverage | >90% | 90.13% | ✅ Achieved |
| Type Safety | 100% | 100% | ✅ Perfect |
| Linting Errors | 0 | 0 | ✅ Clean |
| Unit Tests | >150 | 161 | ✅ Exceeded |
| Documentation | Complete | Comprehensive | ✅ Excellent |

### 🎯 Implementation Highlights

**Performance Optimizations**:
- Concurrent device fetching using `asyncio.gather()`
- Efficient session reuse and connection pooling
- Smart authentication caching with 4-hour token lifetime

**Resilience Features**:
- Circuit breaker prevents cascading failures
- Exponential backoff with jitter for retries
- Rate limiting with Retry-After header support
- Automatic reauthentication on 401/403 responses

**Code Organization**:
- Clean separation of concerns (auth, client, devices, models, resilience)
- Centralized constants in `const.py`
- Comprehensive exception hierarchy
- Type-safe data models with dataclasses

**LED State Logic**:
- Properly implements "LED on = device powered AND brightness > 0"
- Matches physical device behavior
- Well-documented in code and README

**Reference Implementation Available**:
The `research/thermacell_liv/` folder contains a complete, production-ready Home Assistant integration. Used as authoritative reference for API behavior, error handling, and best practices.
- We only need to implement device control and updates, any user management capabilities would not be needed for our project.

## Documentation Organization

### Directory Structure

**IMPORTANT**: Keep documentation organized following these strict guidelines:

```
pythermacell/
├── README.md                    # Main project README (root only)
├── CLAUDE.md                    # This file (root only)
├── LICENSE                      # Project license (root only)
│
├── docs/                        # All documentation goes here
│   ├── README.md                # Documentation index (links to all docs)
│   ├── CHANGELOG.md             # Version history
│   │
│   ├── api/                     # API endpoint documentation
│   │   ├── README.md            # API overview and quick reference
│   │   ├── LED_CONTROL.md       # ⚠️ LED control (saturation causes crashes)
│   │   ├── GROUPS_API.md        # Device grouping functionality
│   │   └── OTA_UPDATE_ENDPOINTS.md  # OTA firmware updates
│   │
│   ├── architecture/            # System design documentation
│   │   ├── README.md            # Architecture overview
│   │   ├── AUTHENTICATION.md    # JWT auth flow
│   │   └── RESILIENCE.md        # Circuit breaker, retries, rate limiting
│   │
│   ├── testing/                 # Test documentation
│   │   ├── TESTING.md           # Test guide
│   │   └── INTEGRATION_TEST_RESULTS.md  # Test results
│   │
│   ├── research/                # Research and analysis
│   │   ├── API_GAP_ANALYSIS.md  # Complete API coverage
│   │   ├── API_GAP_ANALYSIS_FOCUSED.md  # Priority features
│   │   └── API_IMPLEMENTATION_PRIORITY.md  # Roadmap
│   │
│   └── development/             # Development notes
│       ├── IMPROVEMENTS.md      # Enhancement proposals
│       ├── CODE_REVIEW_FEEDBACK.md  # Review notes
│       └── DEVICE_POWER_FIX.md  # Debugging notes
│
└── research/                    # External reference materials (read-only)
    ├── com.thermacell.liv/      # Decompiled Android APK
    └── thermacell_liv/          # Home Assistant integration
```

### Documentation Guidelines

When creating or updating documentation:

1. **Choose the correct category**:
   - `docs/api/` - API endpoints, parameters, request/response formats
   - `docs/architecture/` - System design, patterns, component interactions
   - `docs/testing/` - Test guides, results, coverage reports
   - `docs/research/` - APK analysis, gap analysis, investigations
   - `docs/development/` - Debug notes, improvement proposals, reviews

2. **Only these files belong in project root**:
   - `README.md` - Main project README
   - `CLAUDE.md` - This file (Claude Code instructions)
   - `LICENSE` - Project license
   - **NO other `.md` files!**

3. **Document naming conventions**:
   - Use descriptive, UPPER_CASE names: `LED_CONTROL.md`, `AUTHENTICATION.md`
   - Avoid generic names: ~~`notes.md`~~, ~~`stuff.md`~~
   - Be specific about content: `DEVICE_POWER_FIX.md` not `fix.md`

4. **Cross-reference related docs**:
   - Use relative paths: `[Auth](../architecture/AUTHENTICATION.md)`
   - Update index files (`docs/README.md` and category READMEs)
   - Link to related documentation sections

5. **Avoid duplicate/redundant files**:
   - ~~`INDEX.md`~~ (use `README.md`)
   - ~~`DOCUMENTATION_INDEX.md`~~ (use `docs/README.md`)
   - Consolidate similar topics (don't create multiple gap analysis files)

6. **Include metadata** in new docs:
   ```markdown
   # Document Title

   **Category**: API Reference | Architecture | Testing | Research | Development
   **Last Updated**: 2025-11-18
   **Related**: [Related Doc](../path/to/doc.md)
   ```

### Critical API Findings

When documenting API behavior, always reference:

1. **Android APK** (`research/com.thermacell.liv/`) - Source of truth for actual API calls
2. **Home Assistant** (`research/thermacell_liv/`) - Production reference implementation
3. **Live Testing** - Verify behavior with real devices

**Example: LED Saturation Parameter**
- ⚠️ **DO NOT send `LED Saturation`** - Causes device crashes
- Documented in `docs/api/LED_CONTROL.md` with evidence from APK and HA
- APK analysis shows color picker only sends HUE, never saturation
- HA hardcodes saturation to 100% (full saturation)
- Sending saturation causes HTTP 400 and device offline

### Documentation Maintenance

- Update `docs/README.md` when adding new documents
- Update category READMEs (`docs/api/README.md`, etc.) for major additions
- Keep CHANGELOG.md updated with significant changes
- Cross-reference related documentation
- Remove outdated/redundant files

### When Reading/Writing Docs

- **Always use `docs/` prefix** when referencing documentation
- Check `docs/README.md` first to find existing docs
- Don't duplicate information - link to existing docs instead
- Keep root directory clean - only README, CLAUDE.md, and LICENSE