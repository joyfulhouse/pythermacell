# LED Control API Documentation

## Overview

This document details the LED control implementation for Thermacell LIV devices based on comprehensive analysis of:
- Official Android application (decompiled APK)
- Home Assistant reference implementation
- Live API testing with physical devices

## Critical Findings

### ⚠️ LED Saturation Parameter NOT Supported

**IMPORTANT**: The `LED Saturation` parameter **MUST NOT** be sent to the API, despite appearing in the Android app UI as a slider. Sending this parameter causes device crashes and requires manual restart.

**Evidence**:
1. **Home Assistant Reference**: Never sends saturation parameter (verified in production code)
2. **Android APK Analysis**: Color picker only extracts and sends HUE value, not saturation
3. **Live Testing**: Sending saturation causes HTTP 400 errors and device crashes

## Supported LED Parameters

### 1. LED Hue

**API Parameter**: `"LED Hue"`

**Range**: 0-360 degrees (HSV color wheel)

**Type**: Integer

**Validation**:
```python
if not 0 <= hue <= 360:
    raise InvalidParameterError("LED hue must be 0-360")
```

**Evidence from APK**:
- File: `PaletteBar.smali`
- Constant: `0x43b40000` = 360.0f (maximum value)
- Lines: 555, 744, 790 - Hardcoded max limit

**Color Examples**:
- 0° = Red
- 60° = Yellow
- 120° = Green
- 180° = Cyan
- 240° = Blue
- 300° = Magenta
- 360° = Red (wraps around)

### 2. LED Brightness

**API Parameter**: `"LED Brightness"`

**Range**: 0-100 percent

**Type**: Integer

**Validation**:
```python
if not 0 <= brightness <= 100:
    raise InvalidParameterError("LED brightness must be 0-100")
```

**Evidence from APK**:
- File: `PaletteBar.smali`
- Constant: `0x42c80000` = 100.0f (maximum value)
- Lines: 551, 759, 807 - Hardcoded max limit

**Special Values**:
- 0 = LED off (equivalent to `set_led_power(False)`)
- 100 = Maximum brightness

### 3. LED Power

**API Parameter**: `"LED Brightness"` (controlled via brightness value)

**Note**: There is NO separate `"LED Power"` parameter. LED power is controlled by setting brightness to 0 (off) or restoring to a non-zero value (on).

**Implementation**:
```python
async def set_led_power(self, power_on: bool) -> bool:
    """Set LED power state."""
    brightness = 100 if power_on else 0
    params = {"LIV Hub": {"LED Brightness": brightness}}
    return await self._client.update_device_params(self.node_id, params)
```

## API Request Format

### Set LED Color (Hue + Brightness)

**Endpoint**: `PUT /v1/user/nodes/params?nodeid={node_id}`

**Request Body** (CORRECT):
```json
{
  "LIV Hub": {
    "LED Hue": 240,
    "LED Brightness": 75
  }
}
```

**Request Body** (INCORRECT - CAUSES CRASH):
```json
{
  "LIV Hub": {
    "LED Hue": 240,
    "LED Saturation": 100,  // ❌ DO NOT SEND - Causes device crash
    "LED Brightness": 75
  }
}
```

### Set LED Brightness Only

**Request Body**:
```json
{
  "LIV Hub": {
    "LED Brightness": 50
  }
}
```

### Turn LED Off

**Request Body**:
```json
{
  "LIV Hub": {
    "LED Brightness": 0
  }
}
```

### Turn LED On

**Request Body**:
```json
{
  "LIV Hub": {
    "LED Brightness": 100
  }
}
```

## Android App Implementation

### Color Picker Behavior

The Android app uses a circular color picker (`PaletteBar` widget) that:

1. **User selects color** from the color wheel
2. **RGB to HSV conversion** extracts hue, saturation, and value
3. **Only HUE is extracted** from the conversion (index 0 of HSV array)
4. **Saturation and value are discarded**
5. **Only hue parameter is sent** to the API

**Code Evidence** (`ParamAdapter.smali` lines 478-522):
```java
private void circularColorChange(HueViewHolder holder, Param param, int color, boolean moving) {
    float[] hsv = new float[3];
    Color.colorToHSV(color, hsv);

    float hueValue = hsv[0];  // Extract ONLY hue (0-360)
    int hueInt = (int)hueValue;

    // Send ONLY hue to API
    deviceParamUpdates.processSliderChange(param.getName(), hueInt);
}
```

### Saturation Slider (UI Only)

While the Android app shows a saturation slider in the UI:
- It exists as a generic slider control type (`esp.param.saturation`)
- **It is NOT connected to actual LED functionality**
- The slider likely doesn't affect the device (or causes issues if used)
- Home Assistant integration completely ignores this parameter

### Display Logic

When displaying the color picker, the app uses hardcoded saturation:

**Code Evidence** (`ParamAdapter.smali` lines 524-670):
```java
private void displayHueCircle(HueViewHolder holder, Param param) {
    int storedHue = (int)param.getValue();

    float[] hsv = new float[3];
    hsv[0] = storedHue;    // Hue from API
    hsv[1] = 10.0f;        // Saturation HARDCODED to 10% for display
    hsv[2] = 10.0f;        // Value HARDCODED to 10% for display

    int displayColor = Color.HSVToColor(hsv);
    colorPickerView.setColor(displayColor);
}
```

**This is UI-only** - the 10% saturation is only for rendering the color picker circle, not sent to the device.

## Home Assistant Reference Implementation

### Color Conversion

The HA integration converts RGB to HSV but **ignores saturation**:

**Code** (`api.py:183-192`):
```python
async def set_device_led_color(self, node_id: str, _device_name: str,
                               *, red: int, green: int, blue: int) -> bool:
    """Set device LED color."""
    # Convert RGB to HSV
    r_norm, g_norm, b_norm = red / 255.0, green / 255.0, blue / 255.0
    hue_val, _saturation, brightness_val = colorsys.rgb_to_hsv(r_norm, g_norm, b_norm)

    # Extract hue and brightness only
    hue = int(hue_val * 360)
    brightness = int(brightness_val * 100)

    # Send ONLY hue and brightness
    params = {"LIV Hub": {"LED Hue": hue, "LED Brightness": brightness}}
    return await self.set_node_params(node_id, params)
```

**Note**: `_saturation` has underscore prefix indicating it's intentionally ignored.

### HSV to RGB Conversion

When converting back for display, saturation is **hardcoded to 100%**:

**Code** (`coordinator.py:38-56`):
```python
def _convert_hsv_to_rgb(hue: int, brightness: int) -> RGBColor:
    """Convert HSV values to RGB color dictionary."""
    h_norm = hue / 360.0 if hue > 0 else 0
    s_norm = 1.0  # Assume full saturation (100%)
    v_norm = brightness / 100.0

    r, g, b = colorsys.hsv_to_rgb(h_norm, s_norm, v_norm)
    return RGBColor(
        red=int(r * 255),
        green=int(g * 255),
        blue=int(b * 255),
    )
```

## Implementation Guidelines

### ✅ Correct Implementation

```python
async def set_led_color(self, hue: int, brightness: int) -> bool:
    """Set LED color using hue and brightness.

    Note: Saturation is not supported by the Thermacell API and is always
    assumed to be 100% (full saturation). Sending saturation causes device crashes.

    Args:
        hue: Hue value (0-360).
        brightness: Brightness percentage (0-100).

    Returns:
        True if successful, False otherwise.

    Raises:
        InvalidParameterError: If any parameter is outside valid range.
    """
    # Validate hue
    if not 0 <= hue <= 360:
        raise InvalidParameterError(f"LED hue must be 0-360, got {hue}")

    # Validate brightness
    if not 0 <= brightness <= 100:
        raise InvalidParameterError(f"LED brightness must be 0-100, got {brightness}")

    # Only send hue and brightness - saturation is not supported
    params = {
        "LIV Hub": {
            "LED Hue": hue,
            "LED Brightness": brightness,
        }
    }
    return await self._client.update_device_params(self.node_id, params)
```

### ❌ Incorrect Implementation (Causes Crashes)

```python
# DO NOT DO THIS - Causes device crashes
async def set_led_color(self, hue: int, saturation: int, brightness: int) -> bool:
    params = {
        "LIV Hub": {
            "LED Hue": hue,
            "LED Saturation": saturation,  # ❌ Causes crash
            "LED Brightness": brightness,
        }
    }
    return await self._client.update_device_params(self.node_id, params)
```

## Device Requirements

### Power State Dependency

**IMPORTANT**: LED control commands only work when the device is powered on.

```python
# Ensure device is powered on first
if not device.is_powered_on:
    await device.turn_on()
    await asyncio.sleep(2)  # Wait for device to power up

# Now LED control will work
await device.set_led_color(hue=240, brightness=75)
```

### LED State Logic

The LED is considered "on" when:
1. Device (hub) is powered on AND
2. LED brightness > 0

```python
led_is_on = device.is_powered_on and device.led_brightness > 0
```

## Testing Notes

### Integration Test Results

After removing saturation parameter:
- ✅ Devices no longer crash
- ✅ LED color changes work reliably
- ✅ Multiple sequential color changes work
- ✅ No device reboots required

### Before Fix
- Sending saturation caused HTTP 400 errors
- Devices went offline (crashed)
- Required manual power cycle to recover

### After Fix
- All LED control tests pass
- Devices remain online during tests
- No crashes or unexpected behavior

## References

### Source Files
- **Implementation**: `src/pythermacell/devices.py:207-241`
- **Constants**: `src/pythermacell/const.py:15-18`
- **Tests**: `tests/integration/test_device_control_integration.py:239-305`

### Research Files
- **Android APK**: `research/com.thermacell.liv/smali/com/espressif/ui/adapters/ParamAdapter.smali`
- **HA Reference**: `research/thermacell_liv/custom_components/thermacell_liv/api.py`
- **Test Script**: `research/test_led_color_fix.py`

## Summary

| Parameter | Range | Supported | Notes |
|-----------|-------|-----------|-------|
| LED Hue | 0-360 | ✅ Yes | Color wheel degrees |
| LED Brightness | 0-100 | ✅ Yes | Percentage, 0=off |
| LED Saturation | 0-100 | ❌ **NO** | **Causes device crashes** |
| LED Power | N/A | ✅ Via brightness | Set brightness to 0/100 |

**Key Takeaway**: Only send `LED Hue` and `LED Brightness` parameters. Never send `LED Saturation` as it causes device crashes.
