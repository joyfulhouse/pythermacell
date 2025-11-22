"""Stateful device objects for Thermacell hubs.

This module provides rich device objects that maintain local state, support
optimistic updates for responsive control, and provide change notifications.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
from collections.abc import Callable  # noqa: TC003 - Used at runtime for type hints
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any, cast

from pythermacell.const import (
    DEVICE_TYPE_LIV_HUB,
    LED_BRIGHTNESS_MAX,
    LED_BRIGHTNESS_MIN,
    LED_HUE_MAX,
    LED_HUE_MIN,
)
from pythermacell.exceptions import InvalidParameterError


if TYPE_CHECKING:
    from pythermacell.api import ThermacellAPI
    from pythermacell.models import DeviceState

_LOGGER = logging.getLogger(__name__)


class ThermacellDevice:
    """Stateful representation of a Thermacell device with optimistic updates.

    This class represents a real-world Thermacell hub, maintaining local state cache,
    providing responsive control via optimistic updates, and supporting change notifications.

    **Key Features:**
    - **State Caching**: Properties return cached values for instant access
    - **Optimistic Updates**: Control methods update UI immediately, then call API
    - **Auto-refresh**: Optional background polling to keep state current
    - **Change Listeners**: Callbacks for reactive UI updates
    - **Smart Reversion**: Automatic rollback on API failures

    Example:
        Basic usage with manual refresh:

        ```python
        from pythermacell import ThermacellClient

        async with ThermacellClient(username="user@example.com", password="password") as client:
            devices = await client.get_devices()
            device = devices[0]

            # Turn on (optimistic update - instant UI feedback)
            await device.turn_on()

            # Access cached state (no API call)
            print(f"Refill life: {device.refill_life}%")
            print(f"Runtime: {device.system_runtime} minutes")

            # Refresh to get latest state from API
            await device.refresh()
        ```

        Advanced usage with auto-refresh and change listeners:

        ```python
        def on_state_change(device: ThermacellDevice):
            print(f"{device.name} state changed!")
            print(f"  Power: {device.is_powered_on}")
            print(f"  Refill: {device.refill_life}%")


        async with ThermacellClient(username="user@example.com", password="password") as client:
            devices = await client.get_devices()
            device = devices[0]

            # Register change listener
            device.add_listener(on_state_change)

            # Start auto-refresh (polls every 60 seconds)
            await device.start_auto_refresh(interval=60)

            # Control device (optimistic update + listener notification)
            await device.set_led_color(hue=240, brightness=100)

            # Listener will be called on refresh and control operations
            await asyncio.sleep(120)  # Auto-refresh happens in background

            # Cleanup happens automatically on context exit
        ```

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

    def __init__(self, api: ThermacellAPI, state: DeviceState) -> None:
        """Initialize the device.

        Args:
            api: ThermacellAPI instance for HTTP communication.
            state: Initial device state containing info, status, and parameters.
        """
        self._api = api
        self._state = state
        self._last_refresh: datetime = datetime.now(UTC)

        # Change listeners (callbacks that fire on state updates)
        self._listeners: list[Callable[[ThermacellDevice], None]] = []

        # Auto-refresh task
        self._auto_refresh_task: asyncio.Task[None] | None = None
        self._auto_refresh_interval: int = 60  # Default 60 seconds

    # -------------------------------------------------------------------------
    # Device Info Properties (from DeviceInfo)
    # -------------------------------------------------------------------------

    @property
    def node_id(self) -> str:
        """Get device node ID."""
        return self._state.info.node_id

    @property
    def name(self) -> str:
        """Get device name."""
        return self._state.info.name

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

    # -------------------------------------------------------------------------
    # Device Status Properties (computed from DeviceState)
    # -------------------------------------------------------------------------

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
    def last_refresh(self) -> datetime:
        """Get timestamp of last state refresh."""
        return self._last_refresh

    @property
    def state_age_seconds(self) -> float:
        """Get the age of the cached state in seconds.

        Returns:
            Number of seconds since the last state refresh.

        Example:
            >>> if device.state_age_seconds > 60:
            ...     await device.refresh()
        """
        return (datetime.now(UTC) - self._last_refresh).total_seconds()

    # -------------------------------------------------------------------------
    # Device Parameter Properties (from DeviceParams)
    # -------------------------------------------------------------------------

    @property
    def power(self) -> bool | None:
        """Get device power state."""
        return self._state.params.power

    @property
    def led_power(self) -> bool | None:
        """Get LED power state.

        Note: LED is only "on" when device is powered AND brightness > 0.
        """
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

    # -------------------------------------------------------------------------
    # Control Methods (with Optimistic Updates)
    # -------------------------------------------------------------------------

    async def turn_on(self) -> bool:
        """Turn the device on.

        Uses optimistic update: UI updates immediately, then API is called.
        If API call fails, state is reverted automatically.

        Returns:
            True if successful, False otherwise.
        """
        return await self.set_power(True)

    async def turn_off(self) -> bool:
        """Turn the device off.

        Uses optimistic update: UI updates immediately, then API is called.
        If API call fails, state is reverted automatically.

        Returns:
            True if successful, False otherwise.
        """
        return await self.set_power(False)

    async def set_power(self, power_on: bool) -> bool:
        """Set device power state with optimistic update.

        Args:
            power_on: True to turn on, False to turn off.

        Returns:
            True if successful, False otherwise.
        """
        # Save old state for reversion
        old_enable_repellers = self._state.params.enable_repellers
        old_led_power = self._state.params.led_power

        # Optimistic update: Update local state immediately
        self._state.params.enable_repellers = power_on
        self._state.params.power = power_on  # Update read-only status too

        # Recalculate LED power based on new device power
        brightness = self._state.params.led_brightness or 0
        self._state.params.led_power = power_on and brightness > 0

        # Notify listeners immediately (instant UI update)
        self._notify_listeners()

        # Make API call in background
        params: dict[str, dict[str, int | float | bool]] = {DEVICE_TYPE_LIV_HUB: {"Enable Repellers": power_on}}
        success = await self._update_params(params)

        # Revert on failure
        if not success:
            self._state.params.enable_repellers = old_enable_repellers
            self._state.params.power = old_enable_repellers
            self._state.params.led_power = old_led_power
            self._notify_listeners()  # Notify of reversion

        return success

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
        return await self.set_led_brightness(brightness)

    async def set_led_brightness(self, brightness: int) -> bool:
        """Set LED brightness with optimistic update.

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

        # Save old state for reversion
        old_brightness = self._state.params.led_brightness
        old_led_power = self._state.params.led_power

        # Optimistic update
        self._state.params.led_brightness = brightness

        # Recalculate LED power state (device must be on AND brightness > 0)
        device_powered = self._state.params.enable_repellers or False
        self._state.params.led_power = device_powered and brightness > 0

        # Notify listeners
        self._notify_listeners()

        # Make API call
        params: dict[str, dict[str, int | float | bool]] = {DEVICE_TYPE_LIV_HUB: {"LED Brightness": brightness}}
        success = await self._update_params(params)

        # Revert on failure
        if not success:
            self._state.params.led_brightness = old_brightness
            self._state.params.led_power = old_led_power
            self._notify_listeners()

        return success

    async def set_led_color(self, hue: int, brightness: int) -> bool:
        """Set LED color using hue and brightness with optimistic update.

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

        # Save old state for reversion
        old_hue = self._state.params.led_hue
        old_brightness = self._state.params.led_brightness
        old_led_power = self._state.params.led_power

        # Optimistic update
        self._state.params.led_hue = hue
        self._state.params.led_brightness = brightness

        # Recalculate LED power state
        device_powered = self._state.params.enable_repellers or False
        self._state.params.led_power = device_powered and brightness > 0

        # Notify listeners
        self._notify_listeners()

        # Make API call (only send hue and brightness - saturation is not supported)
        params: dict[str, dict[str, int | float | bool]] = {
            DEVICE_TYPE_LIV_HUB: {
                "LED Hue": hue,
                "LED Brightness": brightness,
            }
        }
        success = await self._update_params(params)

        # Revert on failure
        if not success:
            self._state.params.led_hue = old_hue
            self._state.params.led_brightness = old_brightness
            self._state.params.led_power = old_led_power
            self._notify_listeners()

        return success

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

        # Save old state for reversion
        old_refill_life = self._state.params.refill_life

        # Optimistic update: Set to 100%
        self._state.params.refill_life = 100.0
        self._notify_listeners()

        # Use "Refill Reset" parameter with cartridge type value
        params: dict[str, dict[str, int | float | bool]] = {DEVICE_TYPE_LIV_HUB: {"Refill Reset": refill_type}}
        success = await self._update_params(params)

        # Revert on failure
        if not success:
            self._state.params.refill_life = old_refill_life
            self._notify_listeners()

        return success

    async def _update_params(self, params: dict[str, dict[str, int | float | bool]]) -> bool:
        """Update device parameters via API.

        Args:
            params: Parameter updates in API format.

        Returns:
            True if successful, False otherwise.
        """
        from http import HTTPStatus  # noqa: PLC0415 - Lazy import to avoid circular dependency

        status, _ = await self._api.update_node_params(self.node_id, cast("dict[str, Any]", params))
        success = status in (HTTPStatus.OK, HTTPStatus.NO_CONTENT)

        if success:
            _LOGGER.debug("Successfully updated device %s params: %s", self.node_id, params)
        else:
            _LOGGER.warning("Failed to update device %s params: HTTP %d", self.node_id, status)

        return success

    # -------------------------------------------------------------------------
    # State Management
    # -------------------------------------------------------------------------

    async def refresh(self) -> bool:
        """Refresh device state from API.

        This fetches the latest device state from the API and updates
        the internal state cache. Change listeners are notified of the update.

        Returns:
            True if successful, False otherwise.
        """
        # Use the client's fetch method to get complete state
        from http import HTTPStatus  # noqa: PLC0415 - Lazy import to avoid circular dependency

        # Fetch all endpoints concurrently
        results: tuple[Any, ...] = await asyncio.gather(
            self._api.get_node_params(self.node_id),
            self._api.get_node_status(self.node_id),
            self._api.get_node_config(self.node_id),
            return_exceptions=True,
        )

        params_result, status_result, config_result = results

        # Check for exceptions
        for result in [params_result, status_result, config_result]:
            if isinstance(result, Exception):
                _LOGGER.error("Error refreshing device %s: %s", self.node_id, result)
                return False

        # Unpack results (we know they're tuples now)
        params_status, params_data = cast("tuple[int, dict[str, Any] | None]", params_result)
        status_status, status_data = cast("tuple[int, dict[str, Any] | None]", status_result)
        config_status, config_data = cast("tuple[int, dict[str, Any] | None]", config_result)

        # Validate all requests succeeded
        if params_status != HTTPStatus.OK or params_data is None:
            _LOGGER.warning("Failed to refresh params for device %s: HTTP %d", self.node_id, params_status)
            return False

        if status_status != HTTPStatus.OK or status_data is None:
            _LOGGER.warning("Failed to refresh status for device %s: HTTP %d", self.node_id, status_status)
            return False

        if config_status != HTTPStatus.OK or config_data is None:
            _LOGGER.warning("Failed to refresh config for device %s: HTTP %d", self.node_id, config_status)
            return False

        # Import parsing functions from client
        # NOTE: This is a temporary coupling - ideally these would be in a shared module
        from pythermacell.client import ThermacellClient  # noqa: PLC0415 - Lazy import to avoid circular dependency
        from pythermacell.models import DeviceState  # noqa: PLC0415 - Lazy import to avoid circular dependency

        # Create a temporary client instance for parsing (not ideal, but works)
        # In a future refactor, move parsing logic to a separate module
        temp_client = ThermacellClient.__new__(ThermacellClient)
        device_params = temp_client._parse_device_params(params_data)  # noqa: SLF001
        device_status = temp_client._parse_device_status(self.node_id, status_data)  # noqa: SLF001
        device_info = temp_client._parse_device_info(self.node_id, config_data)  # noqa: SLF001

        # Update state
        new_state = DeviceState(
            info=device_info,
            status=device_status,
            params=device_params,
            raw_data={
                "params": params_data,
                "status": status_data,
                "config": config_data,
            },
        )

        await self._update_state(new_state)
        return True

    async def _update_state(self, new_state: DeviceState) -> None:
        """Update internal state and notify listeners.

        This is called internally by refresh() and by ThermacellClient
        when updating cached devices.

        Args:
            new_state: New device state to apply.
        """
        self._state = new_state
        self._last_refresh = datetime.now(UTC)
        self._notify_listeners()

    def _notify_listeners(self) -> None:
        """Notify all registered listeners of state change.

        Listeners are called synchronously in the order they were registered.
        If a listener raises an exception, it is logged but doesn't affect
        other listeners.
        """
        for listener in self._listeners:
            try:
                listener(self)
            except Exception:
                _LOGGER.exception("Error in state change listener for device %s", self.node_id)

    def add_listener(self, callback: Callable[[ThermacellDevice], None]) -> None:
        """Register a callback to be called when device state changes.

        The callback will be called:
        - After successful API updates (optimistic updates)
        - After state refresh from API
        - After optimistic update reversion (on API failure)

        Args:
            callback: Callable that takes a ThermacellDevice instance.

        Example:
            ```python
            def on_change(device: ThermacellDevice):
                print(f"{device.name} changed: power={device.is_powered_on}")


            device.add_listener(on_change)
            ```
        """
        if callback not in self._listeners:
            self._listeners.append(callback)
            _LOGGER.debug("Added state change listener for device %s", self.node_id)

    def remove_listener(self, callback: Callable[[ThermacellDevice], None]) -> None:
        """Unregister a state change callback.

        Args:
            callback: Previously registered callback to remove.
        """
        if callback in self._listeners:
            self._listeners.remove(callback)
            _LOGGER.debug("Removed state change listener for device %s", self.node_id)

    # -------------------------------------------------------------------------
    # Auto-refresh
    # -------------------------------------------------------------------------

    async def start_auto_refresh(self, interval: int = 60) -> None:
        """Start automatic background polling to keep state current.

        This creates a background task that refreshes device state at
        the specified interval. Useful for applications that need
        real-time state updates without manual polling.

        Args:
            interval: Refresh interval in seconds (default: 60).

        Example:
            ```python
            # Start auto-refresh every 30 seconds
            await device.start_auto_refresh(interval=30)

            # Device state will be updated automatically
            # Listeners will be notified on each refresh
            ```
        """
        # Stop existing task if running
        await self.stop_auto_refresh()

        self._auto_refresh_interval = interval
        self._auto_refresh_task = asyncio.create_task(self._auto_refresh_loop())
        _LOGGER.info("Started auto-refresh for device %s (interval: %ds)", self.node_id, interval)

    async def stop_auto_refresh(self) -> None:
        """Stop automatic background polling.

        This cancels the auto-refresh task if it's running.
        """
        if self._auto_refresh_task is not None:
            self._auto_refresh_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._auto_refresh_task
            self._auto_refresh_task = None
            _LOGGER.info("Stopped auto-refresh for device %s", self.node_id)

    async def _auto_refresh_loop(self) -> None:
        """Background task that refreshes state at regular intervals.

        This runs until cancelled by stop_auto_refresh().
        """
        try:
            while True:
                await asyncio.sleep(self._auto_refresh_interval)
                success = await self.refresh()
                if not success:
                    _LOGGER.warning("Auto-refresh failed for device %s", self.node_id)
        except asyncio.CancelledError:
            _LOGGER.debug("Auto-refresh loop cancelled for device %s", self.node_id)

    # -------------------------------------------------------------------------
    # String Representation
    # -------------------------------------------------------------------------

    def __str__(self) -> str:
        """Return string representation of device."""
        return f"{self.name} ({self.node_id})"

    def __repr__(self) -> str:
        """Return detailed string representation of device."""
        return f"ThermacellDevice(node_id='{self.node_id}', name='{self.name}')"
