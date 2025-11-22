"""Data models for Thermacell API requests and responses."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


__all__ = [
    "DeviceInfo",
    "DeviceParams",
    "DeviceState",
    "DeviceStatus",
    "Group",
    "GroupListResponse",
    "GroupNodesResponse",
    "LoginResponse",
]


@dataclass
class LoginResponse:
    """Response from authentication endpoint.

    Attributes:
        access_token: JWT access token for API requests.
        id_token: JWT ID token containing user information.
        user_id: User ID extracted from ID token.
    """

    access_token: str
    id_token: str
    user_id: str


@dataclass
class DeviceInfo:
    """Device information from config endpoint.

    Attributes:
        node_id: Unique device identifier.
        name: Human-readable device name.
        model: Device model (e.g., "Thermacell LIV Hub").
        firmware_version: Current firmware version.
        serial_number: Device serial number.
    """

    node_id: str
    name: str
    model: str
    firmware_version: str
    serial_number: str


@dataclass
class DeviceStatus:
    """Device connectivity status.

    Attributes:
        node_id: Device identifier.
        connected: Whether device is online.
    """

    node_id: str
    connected: bool


@dataclass
class DeviceParams:
    """Device parameter state from params endpoint.

    All parameters are optional as devices may not report all values.

    Attributes:
        power: Device on/off state.
        led_power: LED on/off state.
        led_brightness: LED brightness (0-100).
        led_hue: LED hue in HSV (0-360).
        led_saturation: LED saturation in HSV (0-100).
        refill_life: Refill cartridge remaining percentage (0-100).
        system_runtime: Current session runtime in minutes.
        system_status: System operational status (1=Off, 2=Warming, 3=Protected).
        error: Error code (0=no error).
        enable_repellers: Whether repellers are enabled.
    """

    power: bool | None = None
    led_power: bool | None = None
    led_brightness: int | None = None
    led_hue: int | None = None
    led_saturation: int | None = None
    refill_life: float | None = None
    system_runtime: int | None = None
    system_status: int | None = None
    error: int | None = None
    enable_repellers: bool | None = None


@dataclass
class DeviceState:
    """Complete device state combining info, status, and parameters.

    Attributes:
        info: Device information (model, firmware, etc.).
        status: Connectivity status.
        params: Device parameters (power, LED, refill, etc.).
        raw_data: Original API response data for debugging.
    """

    info: DeviceInfo
    status: DeviceStatus
    params: DeviceParams
    raw_data: dict[str, Any] = field(default_factory=dict)

    @property
    def is_online(self) -> bool:
        """Check if device is online."""
        return self.status.connected

    @property
    def is_powered_on(self) -> bool:
        """Check if device is powered on."""
        return self.params.power or False

    @property
    def has_error(self) -> bool:
        """Check if device has an error."""
        return (self.params.error or 0) > 0


@dataclass
class Group:
    """Group information for device organization.

    Attributes:
        group_id: Unique identifier for the group.
        group_name: User-friendly name of the group.
        is_matter: Whether this is a Matter protocol group.
        primary: Whether this is a primary group.
        total: Number of devices/nodes in this group.
    """

    group_id: str
    group_name: str
    is_matter: bool
    primary: bool
    total: int


@dataclass
class GroupListResponse:
    """Response from groups list endpoint.

    Attributes:
        groups: Array of group objects.
        total: Total number of groups.
    """

    groups: list[Group]
    total: int


@dataclass
class GroupNodesResponse:
    """Response from group nodes endpoint.

    Attributes:
        nodes: Array of node IDs belonging to the group.
        total: Total number of nodes in the group.
    """

    nodes: list[str]
    total: int
