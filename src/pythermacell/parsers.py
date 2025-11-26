"""Parsing utilities for Thermacell API responses.

This module provides shared parsing functions used by both ThermacellClient
and ThermacellDevice to convert raw API responses into data models.
"""

from __future__ import annotations

from typing import Any

from pythermacell.const import DEVICE_TYPE_LIV_HUB
from pythermacell.models import DeviceInfo, DeviceParams, DeviceState, DeviceStatus


__all__ = [
    "parse_device_info",
    "parse_device_params",
    "parse_device_state",
    "parse_device_status",
]


def parse_device_params(data: dict[str, Any]) -> DeviceParams:
    """Parse device parameters from API response.

    The Thermacell API has two power-related fields:
    - "Power": Read-only status indicator (not used for control)
    - "Enable Repellers": Writable control parameter (actual device power)

    LED state logic: The LED is only considered "on" when BOTH conditions are met:
    1. Device is powered on (enable_repellers=True)
    2. LED brightness is greater than 0

    This matches the physical device behavior where the LED cannot be on
    when the device itself is off, even if brightness is set to a non-zero value.

    Args:
        data: Raw parameter data from API in format:
              {"LIV Hub": {"Power": bool, "LED Brightness": int, ...}}

    Returns:
        DeviceParams instance with parsed and calculated state.
    """
    hub_params = data.get(DEVICE_TYPE_LIV_HUB, {})

    # Use "Enable Repellers" for device power (not "Power" which is read-only)
    enable_repellers = hub_params.get("Enable Repellers")
    brightness = hub_params.get("LED Brightness", 0)

    # Calculate LED power state: only "on" when hub powered AND brightness > 0
    # This matches physical device behavior and prevents confusion
    led_power = enable_repellers and brightness > 0 if enable_repellers is not None else None

    return DeviceParams(
        power=enable_repellers,  # Use enable_repellers for power status
        led_power=led_power,  # Calculated from enable_repellers and brightness
        led_brightness=brightness,
        led_hue=hub_params.get("LED Hue"),
        led_saturation=hub_params.get("LED Saturation"),
        refill_life=hub_params.get("Refill Life"),
        system_runtime=hub_params.get("System Runtime"),
        system_status=hub_params.get("System Status"),
        error=hub_params.get("Error"),
        enable_repellers=enable_repellers,
    )


def parse_device_status(node_id: str, data: dict[str, Any]) -> DeviceStatus:
    """Parse device status from API response.

    Args:
        node_id: Device node ID.
        data: Raw status data from API.

    Returns:
        DeviceStatus instance.
    """
    connectivity = data.get("connectivity", {})
    connected = connectivity.get("connected", False)

    return DeviceStatus(node_id=node_id, connected=connected)


def parse_device_info(
    node_id: str,
    config_data: dict[str, Any],
    params_data: dict[str, Any] | None = None,
) -> DeviceInfo:
    """Parse device info from API response.

    User-friendly device names (e.g., "Pool", "ADU") are stored in the params
    endpoint under "LIV Hub" -> "Name", not in the config endpoint. The config
    endpoint's info.name contains the generic device type (e.g., "Thermacell LIV Hub").

    Args:
        node_id: Device node ID.
        config_data: Raw config data from /user/nodes/config endpoint.
        params_data: Raw params data from /user/nodes/params endpoint (optional).
            If provided, the user-friendly name will be extracted from here.

    Returns:
        DeviceInfo instance with user-friendly name if available.
    """
    info = config_data.get("info", {})
    devices = config_data.get("devices", [{}])
    device_data = devices[0] if devices else {}

    # Convert model name to user-friendly format
    model_type = info.get("type", "")
    model = "Thermacell LIV Hub" if model_type == "thermacell-hub" else model_type

    # User-friendly device name comes from params["LIV Hub"]["Name"]
    # Fall back to config info.name, then node_id
    name = node_id  # Default fallback
    if params_data:
        hub_params = params_data.get(DEVICE_TYPE_LIV_HUB, {})
        name = hub_params.get("Name") or info.get("name") or node_id
    else:
        name = info.get("name") or node_id

    return DeviceInfo(
        node_id=node_id,
        name=name,
        model=model,
        firmware_version=info.get("fw_version", "unknown"),
        serial_number=device_data.get("serial_num", "unknown"),
    )


def parse_device_state(
    node_id: str,
    params_data: dict[str, Any],
    status_data: dict[str, Any],
    config_data: dict[str, Any],
) -> DeviceState:
    """Parse complete device state from multiple API responses.

    This is a convenience function that combines all three parsing functions
    into a single DeviceState object. The params_data is passed to parse_device_info
    to extract the user-friendly device name from "LIV Hub" -> "Name".

    Args:
        node_id: Device node ID.
        params_data: Raw params data from /user/nodes/params endpoint.
        status_data: Raw status data from /user/nodes/status endpoint.
        config_data: Raw config data from /user/nodes/config endpoint.

    Returns:
        DeviceState instance with all parsed data.
    """
    return DeviceState(
        info=parse_device_info(node_id, config_data, params_data),
        status=parse_device_status(node_id, status_data),
        params=parse_device_params(params_data),
        raw_data={
            "params": params_data,
            "status": status_data,
            "config": config_data,
        },
    )
