"""Integration tests for Groups API endpoints.

These tests run against the live Thermacell API and require valid credentials.
Credentials should be provided via environment variables in .env file.
"""

from __future__ import annotations

import os

import pytest
from dotenv import load_dotenv

from pythermacell.client import ThermacellClient
from pythermacell.exceptions import AuthenticationError


# Load environment variables
load_dotenv()

# Test credentials from environment
USERNAME = os.getenv("THERMACELL_USERNAME")
PASSWORD = os.getenv("THERMACELL_PASSWORD")
BASE_URL = os.getenv("THERMACELL_API_BASE_URL", "https://api.iot.thermacell.com")


pytestmark = pytest.mark.integration


@pytest.fixture
def skip_if_no_credentials() -> None:
    """Skip test if credentials are not available."""
    if not USERNAME or not PASSWORD:
        pytest.skip("Thermacell credentials not available in environment")


class TestGroupsIntegration:
    """Integration tests for Groups API."""

    async def test_get_groups_real_api(self, skip_if_no_credentials: None) -> None:
        """Test get_groups() against real API."""
        async with ThermacellClient(USERNAME, PASSWORD, base_url=BASE_URL) as client:
            groups = await client.get_groups()

            # Should return a list (may be empty)
            assert isinstance(groups, list)

            # If groups exist, validate structure
            if groups:
                for group in groups:
                    assert hasattr(group, "group_id")
                    assert hasattr(group, "group_name")
                    assert hasattr(group, "is_matter")
                    assert hasattr(group, "primary")
                    assert hasattr(group, "total")

                    # Validate types
                    assert isinstance(group.group_id, str)
                    assert isinstance(group.group_name, str)
                    assert isinstance(group.is_matter, bool)
                    assert isinstance(group.primary, bool)
                    assert isinstance(group.total, int)

                    # Validate values
                    assert len(group.group_id) > 0
                    assert len(group.group_name) > 0
                    assert group.total >= 0

    async def test_get_group_by_id_real_api(self, skip_if_no_credentials: None) -> None:
        """Test get_group() against real API."""
        async with ThermacellClient(USERNAME, PASSWORD, base_url=BASE_URL) as client:
            # First, get all groups
            groups = await client.get_groups()

            if not groups:
                pytest.skip("No groups available for testing")

            # Test getting first group by ID
            group_id = groups[0].group_id
            group = await client.get_group(group_id)

            assert group is not None
            assert group.group_id == group_id
            assert isinstance(group.group_name, str)
            assert len(group.group_name) > 0

    async def test_get_group_nonexistent_id(self, skip_if_no_credentials: None) -> None:
        """Test get_group() with nonexistent group ID."""
        async with ThermacellClient(USERNAME, PASSWORD, base_url=BASE_URL) as client:
            # Use a definitely nonexistent group ID
            group = await client.get_group("nonexistent-group-12345")

            # Should return None for nonexistent group
            assert group is None

    async def test_get_group_nodes_real_api(self, skip_if_no_credentials: None) -> None:
        """Test get_group_nodes() against real API."""
        async with ThermacellClient(USERNAME, PASSWORD, base_url=BASE_URL) as client:
            groups = await client.get_groups()

            if not groups:
                pytest.skip("No groups available for testing")

            # Test getting nodes for first group
            group_id = groups[0].group_id
            nodes = await client.get_group_nodes(group_id)

            # Should return a list (may be empty)
            assert isinstance(nodes, list)

            # All nodes should be strings
            for node_id in nodes:
                assert isinstance(node_id, str)
                assert len(node_id) > 0

            # Number of nodes should match group's total
            assert len(nodes) == groups[0].total

    async def test_get_group_devices_real_api(self, skip_if_no_credentials: None) -> None:
        """Test get_group_devices() against real API."""
        async with ThermacellClient(USERNAME, PASSWORD, base_url=BASE_URL) as client:
            groups = await client.get_groups()

            if not groups:
                pytest.skip("No groups available for testing")

            # Find a group with devices
            group_with_devices = None
            for group in groups:
                if group.total > 0:
                    group_with_devices = group
                    break

            if not group_with_devices:
                pytest.skip("No groups with devices available for testing")

            # Get devices in the group
            devices = await client.get_group_devices(group_with_devices.group_id)

            # Should return a list matching the group's total
            assert isinstance(devices, list)
            assert len(devices) == group_with_devices.total

            # Validate device structure
            for device in devices:
                assert hasattr(device, "node_id")
                assert hasattr(device, "name")
                assert isinstance(device.node_id, str)
                assert isinstance(device.name, str)

    async def test_get_group_devices_empty_group(self, skip_if_no_credentials: None) -> None:
        """Test get_group_devices() with an empty/nonexistent group.

        Note: The API returns all nodes when group_id doesn't match any existing group,
        treating it like no filter is applied. This is the API's documented behavior.
        """
        async with ThermacellClient(USERNAME, PASSWORD, base_url=BASE_URL) as client:
            # Get devices for nonexistent group
            # API returns all devices when group doesn't exist (no filter)
            devices = await client.get_group_devices("nonexistent-group-xyz-12345")

            # Should return a list (may contain all devices due to API behavior)
            assert isinstance(devices, list)

    async def test_groups_workflow_real_api(self, skip_if_no_credentials: None) -> None:
        """Test complete groups workflow."""
        async with ThermacellClient(USERNAME, PASSWORD, base_url=BASE_URL) as client:
            # 1. List all groups
            groups = await client.get_groups()
            assert isinstance(groups, list)

            if not groups:
                pytest.skip("No groups available for testing")

            # 2. Get specific group
            first_group = groups[0]
            group = await client.get_group(first_group.group_id)
            assert group is not None
            assert group.group_id == first_group.group_id

            # 3. Get nodes in group
            nodes = await client.get_group_nodes(first_group.group_id)
            assert len(nodes) == first_group.total

            # 4. Get full device objects
            if first_group.total > 0:
                devices = await client.get_group_devices(first_group.group_id)
                assert len(devices) == first_group.total

                # Verify all devices have the expected node IDs
                device_ids = {device.node_id for device in devices}
                assert device_ids == set(nodes)

    async def test_groups_with_backyard_group(self, skip_if_no_credentials: None) -> None:
        """Test with the specific 'Backyard' group mentioned in requirements.

        This test verifies the specific group created for testing.
        """
        async with ThermacellClient(USERNAME, PASSWORD, base_url=BASE_URL) as client:
            groups = await client.get_groups()

            # Find the "Backyard" group
            backyard_group = None
            for group in groups:
                if group.group_name == "Backyard":
                    backyard_group = group
                    break

            if not backyard_group:
                pytest.skip("Backyard group not found - may have been deleted")

            # Verify backyard group properties
            assert backyard_group.group_name == "Backyard"
            assert isinstance(backyard_group.total, int)
            assert backyard_group.total >= 0

            # Get devices in backyard group
            devices = await client.get_group_devices(backyard_group.group_id)
            assert len(devices) == backyard_group.total

    async def test_invalid_authentication_groups(self) -> None:
        """Test groups API with invalid authentication."""
        async with ThermacellClient(
            "invalid@example.com",
            "wrongpassword",
            base_url=BASE_URL,
        ) as client:
            with pytest.raises(AuthenticationError):
                await client.get_groups()

    async def test_create_update_delete_group_workflow(self, skip_if_no_credentials: None) -> None:
        """Test full create/update/delete workflow for groups.

        This test creates a test group, updates it, then deletes it to avoid
        leaving test data in the real API.
        """
        async with ThermacellClient(USERNAME, PASSWORD, base_url=BASE_URL) as client:
            # Create a new test group
            test_group_name = "Test API Group - Delete Me"
            group_id = await client.create_group(test_group_name)

            assert isinstance(group_id, str)
            assert len(group_id) > 0

            # Verify the group was created
            group = await client.get_group(group_id)
            assert group is not None
            assert group.group_id == group_id
            assert group.group_name == test_group_name
            assert group.total == 0  # No nodes yet

            # Update the group name
            updated_name = "Test API Group - Updated"
            success = await client.update_group(group_id, group_name=updated_name)
            assert success is True

            # Verify the update
            group = await client.get_group(group_id)
            assert group is not None
            assert group.group_name == updated_name

            # Clean up: Delete the test group
            success = await client.delete_group(group_id)
            assert success is True

            # Verify deletion
            group = await client.get_group(group_id)
            assert group is None

    async def test_create_group_with_nodes_real_api(self, skip_if_no_credentials: None) -> None:
        """Test creating a group with nodes in real API.

        This test creates a group with real device nodes, then cleans up.
        """
        async with ThermacellClient(USERNAME, PASSWORD, base_url=BASE_URL) as client:
            # Get available devices
            devices = await client.get_devices()
            if not devices:
                pytest.skip("No devices available for testing")

            # Use first device for testing
            node_id = devices[0].node_id

            # Create group with node
            test_group_name = "Test Group with Nodes"
            group_id = await client.create_group(test_group_name, node_ids=[node_id])

            assert isinstance(group_id, str)
            assert len(group_id) > 0

            # Verify the group has the node
            nodes = await client.get_group_nodes(group_id)
            assert node_id in nodes

            # Clean up
            await client.delete_group(group_id)

    async def test_update_group_nodes_real_api(self, skip_if_no_credentials: None) -> None:
        """Test updating group nodes in real API."""
        async with ThermacellClient(USERNAME, PASSWORD, base_url=BASE_URL) as client:
            # Get available devices
            devices = await client.get_devices()
            if len(devices) < 2:
                pytest.skip("Need at least 2 devices for this test")

            node_ids = [devices[0].node_id, devices[1].node_id]

            # Create group
            group_id = await client.create_group("Test Update Nodes")

            # Update to add nodes
            success = await client.update_group(group_id, node_ids=node_ids)
            assert success is True

            # Verify nodes were added
            group_nodes = await client.get_group_nodes(group_id)
            assert len(group_nodes) == 2
            assert all(node_id in group_nodes for node_id in node_ids)

            # Clean up
            await client.delete_group(group_id)

    async def test_delete_nonexistent_group_real_api(self, skip_if_no_credentials: None) -> None:
        """Test deleting a nonexistent group returns False."""
        async with ThermacellClient(USERNAME, PASSWORD, base_url=BASE_URL) as client:
            # Try to delete a group that definitely doesn't exist
            success = await client.delete_group("nonexistent-group-xyz-12345")
            assert success is False

    async def test_update_nonexistent_group_real_api(self, skip_if_no_credentials: None) -> None:
        """Test updating a nonexistent group returns False."""
        async with ThermacellClient(USERNAME, PASSWORD, base_url=BASE_URL) as client:
            # Try to update a group that doesn't exist
            success = await client.update_group("nonexistent-group-xyz-12345", group_name="New Name")
            assert success is False
