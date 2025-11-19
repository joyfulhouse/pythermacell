"""Device management for Thermacell API."""

from __future__ import annotations

from typing import TYPE_CHECKING

from pythermacell.const import (
    DEVICE_TYPE_LIV_HUB,
    LED_BRIGHTNESS_MAX,
    LED_BRIGHTNESS_MIN,
    LED_HUE_MAX,
    LED_HUE_MIN,
)
from pythermacell.exceptions import InvalidParameterError


if TYPE_CHECKING:
    from pythermacell.client import ThermacellClient
    from pythermacell.models import DeviceState


class ThermacellDevice:
    """Represents a Thermacell device with control and monitoring capabilities.

    This class provides a high-level interface for controlling Thermacell devices,
    including power management, LED control, and status monitoring.

    Attributes:
        node_id: Unique device identifier.
        name: Human-readable device name.
        model: Device model (e.g., "Thermacell LIV Hub").
        firmware_version: Current firmware version.
        serial_number: Device serial number.
        is_online: Whether device is currently connected.
        is_powered_on: Whether device is powered on.
        has_error: Whether device has an error condition.
    """

    def __init__(self, client: ThermacellClient, state: DeviceState) -> None:
        """Initialize the device.

        Args:
            client: ThermacellClient instance for API communication.
            state: Initial device state containing info, status, and parameters.
        """
        self._client = client
        self._state = state

    @property
    def node_id(self) -> str:
        """Get device node ID."""
        return self._state.node_id

    @property
    def name(self) -> str:
        """Get device name."""
        return self._state.name

    @property
    def model(self) -> str:
        """Get device model."""
        return self._state.info.model

    @property
    def firmware_version(self) -> str:
        """Get firmware version."""
        return self._state.info.firmware_version

    @property
    def serial_number(self) -> str:
        """Get device serial number."""
        return self._state.info.serial_number

    @property
    def is_online(self) -> bool:
        """Check if device is online."""
        return self._state.is_online

    @property
    def is_powered_on(self) -> bool:
        """Check if device is powered on."""
        return self._state.is_powered_on

    @property
    def has_error(self) -> bool:
        """Check if device has an error."""
        return self._state.has_error

    @property
    def power(self) -> bool | None:
        """Get device power state."""
        return self._state.params.power

    @property
    def led_power(self) -> bool | None:
        """Get LED power state."""
        return self._state.params.led_power

    @property
    def led_brightness(self) -> int | None:
        """Get LED brightness (0-100)."""
        return self._state.params.led_brightness

    @property
    def led_hue(self) -> int | None:
        """Get LED hue (0-360)."""
        return self._state.params.led_hue

    @property
    def led_saturation(self) -> int | None:
        """Get LED saturation (0-100)."""
        return self._state.params.led_saturation

    @property
    def refill_life(self) -> float | None:
        """Get refill cartridge life percentage (0-100)."""
        return self._state.params.refill_life

    @property
    def system_runtime(self) -> int | None:
        """Get current session runtime in minutes."""
        return self._state.params.system_runtime

    @property
    def system_status(self) -> int | None:
        """Get system operational status (1=Off, 2=Warming, 3=Protected)."""
        return self._state.params.system_status

    @property
    def error(self) -> int | None:
        """Get error code (0=no error)."""
        return self._state.params.error

    @property
    def enable_repellers(self) -> bool | None:
        """Get whether repellers are enabled."""
        return self._state.params.enable_repellers

    async def turn_on(self) -> bool:
        """Turn the device on.

        Returns:
            True if successful, False otherwise.
        """
        return await self.set_power(True)

    async def turn_off(self) -> bool:
        """Turn the device off.

        Returns:
            True if successful, False otherwise.
        """
        return await self.set_power(False)

    async def set_power(self, power_on: bool) -> bool:
        """Set device power state.

        Args:
            power_on: True to turn on, False to turn off.

        Returns:
            True if successful, False otherwise.
        """
        # Use "Enable Repellers" parameter to control device power
        # (not "Power" which is a read-only status indicator)
        params = {DEVICE_TYPE_LIV_HUB: {"Enable Repellers": power_on}}
        return await self._client.update_device_params(self.node_id, params)

    async def set_led_power(self, power_on: bool) -> bool:
        """Set LED power state.

        Note: LED power is controlled via brightness, not a separate parameter.
        Turning off sets brightness to 0; turning on sets to 100.

        Args:
            power_on: True to turn LED on, False to turn off.

        Returns:
            True if successful, False otherwise.
        """
        # LED power is controlled by setting brightness to 0 (off) or 100 (on)
        brightness = 100 if power_on else 0
        params = {DEVICE_TYPE_LIV_HUB: {"LED Brightness": brightness}}
        return await self._client.update_device_params(self.node_id, params)

    async def set_led_brightness(self, brightness: int) -> bool:
        """Set LED brightness.

        Args:
            brightness: Brightness level (0-100).

        Returns:
            True if successful, False otherwise.

        Raises:
            InvalidParameterError: If brightness is outside valid range.
        """
        if not LED_BRIGHTNESS_MIN <= brightness <= LED_BRIGHTNESS_MAX:
            msg = f"LED brightness must be {LED_BRIGHTNESS_MIN}-{LED_BRIGHTNESS_MAX}, got {brightness}"
            raise InvalidParameterError(msg, parameter_name="brightness", value=brightness)

        params = {DEVICE_TYPE_LIV_HUB: {"LED Brightness": brightness}}
        return await self._client.update_device_params(self.node_id, params)

    async def set_led_color(self, hue: int, brightness: int) -> bool:
        """Set LED color using hue and brightness.

        Note: The Thermacell API only accepts hue and brightness for LED color
        control. Saturation is not supported and sending it causes device crashes.
        This matches the Home Assistant reference implementation.

        Args:
            hue: Hue value (0-360).
            brightness: Brightness percentage (0-100).

        Returns:
            True if successful, False otherwise.

        Raises:
            InvalidParameterError: If any parameter is outside valid range.
        """
        # Validate hue
        if not LED_HUE_MIN <= hue <= LED_HUE_MAX:
            msg = f"LED hue must be {LED_HUE_MIN}-{LED_HUE_MAX}, got {hue}"
            raise InvalidParameterError(msg, parameter_name="hue", value=hue)

        # Validate brightness
        if not LED_BRIGHTNESS_MIN <= brightness <= LED_BRIGHTNESS_MAX:
            msg = f"LED brightness must be {LED_BRIGHTNESS_MIN}-{LED_BRIGHTNESS_MAX}, got {brightness}"
            raise InvalidParameterError(msg, parameter_name="brightness", value=brightness)

        # Only send hue and brightness - saturation is not supported
        params = {
            DEVICE_TYPE_LIV_HUB: {
                "LED Hue": hue,
                "LED Brightness": brightness,
            }
        }
        return await self._client.update_device_params(self.node_id, params)

    async def reset_refill(self, refill_type: int = 1) -> bool:
        """Reset refill life counter to 100%.

        Args:
            refill_type: Type of refill cartridge installed:
                - 0: 40 Hour - Yellow Cap
                - 1: 100 Hour - Blue Cap (default)
                - 2: 180 Hour - Gray Cap

        Returns:
            True if successful, False otherwise.

        Raises:
            InvalidParameterError: If refill_type is not 0, 1, or 2.
        """
        if refill_type not in (0, 1, 2):
            msg = f"Refill type must be 0 (40hr), 1 (100hr), or 2 (180hr), got {refill_type}"
            raise InvalidParameterError(msg, parameter_name="refill_type", value=refill_type)

        # Use "Refill Reset" parameter with cartridge type value
        params = {DEVICE_TYPE_LIV_HUB: {"Refill Reset": refill_type}}
        return await self._client.update_device_params(self.node_id, params)

    async def refresh(self) -> bool:
        """Refresh device state from API.

        This fetches the latest device state from the API and updates
        the internal state.

        Returns:
            True if successful, False otherwise.
        """
        new_state = await self._client.get_device_state(self.node_id)
        if new_state is None:
            return False

        self._state = new_state
        return True

    def __str__(self) -> str:
        """Return string representation of device."""
        return f"{self.name} ({self.node_id})"

    def __repr__(self) -> str:
        """Return detailed string representation of device."""
        return f"ThermacellDevice(node_id='{self.node_id}', name='{self.name}')"
