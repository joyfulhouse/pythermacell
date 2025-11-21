"""Serialization and deserialization of API responses.

This module provides stateless functions for converting between raw API responses
and typed domain models. This allows both ThermacellClient and ThermacellDevice
to deserialize API responses without coupling or code duplication.

Design Philosophy:
    - Stateless functions (no classes, no state)
    - Single responsibility (serialization only)
    - Type-safe conversions
    - Business logic for derived fields (e.g., LED state calculation)
"""

from __future__ import annotations

from typing import Any

from pythermacell.const import DEVICE_TYPE_LIV_HUB
from pythermacell.models import DeviceInfo, DeviceParams, DeviceState, DeviceStatus


def deserialize_device_params(data: dict[str, Any]) -> DeviceParams:
    """Deserialize device parameters from /params API response.

    The Thermacell API has two power-related fields:
    - "Power": Read-only status indicator (not used for control)
    - "Enable Repellers": Writable control parameter (actual device power)

    LED State Logic:
        The LED is only considered "on" when BOTH conditions are met:
        1. Device is powered on (enable_repellers=True)
        2. LED brightness is greater than 0

        This matches the physical device behavior where the LED cannot be on
        when the device itself is off, even if brightness is set to a non-zero value.

    Args:
        data: Raw parameter data from API in format:
              {"LIV Hub": {"Power": bool, "LED Brightness": int, ...}}

    Returns:
        DeviceParams instance with parsed and calculated state.

    Example:
        >>> response = {
        ...     "LIV Hub": {
        ...         "Enable Repellers": True,
        ...         "LED Brightness": 80,
        ...         "LED Hue": 120,
        ...         "Refill Life": 95.5
        ...     }
        ... }
        >>> params = deserialize_device_params(response)
        >>> params.power
        True
        >>> params.led_power  # True because powered AND brightness > 0
        True
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


def deserialize_device_status(node_id: str, data: dict[str, Any]) -> DeviceStatus:
    """Deserialize device status from /status API response.

    Args:
        node_id: Device node ID.
        data: Raw status data from API in format:
              {"connectivity": {"connected": bool, ...}}

    Returns:
        DeviceStatus instance.

    Example:
        >>> response = {"connectivity": {"connected": True}}
        >>> status = deserialize_device_status("ABC123", response)
        >>> status.connected
        True
    """
    connectivity = data.get("connectivity", {})
    connected = connectivity.get("connected", False)

    return DeviceStatus(node_id=node_id, connected=connected)


def deserialize_device_info(node_id: str, data: dict[str, Any]) -> DeviceInfo:
    """Deserialize device info from /config API response.

    Args:
        node_id: Device node ID.
        data: Raw config data from API in format:
              {"info": {"name": str, "type": str, ...}, "devices": [...]}

    Returns:
        DeviceInfo instance.

    Example:
        >>> response = {
        ...     "info": {
        ...         "name": "Living Room",
        ...         "type": "thermacell-hub",
        ...         "fw_version": "1.2.3"
        ...     },
        ...     "devices": [{"serial_num": "SN123456"}]
        ... }
        >>> info = deserialize_device_info("ABC123", response)
        >>> info.model
        'Thermacell LIV Hub'
    """
    info = data.get("info", {})
    devices = data.get("devices", [{}])
    device_data = devices[0] if devices else {}

    # Convert model name to user-friendly format
    model_type = info.get("type", "")
    model = "Thermacell LIV Hub" if model_type == "thermacell-hub" else model_type

    return DeviceInfo(
        node_id=node_id,
        name=info.get("name", node_id),
        model=model,
        firmware_version=info.get("fw_version", "unknown"),
        serial_number=device_data.get("serial_num", "unknown"),
    )


def deserialize_device_state(
    node_id: str,
    params_data: dict[str, Any],
    status_data: dict[str, Any],
    config_data: dict[str, Any],
) -> DeviceState:
    """Deserialize complete device state from multiple API responses.

    This is a convenience function that combines the three separate response
    deserializers into a single DeviceState object.

    Args:
        node_id: Device node ID.
        params_data: Raw data from /params endpoint.
        status_data: Raw data from /status endpoint.
        config_data: Raw data from /config endpoint.

    Returns:
        DeviceState instance combining all three response types.

    Example:
        >>> state = deserialize_device_state(
        ...     node_id="ABC123",
        ...     params_data={"LIV Hub": {"Enable Repellers": True}},
        ...     status_data={"connectivity": {"connected": True}},
        ...     config_data={"info": {"name": "Living Room"}}
        ... )
        >>> state.is_online
        True
    """
    device_params = deserialize_device_params(params_data)
    device_status = deserialize_device_status(node_id, status_data)
    device_info = deserialize_device_info(node_id, config_data)

    return DeviceState(
        info=device_info,
        status=device_status,
        params=device_params,
        raw_data={
            "params": params_data,
            "status": status_data,
            "config": config_data,
        },
    )


def serialize_param_update(params: dict[str, dict[str, int | float | bool]]) -> dict[str, Any]:
    """Serialize parameter update for /params PUT request.

    This function validates and formats parameter updates for the API.
    Currently a pass-through, but provides a place for validation logic.

    Args:
        params: Parameter updates in format:
                {"LIV Hub": {"Enable Repellers": bool, "LED Brightness": int, ...}}

    Returns:
        Serialized parameter update (currently unchanged).

    Example:
        >>> update = serialize_param_update({
        ...     "LIV Hub": {"Enable Repellers": True, "LED Brightness": 50}
        ... })
        >>> update["LIV Hub"]["Enable Repellers"]
        True
    """
    # Future: Add validation here
    # - Validate brightness is 0-100
    # - Validate hue is 0-360
    # - Validate parameter names are valid
    return params
