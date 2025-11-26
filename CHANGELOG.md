# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.2.3] - 2025-11-25

### Fixed
- **Device name parsing**: User-friendly device names (e.g., "Pool", "ADU") are now correctly parsed from `params["LIV Hub"]["Name"]` instead of the generic device type from `config["info"]["name"]`
- Falls back to config name, then node_id if params name is not available

### Changed
- Integration tests are now less aggressive to avoid knocking devices offline:
  - Increased rate limit delay between tests (10s for control tests, 5s for regular)
  - `verify_state()` delay increased from 5s to 8s with 5s retry delay
  - Reduced `test_led_color_range` from 11 to 5 test iterations
  - All short delays (1-2s) increased to 5s minimum

### Added
- 3 new test cases for device name parsing fallback logic

## [0.2.2] - 2025-11-24

### Fixed
- Queue now handles event loop changes for reusable clients
- Sequential operations test properly verifies power state

### Added
- Coalescing command queue for intelligent request handling
- Retry logic to integration tests for CI reliability

## [0.1.0] - 2025-11-22

### Added
- Initial release of pythermacell library
- Core functionality:
  - Authentication with ESP RainMaker API
  - Device discovery and management
  - Device control (power, LED, parameters)
  - Three-layer architecture (API, Client, Device)
  - Optimistic updates for responsive UX
  - Auto-refresh and state change listeners
  - Resilience patterns (circuit breaker, exponential backoff, rate limiting)
- ThermacellClient class for high-level device management
- ThermacellAPI class for low-level HTTP operations
- ThermacellDevice class for stateful device representation
- AuthenticationHandler for JWT token management
- Session injection support for Home Assistant integration
- Comprehensive error handling with custom exceptions
- Type-safe implementation (100% mypy strict mode)
- Test coverage: 90.13%
- 212 comprehensive tests (161 unit, 51 integration)
- Documentation: README.md, CLAUDE.md, inline code comments, Google-style docstrings

### Technical Details
- Python 3.13+ support
- aiohttp for async HTTP operations
- ESP RainMaker API integration
- JWT token authentication with 4-hour lifetime
- Automatic token refresh on 401/403
- Rate limiting support (Retry-After header)
- Circuit breaker pattern for fault tolerance
- Exponential backoff with jitter for retries
- Optimistic updates with automatic rollback on failure
- Background auto-refresh with configurable intervals
- State change listener support for reactive programming

---

[0.2.3]: https://github.com/joyfulhouse/pythermacell/releases/tag/v0.2.3
[0.2.2]: https://github.com/joyfulhouse/pythermacell/releases/tag/v0.2.2
[0.1.0]: https://github.com/joyfulhouse/pythermacell/releases/tag/v0.1.0
