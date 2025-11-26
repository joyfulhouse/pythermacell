"""Integration tests for device control operations with real API."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

import pytest

from pythermacell import InvalidParameterError, ThermacellClient


if TYPE_CHECKING:
    from collections.abc import Callable

    from pythermacell import ThermacellDevice


pytestmark = [pytest.mark.integration, pytest.mark.asyncio, pytest.mark.slow]


async def verify_state(
    device: ThermacellDevice,
    condition: Callable[[ThermacellDevice], bool],
    *,
    delay: float = 8.0,
    max_retries: int = 3,
) -> bool:
    """Verify device state after a command with retry logic.

    This gives the device time to process commands, then verifies state with
    retries to handle slower CI environments and network variability.

    Important: Each refresh makes 3 API calls, so we use longer delays between
    retries to avoid overwhelming the device firmware.

    Args:
        device: Device to check.
        condition: Function that returns True when desired state is reached.
        delay: How long to wait before each refresh attempt (default 8.0 seconds).
        max_retries: Maximum number of refresh attempts (default 3).

    Returns:
        True if condition was met within retries, False otherwise.
    """
    for attempt in range(max_retries):
        # Give device time to process the command
        await asyncio.sleep(delay)

        # Refresh to get updated state (lightweight refresh - 2 API calls)
        await device.refresh()

        # Check if condition is met
        if condition(device):
            return True

        # Longer pause before retry to avoid overwhelming device
        if attempt < max_retries - 1:
            await asyncio.sleep(5)

    return False


@pytest.fixture
async def test_device(shared_integration_client: ThermacellClient, test_device_id: str | None) -> ThermacellDevice:
    """Get a test device to use for control tests.

    Uses the shared session-scoped client to avoid re-authentication.
    """
    if test_device_id is None:
        devices = await shared_integration_client.get_devices()
        if len(devices) == 0:
            pytest.skip("No devices available for testing")

        # Find first ONLINE device for control tests
        device = None
        for d in devices:
            if d.is_online:
                device = d
                break

        if device is None:
            pytest.skip("No online devices available for testing")
    else:
        device = await shared_integration_client.get_device(test_device_id)
        if device is None:
            pytest.skip(f"Test device {test_device_id} not found")

    return device


class TestDevicePowerControl:
    """Integration tests for device power control."""

    async def test_turn_on_device(self, test_device: ThermacellDevice) -> None:
        """Test turning device on."""
        # Turn device on
        success = await test_device.turn_on()
        assert success, "Turn on should succeed"

        # Wait for API to process
        await asyncio.sleep(5)

        # Refresh state and verify
        refreshed = await test_device.refresh()
        assert refreshed, "State refresh should succeed"
        assert test_device.is_powered_on, "Device should be powered on"

    async def test_set_power_state(self, test_device: ThermacellDevice) -> None:
        """Test setting power state directly."""
        # Get current state
        original_power = test_device.power

        # Toggle power state
        new_power = not original_power if original_power is not None else True

        success = await test_device.set_power(new_power)
        assert success, "Set power should succeed"

        # Wait for API to process and state to update
        state_updated = await verify_state(test_device, lambda d: d.power == new_power)
        assert state_updated, f"Power should be {new_power} after set_power within timeout"

        # Restore original state
        await test_device.set_power(original_power if original_power is not None else False)
        await asyncio.sleep(5)

    async def test_power_toggle_sequence(self, test_device: ThermacellDevice) -> None:
        """Test toggling power on and off in sequence."""
        # Turn on
        await test_device.turn_on()
        state_updated = await verify_state(test_device, lambda d: d.is_powered_on)
        assert state_updated, "Device should be on after turn_on within timeout"

        # Turn off
        await test_device.turn_off()
        state_updated = await verify_state(test_device, lambda d: not d.is_powered_on)
        assert state_updated, "Device should be off after turn_off within timeout"

        # Turn back on to leave device in ready state for other tests
        await test_device.turn_on()
        state_updated = await verify_state(test_device, lambda d: d.is_powered_on)
        assert state_updated, "Device should be back on for subsequent tests within timeout"


class TestLEDControl:
    """Integration tests for LED control."""

    async def test_set_led_power_on(self, test_device: ThermacellDevice) -> None:
        """Test turning LED on."""
        # Ensure device is powered on first (LED requires device power)
        await test_device.turn_on()
        await asyncio.sleep(5)

        # Turn LED on
        success = await test_device.set_led_power(True)
        assert success, "Set LED power should succeed"

        # Wait for API to process
        await asyncio.sleep(5)

        # Refresh and verify
        await test_device.refresh()
        assert test_device.led_power, "LED should be powered on"

    async def test_set_led_power_off(self, test_device: ThermacellDevice) -> None:
        """Test turning LED off."""
        success = await test_device.set_led_power(False)
        assert success, "Set LED power should succeed"

        # Wait for state to update with retry logic
        state_updated = await verify_state(test_device, lambda d: not d.led_power)
        assert state_updated, "LED should be powered off within timeout"

    async def test_set_led_brightness(self, test_device: ThermacellDevice) -> None:
        """Test setting LED brightness."""
        # Ensure device is powered on
        await test_device.turn_on()
        state_updated = await verify_state(test_device, lambda d: d.is_powered_on)
        if not state_updated:
            pytest.skip("Device did not power on - cannot test LED brightness")

        # Set brightness to 50%
        success = await test_device.set_led_brightness(50)
        assert success, "Set brightness should succeed"

        # Wait for state to update with retry logic
        state_updated = await verify_state(test_device, lambda d: d.led_brightness == 50)
        assert state_updated, "Brightness should be 50"

        # Set brightness to 100%
        await test_device.set_led_brightness(100)
        state_updated = await verify_state(test_device, lambda d: d.led_brightness == 100)
        assert state_updated, "Brightness should be 100"

    async def test_set_led_brightness_validation(self, test_device: ThermacellDevice) -> None:
        """Test LED brightness validation."""
        # Test below minimum
        with pytest.raises(InvalidParameterError, match=r"brightness.*0-100"):
            await test_device.set_led_brightness(-1)

        # Test above maximum
        with pytest.raises(InvalidParameterError, match=r"brightness.*0-100"):
            await test_device.set_led_brightness(101)

        # Test valid values at boundaries
        success = await test_device.set_led_brightness(0)
        assert success, "Brightness 0 should be valid"

        await asyncio.sleep(5)

        success = await test_device.set_led_brightness(100)
        assert success, "Brightness 100 should be valid"

    async def test_set_led_color(self, test_device: ThermacellDevice) -> None:
        """Test setting LED color using hue and brightness.

        Note: Saturation is not supported by the Thermacell API and is always
        assumed to be 100% (full saturation). Sending saturation causes device crashes.
        """
        # Ensure device is powered on and wait for it to actually be on
        await test_device.turn_on()
        state_updated = await verify_state(test_device, lambda d: d.is_powered_on)
        if not state_updated:
            pytest.skip("Device did not power on - cannot test LED color control")

        # Check refill life - if too low, device forces LED to red and test will fail
        if test_device.refill_life is not None and test_device.refill_life < 20:
            pytest.skip("Refill life too low - device firmware forces LED to red as warning")

        # Set color to green (hue=120, full brightness) - avoid red which may be forced by low refill
        success = await test_device.set_led_color(hue=120, brightness=100)
        assert success, "Set color should succeed"

        # Wait for state to update with retry logic
        state_updated = await verify_state(
            test_device,
            lambda d: d.led_hue == 120 and d.led_brightness == 100,
            delay=10.0,
            max_retries=4,
        )
        assert state_updated, "LED color should update to green within timeout"

        # Set color to blue (hue=240)
        await test_device.set_led_color(hue=240, brightness=75)
        state_updated = await verify_state(
            test_device,
            lambda d: d.led_hue == 240 and d.led_brightness == 75,
            delay=10.0,
            max_retries=4,
        )
        assert state_updated, "LED color should update to blue within timeout"

    async def test_set_led_color_validation(self, test_device: ThermacellDevice) -> None:
        """Test LED color parameter validation."""
        # Test invalid hue
        with pytest.raises(InvalidParameterError, match=r"hue.*0-360"):
            await test_device.set_led_color(hue=-1, brightness=100)

        with pytest.raises(InvalidParameterError, match=r"hue.*0-360"):
            await test_device.set_led_color(hue=361, brightness=100)

        # Test invalid brightness
        with pytest.raises(InvalidParameterError, match=r"brightness.*0-100"):
            await test_device.set_led_color(hue=0, brightness=-1)

        with pytest.raises(InvalidParameterError, match=r"brightness.*0-100"):
            await test_device.set_led_color(hue=0, brightness=101)

    async def test_led_color_range(self, test_device: ThermacellDevice) -> None:
        """Test LED color across a sample of the hue range.

        Note: Saturation is not supported and is always 100% (full saturation).

        This test uses a reduced set of values to avoid overwhelming the device.
        Full range testing should be done manually when needed.
        """
        # Ensure device is powered on
        await test_device.turn_on()
        await asyncio.sleep(3)

        # Test a sample of hue values (reduced from 7 to 3 to avoid device stress)
        for hue in [0, 120, 240]:
            success = await test_device.set_led_color(hue=hue, brightness=100)
            assert success, f"Setting hue {hue} should succeed"
            await asyncio.sleep(5)  # Increased from 1 to 5 seconds

        # Test boundary brightness values only (reduced from 4 to 2)
        for brightness in [50, 100]:
            success = await test_device.set_led_color(hue=120, brightness=brightness)
            assert success, f"Setting brightness {brightness} should succeed"
            await asyncio.sleep(5)  # Increased from 1 to 5 seconds


class TestRefillControl:
    """Integration tests for refill cartridge management."""

    async def test_reset_refill(self, test_device: ThermacellDevice) -> None:
        """Test resetting refill life counter."""
        # Reset refill to 100%
        success = await test_device.reset_refill()
        assert success, "Reset refill should succeed"

        # Wait for state to update with retry logic
        state_updated = await verify_state(test_device, lambda d: d.refill_life == 100.0)
        assert state_updated, "Refill life should be 100% after reset within timeout"


class TestDeviceRefresh:
    """Integration tests for device state refresh."""

    async def test_refresh_device_state(self, test_device: ThermacellDevice) -> None:
        """Test refreshing device state from API."""
        # Get initial state
        initial_node_id = test_device.node_id

        # Refresh state
        success = await test_device.refresh()
        assert success, "Refresh should succeed"

        # Verify device still has same identity
        assert test_device.node_id == initial_node_id, "Node ID should not change"

        # Verify state was updated (all properties should be accessible)
        assert test_device.name is not None, "Name should be set after refresh"
        assert test_device.model is not None, "Model should be set after refresh"

    async def test_refresh_after_control_operation(self, test_device: ThermacellDevice) -> None:
        """Test refresh captures state changes from control operations."""
        # Turn device on
        await test_device.turn_on()

        # Wait for state to update
        state_updated = await verify_state(test_device, lambda d: d.is_powered_on)
        assert state_updated, "Refresh should show device is on within timeout"

        # Turn device off
        await test_device.turn_off()

        # Wait for state to update
        state_updated = await verify_state(test_device, lambda d: not d.is_powered_on)
        assert state_updated, "Refresh should show device is off within timeout"


class TestConcurrentControlOperations:
    """Integration tests for concurrent control operations."""

    async def test_sequential_control_operations(self, test_device: ThermacellDevice) -> None:
        """Test multiple control operations in sequence."""
        # Turn on
        await test_device.turn_on()
        state_updated = await verify_state(test_device, lambda d: d.is_powered_on)
        if not state_updated:
            pytest.skip("Device did not power on - cannot test sequential operations")

        # Set LED color
        await test_device.set_led_color(hue=120, brightness=80)
        await verify_state(
            test_device,
            lambda d: d.led_hue == 120 and d.led_brightness == 80,
            delay=10.0,
            max_retries=4,
        )

        # Set LED brightness
        await test_device.set_led_brightness(50)

        # Wait for final state and verify brightness changed
        # Note: Also verify power is on as LED operations require device to be powered
        state_updated = await verify_state(
            test_device,
            lambda d: d.led_brightness == 50 and d.is_powered_on,
        )
        assert state_updated, "Brightness should update to 50 and device should remain on"

    async def test_device_state_consistency(self, test_device: ThermacellDevice) -> None:
        """Test device state remains consistent after multiple operations."""
        # Perform multiple operations with adequate delays to avoid device stress
        await test_device.turn_on()
        await asyncio.sleep(5)

        await test_device.set_led_color(hue=240, brightness=100)
        await asyncio.sleep(5)

        await test_device.set_led_brightness(75)
        await asyncio.sleep(5)

        # Refresh state
        await test_device.refresh()

        # Verify all state is internally consistent
        assert test_device.node_id is not None, "Node ID should be set"
        assert test_device.name is not None, "Name should be set"
        assert isinstance(test_device.is_online, bool), "Online status should be bool"
        assert isinstance(test_device.is_powered_on, bool), "Power status should be bool"


class TestErrorRecovery:
    """Integration tests for error recovery during control operations."""

    async def test_control_operation_after_network_delay(self, test_device: ThermacellDevice) -> None:
        """Test control operations work after delays."""
        # Perform operation
        success = await test_device.turn_on()
        assert success, "Operation should succeed"

        # Long delay simulating network issues
        await asyncio.sleep(5)

        # Perform another operation
        success = await test_device.set_led_brightness(75)
        assert success, "Operation should succeed after delay"

    async def test_refresh_after_failed_state(self, test_device: ThermacellDevice) -> None:
        """Test refresh can recover device state."""
        # Refresh should always work even if previous operations failed
        success = await test_device.refresh()
        assert success, "Refresh should succeed"

        # Verify device is in valid state
        assert test_device.node_id is not None, "Device should have node_id"
        assert test_device.name is not None, "Device should have name"


class TestZFinalCleanup:
    """Final cleanup tests that run last to avoid affecting other tests."""

    async def test_turn_off_device(self, test_device: ThermacellDevice) -> None:
        """Test turning device off.

        Note: This test runs last (TestZ* class name) to avoid leaving the device
        off for subsequent tests that require the device to be powered on.
        """
        # Turn device off
        success = await test_device.turn_off()
        assert success, "Turn off should succeed"

        # Wait for state to update with retry logic
        state_updated = await verify_state(test_device, lambda d: not d.is_powered_on)
        assert state_updated, "Device should be powered off within timeout"
