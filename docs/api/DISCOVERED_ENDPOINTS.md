# Discovered API Endpoints from Android APK Analysis

**Date**: 2025-01-18
**Source**: Decompiled Thermacell LIV Android APK v1.5.0+
**Analysis Method**: Static analysis of smali bytecode in `research/com.thermacell.liv/`

## Summary

Comprehensive analysis of the Android APK revealed **54 total API endpoint variations**, with **47 new endpoints** beyond those currently documented in `openapi.yaml`.

## Current Documentation Status

### Already Documented (7 endpoints)
✅ POST /v1/login2 - User authentication
✅ POST /v1/logout2 - User logout
✅ GET /v1/user/nodes - Get user devices
✅ GET /v1/user/nodes/status - Get device connectivity
✅ GET /v1/user/nodes/config - Get device configuration
✅ GET /v1/user/nodes/params - Get device state
✅ PUT /v1/user/nodes/params - Update device parameters

---

## Newly Discovered Endpoints (47 total)

### Priority 1: Essential for Device Control (Recommended for pythermacell)

#### User Management
```
POST /{version}/user - Create user account
POST /{version}/user - Confirm user account with verification code
GET /{version}/user - Get user profile
DELETE /{version}/user - Delete user account
PUT /{version}/password - Change password (authenticated)
PUT /{version}/forgotpassword - Reset password (unauthenticated)
```

#### Node/Device Management
```
PUT /{version}/user/nodes - Add/claim device to account
PUT /{version}/user/nodes - Remove device from account
PUT /{version}/user/nodes/mapping - Add metadata tags to nodes
DELETE /{version}/user/nodes/mapping - Remove metadata tags from nodes
GET /{version}/user/nodes/mapping - Check node addition request status
PUT /{version}/user/nodes/params - Update multiple nodes simultaneously
```

#### Device Grouping
```
GET /{version}/user/node_group - List all device groups
POST /{version}/user/node_group - Create device group
PUT /{version}/user/node_group - Update group membership
DELETE /{version}/user/node_group - Delete device group
```
**Use Case**: Control multiple LIV Hubs simultaneously (e.g., "turn on all patio repellers")

#### OTA Firmware Updates
```
GET /{version}/user/nodes/ota_update - Check for firmware updates
POST /{version}/user/nodes/ota_update - Initiate OTA update
GET /{version}/user/nodes/ota_status - Get update status
```
**Use Case**: Programmatic firmware management

---

### Priority 2: Advanced Features

#### Device Sharing
```
GET /{version}/user/nodes/sharing - Get sharing info for node
PUT /{version}/user/nodes/sharing - Share nodes with another user
DELETE /{version}/user/nodes/sharing - Remove user access
GET /{version}/user/nodes/sharing/requests - List sharing requests
PUT /{version}/user/nodes/sharing/requests - Accept/decline sharing request
DELETE /{version}/user/nodes/sharing/requests - Cancel pending request
```
**Use Case**: Family/household device sharing

#### Automation/Scheduling
```
GET /{version}/user/node_automation - List automations
GET /{version}/user/node_automation - Get specific automation details
POST /{version}/user/node_automation - Create automation/schedule
PUT /{version}/user/node_automation - Update automation
DELETE /{version}/user/node_automation - Delete automation
```
**Use Case**: Scheduled device activation, geo-fencing triggers

#### Time Series Data
```
GET /{version}/user/nodes/tsdata - Retrieve historical parameter data
```
**Parameters**:
- `node_id`: Device identifier
- `param_name`: Parameter to query (e.g., "System Runtime")
- `aggregate`: avg, min, max, count
- `aggregation_interval`: Time bucket size
- `start_time`, `end_time`: Unix timestamps
- `timezone`: Timezone for aggregation

**Use Case**: Usage analytics, runtime statistics

#### Push Notifications
```
POST /{version}/user/push_notification/mobile_platform_endpoint - Register device token
DELETE /{version}/user/push_notification/mobile_platform_endpoint - Unregister device
```
**Use Case**: Mobile app notifications for device events

---

### Priority 3: Platform Integration

#### Device Claiming/Provisioning
```
POST /NA/claim/initiate - Initiate device claiming (pairing)
POST /NA/claim/verify - Verify and complete claiming
```
**Note**: Region-specific endpoints (NA = North America)

#### OAuth 2.0 Authentication
```
POST https://3pauth.iot.thermacell.com/token - OAuth token exchange
POST /{version}/login - Get API tokens from OAuth tokens
```
**Supported Providers**: GitHub, Google, Apple (confirmed via APK)

#### API Version Detection
```
GET /{version}/apiversions - Get list of supported API versions
```

---

### Priority 4: External Integrations (Out of Scope)

#### Alexa Integration (Amazon APIs)
```
GET https://api.amazonalexa.com/v1/alexaApiEndpoint
POST https://api.amazon.com/auth/o2/token
POST https://{alexa-endpoint}/v1/users/~current/skills/null/enablement
DELETE https://{alexa-endpoint}/v1/users/~current/skills/null/enablement
GET https://{alexa-endpoint}/v1/users/~current/skills/null/enablement
```

---

## Implementation Recommendations

### For pythermacell v0.2.0+

**High Priority** (Extend core device control):
1. ✅ **Groups API** - Multi-device control
2. ✅ **OTA Updates** - Firmware management
3. ✅ **Time Series Data** - Usage analytics

**Medium Priority** (Advanced features):
4. **Device Sharing** - Family/household support
5. **Automation** - Scheduling and geo-fencing
6. **Push Notifications** - Real-time alerts

**Low Priority** (Platform integration):
7. **Device Claiming** - Setup/onboarding flows
8. **OAuth 2.0** - Social login support

### API Version Strategy

The APK reveals the app uses **dual versioning**:
- `/v1/user/nodes` - Standard endpoint
- `/v1/user2/nodes` - Alternative v2 variant

The app queries `/apiversions` to detect support and adapts endpoints accordingly.

**Recommendation**: Implement version detection in client initialization to future-proof against API changes.

---

## Technical Details

### Key Source Files Analyzed

1. **ApiInterface.smali** (2,313 lines)
   - Main API interface definitions
   - All HTTP method signatures

2. **ApiManager.smali** (5,800+ lines)
   - Implementation with URL construction
   - Request/response handling

3. **AlexaApiInterface.smali** (300+ lines)
   - Alexa skill integration

4. **EspApplication.smali**
   - Base URL configuration: `https://api.iot.thermacell.com`
   - OAuth URL: `https://3pauth.iot.thermacell.com`

### Authentication Flow

```python
# Standard username/password
POST /v1/login2
  → {accesstoken, idtoken, refreshtoken}

# OAuth (GitHub, Google, Apple)
1. POST https://3pauth.iot.thermacell.com/token
     → {id_token, access_token, refresh_token, is_github_login}
2. POST /v1/login
     → {accesstoken, idtoken, refreshtoken}
```

### Dual API Pattern

Many endpoints have two variants:
- `/v1/user/...` - Standard API
- `/v1/user2/...` - Alternative version

The app checks supported versions and uses the appropriate variant.

---

## Next Steps

### Documentation
1. ✅ Create this discovery document
2. ⬜ Update `openapi.yaml` with Priority 1 endpoints
3. ⬜ Create separate OpenAPI specs for:
   - Groups API
   - OTA API
   - Sharing API
   - Automation API

### Implementation
1. ⬜ Add version detection to `ThermacellClient`
2. ⬜ Implement Groups API (`client.get_groups()`, `client.create_group()`)
3. ⬜ Implement OTA API (`client.check_firmware()`, `client.update_firmware()`)
4. ⬜ Implement Time Series API (`client.get_history()`)

### Testing
1. ⬜ Validate new endpoints with real API
2. ⬜ Document rate limits and throttling behavior
3. ⬜ Test multi-device group operations

---

## References

- **APK Source**: `research/com.thermacell.liv/`
- **Current OpenAPI**: `docs/api/openapi.yaml`
- **ESP RainMaker Docs**: https://swaggerapis.rainmaker.espressif.com/
- **Home Assistant Integration**: `research/thermacell_liv/`

---

## Appendix: Complete Endpoint List

See [GROUPS_API.md](GROUPS_API.md) for device grouping documentation.
See [OTA_UPDATE_ENDPOINTS.md](OTA_UPDATE_ENDPOINTS.md) for firmware update documentation.

For a complete list of all 54 endpoints with full request/response schemas, see the APK analysis output.
