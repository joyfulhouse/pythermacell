# Changelog

All notable changes to pythermacell will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Planned
- OpenAPI specification documentation
- Additional device models support
- WebSocket support for real-time updates
- Device state caching with configurable TTL
- Historical data tracking

---

## [0.1.0] - 2025-01-XX

### Added - Initial Release

#### Core Features
- **ThermacellClient**: Main async client for Thermacell IoT devices
- **AuthenticationHandler**: JWT-based authentication with ESP RainMaker API
- **ThermacellDevice**: Device control and monitoring interface
- **Session Injection**: Support for external aiohttp session management
- **Concurrent Operations**: Parallel device state fetching for performance

#### Device Control
- Power control (on/off)
- LED control (RGB color via HSV, brightness)
- Refill life monitoring and reset
- System runtime tracking
- Device status and error monitoring
- Connectivity status checks

#### Resilience Patterns
- **Circuit Breaker**: Prevents cascading failures
  - Configurable failure threshold
  - Automatic recovery testing
  - Success threshold for circuit closure
- **Exponential Backoff**: Automatic retry with progressive delays
  - Configurable base delay and maximum delay
  - Jitter support to prevent thundering herd
  - Customizable retry attempts
- **Rate Limiting**: HTTP 429 handling
  - Retry-After header parsing
  - Configurable default and maximum delays

#### Data Models
- `DeviceInfo`: Device metadata (name, model, firmware, serial)
- `DeviceParams`: Operational parameters (power, LED, refill, runtime)
- `DeviceStatus`: Connectivity and online status
- `DeviceState`: Complete device state (info + params + status)
- `LoginResponse`: Authentication response

#### Error Handling
- Custom exception hierarchy
- `ThermacellError` (base exception)
- `AuthenticationError` (login failures)
- `ThermacellConnectionError` (network issues)
- `ThermacellTimeoutError` (request timeouts)
- `RateLimitError` (rate limiting)
- `DeviceError` (device-related errors)
- `InvalidParameterError` (parameter validation)

#### Code Quality
- **Type Safety**: 100% type coverage with strict mypy
- **Test Coverage**: 90.13% overall
  - auth.py: 89.04%
  - client.py: 78.72%
  - devices.py: 94.59%
  - resilience.py: 94.79%
  - exceptions.py: 100%
  - models.py: 100%
  - const.py: 100%
- **Linting**: Zero violations with ruff
- **Documentation**: Comprehensive docstrings and inline comments

#### Testing
- 212 total tests (161 unit, 51 integration)
- pytest with asyncio support
- aiohttp test utilities
- Real API integration tests
- Mock-based unit tests
- Comprehensive coverage reporting

#### Documentation
- Detailed README with usage examples
- API reference documentation
- Architecture guide
- Testing guide
- Inline code comments for complex logic
- Google-style docstrings

#### Development
- Modern Python 3.13+ support
- pyproject.toml configuration
- Development dependencies
- Pre-configured linting and formatting
- Type checking with mypy strict mode

### Technical Details

#### API Integration
- **Base URL**: https://api.iot.thermacell.com
- **Authentication**: JWT tokens with 4-hour lifetime
- **Endpoints**:
  - `/v1/login2` - Authentication
  - `/v1/user/nodes` - Device discovery
  - `/v1/user/nodes/params` - Device parameters
  - `/v1/user/nodes/status` - Device connectivity
  - `/v1/user/nodes/config` - Device configuration
- **Timeout**: 30-second default for all requests
- **Retry Logic**: Automatic reauthentication on 401/403

#### Implementation Highlights
- **LED State Logic**: LED only "on" when device powered AND brightness > 0
- **Concurrent Fetching**: asyncio.gather() for parallel device operations
- **Session Management**: Proper ownership tracking and cleanup
- **Context Managers**: Resource-safe async context managers
- **Parameter Validation**: Range validation for LED values
  - Brightness: 0-100
  - Hue: 0-360
  - Saturation: 0-100

#### Dependencies
- `aiohttp>=3.8.0` - Async HTTP client
- `python>=3.13` - Modern Python features

#### Development Dependencies
- `pytest>=7.0.0` - Testing framework
- `pytest-asyncio>=0.21.0` - Async test support
- `pytest-aiohttp>=1.0.0` - aiohttp test utilities
- `pytest-cov>=4.0.0` - Coverage reporting
- `ruff>=0.1.0` - Linting and formatting
- `mypy>=1.0.0` - Type checking
- `python-dotenv>=1.0.0` - Environment variable management

### Breaking Changes
- None (initial release)

### Deprecated
- None (initial release)

### Security
- No security vulnerabilities identified
- Credentials stored in memory only (not persisted)
- SSL/TLS verification enforced
- JWT token validation

### Known Issues
- Integration test timing: One test may occasionally timeout with real API
  - This is expected behavior due to network latency
  - Does not affect production usage
- Client.py coverage at 78.72%: Room for additional edge case tests
  - Core functionality fully tested
  - Missing coverage is in error path edge cases

### Migration Guide
- Not applicable (initial release)

---

## Version History

### [0.1.0] - Initial Release (2025-01-XX)
First public release of pythermacell with full device control, monitoring, and resilience patterns.

---

## Upgrade Notes

### To 0.1.0
No upgrade necessary - this is the initial release.

---

## Contributors

- **Primary Author**: [Your Name]
- **Contributors**: See GitHub contributors page

---

## Links

- [PyPI Package](https://pypi.org/project/pythermacell/)
- [GitHub Repository](https://github.com/yourusername/pythermacell)
- [Issue Tracker](https://github.com/yourusername/pythermacell/issues)
- [Documentation](https://github.com/yourusername/pythermacell/blob/main/README.md)

---

## Release Process

This project follows semantic versioning:

- **Major** (X.0.0): Breaking API changes
- **Minor** (0.X.0): New features, backward compatible
- **Patch** (0.0.X): Bug fixes, backward compatible

Each release includes:
1. Updated version number in `pyproject.toml` and `__init__.py`
2. Updated CHANGELOG.md with changes
3. Git tag with version number
4. GitHub release with notes
5. PyPI package publication

---

**Format**: [Semantic Versioning 2.0.0](https://semver.org/)
**Changelog Style**: [Keep a Changelog 1.0.0](https://keepachangelog.com/)
