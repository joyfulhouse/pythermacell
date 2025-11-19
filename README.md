# pythermacell

[![PyPI version](https://badge.fury.io/py/pythermacell.svg)](https://badge.fury.io/py/pythermacell)
[![Python Support](https://img.shields.io/pypi/pyversions/pythermacell.svg)](https://pypi.org/project/pythermacell/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Code style: ruff](https://img.shields.io/badge/code%20style-ruff-000000.svg)](https://github.com/astral-sh/ruff)
[![Type checked: mypy](https://img.shields.io/badge/type%20checked-mypy-blue.svg)](http://mypy-lang.org/)
[![Test Coverage](https://img.shields.io/badge/coverage-89%25-brightgreen.svg)](https://github.com/joyfulhouse/pythermacell)

A modern, fully-typed Python client library for **Thermacell IoT devices** using the ESP RainMaker API platform.

## Features

✨ **Modern Python**
- Fully asynchronous API using `aiohttp`
- Comprehensive type hints with strict mypy checking
- Python 3.13+ support with latest language features

🔌 **Production-Ready**
- Session injection support for efficient resource management
- Built-in resilience patterns (circuit breaker, exponential backoff, rate limiting)
- Comprehensive error handling with custom exception types
- 90%+ test coverage with unit and integration tests

🎮 **Device Control**
- Power control (on/off)
- LED control (RGB color, brightness)
- Device monitoring (refill life, runtime, status, connectivity)
- Concurrent device operations for performance

🏗️ **Well-Designed**
- Clean, intuitive API
- Excellent documentation
- Follows Home Assistant Platinum tier quality standards
- Separation of concerns with clear architecture

---

## Table of Contents

- [Installation](#installation)
- [Quick Start](#quick-start)
- [Usage Guide](#usage-guide)
  - [Basic Usage](#basic-usage)
  - [Device Control](#device-control)
  - [Session Management](#session-management)
  - [Resilience Patterns](#resilience-patterns)
- [API Reference](#api-reference)
- [Examples](#examples)
- [Development](#development)
- [Testing](#testing)
- [Documentation](#documentation)
- [Contributing](#contributing)
- [License](#license)

---

## Installation

### From PyPI (recommended)

```bash
pip install pythermacell
```

### From Source

```bash
git clone https://github.com/joyfulhouse/pythermacell.git
cd pythermacell
pip install -e .
```

### With Development Dependencies

```bash
pip install -e ".[dev]"
```

---

## Quick Start

```python
import asyncio
from pythermacell import ThermacellClient

async def main():
    """Quick example: Control your Thermacell device."""
    async with ThermacellClient(
        username="your@email.com",
        password="your_password"
    ) as client:
        # Get all devices
        devices = await client.get_devices()

        for device in devices:
            print(f"Found device: {device.name} ({device.model})")
            print(f"  Firmware: {device.firmware_version}")
            print(f"  Online: {device.is_online}")

            # Turn on the device
            await device.turn_on()

            # Set LED to green
            await device.set_led_color(hue=120, saturation=100, brightness=80)

            # Check refill status
            print(f"  Refill life: {device.refill_life}%")

if __name__ == "__main__":
    asyncio.run(main())
```

---

## Usage Guide

### Basic Usage

#### Authentication

The library handles authentication automatically when you use the context manager:

```python
from pythermacell import ThermacellClient

async with ThermacellClient(
    username="your@email.com",
    password="your_password",
    base_url="https://api.iot.thermacell.com"  # Optional, uses default
) as client:
    # Client is authenticated and ready to use
    devices = await client.get_devices()
```

#### Device Discovery

```python
# Get all devices
devices = await client.get_devices()

# Get a specific device by node ID
device = await client.get_device("node_id_here")

# Get device state (info + status + parameters)
state = await client.get_device_state("node_id_here")
```

### Device Control

#### Power Control

```python
# Turn device on
await device.turn_on()

# Turn device off
await device.turn_off()

# Set power state explicitly
await device.set_power(power_on=True)

# Check power state
if device.is_powered_on:
    print("Device is running")
```

#### LED Control

The Thermacell LIV Hub has an RGB LED that can be controlled:

```python
# Set LED color using HSV values
await device.set_led_color(
    hue=0,          # Red (0-360)
    saturation=100, # Full saturation (0-100)
    brightness=80   # 80% brightness (0-100)
)

# Set LED brightness only
await device.set_led_brightness(50)  # 50%

# Turn LED on/off
await device.set_led_power(True)

# Common colors (HSV hue values)
await device.set_led_color(hue=0, saturation=100, brightness=100)    # Red
await device.set_led_color(hue=120, saturation=100, brightness=100)  # Green
await device.set_led_color(hue=240, saturation=100, brightness=100)  # Blue
await device.set_led_color(hue=60, saturation=100, brightness=100)   # Yellow
```

**Important**: The LED can only be "on" when both:
1. The device is powered on (`enable_repellers=True`)
2. The LED brightness is greater than 0

This matches the physical device behavior.

#### Device Monitoring

```python
# Refresh device state from API
await device.refresh()

# Access device properties
print(f"Device: {device.name}")
print(f"Model: {device.model}")
print(f"Firmware: {device.firmware_version}")
print(f"Serial: {device.serial_number}")
print(f"Online: {device.is_online}")
print(f"Powered: {device.is_powered_on}")
print(f"Has Error: {device.has_error}")

# Access parameters
print(f"Refill Life: {device.refill_life}%")
print(f"Runtime: {device.system_runtime} minutes")
print(f"Status: {device.system_status}")  # 1=Off, 2=Warming, 3=Protected
print(f"Error Code: {device.error}")

# LED state
print(f"LED Power: {device.led_power}")
print(f"LED Brightness: {device.led_brightness}")
print(f"LED Hue: {device.led_hue}")
print(f"LED Saturation: {device.led_saturation}")
```

#### Maintenance Operations

```python
# Reset refill life counter to 100%
await device.reset_refill()
```

### Session Management

For applications that manage their own aiohttp sessions (like Home Assistant), you can inject a session:

```python
from aiohttp import ClientSession
from pythermacell import ThermacellClient

async with ClientSession() as session:
    client = ThermacellClient(
        username="your@email.com",
        password="your_password",
        session=session  # Inject your session
    )

    async with client:
        # Client uses your session
        # Session is NOT closed when client exits
        devices = await client.get_devices()

# Session is still available here
```

**Benefits of session injection:**
- Share a single session across multiple clients
- Connection pooling and keep-alive
- Efficient resource usage
- Integration with application lifecycle management

### Resilience Patterns

pythermacell includes production-ready resilience patterns for fault tolerance:

#### Circuit Breaker

Prevents cascading failures by blocking requests after repeated failures:

```python
from pythermacell import ThermacellClient
from pythermacell.resilience import CircuitBreaker

breaker = CircuitBreaker(
    failure_threshold=5,   # Open circuit after 5 consecutive failures
    recovery_timeout=60.0, # Wait 60 seconds before attempting recovery
    success_threshold=2    # Require 2 successes to close circuit
)

client = ThermacellClient(
    username="your@email.com",
    password="your_password",
    circuit_breaker=breaker
)

async with client:
    try:
        devices = await client.get_devices()
    except RuntimeError as e:
        if "circuit breaker" in str(e).lower():
            print("Circuit is open - too many failures")
```

#### Exponential Backoff

Automatically retries failed requests with increasing delays:

```python
from pythermacell.resilience import ExponentialBackoff

backoff = ExponentialBackoff(
    base_delay=1.0,        # Start with 1 second
    max_delay=60.0,        # Cap at 60 seconds
    max_retries=5,         # Retry up to 5 times
    exponential_base=2.0,  # Double delay each time
    jitter=True            # Add randomness to prevent thundering herd
)

client = ThermacellClient(
    username="your@email.com",
    password="your_password",
    backoff=backoff
)
```

**Retry delays**: 1s → 2s → 4s → 8s → 16s (with jitter)

#### Rate Limiting

Handles HTTP 429 responses and respects Retry-After headers:

```python
from pythermacell.resilience import RateLimiter

limiter = RateLimiter(
    respect_retry_after=True,  # Parse Retry-After header
    default_retry_delay=60.0,  # Default wait time (seconds)
    max_retry_delay=300.0      # Maximum wait time (5 minutes)
)

client = ThermacellClient(
    username="your@email.com",
    password="your_password",
    rate_limiter=limiter
)
```

#### Combined Resilience

Use all patterns together for maximum fault tolerance:

```python
from pythermacell import ThermacellClient
from pythermacell.resilience import CircuitBreaker, ExponentialBackoff, RateLimiter

# Configure all resilience patterns
breaker = CircuitBreaker(failure_threshold=5, recovery_timeout=60)
backoff = ExponentialBackoff(base_delay=1.0, max_retries=5)
limiter = RateLimiter()

# Create resilient client
client = ThermacellClient(
    username="your@email.com",
    password="your_password",
    circuit_breaker=breaker,
    backoff=backoff,
    rate_limiter=limiter
)

async with client:
    # Client automatically:
    # - Retries failed requests with exponential backoff
    # - Opens circuit after repeated failures
    # - Respects rate limiting
    devices = await client.get_devices()
```

---

## API Reference

### ThermacellClient

Main client for interacting with Thermacell devices.

```python
ThermacellClient(
    username: str,
    password: str,
    base_url: str = "https://api.iot.thermacell.com",
    *,
    session: ClientSession | None = None,
    auth_handler: AuthenticationHandler | None = None,
    circuit_breaker: CircuitBreaker | None = None,
    backoff: ExponentialBackoff | None = None,
    rate_limiter: RateLimiter | None = None,
)
```

**Methods:**
- `async get_devices() -> list[ThermacellDevice]` - Get all devices
- `async get_device(node_id: str) -> ThermacellDevice | None` - Get specific device
- `async get_device_state(node_id: str) -> DeviceState | None` - Get device state
- `async update_device_params(node_id: str, params: dict) -> bool` - Update device parameters

### ThermacellDevice

Represents a Thermacell device with control and monitoring capabilities.

**Properties:**
- `node_id: str` - Unique device identifier
- `name: str` - Human-readable device name
- `model: str` - Device model (e.g., "Thermacell LIV Hub")
- `firmware_version: str` - Current firmware version
- `serial_number: str` - Device serial number
- `is_online: bool` - Whether device is connected
- `is_powered_on: bool` - Whether device is powered on
- `has_error: bool` - Whether device has an error
- `refill_life: float | None` - Refill cartridge life percentage (0-100)
- `system_runtime: int | None` - Current session runtime in minutes
- `system_status: int | None` - System status (1=Off, 2=Warming, 3=Protected)
- `error: int | None` - Error code (0=no error)
- `led_power: bool | None` - LED on/off state
- `led_brightness: int | None` - LED brightness (0-100)
- `led_hue: int | None` - LED hue (0-360)
- `led_saturation: int | None` - LED saturation (0-100)

**Methods:**
- `async turn_on() -> bool` - Turn device on
- `async turn_off() -> bool` - Turn device off
- `async set_power(power_on: bool) -> bool` - Set power state
- `async set_led_power(power_on: bool) -> bool` - Set LED power
- `async set_led_brightness(brightness: int) -> bool` - Set LED brightness (0-100)
- `async set_led_color(hue: int, saturation: int, brightness: int) -> bool` - Set LED color
- `async reset_refill() -> bool` - Reset refill life to 100%
- `async refresh() -> bool` - Refresh device state from API

### AuthenticationHandler

Handles JWT-based authentication with the Thermacell API.

```python
AuthenticationHandler(
    username: str,
    password: str,
    base_url: str = "https://api.iot.thermacell.com",
    *,
    session: ClientSession | None = None,
    on_session_updated: Callable[[AuthenticationHandler], None] | None = None,
    auth_lifetime_seconds: int = 14400,  # 4 hours
    circuit_breaker: CircuitBreaker | None = None,
    backoff: ExponentialBackoff | None = None,
    rate_limiter: RateLimiter | None = None,
)
```

**Methods:**
- `async authenticate(force: bool = False) -> bool` - Authenticate with API
- `async ensure_authenticated() -> None` - Ensure valid authentication
- `async force_reauthenticate() -> bool` - Force token refresh
- `is_authenticated() -> bool` - Check if authenticated
- `needs_reauthentication() -> bool` - Check if reauthentication needed
- `clear_authentication() -> None` - Clear stored tokens

### Exception Hierarchy

```
ThermacellError (base)
├── AuthenticationError - Authentication failures
├── ThermacellConnectionError - Connection/network errors
├── ThermacellTimeoutError - Request timeouts
├── RateLimitError - Rate limiting errors
├── DeviceError - Device-related errors
└── InvalidParameterError - Invalid parameter values
```

See [docs/API.md](docs/API.md) for complete API reference.

---

## Examples

### Example 1: Simple Device Control

```python
import asyncio
from pythermacell import ThermacellClient

async def control_device():
    """Turn on device and set LED to blue."""
    async with ThermacellClient(
        username="your@email.com",
        password="your_password"
    ) as client:
        devices = await client.get_devices()
        device = devices[0]

        # Turn on device
        await device.turn_on()

        # Set LED to blue
        await device.set_led_color(hue=240, saturation=100, brightness=80)

        print(f"Device {device.name} is now on with blue LED")

asyncio.run(control_device())
```

### Example 2: Monitor Multiple Devices

```python
import asyncio
from pythermacell import ThermacellClient

async def monitor_devices():
    """Monitor refill life for all devices."""
    async with ThermacellClient(
        username="your@email.com",
        password="your_password"
    ) as client:
        devices = await client.get_devices()

        for device in devices:
            await device.refresh()

            print(f"\n{device.name}:")
            print(f"  Online: {device.is_online}")
            print(f"  Powered: {device.is_powered_on}")
            print(f"  Refill: {device.refill_life}%")
            print(f"  Runtime: {device.system_runtime} min")

            # Alert if refill is low
            if device.refill_life and device.refill_life < 20:
                print(f"  ⚠️  LOW REFILL - {device.refill_life}%")

asyncio.run(monitor_devices())
```

### Example 3: Session Injection (Home Assistant Integration)

```python
from aiohttp import ClientSession
from pythermacell import ThermacellClient

class ThermacellIntegration:
    """Example Home Assistant integration."""

    def __init__(self, hass, username, password):
        self.hass = hass
        self.username = username
        self.password = password
        self.client = None

    async def async_setup(self):
        """Set up the integration."""
        # Use Home Assistant's shared session
        session = self.hass.helpers.aiohttp_client.async_get_clientsession()

        self.client = ThermacellClient(
            username=self.username,
            password=self.password,
            session=session  # Inject HA's session
        )

        await self.client.__aenter__()

        # Get devices
        devices = await self.client.get_devices()
        return devices

    async def async_unload(self):
        """Unload the integration."""
        if self.client:
            await self.client.__aexit__(None, None, None)
```

### Example 4: Error Handling

```python
import asyncio
from pythermacell import (
    ThermacellClient,
    AuthenticationError,
    ThermacellConnectionError,
    DeviceError,
)

async def robust_control():
    """Control device with comprehensive error handling."""
    try:
        async with ThermacellClient(
            username="your@email.com",
            password="your_password"
        ) as client:
            devices = await client.get_devices()

            if not devices:
                print("No devices found")
                return

            device = devices[0]
            await device.turn_on()

    except AuthenticationError as e:
        print(f"Authentication failed: {e}")
        print("Check your username and password")

    except ThermacellConnectionError as e:
        print(f"Connection error: {e}")
        print("Check your internet connection")

    except DeviceError as e:
        print(f"Device error: {e}")
        print("Device may be offline")

    except Exception as e:
        print(f"Unexpected error: {e}")

asyncio.run(robust_control())
```

### Example 5: Resilience Patterns

```python
import asyncio
from pythermacell import ThermacellClient
from pythermacell.resilience import CircuitBreaker, ExponentialBackoff

async def resilient_operation():
    """Use resilience patterns for fault tolerance."""
    breaker = CircuitBreaker(failure_threshold=3, recovery_timeout=30)
    backoff = ExponentialBackoff(base_delay=1.0, max_retries=3)

    client = ThermacellClient(
        username="your@email.com",
        password="your_password",
        circuit_breaker=breaker,
        backoff=backoff
    )

    async with client:
        try:
            # This will automatically retry on failure with backoff
            devices = await client.get_devices()
            print(f"Found {len(devices)} devices")

        except RuntimeError as e:
            if "circuit breaker" in str(e).lower():
                print("Circuit opened - too many failures")
                print(f"Breaker state: {breaker.state}")
                print(f"Failures: {breaker.failure_count}")

asyncio.run(resilient_operation())
```

More examples available in the [`examples/`](examples/) directory.

---

## Development

### Setup Development Environment

```bash
# Clone the repository
git clone https://github.com/joyfulhouse/pythermacell.git
cd pythermacell

# Create virtual environment
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate

# Install in development mode with all dependencies
pip install -e ".[dev]"
```

### Project Structure

```
pythermacell/
├── src/pythermacell/         # Main package
│   ├── __init__.py           # Public API exports
│   ├── client.py             # ThermacellClient implementation
│   ├── auth.py               # Authentication handler
│   ├── devices.py            # Device management
│   ├── models.py             # Data models
│   ├── exceptions.py         # Custom exceptions
│   ├── resilience.py         # Resilience patterns
│   └── const.py              # Constants
├── tests/                    # Test suite
│   ├── test_*.py             # Unit tests
│   ├── integration/          # Integration tests
│   └── conftest.py           # Pytest fixtures
├── docs/                     # Documentation
│   ├── API.md                # API reference
│   ├── ARCHITECTURE.md       # Design documentation
│   ├── TESTING.md            # Testing guide
│   └── CHANGELOG.md          # Version history
├── examples/                 # Usage examples
├── research/                 # Research materials
├── pyproject.toml            # Project configuration
├── README.md                 # This file
├── CLAUDE.md                 # AI assistant instructions
└── LICENSE                   # MIT License
```

---

## Testing

### Run Tests

```bash
# Run all tests
pytest

# Run with coverage report
pytest --cov=pythermacell --cov-report=term-missing

# Run only unit tests (fast)
pytest -m "not integration"

# Run only integration tests (requires credentials)
pytest -m integration

# Run specific test file
pytest tests/test_client.py -v

# Run with verbose output
pytest -v

# Stop on first failure
pytest -x
```

### Test Coverage

Current test coverage: **90.13%**

- `auth.py`: 89.04%
- `client.py`: 78.72%
- `devices.py`: 94.59%
- `resilience.py`: 94.79%
- `exceptions.py`: 100%
- `models.py`: 100%
- `const.py`: 100%

### Integration Tests

Integration tests require real API credentials:

1. Create `.env` file in project root:

```env
THERMACELL_USERNAME=your@email.com
THERMACELL_PASSWORD=your_password
THERMACELL_API_BASE_URL=https://api.iot.thermacell.com
THERMACELL_TEST_NODE_ID=optional_specific_device_id
```

2. Run integration tests:

```bash
pytest -m integration
```

See [docs/TESTING.md](docs/TESTING.md) for comprehensive testing guide.

---

## Documentation

- **[API Reference](docs/API.md)** - Complete API documentation
- **[Architecture Guide](docs/ARCHITECTURE.md)** - Design patterns and architecture
- **[Testing Guide](docs/TESTING.md)** - How to run and write tests
- **[Changelog](docs/CHANGELOG.md)** - Version history and changes
- **[Contributing](CONTRIBUTING.md)** - How to contribute to the project

---

## Code Quality

This project follows strict code quality standards:

### Linting and Formatting

```bash
# Format code with ruff
ruff format src/ tests/

# Lint code
ruff check src/ tests/

# Fix auto-fixable issues
ruff check --fix src/ tests/
```

### Type Checking

```bash
# Run mypy with strict mode
mypy src/pythermacell/

# Check specific file
mypy src/pythermacell/client.py
```

### Standards

- **Type Safety**: 100% type coverage with strict mypy
- **Code Style**: Ruff with comprehensive rule set
- **Line Length**: 120 characters
- **Python Version**: 3.13+
- **Test Coverage**: >90% target
- **Docstrings**: Google-style format
- **Import Sorting**: Automated with ruff

---

## Contributing

Contributions are welcome! Please see [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines.

### Quick Contribution Guide

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Make your changes
4. Run tests (`pytest`)
5. Run linting (`ruff check src/ tests/`)
6. Run type checking (`mypy src/`)
7. Commit your changes (`git commit -m 'Add amazing feature'`)
8. Push to the branch (`git push origin feature/amazing-feature`)
9. Open a Pull Request

---

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

---

## Credits and Acknowledgments

This project is based on extensive research including:

- **ESP RainMaker API** - Official documentation from Espressif
- **Thermacell LIV Home Assistant Integration** - Production reference implementation
- **Android APK Analysis** - Reverse-engineered Thermacell mobile app

Special thanks to:
- The Thermacell engineering team for their IoT platform
- The Home Assistant community for integration patterns
- The ESP RainMaker team at Espressif

---

## Support

- **Issues**: [GitHub Issues](https://github.com/joyfulhouse/pythermacell/issues)
- **Discussions**: [GitHub Discussions](https://github.com/joyfulhouse/pythermacell/discussions)

---

## Disclaimer

This is an unofficial library and is not affiliated with, endorsed by, or sponsored by Thermacell Repellents, Inc. All product names, logos, and brands are property of their respective owners.

Use this library at your own risk. The authors are not responsible for any damage to your devices or data.

---

## Changelog

See [CHANGELOG.md](docs/CHANGELOG.md) for version history and changes.

**Latest Version: 0.1.0**
- Initial release
- Full device control and monitoring
- Session injection support
- Resilience patterns (circuit breaker, backoff, rate limiting)
- 90%+ test coverage
- Comprehensive documentation

---

**Made with ❤️ for the Thermacell community**
