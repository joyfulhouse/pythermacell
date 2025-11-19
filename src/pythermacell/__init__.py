"""Python client library for Thermacell IoT devices.

This package provides an async client for interacting with Thermacell devices
through the ESP RainMaker API platform.
"""

from __future__ import annotations

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


__version__ = "0.1.0"

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
    "ThermacellClient",
    "ThermacellConnectionError",
    "ThermacellDevice",
    "ThermacellError",
    "ThermacellTimeoutError",
    "__version__",
    "retry_with_backoff",
]
