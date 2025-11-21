"""Python client library for Thermacell IoT devices.

This package provides an async client for interacting with Thermacell devices
through the ESP RainMaker API platform.

The library is organized into three layers:
1. **API Layer** (pythermacell.api): Low-level HTTP communication with the Thermacell API
2. **Client Layer** (pythermacell.client): Device management and coordination
3. **Device Layer** (pythermacell.devices): Stateful device objects with optimistic updates

Example:
    Basic usage:

    ```python
    from pythermacell import ThermacellClient

    async with ThermacellClient(username="user@example.com", password="password") as client:
        # Discover devices
        devices = await client.get_devices()

        # Control devices (with optimistic updates)
        for device in devices:
            await device.turn_on()
            await device.set_led_color(hue=120, brightness=80)

        # Access cached state
        print(f"Refill life: {devices[0].refill_life}%")
    ```

    Advanced usage with direct API access:

    ```python
    from pythermacell import ThermacellClient, ThermacellAPI

    async with ThermacellClient(username="user@example.com", password="password") as client:
        # High-level device management
        devices = await client.get_devices()

        # Direct API access for custom operations
        api = client.api
        status, data = await api.get_node_params(devices[0].node_id)
    ```
"""

from __future__ import annotations

from pythermacell.api import ThermacellAPI
from pythermacell.auth import AuthenticationHandler
from pythermacell.client import ThermacellClient
from pythermacell.devices import ThermacellDevice
from pythermacell.exceptions import (
    AuthenticationError,
    DeviceError,
    InvalidParameterError,
    RateLimitError,
    ThermacellConnectionError,
    ThermacellError,
    ThermacellTimeoutError,
)
from pythermacell.models import (
    DeviceInfo,
    DeviceParams,
    DeviceState,
    DeviceStatus,
    Group,
    GroupListResponse,
    GroupNodesResponse,
    LoginResponse,
)
from pythermacell.resilience import (
    CircuitBreaker,
    CircuitState,
    ExponentialBackoff,
    RateLimiter,
    retry_with_backoff,
)
from pythermacell.serializers import (
    deserialize_device_info,
    deserialize_device_params,
    deserialize_device_state,
    deserialize_device_status,
    serialize_param_update,
)


__version__ = "0.2.0"

__all__ = [
    "AuthenticationError",
    "AuthenticationHandler",
    "CircuitBreaker",
    "CircuitState",
    "DeviceError",
    "DeviceInfo",
    "DeviceParams",
    "DeviceState",
    "DeviceStatus",
    "ExponentialBackoff",
    "Group",
    "GroupListResponse",
    "GroupNodesResponse",
    "InvalidParameterError",
    "LoginResponse",
    "RateLimitError",
    "RateLimiter",
    "ThermacellAPI",
    "ThermacellClient",
    "ThermacellConnectionError",
    "ThermacellDevice",
    "ThermacellError",
    "ThermacellTimeoutError",
    "__version__",
    "deserialize_device_info",
    "deserialize_device_params",
    "deserialize_device_state",
    "deserialize_device_status",
    "retry_with_backoff",
    "serialize_param_update",
]
