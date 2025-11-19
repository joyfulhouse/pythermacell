"""Custom exceptions for pythermacell library."""

from __future__ import annotations

from typing import Any


class ThermacellError(Exception):
    """Base exception for all Thermacell errors."""


class AuthenticationError(ThermacellError):
    """Exception raised for authentication failures."""


class ThermacellConnectionError(ThermacellError):
    """Exception raised for connection failures."""


class ThermacellTimeoutError(ThermacellError):
    """Exception raised when API requests timeout."""


class RateLimitError(ThermacellError):
    """Exception raised when API rate limit is exceeded.

    Attributes:
        retry_after: Optional number of seconds to wait before retrying.
    """

    def __init__(self, message: str = "", retry_after: int | None = None) -> None:
        """Initialize RateLimitError.

        Args:
            message: Error message.
            retry_after: Optional number of seconds to wait before retrying.
        """
        super().__init__(message)
        self.retry_after = retry_after


class DeviceError(ThermacellError):
    """Exception raised for device-related errors.

    Attributes:
        device_id: Optional device ID associated with the error.
    """

    def __init__(self, message: str = "", device_id: str | None = None) -> None:
        """Initialize DeviceError.

        Args:
            message: Error message.
            device_id: Optional device ID associated with the error.
        """
        super().__init__(message)
        self.device_id = device_id


class InvalidParameterError(ThermacellError):
    """Exception raised for invalid parameter values.

    Attributes:
        parameter_name: Optional name of the invalid parameter.
        value: Optional value that was invalid.
    """

    def __init__(
        self,
        message: str = "",
        parameter_name: str | None = None,
        value: Any = None,
    ) -> None:
        """Initialize InvalidParameterError.

        Args:
            message: Error message.
            parameter_name: Optional name of the invalid parameter.
            value: Optional value that was invalid.
        """
        super().__init__(message)
        self.parameter_name = parameter_name
        self.value = value
