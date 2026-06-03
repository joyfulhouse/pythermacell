# Usage Guide

Detailed usage for pythermacell. See the [README](../README.md) for a quick
start, and [`examples/`](../examples/) for complete runnable scripts.

## Contents

- [Authentication](#authentication)
- [Device Discovery](#device-discovery)
- [Device Control](#device-control)
  - [Power Control](#power-control)
  - [LED Control](#led-control)
  - [Device Monitoring](#device-monitoring)
- [Optimistic Updates](#optimistic-updates)
- [Auto-Refresh](#auto-refresh)
- [State Change Listeners](#state-change-listeners)
- [Maintenance Operations](#maintenance-operations)
- [Session Management](#session-management)
- [Resilience Patterns](#resilience-patterns)
- [Error Handling](#error-handling)
- [API Reference](#api-reference)
  - [ThermacellClient](#thermacellclient)
  - [ThermacellDevice](#thermacelldevice)
  - [AuthenticationHandler](#authenticationhandler)
  - [ThermacellAPI](#thermacellapi)
  - [Exception Hierarchy](#exception-hierarchy)
- [Examples](#examples)

## Authentication

The library handles authentication automatically when you use the context
manager:

```python
from pythermacell import ThermacellClient

async with ThermacellClient(
    username="your@email.com",
    password="your_password",
    base_url="https://api.iot.thermacell.com",  # Optional, uses default
) as client:
    # Client is authenticated and ready to use
    devices = await client.get_devices()
```

For the JWT flow, token lifetime, and automatic refresh on 401/403, see
[architecture/AUTHENTICATION.md](architecture/AUTHENTICATION.md).

## Device Discovery

```python
# Get all devices
devices = await client.get_devices()

# Get a specific device by node ID
device = await client.get_device("node_id_here")

# Get device state (info + status + parameters)
state = await client.get_device_state("node_id_here")
```

## Device Control

### Power Control

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

### LED Control

The Thermacell LIV Hub has an RGB LED that can be controlled:

```python
# Set LED color using HSV values
await device.set_led_color(
    hue=0,          # Red (0-360)
    saturation=100, # Full saturation (0-100)
    brightness=80,  # 80% brightness (0-100)
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

This matches the physical device behavior. For protocol-level notes and the
saturation-parameter caveat, see [api/LED_CONTROL.md](api/LED_CONTROL.md).

### Device Monitoring

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

## Optimistic Updates

Device control methods use optimistic updates for instant UI responsiveness:

```python
# Old behavior: Wait ~2.5s for API response before UI updates
# New behavior: UI updates instantly (~0.01s), API call happens in background

await device.turn_on()  # UI updates immediately
# If API call fails, state automatically reverts
```

**How it works:**

1. Local state updates immediately (instant UI feedback)
2. API call executes in background (~2.5s)
3. On failure, state automatically reverts and listeners are notified

## Auto-Refresh

Keep device state current with automatic background polling:

```python
# Start auto-refresh (polls every 60 seconds)
await device.start_auto_refresh(interval=60)

# Device state is automatically kept up-to-date
# Change listeners are notified on each refresh

# Stop auto-refresh
await device.stop_auto_refresh()
```

## State Change Listeners

Register callbacks to react to state changes:

```python
def on_state_change(device):
    print(f"{device.name} changed!")
    print(f"  Power: {device.is_powered_on}")
    print(f"  Refill: {device.refill_life}%")
    print(f"  Last refresh: {device.last_refresh}")

# Register listener
device.add_listener(on_state_change)

# Listener called on:
# - Optimistic updates (immediate)
# - Auto-refresh (every interval)
# - Manual refresh (when you call device.refresh())
# - Failed updates (reversion)

# Remove listener
device.remove_listener(on_state_change)
```

## Maintenance Operations

```python
# Reset refill life counter to 100%
await device.reset_refill()
```

## Session Management

For applications that manage their own aiohttp sessions (like Home Assistant),
you can inject a session:

```python
from aiohttp import ClientSession
from pythermacell import ThermacellClient

async with ClientSession() as session:
    client = ThermacellClient(
        username="your@email.com",
        password="your_password",
        session=session,  # Inject your session
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

## Resilience Patterns

pythermacell includes production-ready resilience patterns for fault tolerance:
a **circuit breaker**, **exponential backoff**, and a **rate limiter**. They can
be used independently or combined.

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
    rate_limiter=limiter,
)

async with client:
    # Client automatically:
    # - Retries failed requests with exponential backoff
    # - Opens circuit after repeated failures
    # - Respects rate limiting
    devices = await client.get_devices()
```

### Circuit Breaker

Prevents cascading failures by blocking requests after repeated failures:

```python
from pythermacell.resilience import CircuitBreaker

breaker = CircuitBreaker(
    failure_threshold=5,   # Open circuit after 5 consecutive failures
    recovery_timeout=60.0, # Wait 60 seconds before attempting recovery
    success_threshold=2,   # Require 2 successes to close circuit
)
```

When the circuit is open, calls raise a `RuntimeError` mentioning the circuit
breaker:

```python
async with client:
    try:
        devices = await client.get_devices()
    except RuntimeError as e:
        if "circuit breaker" in str(e).lower():
            print("Circuit is open - too many failures")
```

### Exponential Backoff

Automatically retries failed requests with increasing delays:

```python
from pythermacell.resilience import ExponentialBackoff

backoff = ExponentialBackoff(
    base_delay=1.0,        # Start with 1 second
    max_delay=60.0,        # Cap at 60 seconds
    max_retries=5,         # Retry up to 5 times
    exponential_base=2.0,  # Double delay each time
    jitter=True,           # Add randomness to prevent thundering herd
)
```

**Retry delays**: 1s → 2s → 4s → 8s → 16s (with jitter).

### Rate Limiting

Handles HTTP 429 responses and respects `Retry-After` headers:

```python
from pythermacell.resilience import RateLimiter

limiter = RateLimiter(
    respect_retry_after=True,  # Parse Retry-After header
    default_retry_delay=60.0,  # Default wait time (seconds)
    max_retry_delay=300.0,     # Maximum wait time (5 minutes)
)
```

For state machines, transition diagrams, and design rationale, see
[architecture/RESILIENCE.md](architecture/RESILIENCE.md).

## Error Handling

Catch the specific exceptions raised by the library:

```python
import asyncio
from pythermacell import (
    ThermacellClient,
    AuthenticationError,
    ThermacellConnectionError,
    DeviceError,
)


async def robust_control():
    """Control a device with comprehensive error handling."""
    try:
        async with ThermacellClient(
            username="your@email.com",
            password="your_password",
        ) as client:
            devices = await client.get_devices()
            if not devices:
                print("No devices found")
                return

            device = devices[0]
            await device.turn_on()

    except AuthenticationError as e:
        print(f"Authentication failed: {e}")  # Check username/password
    except ThermacellConnectionError as e:
        print(f"Connection error: {e}")       # Check internet connection
    except DeviceError as e:
        print(f"Device error: {e}")           # Device may be offline
    except Exception as e:
        print(f"Unexpected error: {e}")


asyncio.run(robust_control())
```

The full exception hierarchy is documented [below](#exception-hierarchy).

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

- `async get_devices() -> list[ThermacellDevice]` — Get all devices (with state caching)
- `async get_device(node_id: str) -> ThermacellDevice | None` — Get specific device (cached)
- `async refresh_all() -> None` — Refresh state for all cached devices
- `api: ThermacellAPI` — Access low-level API for advanced use cases

### ThermacellDevice

Represents a Thermacell device with control and monitoring capabilities.

**Properties:**

- `node_id: str` — Unique device identifier
- `name: str` — Human-readable device name
- `model: str` — Device model (e.g., "Thermacell LIV Hub")
- `firmware_version: str` — Current firmware version
- `serial_number: str` — Device serial number
- `is_online: bool` — Whether device is connected
- `is_powered_on: bool` — Whether device is powered on
- `has_error: bool` — Whether device has an error
- `refill_life: float | None` — Refill cartridge life percentage (0-100)
- `system_runtime: int | None` — Current session runtime in minutes
- `system_status: int | None` — System status (1=Off, 2=Warming, 3=Protected)
- `error: int | None` — Error code (0=no error)
- `led_power: bool | None` — LED on/off state
- `led_brightness: int | None` — LED brightness (0-100)
- `led_hue: int | None` — LED hue (0-360)
- `led_saturation: int | None` — LED saturation (0-100)
- `last_refresh: datetime` — Timestamp of last state refresh

**Methods:**

- `async turn_on() -> bool` — Turn device on (optimistic)
- `async turn_off() -> bool` — Turn device off (optimistic)
- `async set_power(power_on: bool) -> bool` — Set power state (optimistic)
- `async set_led_power(power_on: bool) -> bool` — Set LED power (optimistic)
- `async set_led_brightness(brightness: int) -> bool` — Set LED brightness (optimistic)
- `async set_led_color(hue: int, brightness: int) -> bool` — Set LED color (optimistic)
- `async reset_refill(refill_type: int = 1) -> bool` — Reset refill life (optimistic)
- `async refresh() -> bool` — Refresh device state from API
- `async start_auto_refresh(interval: int = 60) -> None` — Start background polling
- `async stop_auto_refresh() -> None` — Stop background polling
- `add_listener(callback: Callable) -> None` — Register state change callback
- `remove_listener(callback: Callable) -> None` — Unregister callback

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

- `async authenticate(force: bool = False) -> bool` — Authenticate with API
- `async ensure_authenticated() -> None` — Ensure valid authentication
- `async force_reauthenticate() -> bool` — Force token refresh
- `is_authenticated() -> bool` — Check if authenticated
- `needs_reauthentication() -> bool` — Check if reauthentication needed
- `clear_authentication() -> None` — Clear stored tokens

See [architecture/AUTHENTICATION.md](architecture/AUTHENTICATION.md) for the full
flow.

### ThermacellAPI

Low-level API client for direct HTTP communication.

```python
ThermacellAPI(
    *,
    auth_handler: AuthenticationHandler,
    session: ClientSession | None = None,
    base_url: str = "https://api.iot.thermacell.com",
    circuit_breaker: CircuitBreaker | None = None,
    backoff: ExponentialBackoff | None = None,
    rate_limiter: RateLimiter | None = None,
)
```

**Methods:** (all return `tuple[int, dict | None]`)

- `async get_nodes() -> tuple[int, dict | None]` — Get device list
- `async get_node_params(node_id: str) -> tuple[int, dict | None]` — Get device parameters
- `async get_node_status(node_id: str) -> tuple[int, dict | None]` — Get device status
- `async get_node_config(node_id: str) -> tuple[int, dict | None]` — Get device config
- `async update_node_params(node_id: str, params: dict) -> tuple[int, dict | None]` — Update parameters

Access via the client: `status, data = await client.api.get_node_params(node_id)`.

Endpoint-level documentation lives under [api/](api/README.md).

### Exception Hierarchy

```
ThermacellError (base)
├── AuthenticationError        - Authentication failures
├── ThermacellConnectionError  - Connection/network errors
├── ThermacellTimeoutError     - Request timeouts
├── RateLimitError             - Rate limiting errors
├── DeviceError                - Device-related errors
└── InvalidParameterError      - Invalid parameter values
```

## Examples

The [`examples/`](../examples/) directory contains complete, runnable scripts.

### Simple Device Control

```python
import asyncio
from pythermacell import ThermacellClient


async def control_device():
    """Turn on a device and set its LED to blue."""
    async with ThermacellClient(
        username="your@email.com",
        password="your_password",
    ) as client:
        devices = await client.get_devices()
        device = devices[0]

        await device.turn_on()
        await device.set_led_color(hue=240, saturation=100, brightness=80)

        print(f"Device {device.name} is now on with a blue LED")


asyncio.run(control_device())
```

### Monitor Multiple Devices

```python
import asyncio
from pythermacell import ThermacellClient


async def monitor_devices():
    """Monitor refill life for all devices."""
    async with ThermacellClient(
        username="your@email.com",
        password="your_password",
    ) as client:
        for device in await client.get_devices():
            await device.refresh()

            print(f"\n{device.name}:")
            print(f"  Online: {device.is_online}")
            print(f"  Powered: {device.is_powered_on}")
            print(f"  Refill: {device.refill_life}%")
            print(f"  Runtime: {device.system_runtime} min")

            if device.refill_life and device.refill_life < 20:
                print(f"  LOW REFILL - {device.refill_life}%")


asyncio.run(monitor_devices())
```

### Session Injection (Home Assistant Integration)

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
        """Set up the integration using Home Assistant's shared session."""
        session = self.hass.helpers.aiohttp_client.async_get_clientsession()

        self.client = ThermacellClient(
            username=self.username,
            password=self.password,
            session=session,  # Inject HA's session
        )

        await self.client.__aenter__()
        return await self.client.get_devices()

    async def async_unload(self):
        """Unload the integration."""
        if self.client:
            await self.client.__aexit__(None, None, None)
```

The production integration is [Thermacell LIV](https://github.com/joyfulhouse/thermacell_liv).

### Resilience Patterns

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
        backoff=backoff,
    )

    async with client:
        try:
            devices = await client.get_devices()  # Retries on failure with backoff
            print(f"Found {len(devices)} devices")
        except RuntimeError as e:
            if "circuit breaker" in str(e).lower():
                print("Circuit opened - too many failures")
                print(f"Breaker state: {breaker.state}")
                print(f"Failures: {breaker.failure_count}")


asyncio.run(resilient_operation())
```

### Advanced Features

```python
import asyncio
from pythermacell import ThermacellClient


async def advanced_features():
    """Optimistic updates, auto-refresh, and listeners together."""
    async with ThermacellClient(
        username="your@email.com",
        password="your_password",
    ) as client:
        devices = await client.get_devices()
        device = devices[0]

        # Register a state change listener
        def on_change(d):
            print(f"[{d.last_refresh}] {d.name}: power={d.is_powered_on}, refill={d.refill_life}%")

        device.add_listener(on_change)

        # Background polling every 30 seconds
        await device.start_auto_refresh(interval=30)

        # Control with optimistic updates (instant feedback)
        await device.turn_on()                          # returns after local state update
        print(f"Device state: {device.is_powered_on}")  # True (instant)
        await device.set_led_color(hue=120, brightness=100)

        # Wait for auto-refresh to trigger the listener
        await asyncio.sleep(35)

        # Direct API access for advanced use cases
        status, raw_data = await client.api.get_node_params(device.node_id)
        print(f"Raw API response (status {status}): {raw_data}")

        await device.stop_auto_refresh()


asyncio.run(advanced_features())
```
