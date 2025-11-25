"""Constants for pythermacell library."""

from __future__ import annotations


# API Configuration
DEFAULT_BASE_URL = "https://api.iot.thermacell.com"
DEFAULT_TIMEOUT = 30  # seconds
DEFAULT_AUTH_LIFETIME_SECONDS = 14400  # 4 hours - extended for fewer reauthentications

# Device Types
DEVICE_TYPE_LIV_HUB = "LIV Hub"

# Parameter Validation
LED_BRIGHTNESS_MIN = 0
LED_BRIGHTNESS_MAX = 100
LED_HUE_MIN = 0
LED_HUE_MAX = 360
LED_SATURATION_MIN = 0
LED_SATURATION_MAX = 100

# JWT Token Constants
JWT_PARTS_COUNT = 3
BASE64_PADDING_MODULO = 4

# Request Queue Configuration
DEFAULT_MIN_REQUEST_INTERVAL = 0.5  # 500ms minimum between API calls
DEFAULT_COMMAND_TIMEOUT = 10.0  # Max time to wait for queued command
DEFAULT_MAX_QUEUE_SIZE = 10  # Maximum pending commands
