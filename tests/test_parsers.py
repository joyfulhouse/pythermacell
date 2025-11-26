"""Tests for the parsers module."""

from pythermacell.models import DeviceInfo, DeviceParams, DeviceState, DeviceStatus
from pythermacell.parsers import (
    parse_device_info,
    parse_device_params,
    parse_device_state,
    parse_device_status,
)


class TestParseDeviceParams:
    """Tests for parse_device_params function."""

    def test_parse_complete_params(self) -> None:
        """Test parsing complete device parameters."""
        data = {
            "LIV Hub": {
                "Enable Repellers": True,
                "LED Brightness": 75,
                "LED Hue": 120,
                "LED Saturation": 100,
                "Refill Life": 85.5,
                "System Runtime": 30,
                "System Status": 3,
                "Error": 0,
            }
        }

        params = parse_device_params(data)

        assert isinstance(params, DeviceParams)
        assert params.power is True  # Uses Enable Repellers
        assert params.enable_repellers is True
        assert params.led_brightness == 75
        assert params.led_hue == 120
        assert params.led_saturation == 100
        assert params.refill_life == 85.5
        assert params.system_runtime == 30
        assert params.system_status == 3
        assert params.error == 0

    def test_parse_led_power_on_when_powered_and_brightness(self) -> None:
        """Test LED power is on when device powered and brightness > 0."""
        data = {
            "LIV Hub": {
                "Enable Repellers": True,
                "LED Brightness": 50,
            }
        }

        params = parse_device_params(data)

        assert params.led_power is True

    def test_parse_led_power_off_when_powered_but_zero_brightness(self) -> None:
        """Test LED power is off when device powered but brightness is 0."""
        data = {
            "LIV Hub": {
                "Enable Repellers": True,
                "LED Brightness": 0,
            }
        }

        params = parse_device_params(data)

        assert params.led_power is False

    def test_parse_led_power_off_when_not_powered(self) -> None:
        """Test LED power is off when device is not powered."""
        data = {
            "LIV Hub": {
                "Enable Repellers": False,
                "LED Brightness": 100,
            }
        }

        params = parse_device_params(data)

        assert params.led_power is False

    def test_parse_led_power_none_when_enable_repellers_none(self) -> None:
        """Test LED power is None when Enable Repellers is not present."""
        data = {
            "LIV Hub": {
                "LED Brightness": 100,
            }
        }

        params = parse_device_params(data)

        assert params.led_power is None

    def test_parse_empty_hub_params(self) -> None:
        """Test parsing with empty LIV Hub section."""
        data = {"LIV Hub": {}}

        params = parse_device_params(data)

        assert params.power is None
        assert params.enable_repellers is None
        assert params.led_brightness == 0  # Defaults to 0
        assert params.led_power is None

    def test_parse_missing_liv_hub(self) -> None:
        """Test parsing with missing LIV Hub key."""
        data = {}

        params = parse_device_params(data)

        assert params.power is None
        assert params.led_brightness == 0


class TestParseDeviceStatus:
    """Tests for parse_device_status function."""

    def test_parse_connected_status(self) -> None:
        """Test parsing connected device status."""
        data = {"connectivity": {"connected": True}}

        status = parse_device_status("node123", data)

        assert isinstance(status, DeviceStatus)
        assert status.node_id == "node123"
        assert status.connected is True

    def test_parse_disconnected_status(self) -> None:
        """Test parsing disconnected device status."""
        data = {"connectivity": {"connected": False}}

        status = parse_device_status("node456", data)

        assert status.node_id == "node456"
        assert status.connected is False

    def test_parse_missing_connectivity(self) -> None:
        """Test parsing with missing connectivity key."""
        data = {}

        status = parse_device_status("node789", data)

        assert status.connected is False  # Defaults to False

    def test_parse_missing_connected(self) -> None:
        """Test parsing with missing connected key."""
        data = {"connectivity": {}}

        status = parse_device_status("node000", data)

        assert status.connected is False  # Defaults to False


class TestParseDeviceInfo:
    """Tests for parse_device_info function."""

    def test_parse_complete_info(self) -> None:
        """Test parsing complete device info."""
        data = {
            "info": {
                "name": "Living Room Hub",
                "type": "thermacell-hub",
                "fw_version": "1.2.3",
            },
            "devices": [{"serial_num": "ABC123"}],
        }

        info = parse_device_info("node123", data)

        assert isinstance(info, DeviceInfo)
        assert info.node_id == "node123"
        assert info.name == "Living Room Hub"
        assert info.model == "Thermacell LIV Hub"  # Converted from type
        assert info.firmware_version == "1.2.3"
        assert info.serial_number == "ABC123"

    def test_parse_non_hub_type(self) -> None:
        """Test parsing with non-thermacell-hub type."""
        data = {
            "info": {
                "name": "Custom Device",
                "type": "other-device",
                "fw_version": "2.0.0",
            },
            "devices": [{"serial_num": "XYZ789"}],
        }

        info = parse_device_info("nodeXYZ", data)

        assert info.model == "other-device"  # Uses type directly

    def test_parse_missing_info(self) -> None:
        """Test parsing with missing info section."""
        data = {"devices": [{"serial_num": "123"}]}

        info = parse_device_info("node111", data)

        assert info.name == "node111"  # Uses node_id as name
        assert info.model == ""  # Empty string for missing type
        assert info.firmware_version == "unknown"
        assert info.serial_number == "123"

    def test_parse_missing_devices(self) -> None:
        """Test parsing with missing devices section."""
        data = {"info": {"name": "Hub"}}

        info = parse_device_info("node222", data)

        assert info.serial_number == "unknown"

    def test_parse_empty_devices_list(self) -> None:
        """Test parsing with empty devices list."""
        data = {"info": {"name": "Hub"}, "devices": []}

        info = parse_device_info("node333", data)

        assert info.serial_number == "unknown"

    def test_parse_name_from_params(self) -> None:
        """Test that user-friendly name comes from params, not config.

        User-assigned names like "Pool" or "ADU" are stored in the params
        endpoint under "LIV Hub" -> "Name", while config only has the generic
        device type name "Thermacell LIV Hub".
        """
        config_data = {
            "info": {
                "name": "Thermacell LIV Hub",  # Generic device type name
                "type": "thermacell-hub",
                "fw_version": "1.0.0",
            },
            "devices": [{"serial_num": "ABC123"}],
        }
        params_data = {
            "LIV Hub": {
                "Name": "Pool",  # User-friendly name
                "Enable Repellers": True,
            }
        }

        info = parse_device_info("node123", config_data, params_data)

        assert info.name == "Pool"  # Should use params name, not config name
        assert info.node_id == "node123"
        assert info.model == "Thermacell LIV Hub"

    def test_parse_name_fallback_to_config_when_no_params_name(self) -> None:
        """Test fallback to config name when params has no Name field."""
        config_data = {
            "info": {
                "name": "My Custom Hub",
                "type": "thermacell-hub",
                "fw_version": "1.0.0",
            },
            "devices": [{"serial_num": "ABC123"}],
        }
        params_data = {
            "LIV Hub": {
                "Enable Repellers": True,
                # No "Name" field
            }
        }

        info = parse_device_info("node456", config_data, params_data)

        assert info.name == "My Custom Hub"  # Falls back to config name

    def test_parse_name_fallback_to_node_id(self) -> None:
        """Test fallback to node_id when neither params nor config has name."""
        config_data = {
            "info": {
                "type": "thermacell-hub",
                "fw_version": "1.0.0",
            },
            "devices": [{"serial_num": "ABC123"}],
        }
        params_data = {
            "LIV Hub": {
                "Enable Repellers": True,
            }
        }

        info = parse_device_info("node789", config_data, params_data)

        assert info.name == "node789"  # Falls back to node_id


class TestParseDeviceState:
    """Tests for parse_device_state function."""

    def test_parse_complete_state(self) -> None:
        """Test parsing complete device state from all endpoints."""
        params_data = {
            "LIV Hub": {
                "Name": "Backyard",  # User-friendly name from params
                "Enable Repellers": True,
                "LED Brightness": 100,
            }
        }
        status_data = {"connectivity": {"connected": True}}
        config_data = {
            "info": {
                "name": "Thermacell LIV Hub",  # Generic name from config
                "type": "thermacell-hub",
                "fw_version": "1.0.0",
            },
            "devices": [{"serial_num": "SN123"}],
        }

        state = parse_device_state("node_abc", params_data, status_data, config_data)

        assert isinstance(state, DeviceState)
        assert state.info.node_id == "node_abc"
        assert state.info.name == "Backyard"  # Uses params Name, not config name
        assert state.status.connected is True
        assert state.params.enable_repellers is True
        assert state.params.led_brightness == 100
        assert state.raw_data["params"] == params_data
        assert state.raw_data["status"] == status_data
        assert state.raw_data["config"] == config_data

    def test_state_computed_properties(self) -> None:
        """Test computed properties on DeviceState."""
        params_data = {
            "LIV Hub": {
                "Enable Repellers": True,
                "Error": 5,
            }
        }
        status_data = {"connectivity": {"connected": True}}
        config_data = {"info": {"name": "Hub"}, "devices": []}

        state = parse_device_state("node123", params_data, status_data, config_data)

        assert state.is_online is True
        assert state.is_powered_on is True
        assert state.has_error is True

    def test_state_offline_device(self) -> None:
        """Test state for offline device."""
        params_data = {"LIV Hub": {"Enable Repellers": False}}
        status_data = {"connectivity": {"connected": False}}
        config_data = {"info": {"name": "Hub"}, "devices": []}

        state = parse_device_state("node_off", params_data, status_data, config_data)

        assert state.is_online is False
        assert state.is_powered_on is False
        assert state.has_error is False
