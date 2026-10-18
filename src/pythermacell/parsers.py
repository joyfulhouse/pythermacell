"""Parsing utilities for Thermacell API responses.

This module provides shared parsing functions used by both ThermacellClient
and ThermacellDevice to convert raw API responses into data models.
"""

from __future__ import annotations

import math
from typing import Any

from pythermacell.const import DEVICE_TYPE_LIV_HUB, SYSTEM_RUNTIME_MULTIPLIER
from pythermacell.models import DeviceInfo, DeviceParams, DeviceState, DeviceStatus


__all__ = [
    "parse_device_info",
    "parse_device_params",
    "parse_device_state",
    "parse_device_status",
]

MAX_REFILL_PERCENT = 100


def get_power_parameter_name(config: dict[str, Any]) -> str:
    """Resolve the hub's writable power parameter from RainMaker metadata."""
    for device in config.get("devices", []):
        if device.get("name") != DEVICE_TYPE_LIV_HUB:
            continue
        for param in device.get("params", []):
            if param.get("type") == "esp.param.power" and "write" in param.get("properties", []):
                name = param.get("name")
                if isinstance(name, str) and name:
                    return name
    return "Enable Repellers"


def parse_device_params(data: dict[str, Any], config: dict[str, Any] | None = None) -> DeviceParams:
    """Parse device parameters from API response.

    The writable power field is resolved by esp.param.power metadata in the
    node configuration. Older hubs use "Enable Repellers"; other firmware can
    advertise "Power" as writable. Without config, use the legacy field.

    LED state logic: The LED is only considered "on" when BOTH conditions are met:
    1. Device is powered on (enable_repellers=True)
    2. LED brightness is greater than 0

    This matches the physical device behavior where the LED cannot be on
    when the device itself is off, even if brightness is set to a non-zero value.

    Args:
        data: Raw parameter data from API in format:
              {"LIV Hub": {"Power": bool, "LED Brightness": int, ...}}
        config: Optional node config used to resolve the writable power field.

    Returns:
        DeviceParams instance with parsed and calculated state.
    """
    hub_params = data.get(DEVICE_TYPE_LIV_HUB, {})

    # Read the same config-advertised field used for power writes.
    enable_repellers = hub_params.get(get_power_parameter_name(config or {}))
    brightness = hub_params.get("LED Brightness", 0)

    # Calculate LED power state: only "on" when hub powered AND brightness > 0
    # This matches physical device behavior and prevents confusion
    led_power = enable_repellers and brightness > 0 if enable_repellers is not None else None

    # Convert System Runtime from API units (tenths of hours) to minutes
    raw_runtime = hub_params.get("System Runtime")
    system_runtime = raw_runtime * SYSTEM_RUNTIME_MULTIPLIER if raw_runtime is not None else None

    refill = hub_params.get("Refill Life")
    valid_refill = type(refill) in (int, float) and math.isfinite(refill) and 0 <= refill <= MAX_REFILL_PERCENT
    present = True if valid_refill else False if type(refill) in (int, float) and refill == -1 else None

    return DeviceParams(
        power=enable_repellers,  # Use enable_repellers for power status
        led_power=led_power,  # Calculated from enable_repellers and brightness
        led_brightness=brightness,
        led_hue=hub_params.get("LED Hue"),
        led_saturation=hub_params.get("LED Saturation"),
        refill_life=float(refill) if valid_refill else None,
        cartridge_present=present,
        system_runtime=system_runtime,
        system_status=hub_params.get("System Status", hub_params.get("System State")),
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
        params=parse_device_params(params_data, config_data),
        raw_data={
            "params": params_data,
            "status": status_data,
            "config": config_data,
        },
    )
