# Groups API Documentation

**Date**: 2025-11-17
**API Version**: v1
**Status**: Validated with Live API

## Overview

The Thermacell Groups API allows users to organize multiple devices into logical groups for easier management. Groups support full CRUD operations (Create, Read, Update, Delete) through the ESP RainMaker platform.

## Key Findings

### Supported Endpoints

**Read Operations:**
1. **List All Groups**: `GET /v1/user/node_group`
2. **Get Specific Group**: `GET /v1/user/node_group?group_id={id}`
3. **Get Group Nodes**: `GET /v1/user/nodes?group_id={id}`

**Write Operations:**
4. **Create Group**: `POST /v1/user/node_group`
5. **Update Group**: `PUT /v1/user/node_group?group_id={id}`
6. **Delete Group**: `DELETE /v1/user/node_group?group_id={id}`

### Important Limitations

- **No Group Control Endpoints**: Groups do NOT have dedicated `/params`, `/status`, or `/config` endpoints
- **Control Pattern**: To control a group, fetch node IDs via `/v1/user/nodes?group_id={id}`, then control each device individually
- **No Bulk Operations**: The API does not support setting parameters for all devices in a group with a single request

## Endpoint Details

### 1. List All Groups

**Endpoint**: `GET /v1/user/node_group`

**Headers**:
```
Authorization: {access_token}
```

**Query Parameters**: None required (optional `user_id` parameter has no effect)

**Response** (Success - 200 OK):
```json
{
  "groups": [
    {
      "group_id": "TrYibkxmnagQbbETKo8UwT",
      "group_name": "Backyard",
      "is_matter": false,
      "primary": true,
      "total": 2
    }
  ],
  "total": 1
}
```

**Response** (No Groups - 200 OK):
```json
{
  "groups": [],
  "total": 0
}
```

**Edge Case Handling**:
- When no groups exist, the API returns an empty `groups` array with `total: 0`
- This is NOT an error condition - it's a valid response

---

### 2. Get Specific Group

**Endpoint**: `GET /v1/user/node_group?group_id={group_id}`

**Headers**:
```
Authorization: {access_token}
```

**Query Parameters**:
- `group_id` (required): The group ID to retrieve

**Response** (Success - 200 OK):
```json
{
  "groups": [
    {
      "group_id": "TrYibkxmnagQbbETKo8UwT",
      "group_name": "Backyard",
      "is_matter": false,
      "primary": true,
      "total": 2
    }
  ]
}
```

**Notes**:
- Returns a single-element array containing the matching group
- If group_id doesn't exist, returns empty array `{"groups": []}`

---

### 3. Get Group Nodes

**Endpoint**: `GET /v1/user/nodes?group_id={group_id}`

**Headers**:
```
Authorization: {access_token}
```

**Query Parameters**:
- `group_id` (required): The group ID to get nodes for

**Response** (Success - 200 OK):
```json
{
  "nodes": [
    "JM7UVxmMgPUYUhVJVBWEf6",
    "bcJUkwStfpictTZadwy5t7"
  ],
  "total": 2
}
```

**Usage**:
This endpoint returns only node IDs. To get full device details or control devices:
1. Call this endpoint to get node IDs
2. For each node ID, call `/v1/user/nodes/params?nodeid={node_id}` (for state)
3. Or use the existing `client.get_devices()` and filter by group membership

---

## Data Models

### Group Object

| Field | Type | Description |
|-------|------|-------------|
| `group_id` | string | Unique identifier for the group |
| `group_name` | string | User-friendly name of the group |
| `is_matter` | boolean | Whether this is a Matter protocol group |
| `primary` | boolean | Whether this is a primary group |
| `total` | integer | Number of devices/nodes in this group |

### GroupListResponse

| Field | Type | Description |
|-------|------|-------------|
| `groups` | Group[] | Array of group objects |
| `total` | integer | Total number of groups |

### GroupNodesResponse

| Field | Type | Description |
|-------|------|-------------|
| `nodes` | string[] | Array of node IDs |
| `total` | integer | Total number of nodes |

---

## Implementation Strategy

### Recommended Approach

Since groups don't have dedicated control endpoints, we recommend the following architecture:

1. **Group Discovery**:
   - `client.get_groups()` - List all groups
   - `client.get_group(group_id)` - Get specific group details
   - `client.get_group_nodes(group_id)` - Get node IDs in a group

2. **Group Control** (Convenience Methods):
   - `client.get_group_devices(group_id)` - Get full Device objects for a group
   - `device.groups` - Property to expose which groups a device belongs to
   - Group control operations operate on individual devices

### Example Usage

```python
from pythermacell import ThermacellClient

async def main():
    async with ThermacellClient(username, password) as client:
        # Get all groups
        groups = await client.get_groups()

        for group in groups:
            print(f"Group: {group.name} ({group.total} devices)")

            # Get devices in this group
            devices = await client.get_group_devices(group.group_id)

            # Control all devices in the group
            for device in devices:
                await device.turn_on()
                await device.set_led_color(hue=120, saturation=100, brightness=80)
```

---

## Testing Considerations

### Unit Tests

1. **Empty Groups**: Test behavior when `groups` array is empty
2. **Single Group**: Test with one group
3. **Multiple Groups**: Test with multiple groups
4. **Group Filtering**: Test filtering devices by group

### Integration Tests

1. **Live API**: Test against real API (requires credentials in `.env`)
2. **Group Creation**: Cannot be tested (requires mobile app)
3. **Group Deletion**: Cannot be tested (requires mobile app)

---

## Unsupported Endpoints

The following endpoints were tested and are **NOT supported**:

- `/v1/user/node_groups` (plural) - Returns 400 Bad Request
- `/v1/user/node_group/{group_id}` (path parameter) - Returns 400 Bad Request
- `/v1/user/node_group/params?group_id={id}` - Returns 400 Bad Request
- `/v1/user/node_group/status?group_id={id}` - Returns 400 Bad Request
- `/v1/user/node_group/config?group_id={id}` - Returns 400 Bad Request
- `/v2/user/node_group` - Returns 400 (API Version not supported)

---

## Error Responses

### 400 Bad Request

```json
{
  "status": "failure",
  "description": "Bad request"
}
```

**Causes**:
- Invalid endpoint
- Unsupported API version
- Malformed query parameters

### 401 Unauthorized

**Causes**:
- Missing `Authorization` header
- Invalid or expired access token
- Reauthentication required

---

### 4. Create Group

**Endpoint**: `POST /v1/user/node_group`

**Headers**:
```
Authorization: {access_token}
```

**Request Body**:
```json
{
  "group_name": "My New Group",
  "node_list": ["node_id_1", "node_id_2"]
}
```

**Notes**:
- `group_name` is required and cannot be empty
- `node_list` is optional - can create empty group and add nodes later
- Node IDs must be valid device node IDs from your account

**Response** (Success - 200 OK):
```json
{
  "status": "success",
  "group_id": "QtTdMGGA6a6DbGEEwRxsQd"
}
```

**Response** (Error - 400 Bad Request):
```json
{
  "status": "failure",
  "description": "Group name is required"
}
```

---

### 5. Update Group

**Endpoint**: `PUT /v1/user/node_group?group_id={group_id}`

**Headers**:
```
Authorization: {access_token}
```

**Query Parameters**:
- `group_id` (required): The group ID to update

**Request Body**:
```json
{
  "group_name": "Updated Group Name",
  "node_list": ["node_id_1", "node_id_2", "node_id_3"]
}
```

**Notes**:
- `group_name` is required in the request body (use current name if not changing)
- `node_list` is optional - only include to update the node list
- Providing `node_list` replaces the entire list (not a merge)

**Response** (Success - 200 OK):
```json
{
  "status": "success",
  "description": "Successfully updated group"
}
```

**Response** (Error - 400 Bad Request):
```json
{
  "status": "failure",
  "description": "Group id is missing",
  "error_code": 108016
}
```

**Response** (Error - 404 Not Found):
```json
{
  "status": "failure",
  "description": "Group not found"
}
```

---

### 6. Delete Group

**Endpoint**: `DELETE /v1/user/node_group?group_id={group_id}`

**Headers**:
```
Authorization: {access_token}
```

**Query Parameters**:
- `group_id` (required): The group ID to delete

**Request Body**: None

**Response** (Success - 200 OK):
```json
{
  "status": "success",
  "description": "Successfully deleted group"
}
```

**Response** (Error - 400 Bad Request):
```json
{
  "status": "failure",
  "description": "Group id is missing",
  "error_code": 108016
}
```

**Response** (Error - 404 Not Found):
```json
{
  "status": "failure",
  "description": "Group not found"
}
```

---

## Data Models

### Group Object

| Field | Type | Description |
|-------|------|-------------|
| `group_id` | string | Unique identifier for the group |
| `group_name` | string | User-friendly name of the group |
| `is_matter` | boolean | Whether this is a Matter protocol group |
| `primary` | boolean | Whether this is a primary group |
| `total` | integer | Number of devices/nodes in this group |

### GroupListResponse

| Field | Type | Description |
|-------|------|-------------|
| `groups` | Group[] | Array of group objects |
| `total` | integer | Total number of groups |

### GroupNodesResponse

| Field | Type | Description |
|-------|------|-------------|
| `nodes` | string[] | Array of node IDs |
| `total` | integer | Total number of nodes |

---

## Implementation Strategy

### Recommended Approach

Groups support full CRUD operations with the following architecture:

1. **Group Discovery**:
   - `client.get_groups()` - List all groups
   - `client.get_group(group_id)` - Get specific group details
   - `client.get_group_nodes(group_id)` - Get node IDs in a group

2. **Group Management**:
   - `client.create_group(name, node_ids)` - Create new group
   - `client.update_group(group_id, name, node_ids)` - Update group
   - `client.delete_group(group_id)` - Delete group

3. **Group Control** (Convenience Methods):
   - `client.get_group_devices(group_id)` - Get full Device objects for a group
   - `device.groups` - Property to expose which groups a device belongs to
   - Group control operations operate on individual devices

### Example Usage

```python
from pythermacell import ThermacellClient

async def main():
    async with ThermacellClient(username, password) as client:
        # Create a new group
        group_id = await client.create_group("Backyard", node_ids=["node1", "node2"])
        print(f"Created group: {group_id}")

        # Get all groups
        groups = await client.get_groups()
        for group in groups:
            print(f"Group: {group.group_name} ({group.total} devices)")

            # Get devices in this group
            devices = await client.get_group_devices(group.group_id)

            # Control all devices in the group
            for device in devices:
                await device.turn_on()
                await device.set_led_color(hue=120, saturation=100, brightness=80)

        # Update group name
        await client.update_group(group_id, group_name="Updated Backyard")

        # Delete group
        await client.delete_group(group_id)
```

---

## Testing Considerations

### Unit Tests

1. **Empty Groups**: Test behavior when `groups` array is empty
2. **Single Group**: Test with one group
3. **Multiple Groups**: Test with multiple groups
4. **Group Filtering**: Test filtering devices by group
5. **Create Group**: Test group creation with and without nodes
6. **Update Group**: Test updating name and node list
7. **Delete Group**: Test group deletion and nonexistent groups

### Integration Tests

1. **Live API**: Test against real API (requires credentials in `.env`)
2. **Full CRUD Workflow**: Test create → update → delete lifecycle
3. **Group with Nodes**: Test creating and updating groups with devices
4. **Error Cases**: Test nonexistent group IDs, empty names, etc.

---

## Unsupported Endpoints

The following endpoints were tested and are **NOT supported**:

- `/v1/user/node_groups` (plural) - Returns 400 Bad Request
- `/v1/user/node_group/{group_id}` (path parameter) - Returns 400 Bad Request
- `/v1/user/node_group/params?group_id={id}` - Returns 400 Bad Request
- `/v1/user/node_group/status?group_id={id}` - Returns 400 Bad Request
- `/v1/user/node_group/config?group_id={id}` - Returns 400 Bad Request
- `/v2/user/node_group` - Returns 400 (API Version not supported)

---

## Error Responses

### 400 Bad Request

```json
{
  "status": "failure",
  "description": "Bad request"
}
```

**Causes**:
- Invalid endpoint
- Unsupported API version
- Malformed query parameters
- Missing required fields (e.g., group_name, group_id)

### 401 Unauthorized

**Causes**:
- Missing `Authorization` header
- Invalid or expired access token
- Reauthentication required

### 404 Not Found

```json
{
  "status": "failure",
  "description": "Group not found"
}
```

**Causes**:
- Group ID does not exist
- Group was already deleted

---

## References

- Research Scripts:
  - `research/research_groups_detailed.py` (read operations)
  - `research/research_groups_management.py` (write operations)
- API Response Samples: `research/groups_api_responses.json`
- Output Logs: `research/groups_management_output.txt`
- Gap Analysis: `docs/GAP_ANALYSIS.md` (Section 4 - Additional Features)
