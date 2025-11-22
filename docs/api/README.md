# API Documentation

Thermacell IoT API specification and documentation based on ESP RainMaker platform.

---

## Documents

| Document | Description | Status |
|----------|-------------|--------|
| [LED_CONTROL.md](LED_CONTROL.md) | ⚠️ **LED control - CRITICAL: Saturation causes crashes** | ✅ Complete |
| [GROUPS_API.md](GROUPS_API.md) | Device grouping functionality | ✅ Complete |
| [OTA_UPDATE_ENDPOINTS.md](OTA_UPDATE_ENDPOINTS.md) | Over-the-air firmware update endpoints | 📋 Research |
| [openapi.yaml](openapi.yaml) | Complete OpenAPI 3.0 specification | ✅ Validated |

---

## API Overview

**Base URL**: `https://api.iot.thermacell.com`
**Version**: v1
**Authentication**: JWT Bearer token
**Format**: JSON

### Core Endpoints (6 total)

1. **POST `/v1/login2`** - Authenticate and get JWT tokens
2. **GET `/v1/user/nodes`** - List all user devices
3. **GET `/v1/user/nodes/status`** - Get device connectivity status
4. **GET `/v1/user/nodes/config`** - Get device configuration
5. **GET `/v1/user/nodes/params`** - Get device parameters
6. **PUT `/v1/user/nodes/params`** - Update device parameters

See [openapi.yaml](openapi.yaml) for complete specification.

---

## Quick Reference

### Authentication
```bash
curl -X POST "https://api.iot.thermacell.com/v1/login2" \
  -H "Content-Type: application/json" \
  -d '{
    "user_name": "user@example.com",
    "password": "password"
  }'
```

**Response**:
```json
{
  "status": "success",
  "accesstoken": "eyJhbG...",
  "idtoken": "eyJhbG...",
  "refreshtoken": "..."
}
```

### Device Discovery
```bash
curl -X GET "https://api.iot.thermacell.com/v1/user/nodes" \
  -H "Authorization: YOUR_ACCESS_TOKEN"
```

### Device Control (LED Color)

⚠️ **IMPORTANT**: Do NOT send LED Saturation parameter - it causes device crashes! See [LED_CONTROL.md](LED_CONTROL.md) for details.

```bash
# CORRECT - Only hue and brightness
curl -X PUT "https://api.iot.thermacell.com/v1/user/nodes/params?node_id=NODE_ID" \
  -H "Authorization: YOUR_ACCESS_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "LIV Hub": {
      "LED Hue": 240,
      "LED Brightness": 80
    }
  }'
```

---

## Device Parameters

### Control Parameters (Read/Write)

| Parameter | Type | Range | Description | Notes |
|-----------|------|-------|-------------|-------|
| `Enable Repellers` | boolean | true/false | Turn device on/off | Use this, not "Power" |
| `LED Brightness` | integer | 0-100 | LED brightness percentage | 0=off, 100=max |
| `LED Hue` | integer | 0-360 | LED color (HSV hue) | 0=red, 120=green, 240=blue |
| ~~`LED Saturation`~~ | ~~integer~~ | ~~0-100~~ | ~~LED color saturation~~ | ⚠️ **DO NOT USE - CAUSES CRASHES** |
| `Refill Reset` | integer | 0/1/2 | Reset refill counter | 0=40hr, 1=100hr, 2=180hr |

### Status Parameters (Read-Only)

| Parameter | Type | Description |
|-----------|------|-------------|
| `Power` | boolean | Device power status indicator (read-only) |
| `LED Power` | boolean | LED power status (derived from brightness) |
| `System Runtime` | integer | Current session runtime (minutes) |
| `System Status` | integer | 1=Off, 2=Warming, 3=Protected |
| `Error` | integer | Error code (0=no error) |
| `Refill Life` | float | Remaining cartridge life (0-100%) |

---

## Critical Implementation Notes

### ⚠️ LED Saturation Parameter

**DO NOT send `LED Saturation` parameter** - This causes device crashes and requires manual restart!

See [LED_CONTROL.md](LED_CONTROL.md) for comprehensive details based on:
- Android APK analysis
- Home Assistant reference implementation
- Live device testing

### Parameter Naming
- **Control parameter**: `"Enable Repellers"` (read/write)
- **Status parameter**: `"Power"` (read-only)
- Control device using `"Enable Repellers"`, not `"Power"`

### LED State Logic
LED is only "on" when:
1. Device is powered (`Enable Repellers: true`)
2. AND brightness > 0

### Color Space
- Uses HSV, not RGB
- Hue: 0-360 degrees (0=red, 120=green, 240=blue)
- Brightness: 0-100% (NOT saturation-based)
- Saturation: Always assumed to be 100% (full saturation)

### System Status Codes
- `1` - Off
- `2` - Warming Up (~2 minutes)
- `3` - Protected (fully operational)

---

## Using the OpenAPI Specification

### View in Swagger UI
```bash
docker run -p 8080:8080 \
  -e SWAGGER_JSON=/spec/openapi.yaml \
  -v $(pwd)/docs/api:/spec \
  swaggerapi/swagger-ui

# Open http://localhost:8080
```

### Validate Specification
```bash
pip install openapi-spec-validator pyyaml

python3 << 'EOF'
from openapi_spec_validator import validate_spec
from openapi_spec_validator.readers import read_from_filename

spec_dict, spec_url = read_from_filename('docs/api/openapi.yaml')
validate_spec(spec_dict)
print("✅ OpenAPI specification is valid!")
EOF
```

### Generate Client Code
```bash
# Python client
openapi-generator-cli generate \
  -i docs/api/openapi.yaml \
  -g python \
  -o client/python

# TypeScript client
openapi-generator-cli generate \
  -i docs/api/openapi.yaml \
  -g typescript-axios \
  -o client/typescript
```

---

## Error Codes

| Code | Description |
|------|-------------|
| 100002 | API Version is not supported |
| 100006 | Invalid request body |
| 100009 | Node Id is missing |
| 100010 | Node does not belong to user |
| 101002 | Email-id is not in correct format |
| 101009 | Incorrect user name or password |
| 101015 | Account is not verified |
| 102002 | Updating node parameter failed |
| 102003 | Getting node status failed |
| 103020 | Node does not belong to user |

---

## Research Sources

### ESP RainMaker API
- **Official Spec**: https://swaggerapis.rainmaker.espressif.com/
- **Version**: 3.5.0-019431b28
- **License**: Apache 2.0

### Thermacell APK Analysis
- **Location**: `../../research/com.thermacell.liv/`
- **Files**: 14,381 smali files analyzed
- **Version**: 1.5.0+
- **Key Finding**: LED color picker only sends HUE, never saturation

### Production Integration
- **Location**: `../../research/thermacell_liv/`
- **Status**: v1.0.0, production-ready
- **Validation**: Real API integration tests
- **Finding**: Never sends saturation parameter, hardcodes to 100%

---

## Related Documentation

- [LED_CONTROL.md](LED_CONTROL.md) - ⚠️ **Critical LED implementation details**
- [GROUPS_API.md](GROUPS_API.md) - Device grouping functionality
- [../architecture/AUTHENTICATION.md](../architecture/AUTHENTICATION.md) - Authentication flow
- [../testing/TESTING.md](../testing/TESTING.md) - API testing guide
- [../development/DEVICE_POWER_FIX.md](../development/DEVICE_POWER_FIX.md) - Device control implementation
