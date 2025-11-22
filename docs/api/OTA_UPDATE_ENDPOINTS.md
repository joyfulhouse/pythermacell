# OTA Firmware Update Endpoints - Complete Documentation

**Discovery**: The `/user/nodes/ota_update` endpoint serves **dual purpose**:
- **GET** - Check if firmware update is available
- **POST** - Push firmware update to device

---

## Endpoint 1: Check for Available Firmware

### `GET /{version}/user/nodes/ota_update`

**Purpose**: Check if there is a firmware update available for a specific device.

**Summary**: Using this API the end user can check if there is any OTA update for the node which is associated with their account.

**Parameters**:
- `version` (path) - API version (required) - Default: `v1`
- `node_id` (query) - Node identifier (required)

**Request Example**:
```bash
GET /v1/user/nodes/ota_update?node_id=ABCD1234EFGH5678
Authorization: {access_token}
```

**Response - Update Available**:
```json
{
  "status": "success",
  "ota_available": true,
  "description": "New firmware version with bug fixes and performance improvements",
  "fw_version": "5.3.3",
  "ota_job_id": "OTA_JOB_12345",
  "file_size": 245760
}
```

**Response - Update with Firmware URL**:
```json
{
  "status": "success",
  "ota_available": true,
  "description": "New firmware version with bug fixes",
  "fw_version": "5.3.3",
  "ota_job_id": "OTA_JOB_12345",
  "file_size": 245760,
  "url": "https://s3.amazonaws.com/rainmaker-ota/firmware_5.3.3.bin?signature=...",
  "file_md5": "a1b2c3d4e5f6g7h8i9j0k1l2m3n4o5p6"
}
```

**Response - No Update Available**:
```json
{
  "status": "success",
  "ota_available": false,
  "description": "Device is running latest firmware"
}
```

**Response Fields**:
- `status` (string) - Request status ("success" or "failure")
- `ota_available` (boolean) - Whether an OTA update is available
- `description` (string) - Description of the update (optional)
- `fw_version` (string) - Target firmware version (if available)
- `ota_job_id` (string) - OTA job identifier needed for pushing update (if available)
- `file_size` (integer) - Firmware file size in bytes (if available)
- `url` (string) - Pre-signed S3 URL for firmware download (optional)
- `file_md5` (string) - MD5 checksum of firmware file (optional)

**Error Responses**:
- `400` - Node does not belong to user, NodeId is missing, OTA image not found
- `423` - Too much traffic, try again later
- `500` - Internal server error

**Use Cases**:
1. **Check for updates** - Periodic polling to see if new firmware is available
2. **Notification** - Alert user when update is available
3. **Pre-download** - Use the `url` field to download firmware in advance
4. **Update preparation** - Get `ota_job_id` for initiating update

---

## Endpoint 2: Push Firmware Update to Device

### `POST /{version}/user/nodes/ota_update`

**Purpose**: Initiate firmware update on a specific device.

**Summary**: Using this API the end user can push OTA update to the node which is associated with their account.

**Parameters**:
- `version` (path) - API version (required) - Default: `v1`

**Request Body**:
```json
{
  "ota_job_id": "OTA_JOB_12345",
  "node_id": "ABCD1234EFGH5678"
}
```

**Request Fields**:
- `ota_job_id` (string, required) - OTA job identifier obtained from GET request
- `node_id` (string, required) - Node identifier to update

**Request Example**:
```bash
POST /v1/user/nodes/ota_update
Authorization: {access_token}
Content-Type: application/json

{
  "ota_job_id": "OTA_JOB_12345",
  "node_id": "ABCD1234EFGH5678"
}
```

**Response - Success**:
```json
{
  "status": "success",
  "description": "OTA update initiated successfully"
}
```

**Error Responses**:
- `400` - Invalid request body, OTA Job Id missing, NodeId missing, Node is offline
- `500` - Internal server error

**Important Notes**:
- Device must be **online** to receive update
- Use `ota_job_id` from the GET endpoint response
- Update is pushed to device immediately
- Monitor progress with `/user/nodes/ota_status` endpoint

---

## Endpoint 3: Monitor Update Progress

### `GET /{version}/user/nodes/ota_status`

**Purpose**: Check the status of an ongoing or completed firmware update.

**Summary**: Using this API the end user can check the latest status of the OTA Job for a node.

**Parameters**:
- `version` (path) - API version (required) - Default: `v1`
- `node_id` (query) - Node identifier (required)
- `ota_job_id` (query) - OTA job identifier (required)

**Request Example**:
```bash
GET /v1/user/nodes/ota_status?node_id=ABCD1234EFGH5678&ota_job_id=OTA_JOB_12345
Authorization: {access_token}
```

**Response - Update in Progress**:
```json
{
  "status": "in_progress",
  "node_id": "ABCD1234EFGH5678",
  "ota_job_id": "OTA_JOB_12345",
  "timestamp": 1704067200,
  "additional_info": "Downloading firmware... 45%"
}
```

**Response - Update Completed**:
```json
{
  "status": "success",
  "node_id": "ABCD1234EFGH5678",
  "ota_job_id": "OTA_JOB_12345",
  "timestamp": 1704067800,
  "additional_info": "Firmware updated successfully to version 5.3.3"
}
```

**Response - Update Failed**:
```json
{
  "status": "failed",
  "node_id": "ABCD1234EFGH5678",
  "ota_job_id": "OTA_JOB_12345",
  "timestamp": 1704067500,
  "additional_info": "Download failed - connection timeout"
}
```

**Status Values**:
- `initiated` - Update has been queued
- `in_progress` - Update is downloading or installing
- `success` - Update completed successfully
- `failed` - Update failed
- `rejected` - Device rejected the update

**Error Responses**:
- `400` - Node does not belong to user, OTA Job Id missing, NodeId missing
- `404` - OTA status not found
- `500` - Internal server error

---

## Complete Firmware Update Workflow

### Step 1: Check for Available Update
```python
# Check if update is available
response = client.get("/v1/user/nodes/ota_update?node_id=ABCD1234")

if response["ota_available"]:
    print(f"Update available: {response['fw_version']}")
    print(f"Description: {response['description']}")
    print(f"File size: {response['file_size']} bytes")

    ota_job_id = response["ota_job_id"]
else:
    print("No update available")
    exit()
```

### Step 2: Initiate Update
```python
# Push update to device
client.post("/v1/user/nodes/ota_update", json={
    "ota_job_id": ota_job_id,
    "node_id": "ABCD1234"
})
print("Update initiated")
```

### Step 3: Monitor Progress
```python
import time

while True:
    status = client.get(
        f"/v1/user/nodes/ota_status?node_id=ABCD1234&ota_job_id={ota_job_id}"
    )

    print(f"Status: {status['status']}")
    print(f"Info: {status.get('additional_info', 'N/A')}")

    if status["status"] in ["success", "failed", "rejected"]:
        break

    time.sleep(10)  # Poll every 10 seconds
```

### Step 4: Verify Update
```python
# Get device config to confirm new firmware version
config = client.get("/v1/user/nodes/config?node_id=ABCD1234")
current_version = config["info"]["fw_version"]

print(f"Current firmware: {current_version}")
if current_version == "5.3.3":
    print("Update successful!")
else:
    print("Update may have failed - version mismatch")
```

---

## Python Client Example

```python
from pythermacell import ThermacellClient

async def check_and_update_firmware(node_id: str):
    """Complete firmware update workflow."""
    async with ThermacellClient(username, password) as client:
        # Step 1: Check for updates
        update_info = await client.check_firmware_update(node_id)

        if not update_info.ota_available:
            print("Device is up to date")
            return

        print(f"Update available: {update_info.fw_version}")
        print(f"Description: {update_info.description}")
        print(f"Size: {update_info.file_size / 1024:.1f} KB")

        # Step 2: User confirmation
        confirm = input("Install update? (y/n): ")
        if confirm.lower() != 'y':
            return

        # Step 3: Initiate update
        await client.push_firmware_update(
            node_id=node_id,
            ota_job_id=update_info.ota_job_id
        )
        print("Update initiated...")

        # Step 4: Monitor progress
        while True:
            status = await client.get_ota_status(
                node_id=node_id,
                ota_job_id=update_info.ota_job_id
            )

            print(f"Status: {status.status} - {status.additional_info}")

            if status.status == "success":
                print("Firmware update completed successfully!")
                break
            elif status.status in ["failed", "rejected"]:
                print(f"Update failed: {status.additional_info}")
                break

            await asyncio.sleep(10)

        # Step 5: Verify
        config = await client.get_node_config(node_id)
        print(f"Current firmware: {config.info.fw_version}")
```

---

## Key Implementation Notes

### Discovery: Dual-Purpose Endpoint
The `/user/nodes/ota_update` endpoint was initially thought to only initiate updates, but it actually serves **two purposes**:

1. **GET** - Check firmware availability (returns `ota_available` boolean)
2. **POST** - Initiate firmware update

This is **critical** for the client implementation because:
- You can poll GET periodically to check for updates
- The GET response includes all necessary information (`ota_job_id`, `fw_version`, `file_size`)
- The POST endpoint requires the `ota_job_id` from the GET response

### Polling Strategy
**Check for updates**: Poll GET endpoint periodically (e.g., daily)
```python
# Check once per day for new firmware
schedule.every(24).hours.do(check_firmware_update)
```

**Monitor update progress**: Poll status endpoint frequently during update
```python
# Poll every 5-10 seconds during active update
while updating:
    status = get_ota_status()
    await asyncio.sleep(10)
```

### Error Handling
- **Device offline**: POST will fail with 400 if device is offline
- **Too much traffic**: 423 response means retry later
- **Invalid ota_job_id**: Ensure you use the exact ID from GET response
- **Timeout**: Updates can take several minutes, don't timeout too quickly

### Security Considerations
- Pre-signed URLs in GET response are time-limited
- Always verify `file_md5` if downloading firmware directly
- Only push updates from trusted `ota_job_id` values

---

## Integration with Home Assistant

### Firmware Update Sensor
```python
class ThermacellFirmwareUpdateSensor(CoordinatorEntity, BinarySensorEntity):
    """Binary sensor indicating if firmware update is available."""

    async def async_update(self):
        """Check for firmware update."""
        update_info = await self.coordinator.api.check_firmware_update(
            self.node_id
        )
        self._attr_is_on = update_info.get("ota_available", False)
        self._attr_extra_state_attributes = {
            "available_version": update_info.get("fw_version"),
            "description": update_info.get("description"),
            "file_size": update_info.get("file_size"),
        }
```

### Firmware Update Button
```python
class ThermacellFirmwareUpdateButton(CoordinatorEntity, ButtonEntity):
    """Button to initiate firmware update."""

    async def async_press(self):
        """Initiate firmware update."""
        # Get latest update info
        update_info = await self.coordinator.api.check_firmware_update(
            self.node_id
        )

        if not update_info.get("ota_available"):
            raise HomeAssistantError("No update available")

        # Push update
        await self.coordinator.api.push_firmware_update(
            node_id=self.node_id,
            ota_job_id=update_info["ota_job_id"]
        )

        # Start monitoring progress
        self.hass.async_create_task(
            self._monitor_update_progress(update_info["ota_job_id"])
        )
```

---

## Summary

**Three OTA Endpoints Needed**:
1. ✅ `GET /v1/user/nodes/ota_update` - **Check for available firmware**
2. ✅ `POST /v1/user/nodes/ota_update` - **Initiate firmware update**
3. ✅ `GET /v1/user/nodes/ota_status` - **Monitor update progress**

**Answer to Your Question**:
Yes! The **`GET /v1/user/nodes/ota_update`** endpoint indicates whether a firmware update is available via the `ota_available` boolean field in the response.

**Implementation Priority**: HIGH
- Essential for complete device lifecycle management
- Required for security patch deployment
- Enables remote firmware management
- Estimated effort: 2-3 days for all three endpoints

---

**Last Updated**: 2025-11-17
**Source**: ESP RainMaker API v3.5.0 (Official Specification)
**Status**: Ready for implementation
