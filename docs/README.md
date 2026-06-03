# Documentation

Documentation for pythermacell — a Python client for Thermacell IoT devices.

| Document | Description |
|---|---|
| [USAGE.md](USAGE.md) | Usage guide, examples, and full API reference |
| [DEVELOPMENT.md](DEVELOPMENT.md) | Development environment, testing, and quality checks |
| [MIGRATION_v0.2.0.md](MIGRATION_v0.2.0.md) | Upgrading from v0.1.0 to v0.2.0 |

## Architecture

| Document | Description |
|---|---|
| [architecture/README.md](architecture/README.md) | System design and components |
| [architecture/AUTHENTICATION.md](architecture/AUTHENTICATION.md) | JWT authentication flow |
| [architecture/RESILIENCE.md](architecture/RESILIENCE.md) | Circuit breaker, backoff, rate limiting |

## API Reference

| Document | Description |
|---|---|
| [api/README.md](api/README.md) | ESP RainMaker API overview |
| [api/DISCOVERED_ENDPOINTS.md](api/DISCOVERED_ENDPOINTS.md) | Complete endpoint catalog |
| [api/LED_CONTROL.md](api/LED_CONTROL.md) | LED color control and the saturation caveat |
| [api/GROUPS_API.md](api/GROUPS_API.md) | Device grouping functionality |
| [api/OTA_UPDATE_ENDPOINTS.md](api/OTA_UPDATE_ENDPOINTS.md) | Over-the-air firmware updates |
| [api/openapi.yaml](api/openapi.yaml) | OpenAPI specification |

## Testing

| Document | Description |
|---|---|
| [testing/TESTING.md](testing/TESTING.md) | Unit and integration testing guide |
| [testing/INTEGRATION_TEST_RESULTS.md](testing/INTEGRATION_TEST_RESULTS.md) | Live API test results |

## Reference

- [development/CODE_REVIEW_PYTHON_BEST_PRACTICES.md](development/CODE_REVIEW_PYTHON_BEST_PRACTICES.md)
  — Python best-practices review notes.

---

> Internal design notes, session logs, and process artifacts (such as CI/CD
> pipeline analyses) live in [`claude/`](claude/) and are not part of the
> user-facing documentation. Exploratory research materials under `research/`
> are kept locally and excluded from version control.
