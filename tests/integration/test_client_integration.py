"""Integration tests for ThermacellClient with real API."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

import pytest
from aiohttp import ClientSession

from pythermacell import ThermacellClient, ThermacellDevice
from pythermacell.models import DeviceState


if TYPE_CHECKING:
    from collections.abc import AsyncGenerator


pytestmark = [pytest.mark.integration, pytest.mark.asyncio]


@pytest.fixture
async def session() -> AsyncGenerator[ClientSession]:
    """Create aiohttp session for tests."""
    async with ClientSession() as sess:
        yield sess


@pytest.fixture
async def client(integration_config: dict[str, str], session: ClientSession) -> AsyncGenerator[ThermacellClient]:
    """Create authenticated client for tests."""
    client = ThermacellClient(
        username=integration_config["username"],
        password=integration_config["password"],
        base_url=integration_config["base_url"],
        session=session,
    )

    async with client:
        yield client


class TestClientSessionManagement:
    """Integration tests for client session management."""

    async def test_client_with_injected_session(
        self, integration_config: dict[str, str], session: ClientSession
    ) -> None:
        """Test client works with injected session."""
        client = ThermacellClient(
            username=integration_config["username"],
            password=integration_config["password"],
            base_url=integration_config["base_url"],
            session=session,  # Inject session
        )

        async with client:
            devices = await client.get_devices()

            # Should work with injected session
            assert isinstance(devices, list), "Should return list of devices"

        # Session should still be open (client doesn't own it)
        assert not session.closed, "Injected session should not be closed by client"

    async def test_client_with_owned_session(self, integration_config: dict[str, str]) -> None:
        """Test client creates and manages its own session."""
        client = ThermacellClient(
            username=integration_config["username"],
            password=integration_config["password"],
            base_url=integration_config["base_url"],
            # No session provided - client will create one
        )

        async with client:
            devices = await client.get_devices()

            # Should work with owned session
            assert isinstance(devices, list), "Should return list of devices"

        # Session should be closed after exiting context


class TestDeviceDiscovery:
    """Integration tests for device discovery."""

    async def test_get_devices(self, client: ThermacellClient) -> None:
        """Test discovering all user devices."""
        devices = await client.get_devices()

        # Verify we got a list
        assert isinstance(devices, list), "Should return list of devices"

        # If account has devices, verify they're properly structured
        if len(devices) > 0:
            device = devices[0]

            # Verify device type
            assert isinstance(device, ThermacellDevice), "Should return ThermacellDevice instances"

            # Verify device has required attributes
            assert device.node_id is not None, "Device should have node_id"
            assert isinstance(device.node_id, str), "node_id should be string"
            assert len(device.node_id) > 0, "node_id should not be empty"

            assert device.name is not None, "Device should have name"
            assert isinstance(device.name, str), "name should be string"

            assert device.model is not None, "Device should have model"
            assert device.firmware_version is not None, "Device should have firmware version"
            assert device.serial_number is not None, "Device should have serial number"

    async def test_get_device_by_id(self, client: ThermacellClient, test_device_id: str | None) -> None:
        """Test getting specific device by node ID."""
        # Get a device ID to test with
        if test_device_id is None:
            devices = await client.get_devices()
            if len(devices) == 0:
                pytest.skip("No devices available for testing")
            node_id = devices[0].node_id
        else:
            node_id = test_device_id

        # Get device by ID
        device = await client.get_device(node_id)

        # Verify device was found
        assert device is not None, f"Device {node_id} should be found"
        assert isinstance(device, ThermacellDevice), "Should return ThermacellDevice"
        assert device.node_id == node_id, "Should return correct device"

    async def test_get_nonexistent_device(self, client: ThermacellClient) -> None:
        """Test getting device that doesn't exist."""
        fake_node_id = "NONEXISTENT-DEVICE-ID-12345"

        device = await client.get_device(fake_node_id)

        # Should return None for nonexistent device
        assert device is None, "Should return None for nonexistent device"


class TestDeviceState:
    """Integration tests for device state retrieval."""

    async def test_get_device_state(self, client: ThermacellClient, test_device_id: str | None) -> None:
        """Test retrieving complete device state."""
        # Get a device ID to test with
        if test_device_id is None:
            devices = await client.get_devices()
            if len(devices) == 0:
                pytest.skip("No devices available for testing")
            node_id = devices[0].node_id
        else:
            node_id = test_device_id

        # Get device and access its internal state
        device = await client.get_device(node_id)
        assert device is not None, "Should return device"
        state = device._state

        # Verify state structure
        assert state is not None, "Should return device state"
        assert isinstance(state, DeviceState), "Should return DeviceState instance"

        # Verify info
        assert state.info is not None, "State should have info"
        assert state.info.node_id == node_id, "Info should have correct node_id"
        assert state.info.name is not None, "Info should have name"
        assert state.info.model is not None, "Info should have model"
        assert state.info.firmware_version is not None, "Info should have firmware version"
        assert state.info.serial_number is not None, "Info should have serial number"

        # Verify status
        assert state.status is not None, "State should have status"
        assert state.status.node_id == node_id, "Status should have correct node_id"
        assert isinstance(state.status.connected, bool), "Status should have connected flag"

        # Verify params
        assert state.params is not None, "State should have params"

        # Verify convenient properties
        assert state.node_id == node_id, "State should have node_id property"
        assert state.name is not None, "State should have name property"
        assert isinstance(state.is_online, bool), "State should have is_online property"
        assert isinstance(state.is_powered_on, bool), "State should have is_powered_on property"
        assert isinstance(state.has_error, bool), "State should have has_error property"

        # Verify raw data is included
        assert state.raw_data is not None, "State should have raw_data"
        assert "params" in state.raw_data, "Raw data should include params"
        assert "status" in state.raw_data, "Raw data should include status"
        assert "config" in state.raw_data, "Raw data should include config"

    async def test_device_state_params(self, client: ThermacellClient, test_device_id: str | None) -> None:  # noqa: PLR0912
        """Test device state contains all expected parameters."""
        # Get a device ID to test with
        if test_device_id is None:
            devices = await client.get_devices()
            if len(devices) == 0:
                pytest.skip("No devices available for testing")
            node_id = devices[0].node_id
        else:
            node_id = test_device_id

        # Get device and access its state
        device = await client.get_device(node_id)
        assert device is not None, "Should return device"
        state = device._state
        assert state is not None, "Should have device state"

        params = state.params

        # Verify parameter types (values might be None)
        if params.power is not None:
            assert isinstance(params.power, bool), "power should be bool"

        if params.led_power is not None:
            assert isinstance(params.led_power, bool), "led_power should be bool"

        if params.led_brightness is not None:
            assert isinstance(params.led_brightness, int), "led_brightness should be int"
            assert 0 <= params.led_brightness <= 100, "led_brightness should be 0-100"

        if params.led_hue is not None:
            assert isinstance(params.led_hue, int), "led_hue should be int"
            assert 0 <= params.led_hue <= 360, "led_hue should be 0-360"

        if params.led_saturation is not None:
            assert isinstance(params.led_saturation, int), "led_saturation should be int"
            assert 0 <= params.led_saturation <= 100, "led_saturation should be 0-100"

        if params.refill_life is not None:
            assert isinstance(params.refill_life, (int, float)), "refill_life should be numeric"
            assert 0 <= params.refill_life <= 100, "refill_life should be 0-100"

        if params.system_runtime is not None:
            assert isinstance(params.system_runtime, int), "system_runtime should be int"
            assert params.system_runtime >= 0, "system_runtime should be non-negative"

        if params.system_status is not None:
            assert isinstance(params.system_status, int), "system_status should be int"

        if params.error is not None:
            assert isinstance(params.error, int), "error should be int"

        if params.enable_repellers is not None:
            assert isinstance(params.enable_repellers, bool), "enable_repellers should be bool"


class TestDeviceProperties:
    """Integration tests for device property accessors."""

    async def test_device_properties(self, client: ThermacellClient, test_device_id: str | None) -> None:
        """Test device property accessors return correct values."""
        # Get a device to test with
        if test_device_id is None:
            devices = await client.get_devices()
            if len(devices) == 0:
                pytest.skip("No devices available for testing")
            device = devices[0]
        else:
            device = await client.get_device(test_device_id)
            assert device is not None, "Test device should exist"

        # Test basic properties
        assert isinstance(device.node_id, str), "node_id should be string"
        assert isinstance(device.name, str), "name should be string"
        assert isinstance(device.model, str), "model should be string"
        assert isinstance(device.firmware_version, str), "firmware_version should be string"
        assert isinstance(device.serial_number, str), "serial_number should be string"

        # Test status properties
        assert isinstance(device.is_online, bool), "is_online should be bool"
        assert isinstance(device.is_powered_on, bool), "is_powered_on should be bool"
        assert isinstance(device.has_error, bool), "has_error should be bool"

        # Test parameter properties (may be None)
        # Just verify they don't raise exceptions
        _ = device.power
        _ = device.led_power
        _ = device.led_brightness
        _ = device.led_hue
        _ = device.led_saturation
        _ = device.refill_life
        _ = device.system_runtime
        _ = device.system_status
        _ = device.error
        _ = device.enable_repellers


class TestMultiDeviceScenarios:
    """Integration tests for multiple device scenarios."""

    async def test_concurrent_device_state_retrieval(self, client: ThermacellClient) -> None:
        """Test retrieving state for multiple devices concurrently."""
        devices = await client.get_devices()

        if len(devices) < 2:
            pytest.skip("Need at least 2 devices for concurrent test")

        # Get devices - this internally fetches state concurrently
        # Devices already have their state loaded, just verify them
        assert len(devices) > 0, "Should have devices"
        assert all(d._state is not None for d in devices), "All devices should have state"

        # Verify concurrent refresh works
        await asyncio.gather(*[d.refresh() for d in devices])
        assert all(d._state is not None for d in devices), "All states should be refreshed"

    async def test_multiple_clients_same_session(
        self, integration_config: dict[str, str], session: ClientSession
    ) -> None:
        """Test multiple clients can share the same session."""
        # Create two clients with same session
        client1 = ThermacellClient(
            username=integration_config["username"],
            password=integration_config["password"],
            base_url=integration_config["base_url"],
            session=session,
        )

        client2 = ThermacellClient(
            username=integration_config["username"],
            password=integration_config["password"],
            base_url=integration_config["base_url"],
            session=session,
        )

        async with client1, client2:
            # Both clients should work
            devices1 = await client1.get_devices()
            devices2 = await client2.get_devices()

            # Should get same devices
            assert len(devices1) == len(devices2), "Both clients should see same devices"
