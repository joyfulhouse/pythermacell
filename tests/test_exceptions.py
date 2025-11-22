"""Tests for pythermacell exceptions."""

from __future__ import annotations

from pythermacell.exceptions import (
    AuthenticationError,
    DeviceError,
    InvalidParameterError,
    RateLimitError,
    ThermacellConnectionError,
    ThermacellError,
    ThermacellTimeoutError,
)


class TestThermacellError:
    """Test ThermacellError base exception."""

    def test_base_exception_inherits_from_exception(self) -> None:
        """Test that ThermacellError inherits from Exception."""
        assert issubclass(ThermacellError, Exception)

    def test_base_exception_message(self) -> None:
        """Test that ThermacellError can be created with a message."""
        error = ThermacellError("Test error message")
        assert str(error) == "Test error message"

    def test_base_exception_empty_message(self) -> None:
        """Test that ThermacellError can be created without a message."""
        error = ThermacellError()
        assert isinstance(error, ThermacellError)


class TestAuthenticationError:
    """Test AuthenticationError exception."""

    def test_inherits_from_base_error(self) -> None:
        """Test that AuthenticationError inherits from ThermacellError."""
        assert issubclass(AuthenticationError, ThermacellError)

    def test_error_message(self) -> None:
        """Test AuthenticationError with a message."""
        error = AuthenticationError("Invalid credentials")
        assert str(error) == "Invalid credentials"


class TestConnectionError:
    """Test ConnectionError exception."""

    def test_inherits_from_base_error(self) -> None:
        """Test that ConnectionError inherits from ThermacellError."""
        assert issubclass(ThermacellConnectionError, ThermacellError)

    def test_error_message(self) -> None:
        """Test ConnectionError with a message."""
        error = ConnectionError("Failed to connect")
        assert str(error) == "Failed to connect"


class TestTimeoutError:
    """Test TimeoutError exception."""

    def test_inherits_from_base_error(self) -> None:
        """Test that TimeoutError inherits from ThermacellError."""
        assert issubclass(ThermacellTimeoutError, ThermacellError)

    def test_error_message(self) -> None:
        """Test TimeoutError with a message."""
        error = TimeoutError("Request timed out")
        assert str(error) == "Request timed out"


class TestRateLimitError:
    """Test RateLimitError exception."""

    def test_inherits_from_base_error(self) -> None:
        """Test that RateLimitError inherits from ThermacellError."""
        assert issubclass(RateLimitError, ThermacellError)

    def test_error_message(self) -> None:
        """Test RateLimitError with a message."""
        error = RateLimitError("Too many requests")
        assert str(error) == "Too many requests"

    def test_with_retry_after(self) -> None:
        """Test RateLimitError with retry_after attribute."""
        error = RateLimitError("Too many requests", retry_after=60)
        assert str(error) == "Too many requests"
        assert error.retry_after == 60

    def test_without_retry_after(self) -> None:
        """Test RateLimitError without retry_after attribute."""
        error = RateLimitError("Too many requests")
        assert error.retry_after is None


class TestDeviceError:
    """Test DeviceError exception."""

    def test_inherits_from_base_error(self) -> None:
        """Test that DeviceError inherits from ThermacellError."""
        assert issubclass(DeviceError, ThermacellError)

    def test_error_message(self) -> None:
        """Test DeviceError with a message."""
        error = DeviceError("Device not found")
        assert str(error) == "Device not found"

    def test_with_device_id(self) -> None:
        """Test DeviceError with device_id attribute."""
        error = DeviceError("Device offline", device_id="node123")
        assert str(error) == "Device offline"
        assert error.device_id == "node123"

    def test_without_device_id(self) -> None:
        """Test DeviceError without device_id attribute."""
        error = DeviceError("Device error")
        assert error.device_id is None


class TestInvalidParameterError:
    """Test InvalidParameterError exception."""

    def test_inherits_from_base_error(self) -> None:
        """Test that InvalidParameterError inherits from ThermacellError."""
        assert issubclass(InvalidParameterError, ThermacellError)

    def test_error_message(self) -> None:
        """Test InvalidParameterError with a message."""
        error = InvalidParameterError("Invalid parameter value")
        assert str(error) == "Invalid parameter value"

    def test_with_parameter_name(self) -> None:
        """Test InvalidParameterError with parameter_name attribute."""
        error = InvalidParameterError("Invalid hue value", parameter_name="LED Hue")
        assert str(error) == "Invalid hue value"
        assert error.parameter_name == "LED Hue"

    def test_without_parameter_name(self) -> None:
        """Test InvalidParameterError without parameter_name attribute."""
        error = InvalidParameterError("Invalid parameter")
        assert error.parameter_name is None

    def test_with_value(self) -> None:
        """Test InvalidParameterError with value attribute."""
        error = InvalidParameterError("Invalid value", parameter_name="LED Hue", value=400)
        assert error.parameter_name == "LED Hue"
        assert error.value == 400

    def test_without_value(self) -> None:
        """Test InvalidParameterError without value attribute."""
        error = InvalidParameterError("Invalid parameter")
        assert error.value is None
