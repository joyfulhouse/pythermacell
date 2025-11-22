"""Tests for ThermacellDevice class."""

from __future__ import annotations

from http import HTTPStatus
from typing import TYPE_CHECKING
from unittest.mock import AsyncMock

import pytest

from pythermacell.devices import ThermacellDevice
from pythermacell.exceptions import InvalidParameterError
from pythermacell.models import DeviceInfo, DeviceParams, DeviceState, DeviceStatus


if TYPE_CHECKING:
    from pythermacell.api import ThermacellAPI


@pytest.fixture
def mock_api() -> ThermacellAPI:
    """Create a mock ThermacellAPI."""
    api = AsyncMock()
    # Mock update_node_params to return (200, {})
    api.update_node_params = AsyncMock(return_value=(HTTPStatus.OK, {}))
    # Mock get_node_* methods for refresh tests
    api.get_node_params = AsyncMock(
        return_value=(
            HTTPStatus.OK,
            {
                "LIV Hub": {
                    "Power": True,
                    "LED Brightness": 80,
                    "LED Hue": 120,
                    "LED Saturation": 100,
                    "Refill Life": 75.5,
                    "System Runtime": 120,
                    "System Status": 3,
                    "Error": 0,
                    "Enable Repellers": True,
                }
            },
        )
    )
    api.get_node_status = AsyncMock(return_value=(HTTPStatus.OK, {"connectivity": {"connected": True}}))
    api.get_node_config = AsyncMock(
        return_value=(
            HTTPStatus.OK,
            {
                "info": {"name": "Test Device", "type": "thermacell-hub", "fw_version": "5.3.3"},
                "devices": [{"serial_num": "SN123456"}],
            },
        )
    )
    return api


@pytest.fixture
def device_info() -> DeviceInfo:
    """Create sample device info."""
    return DeviceInfo(
        node_id="test-node-123",
        name="Test Device",
        model="Thermacell LIV Hub",
        firmware_version="5.3.2",
        serial_number="SN123456",
    )


@pytest.fixture
def device_status() -> DeviceStatus:
    """Create sample device status."""
    return DeviceStatus(
        node_id="test-node-123",
        connected=True,
    )


@pytest.fixture
def device_params() -> DeviceParams:
    """Create sample device parameters."""
    return DeviceParams(
        power=True,
        led_power=True,
        led_brightness=80,
        led_hue=120,
        led_saturation=100,
        refill_life=75.5,
        system_runtime=120,
        system_status=3,
        error=0,
        enable_repellers=True,
    )


@pytest.fixture
def device_state(device_info: DeviceInfo, device_status: DeviceStatus, device_params: DeviceParams) -> DeviceState:
    """Create complete device state."""
    return DeviceState(
        info=device_info,
        status=device_status,
        params=device_params,
    )


@pytest.fixture
def device(mock_api: ThermacellAPI, device_state: DeviceState) -> ThermacellDevice:
    """Create a ThermacellDevice instance."""
    return ThermacellDevice(api=mock_api, state=device_state)


class TestDeviceInitialization:
    """Test device initialization."""

    async def test_init_with_state(self, mock_api: ThermacellAPI, device_state: DeviceState) -> None:
        """Test device initialization with state."""
        device = ThermacellDevice(api=mock_api, state=device_state)

        assert device.node_id == "test-node-123"
        assert device.name == "Test Device"
        assert device.model == "Thermacell LIV Hub"
        assert device.firmware_version == "5.3.2"
        assert device.serial_number == "SN123456"

    async def test_properties_from_state(self, device: ThermacellDevice) -> None:
        """Test that properties correctly reflect state."""
        assert device.is_online is True
        assert device.is_powered_on is True
        assert device.has_error is False
        assert device.power is True
        assert device.led_power is True
        assert device.led_brightness == 80
        assert device.led_hue == 120
        assert device.led_saturation == 100
        assert device.refill_life == 75.5


class TestDevicePowerControl:
    """Test device power control methods."""

    async def test_turn_on(self, device: ThermacellDevice, mock_api: ThermacellAPI) -> None:
        """Test turning device on."""
        result = await device.turn_on()

        assert result is True
        mock_api.update_node_params.assert_called_once_with(
            device.node_id,
            {"LIV Hub": {"Enable Repellers": True}},
        )

    async def test_turn_off(self, device: ThermacellDevice, mock_api: ThermacellAPI) -> None:
        """Test turning device off."""
        result = await device.turn_off()

        assert result is True
        mock_api.update_node_params.assert_called_once_with(
            device.node_id,
            {"LIV Hub": {"Enable Repellers": False}},
        )

    async def test_set_power_on(self, device: ThermacellDevice, mock_api: ThermacellAPI) -> None:
        """Test setting power to on."""
        result = await device.set_power(True)

        assert result is True
        mock_api.update_node_params.assert_called_once_with(
            device.node_id,
            {"LIV Hub": {"Enable Repellers": True}},
        )

    async def test_set_power_off(self, device: ThermacellDevice, mock_api: ThermacellAPI) -> None:
        """Test setting power to off."""
        result = await device.set_power(False)

        assert result is True
        mock_api.update_node_params.assert_called_once_with(
            device.node_id,
            {"LIV Hub": {"Enable Repellers": False}},
        )

    async def test_turn_on_failure(self, device: ThermacellDevice, mock_api: ThermacellAPI) -> None:
        """Test turn on when API call fails."""
        mock_api.update_node_params.return_value = (HTTPStatus.INTERNAL_SERVER_ERROR, None)

        result = await device.turn_on()

        assert result is False


class TestLEDControl:
    """Test LED control methods."""

    async def test_set_led_power_on(self, device: ThermacellDevice, mock_api: ThermacellAPI) -> None:
        """Test turning LED on."""
        result = await device.set_led_power(True)

        assert result is True
        mock_api.update_node_params.assert_called_once_with(
            device.node_id,
            {"LIV Hub": {"LED Brightness": 100}},
        )

    async def test_set_led_power_off(self, device: ThermacellDevice, mock_api: ThermacellAPI) -> None:
        """Test turning LED off."""
        result = await device.set_led_power(False)

        assert result is True
        mock_api.update_node_params.assert_called_once_with(
            device.node_id,
            {"LIV Hub": {"LED Brightness": 0}},
        )

    async def test_set_led_brightness_valid(self, device: ThermacellDevice, mock_api: ThermacellAPI) -> None:
        """Test setting LED brightness with valid value."""
        result = await device.set_led_brightness(50)

        assert result is True
        mock_api.update_node_params.assert_called_once_with(
            device.node_id,
            {"LIV Hub": {"LED Brightness": 50}},
        )

    async def test_set_led_brightness_min(self, device: ThermacellDevice, mock_api: ThermacellAPI) -> None:
        """Test setting LED brightness to minimum."""
        result = await device.set_led_brightness(0)

        assert result is True
        mock_api.update_node_params.assert_called_once_with(
            device.node_id,
            {"LIV Hub": {"LED Brightness": 0}},
        )

    async def test_set_led_brightness_max(self, device: ThermacellDevice, mock_api: ThermacellAPI) -> None:
        """Test setting LED brightness to maximum."""
        result = await device.set_led_brightness(100)

        assert result is True
        mock_api.update_node_params.assert_called_once_with(
            device.node_id,
            {"LIV Hub": {"LED Brightness": 100}},
        )

    async def test_set_led_brightness_invalid_low(self, device: ThermacellDevice) -> None:
        """Test setting LED brightness below minimum raises error."""
        with pytest.raises(InvalidParameterError) as exc_info:
            await device.set_led_brightness(-1)

        assert "brightness" in str(exc_info.value).lower()
        assert exc_info.value.parameter_name == "brightness"
        assert exc_info.value.value == -1

    async def test_set_led_brightness_invalid_high(self, device: ThermacellDevice) -> None:
        """Test setting LED brightness above maximum raises error."""
        with pytest.raises(InvalidParameterError) as exc_info:
            await device.set_led_brightness(101)

        assert "brightness" in str(exc_info.value).lower()
        assert exc_info.value.parameter_name == "brightness"
        assert exc_info.value.value == 101

    async def test_set_led_color_valid(self, device: ThermacellDevice, mock_api: ThermacellAPI) -> None:
        """Test setting LED color with valid hue and brightness values.

        Note: Saturation is not supported - always assumed to be 100%.
        """
        result = await device.set_led_color(hue=180, brightness=75)

        assert result is True
        mock_api.update_node_params.assert_called_once_with(
            device.node_id,
            {
                "LIV Hub": {
                    "LED Hue": 180,
                    "LED Brightness": 75,
                }
            },
        )

    async def test_set_led_color_min_values(self, device: ThermacellDevice, mock_api: ThermacellAPI) -> None:
        """Test setting LED color with minimum values."""
        result = await device.set_led_color(hue=0, brightness=0)

        assert result is True
        mock_api.update_node_params.assert_called_once()

    async def test_set_led_color_max_values(self, device: ThermacellDevice, mock_api: ThermacellAPI) -> None:
        """Test setting LED color with maximum values."""
        result = await device.set_led_color(hue=360, brightness=100)

        assert result is True
        mock_api.update_node_params.assert_called_once()

    async def test_set_led_color_invalid_hue_low(self, device: ThermacellDevice) -> None:
        """Test setting LED color with hue below minimum."""
        with pytest.raises(InvalidParameterError) as exc_info:
            await device.set_led_color(hue=-1, brightness=50)

        assert exc_info.value.parameter_name == "hue"
        assert exc_info.value.value == -1

    async def test_set_led_color_invalid_hue_high(self, device: ThermacellDevice) -> None:
        """Test setting LED color with hue above maximum."""
        with pytest.raises(InvalidParameterError) as exc_info:
            await device.set_led_color(hue=361, brightness=50)

        assert exc_info.value.parameter_name == "hue"


class TestRefillControl:
    """Test refill-related methods."""

    async def test_reset_refill(self, device: ThermacellDevice, mock_api: ThermacellAPI) -> None:
        """Test resetting refill life to 100%.

        Uses default refill type 1 (100 Hour - Blue Cap).
        """
        result = await device.reset_refill()

        assert result is True
        mock_api.update_node_params.assert_called_once_with(
            device.node_id,
            {"LIV Hub": {"Refill Reset": 1}},
        )


class TestDeviceRefresh:
    """Test device state refresh."""

    async def test_refresh_success(self, device: ThermacellDevice, mock_api: ThermacellAPI) -> None:
        """Test refreshing device state."""
        # Mock the three API calls that refresh() makes
        mock_api.get_node_params = AsyncMock(
            return_value=(
                HTTPStatus.OK,
                {
                    "LIV Hub": {
                        "Power": False,
                        "LED Brightness": 50,
                        "LED Hue": 200,
                        "LED Saturation": 100,
                        "Refill Life": 50.0,
                        "System Runtime": 60,
                        "System Status": 1,
                        "Error": 0,
                        "Enable Repellers": False,
                    }
                },
            )
        )
        mock_api.get_node_status = AsyncMock(return_value=(HTTPStatus.OK, {"connectivity": {"connected": True}}))
        mock_api.get_node_config = AsyncMock(
            return_value=(
                HTTPStatus.OK,
                {
                    "info": {"name": "Test Device", "type": "thermacell-hub", "fw_version": "5.3.3"},
                    "devices": [{"serial_num": "SN123456"}],
                },
            )
        )

        result = await device.refresh()

        assert result is True
        assert device.firmware_version == "5.3.3"
        assert device.power is False
        assert device.led_brightness == 50
        mock_api.get_node_params.assert_called_once_with(device.node_id)
        mock_api.get_node_status.assert_called_once_with(device.node_id)
        mock_api.get_node_config.assert_called_once_with(device.node_id)

    async def test_refresh_failure(self, device: ThermacellDevice, mock_api: ThermacellAPI) -> None:
        """Test refresh when API call fails."""
        mock_api.get_node_params = AsyncMock(return_value=(HTTPStatus.INTERNAL_SERVER_ERROR, None))

        result = await device.refresh()

        assert result is False


class TestDeviceStateProperties:
    """Test device state property accessors."""

    async def test_offline_device(self, mock_api: ThermacellAPI, device_state: DeviceState) -> None:
        """Test properties when device is offline."""
        device_state.status.connected = False
        device = ThermacellDevice(api=mock_api, state=device_state)

        assert device.is_online is False

    async def test_powered_off_device(self, mock_api: ThermacellAPI, device_state: DeviceState) -> None:
        """Test properties when device is powered off."""
        device_state.params.power = False
        device = ThermacellDevice(api=mock_api, state=device_state)

        assert device.is_powered_on is False
        assert device.power is False

    async def test_device_with_error(self, mock_api: ThermacellAPI, device_state: DeviceState) -> None:
        """Test properties when device has error."""
        device_state.params.error = 5
        device = ThermacellDevice(api=mock_api, state=device_state)

        assert device.has_error is True
        assert device.error == 5

    async def test_device_without_error(self, mock_api: ThermacellAPI, device_state: DeviceState) -> None:
        """Test properties when device has no error."""
        device_state.params.error = 0
        device = ThermacellDevice(api=mock_api, state=device_state)

        assert device.has_error is False
        assert device.error == 0

    async def test_none_parameter_values(self, mock_api: ThermacellAPI, device_state: DeviceState) -> None:
        """Test properties when parameters are None."""
        device_state.params.power = None
        device_state.params.led_brightness = None
        device = ThermacellDevice(api=mock_api, state=device_state)

        assert device.power is None
        assert device.led_brightness is None
        assert device.is_powered_on is False  # None treated as False

    async def test_state_age_seconds(self, mock_api: ThermacellAPI, device_state: DeviceState) -> None:
        """Test state_age_seconds property tracks time since last refresh."""
        import asyncio

        device = ThermacellDevice(api=mock_api, state=device_state)

        # Immediately after creation, age should be near 0
        initial_age = device.state_age_seconds
        assert initial_age >= 0
        assert initial_age < 0.1  # Should be very recent

        # Wait a bit and check age has increased
        await asyncio.sleep(0.2)
        age_after_wait = device.state_age_seconds
        assert age_after_wait >= 0.2
        assert age_after_wait < 0.3  # Allow some margin

        # After refresh, age should reset
        await device.refresh()
        age_after_refresh = device.state_age_seconds
        assert age_after_refresh >= 0
        assert age_after_refresh < 0.1  # Should be very recent again


class TestDeviceRepresentation:
    """Test device string representation."""

    async def test_str_representation(self, device: ThermacellDevice) -> None:
        """Test string representation of device."""
        result = str(device)

        assert "Test Device" in result
        assert "test-node-123" in result

    async def test_repr_representation(self, device: ThermacellDevice) -> None:
        """Test repr representation of device."""
        result = repr(device)

        assert "ThermacellDevice" in result
        assert "test-node-123" in result
