"""Comprehensive tests for serializers module."""

from __future__ import annotations

from pythermacell.models import DeviceInfo, DeviceParams, DeviceState, DeviceStatus
from pythermacell.serializers import (
    deserialize_device_info,
    deserialize_device_params,
    deserialize_device_state,
    deserialize_device_status,
    serialize_param_update,
)


class TestDeserializeDeviceParams:
    """Test deserialize_device_params function."""

    def test_deserialize_full_params(self) -> None:
        """Test deserializing complete parameter set."""
        data = {
            "LIV Hub": {
                "Power": True,
                "LED Power": True,
                "LED Brightness": 80,
                "LED Hue": 120,
                "LED Saturation": 100,
                "Refill Life": 75.5,
                "System Runtime": 120,
                "System Status": 3,
                "Error": 0,
                "Enable Repellers": True,
            }
        }

        params = deserialize_device_params(data)

        assert isinstance(params, DeviceParams)
        assert params.power is True
        assert params.led_power is True
        assert params.led_brightness == 80
        assert params.led_hue == 120
        assert params.led_saturation == 100
        assert params.refill_life == 75.5
        assert params.system_runtime == 120
        assert params.system_status == 3
        assert params.error == 0
        assert params.enable_repellers is True

    def test_deserialize_params_powered_off(self) -> None:
        """Test deserializing params when device is off."""
        data = {
            "LIV Hub": {
                "Enable Repellers": False,
                "LED Brightness": 50,  # Non-zero brightness but device off
                "LED Hue": 180,
            }
        }

        params = deserialize_device_params(data)

        # Device is off
        assert params.power is False
        assert params.enable_repellers is False
        # LED should be off even with brightness > 0 because device is off
        assert params.led_power is False
        assert params.led_brightness == 50  # Brightness value preserved
        assert params.led_hue == 180

    def test_deserialize_params_led_off_zero_brightness(self) -> None:
        """Test LED is off when brightness is 0 even if device is on."""
        data = {
            "LIV Hub": {
                "Enable Repellers": True,  # Device is on
                "LED Brightness": 0,  # But LED brightness is 0
            }
        }

        params = deserialize_device_params(data)

        assert params.power is True
        assert params.enable_repellers is True
        # LED should be off because brightness is 0
        assert params.led_power is False
        assert params.led_brightness == 0

    def test_deserialize_params_led_on_conditions(self) -> None:
        """Test LED is only on when BOTH device powered AND brightness > 0."""
        data = {
            "LIV Hub": {
                "Enable Repellers": True,
                "LED Brightness": 50,
            }
        }

        params = deserialize_device_params(data)

        # Both conditions met
        assert params.power is True
        assert params.led_brightness == 50
        assert params.led_power is True

    def test_deserialize_params_empty_data(self) -> None:
        """Test deserializing empty data returns all None values."""
        data = {}

        params = deserialize_device_params(data)

        assert params.power is None
        assert params.led_power is None
        assert params.led_brightness == 0  # Default from get()
        assert params.led_hue is None
        assert params.led_saturation is None
        assert params.refill_life is None
        assert params.system_runtime is None
        assert params.system_status is None
        assert params.error is None
        assert params.enable_repellers is None

    def test_deserialize_params_partial_data(self) -> None:
        """Test deserializing partial parameter set."""
        data = {
            "LIV Hub": {
                "Enable Repellers": True,
                "Refill Life": 50.0,
                "System Runtime": 300,
            }
        }

        params = deserialize_device_params(data)

        assert params.power is True
        assert params.enable_repellers is True
        assert params.refill_life == 50.0
        assert params.system_runtime == 300
        # Missing fields are None
        assert params.led_hue is None
        assert params.led_saturation is None
        assert params.error is None

    def test_deserialize_params_enable_repellers_none(self) -> None:
        """Test handling None for enable_repellers."""
        data = {
            "LIV Hub": {
                "LED Brightness": 80,
            }
        }

        params = deserialize_device_params(data)

        assert params.power is None
        assert params.enable_repellers is None
        # LED power should be None when enable_repellers is None
        assert params.led_power is None
        assert params.led_brightness == 80


class TestDeserializeDeviceStatus:
    """Test deserialize_device_status function."""

    def test_deserialize_status_connected(self) -> None:
        """Test deserializing connected status."""
        data = {"connectivity": {"connected": True}}

        status = deserialize_device_status("node123", data)

        assert isinstance(status, DeviceStatus)
        assert status.node_id == "node123"
        assert status.connected is True

    def test_deserialize_status_disconnected(self) -> None:
        """Test deserializing disconnected status."""
        data = {"connectivity": {"connected": False}}

        status = deserialize_device_status("node456", data)

        assert status.node_id == "node456"
        assert status.connected is False

    def test_deserialize_status_empty_data(self) -> None:
        """Test deserializing empty data defaults to disconnected."""
        data = {}

        status = deserialize_device_status("node789", data)

        assert status.node_id == "node789"
        assert status.connected is False  # Default

    def test_deserialize_status_missing_connected_field(self) -> None:
        """Test deserializing when connected field is missing."""
        data = {"connectivity": {}}

        status = deserialize_device_status("node999", data)

        assert status.node_id == "node999"
        assert status.connected is False  # Default


class TestDeserializeDeviceInfo:
    """Test deserialize_device_info function."""

    def test_deserialize_info_thermacell_hub(self) -> None:
        """Test deserializing Thermacell LIV Hub info."""
        data = {
            "info": {
                "name": "Living Room",
                "type": "thermacell-hub",
                "fw_version": "5.3.2",
            },
            "devices": [{"serial_num": "SN123456"}],
        }

        info = deserialize_device_info("node123", data)

        assert isinstance(info, DeviceInfo)
        assert info.node_id == "node123"
        assert info.name == "Living Room"
        assert info.model == "Thermacell LIV Hub"  # Friendly name
        assert info.firmware_version == "5.3.2"
        assert info.serial_number == "SN123456"

    def test_deserialize_info_unknown_type(self) -> None:
        """Test deserializing unknown device type."""
        data = {
            "info": {
                "name": "Unknown Device",
                "type": "unknown-type",
                "fw_version": "1.0.0",
            },
            "devices": [{"serial_num": "SN999999"}],
        }

        info = deserialize_device_info("node999", data)

        # Unknown type is used as-is (not converted)
        assert info.model == "unknown-type"
        assert info.name == "Unknown Device"
        assert info.firmware_version == "1.0.0"
        assert info.serial_number == "SN999999"

    def test_deserialize_info_empty_data(self) -> None:
        """Test deserializing empty data uses defaults."""
        data = {}

        info = deserialize_device_info("node456", data)

        assert info.node_id == "node456"
        assert info.name == "node456"  # Defaults to node_id
        assert info.model == ""  # Empty type
        assert info.firmware_version == "unknown"
        assert info.serial_number == "unknown"

    def test_deserialize_info_missing_optional_fields(self) -> None:
        """Test deserializing when optional fields are missing."""
        data = {
            "info": {
                "name": "Test Device",
            },
            "devices": [],
        }

        info = deserialize_device_info("node789", data)

        assert info.name == "Test Device"
        # Missing fields use defaults
        assert info.model == ""
        assert info.firmware_version == "unknown"
        assert info.serial_number == "unknown"

    def test_deserialize_info_no_devices_array(self) -> None:
        """Test deserializing when devices array is missing."""
        data = {
            "info": {
                "name": "Test Device",
                "type": "thermacell-hub",
                "fw_version": "5.3.2",
            }
        }

        info = deserialize_device_info("node111", data)

        assert info.name == "Test Device"
        assert info.model == "Thermacell LIV Hub"
        assert info.firmware_version == "5.3.2"
        assert info.serial_number == "unknown"  # No devices array


class TestDeserializeDeviceState:
    """Test deserialize_device_state function."""

    def test_deserialize_complete_state(self) -> None:
        """Test deserializing complete device state from all three endpoints."""
        params_data = {
            "LIV Hub": {
                "Enable Repellers": True,
                "LED Brightness": 80,
                "LED Hue": 120,
                "Refill Life": 75.5,
                "System Runtime": 120,
            }
        }
        status_data = {"connectivity": {"connected": True}}
        config_data = {
            "info": {
                "name": "Test Device",
                "type": "thermacell-hub",
                "fw_version": "5.3.2",
            },
            "devices": [{"serial_num": "SN123456"}],
        }

        state = deserialize_device_state(
            node_id="node123",
            params_data=params_data,
            status_data=status_data,
            config_data=config_data,
        )

        assert isinstance(state, DeviceState)
        # Check info
        assert state.info.node_id == "node123"
        assert state.info.name == "Test Device"
        assert state.info.model == "Thermacell LIV Hub"
        assert state.info.firmware_version == "5.3.2"
        assert state.info.serial_number == "SN123456"
        # Check status
        assert state.status.node_id == "node123"
        assert state.status.connected is True
        # Check params
        assert state.params.power is True
        assert state.params.led_brightness == 80
        assert state.params.led_hue == 120
        assert state.params.refill_life == 75.5
        assert state.params.system_runtime == 120
        # Check raw_data
        assert state.raw_data["params"] == params_data
        assert state.raw_data["status"] == status_data
        assert state.raw_data["config"] == config_data

    def test_deserialize_state_offline_device(self) -> None:
        """Test deserializing state for offline device."""
        params_data = {
            "LIV Hub": {
                "Enable Repellers": False,
                "LED Brightness": 0,
                "Refill Life": 50.0,
            }
        }
        status_data = {"connectivity": {"connected": False}}
        config_data = {
            "info": {
                "name": "Offline Device",
                "type": "thermacell-hub",
            }
        }

        state = deserialize_device_state(
            node_id="node999",
            params_data=params_data,
            status_data=status_data,
            config_data=config_data,
        )

        # Device is offline
        assert state.status.connected is False
        assert state.is_online is False
        # Device is off
        assert state.params.power is False
        assert state.params.led_power is False

    def test_deserialize_state_empty_data(self) -> None:
        """Test deserializing state with empty data."""
        state = deserialize_device_state(
            node_id="node456",
            params_data={},
            status_data={},
            config_data={},
        )

        # Check defaults
        assert state.info.node_id == "node456"
        assert state.info.name == "node456"
        assert state.status.connected is False
        assert state.params.power is None
        assert state.raw_data["params"] == {}
        assert state.raw_data["status"] == {}
        assert state.raw_data["config"] == {}

    def test_deserialize_state_convenience_properties(self) -> None:
        """Test DeviceState convenience properties work correctly."""
        params_data = {
            "LIV Hub": {
                "Enable Repellers": True,
                "LED Brightness": 50,
                "LED Hue": 240,
            }
        }
        status_data = {"connectivity": {"connected": True}}
        config_data = {
            "info": {"name": "Test", "type": "thermacell-hub"}
        }

        state = deserialize_device_state(
            node_id="node111",
            params_data=params_data,
            status_data=status_data,
            config_data=config_data,
        )

        # Test convenience properties
        assert state.is_online is True
        assert state.is_powered_on is True
        # Test convenience properties for params
        assert state.led_brightness == 50
        assert state.led_hue == 240


class TestSerializeParamUpdate:
    """Test serialize_param_update function."""

    def test_serialize_param_update_passthrough(self) -> None:
        """Test serialize_param_update is currently pass-through."""
        params = {
            "LIV Hub": {
                "Enable Repellers": True,
                "LED Brightness": 80,
            }
        }

        result = serialize_param_update(params)

        # Currently a pass-through - returns same data
        assert result == params
        # Since it's pass-through now, it IS the same object
        assert result is params

    def test_serialize_param_update_power_control(self) -> None:
        """Test serializing power control parameters."""
        params = {
            "LIV Hub": {
                "Enable Repellers": False,
            }
        }

        result = serialize_param_update(params)

        assert result["LIV Hub"]["Enable Repellers"] is False

    def test_serialize_param_update_led_control(self) -> None:
        """Test serializing LED control parameters."""
        params = {
            "LIV Hub": {
                "LED Brightness": 100,
                "LED Hue": 180,
            }
        }

        result = serialize_param_update(params)

        assert result["LIV Hub"]["LED Brightness"] == 100
        assert result["LIV Hub"]["LED Hue"] == 180

    def test_serialize_param_update_multiple_params(self) -> None:
        """Test serializing multiple parameters."""
        params = {
            "LIV Hub": {
                "Enable Repellers": True,
                "LED Brightness": 50,
                "LED Hue": 120,
            }
        }

        result = serialize_param_update(params)

        assert len(result["LIV Hub"]) == 3
        assert result["LIV Hub"]["Enable Repellers"] is True
        assert result["LIV Hub"]["LED Brightness"] == 50
        assert result["LIV Hub"]["LED Hue"] == 120


class TestLEDStateBehavior:
    """Test LED state calculation logic across different scenarios."""

    def test_led_on_requires_both_conditions(self) -> None:
        """Test LED is only on when device powered AND brightness > 0."""
        # Case 1: Device ON, brightness > 0 → LED ON
        data1 = {"LIV Hub": {"Enable Repellers": True, "LED Brightness": 50}}
        params1 = deserialize_device_params(data1)
        assert params1.led_power is True

        # Case 2: Device ON, brightness = 0 → LED OFF
        data2 = {"LIV Hub": {"Enable Repellers": True, "LED Brightness": 0}}
        params2 = deserialize_device_params(data2)
        assert params2.led_power is False

        # Case 3: Device OFF, brightness > 0 → LED OFF
        data3 = {"LIV Hub": {"Enable Repellers": False, "LED Brightness": 50}}
        params3 = deserialize_device_params(data3)
        assert params3.led_power is False

        # Case 4: Device OFF, brightness = 0 → LED OFF
        data4 = {"LIV Hub": {"Enable Repellers": False, "LED Brightness": 0}}
        params4 = deserialize_device_params(data4)
        assert params4.led_power is False

    def test_led_power_matches_physical_behavior(self) -> None:
        """Test LED power state matches physical device behavior."""
        # Physical device: LED cannot be on when device is off
        data = {
            "LIV Hub": {
                "Enable Repellers": False,
                "LED Brightness": 100,  # Full brightness setting
            }
        }

        params = deserialize_device_params(data)

        # LED must be off because device is off (physical constraint)
        assert params.led_power is False
        # But brightness value is preserved for when device turns on
        assert params.led_brightness == 100

    def test_led_power_none_when_enable_repellers_none(self) -> None:
        """Test LED power is None when enable_repellers is None."""
        data = {"LIV Hub": {"LED Brightness": 50}}

        params = deserialize_device_params(data)

        # Cannot determine LED state without knowing device power state
        assert params.enable_repellers is None
        assert params.led_power is None
        assert params.led_brightness == 50


class TestDeviceStateConvenienceProperties:
    """Test DeviceState convenience properties comprehensively."""

    def test_all_convenience_properties(self) -> None:
        """Test all convenience properties return correct values."""
        params_data = {
            "LIV Hub": {
                "Enable Repellers": True,
                "LED Brightness": 75,
                "LED Hue": 200,
                "LED Saturation": 90,
                "Refill Life": 85.0,
                "System Runtime": 300,
                "System Status": 3,
                "Error": 0,
            }
        }
        status_data = {"connectivity": {"connected": True}}
        config_data = {
            "info": {
                "name": "Test Device",
                "type": "thermacell-hub",
                "fw_version": "5.3.2",
            },
            "devices": [{"serial_num": "SN123456"}],
        }

        state = deserialize_device_state(
            node_id="TEST001",
            params_data=params_data,
            status_data=status_data,
            config_data=config_data,
        )

        # Test all convenience properties
        # From DeviceInfo
        assert state.node_id == "TEST001"
        assert state.name == "Test Device"
        assert state.model == "Thermacell LIV Hub"
        assert state.firmware_version == "5.3.2"
        assert state.serial_number == "SN123456"

        # From DeviceStatus
        assert state.is_online is True

        # From DeviceParams
        assert state.is_powered_on is True
        assert state.power is True
        assert state.led_power is True
        assert state.led_brightness == 75
        assert state.led_hue == 200
        assert state.led_saturation == 90
        assert state.refill_life == 85.0
        assert state.runtime_minutes == 300
        assert state.system_status == 3
        assert state.error_code == 0
        assert state.has_error is False


class TestIntegrationScenarios:
    """Test real-world integration scenarios."""

    def test_device_discovery_flow(self) -> None:
        """Test complete device discovery flow."""
        # Simulates fetching all three endpoints for a device
        params_data = {
            "LIV Hub": {
                "Enable Repellers": True,
                "LED Brightness": 75,
                "LED Hue": 200,
                "Refill Life": 85.0,
                "System Runtime": 300,
                "System Status": 3,
                "Error": 0,
            }
        }
        status_data = {"connectivity": {"connected": True}}
        config_data = {
            "info": {
                "name": "Patio Repeller",
                "type": "thermacell-hub",
                "fw_version": "5.3.2",
            },
            "devices": [{"serial_num": "SN987654"}],
        }

        state = deserialize_device_state(
            node_id="PATIO001",
            params_data=params_data,
            status_data=status_data,
            config_data=config_data,
        )

        # Verify complete state using convenience properties
        assert state.node_id == "PATIO001"
        assert state.name == "Patio Repeller"
        assert state.is_online is True
        assert state.is_powered_on is True
        # Test info convenience properties
        assert state.model == "Thermacell LIV Hub"
        assert state.firmware_version == "5.3.2"
        assert state.serial_number == "SN987654"
        # Test params convenience properties
        assert state.led_brightness == 75
        assert state.led_hue == 200
        assert state.refill_life == 85.0
        assert state.runtime_minutes == 300

    def test_offline_device_handling(self) -> None:
        """Test handling offline device state."""
        params_data = {
            "LIV Hub": {
                "Enable Repellers": False,
                "LED Brightness": 0,
                "Refill Life": 30.0,
            }
        }
        status_data = {"connectivity": {"connected": False}}
        config_data = {
            "info": {"name": "Garage Repeller", "type": "thermacell-hub"}
        }

        state = deserialize_device_state(
            node_id="GARAGE001",
            params_data=params_data,
            status_data=status_data,
            config_data=config_data,
        )

        # Offline device characteristics using convenience properties
        assert state.is_online is False
        assert state.is_powered_on is False
        assert state.led_brightness == 0
        assert state.refill_life == 30.0

    def test_low_refill_scenario(self) -> None:
        """Test device with low refill life."""
        params_data = {
            "LIV Hub": {
                "Enable Repellers": True,
                "Refill Life": 5.5,  # Low refill
                "System Status": 3,
            }
        }
        status_data = {"connectivity": {"connected": True}}
        config_data = {"info": {"name": "Test", "type": "thermacell-hub"}}

        state = deserialize_device_state(
            node_id="TEST001",
            params_data=params_data,
            status_data=status_data,
            config_data=config_data,
        )

        # Device operational but low refill using convenience properties
        assert state.is_online is True
        assert state.is_powered_on is True
        assert state.refill_life == 5.5  # Should trigger low refill warning
