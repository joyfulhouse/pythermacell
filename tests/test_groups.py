"""Unit tests for Groups functionality."""

from __future__ import annotations

from http import HTTPStatus
from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, MagicMock

import pytest
from aiohttp import web

from pythermacell.client import ThermacellClient
from pythermacell.models import Group, GroupListResponse, GroupNodesResponse


if TYPE_CHECKING:
    from aiohttp.test_utils import TestClient
    from aiohttp.web import Application


# Sample API responses
SAMPLE_GROUPS_RESPONSE = {
    "groups": [
        {
            "group_id": "group-1",
            "group_name": "Backyard",
            "is_matter": False,
            "primary": True,
            "total": 2,
        },
        {
            "group_id": "group-2",
            "group_name": "Living Room",
            "is_matter": False,
            "primary": False,
            "total": 1,
        },
    ],
    "total": 2,
}

SAMPLE_EMPTY_GROUPS_RESPONSE = {"groups": [], "total": 0}

SAMPLE_SINGLE_GROUP_RESPONSE = {
    "groups": [
        {
            "group_id": "group-1",
            "group_name": "Backyard",
            "is_matter": False,
            "primary": True,
            "total": 2,
        }
    ]
}

SAMPLE_GROUP_NODES_RESPONSE = {
    "nodes": ["node-1", "node-2", "node-3"],
    "total": 3,
}

SAMPLE_EMPTY_NODES_RESPONSE = {"nodes": [], "total": 0}


class TestGroupModels:
    """Test Group data models."""

    def test_group_model(self) -> None:
        """Test Group model creation."""
        group = Group(
            group_id="test-group-123",
            group_name="Test Group",
            is_matter=False,
            primary=True,
            total=3,
        )

        assert group.group_id == "test-group-123"
        assert group.group_name == "Test Group"
        assert group.is_matter is False
        assert group.primary is True
        assert group.total == 3

    def test_group_list_response_with_groups(self) -> None:
        """Test GroupListResponse with groups."""
        groups = [
            Group(
                group_id="group-1",
                group_name="Living Room",
                is_matter=False,
                primary=True,
                total=2,
            ),
            Group(
                group_id="group-2",
                group_name="Backyard",
                is_matter=False,
                primary=False,
                total=1,
            ),
        ]
        response = GroupListResponse(groups=groups, total=2)

        assert len(response.groups) == 2
        assert response.total == 2
        assert response.groups[0].group_name == "Living Room"
        assert response.groups[1].group_name == "Backyard"

    def test_group_list_response_empty(self) -> None:
        """Test GroupListResponse with no groups."""
        response = GroupListResponse(groups=[], total=0)

        assert len(response.groups) == 0
        assert response.total == 0
        assert response.groups == []

    def test_group_nodes_response(self) -> None:
        """Test GroupNodesResponse model."""
        response = GroupNodesResponse(
            nodes=["node-1", "node-2", "node-3"],
            total=3,
        )

        assert len(response.nodes) == 3
        assert response.total == 3
        assert "node-1" in response.nodes
        assert "node-2" in response.nodes
        assert "node-3" in response.nodes

    def test_group_nodes_response_empty(self) -> None:
        """Test GroupNodesResponse with no nodes."""
        response = GroupNodesResponse(nodes=[], total=0)

        assert len(response.nodes) == 0
        assert response.total == 0


@pytest.fixture
def groups_app() -> Application:
    """Create a test aiohttp application for Groups endpoints."""
    app = web.Application()

    async def get_groups(request: web.Request) -> web.Response:
        """Mock /v1/user/node_group endpoint."""
        group_id = request.query.get("group_id")
        if group_id:
            # Get specific group
            if group_id == "nonexistent":
                return web.json_response({"groups": []})
            if group_id == "group-1":
                return web.json_response(SAMPLE_SINGLE_GROUP_RESPONSE)
            return web.json_response({"groups": []})
        # Get all groups
        return web.json_response(SAMPLE_GROUPS_RESPONSE)

    async def create_group(request: web.Request) -> web.Response:
        """Mock POST /v1/user/node_group endpoint."""
        data = await request.json()
        group_name = data.get("group_name", "")
        if not group_name or not group_name.strip():
            return web.json_response(
                {"status": "failure", "description": "Group name is required"},
                status=HTTPStatus.BAD_REQUEST,
            )
        return web.json_response({"status": "success", "group_id": "new-group-123"})

    async def update_group(request: web.Request) -> web.Response:
        """Mock PUT /v1/user/node_group endpoint."""
        group_id = request.query.get("group_id")
        if not group_id:
            return web.json_response(
                {"status": "failure", "description": "Group id is missing"},
                status=HTTPStatus.BAD_REQUEST,
            )
        if group_id == "nonexistent":
            return web.json_response(
                {"status": "failure", "description": "Group not found"},
                status=HTTPStatus.NOT_FOUND,
            )
        return web.json_response({"status": "success", "description": "Successfully updated group"})

    async def delete_group(request: web.Request) -> web.Response:
        """Mock DELETE /v1/user/node_group endpoint."""
        group_id = request.query.get("group_id")
        if not group_id:
            return web.json_response(
                {"status": "failure", "description": "Group id is missing"},
                status=HTTPStatus.BAD_REQUEST,
            )
        if group_id == "nonexistent":
            return web.json_response(
                {"status": "failure", "description": "Group not found"},
                status=HTTPStatus.NOT_FOUND,
            )
        return web.json_response({"status": "success", "description": "Successfully deleted group"})

    async def get_nodes(request: web.Request) -> web.Response:
        """Mock /v1/user/nodes endpoint with group filtering."""
        group_id = request.query.get("group_id")
        if group_id:
            if group_id == "empty-group":
                return web.json_response(SAMPLE_EMPTY_NODES_RESPONSE)
            if group_id == "group-1":
                return web.json_response(SAMPLE_GROUP_NODES_RESPONSE)
            return web.json_response(SAMPLE_EMPTY_NODES_RESPONSE)
        # Return all nodes (for other tests)
        return web.json_response({"nodes": ["node-1", "node-2"]})

    # Register routes
    app.router.add_get("/v1/user/node_group", get_groups)
    app.router.add_post("/v1/user/node_group", create_group)
    app.router.add_put("/v1/user/node_group", update_group)
    app.router.add_delete("/v1/user/node_group", delete_group)
    app.router.add_get("/v1/user/nodes", get_nodes)

    return app


@pytest.fixture
async def mock_auth() -> AsyncMock:
    """Create mock authentication handler."""
    auth = AsyncMock()
    auth.access_token = "test-access-token"
    auth.user_id = "test-user-123"
    auth.is_authenticated.return_value = True
    auth.ensure_authenticated = AsyncMock()
    auth.should_retry_on_status = MagicMock(return_value=False)
    auth.set_session = MagicMock()
    auth.__aenter__ = AsyncMock(return_value=auth)
    auth.__aexit__ = AsyncMock()
    return auth


class TestClientGroupMethods:
    """Test ThermacellClient group-related methods."""

    async def test_get_groups_success(
        self,
        aiohttp_client: TestClient,
        groups_app: Application,
        mock_auth: AsyncMock,
    ) -> None:
        """Test successfully getting groups list."""
        client = await aiohttp_client(groups_app)

        thermacell_client = ThermacellClient(
            username="test@example.com",
            password="password",
            base_url=str(client.make_url("")),
        )
        thermacell_client._session = client.session
        thermacell_client._api._session = client.session
        thermacell_client._api._auth_handler = mock_auth
        thermacell_client._owns_session = False
        thermacell_client._auth_handler = mock_auth

        groups = await thermacell_client.get_groups()

        assert len(groups) == 2
        assert groups[0].group_id == "group-1"
        assert groups[0].group_name == "Backyard"
        assert groups[0].is_matter is False
        assert groups[0].primary is True
        assert groups[0].total == 2
        assert groups[1].group_id == "group-2"
        assert groups[1].group_name == "Living Room"

    async def test_get_groups_empty(
        self,
        aiohttp_client: TestClient,
        mock_auth: AsyncMock,
    ) -> None:
        """Test getting groups when none exist."""
        app = web.Application()

        async def get_empty_groups(request: web.Request) -> web.Response:
            return web.json_response(SAMPLE_EMPTY_GROUPS_RESPONSE)

        app.router.add_get("/v1/user/node_group", get_empty_groups)

        client = await aiohttp_client(app)

        thermacell_client = ThermacellClient(
            username="test@example.com",
            password="password",
            base_url=str(client.make_url("")),
        )
        thermacell_client._session = client.session
        thermacell_client._api._session = client.session
        thermacell_client._api._auth_handler = mock_auth
        thermacell_client._owns_session = False
        thermacell_client._auth_handler = mock_auth

        groups = await thermacell_client.get_groups()

        assert len(groups) == 0
        assert groups == []

    async def test_get_group_by_id_success(
        self,
        aiohttp_client: TestClient,
        groups_app: Application,
        mock_auth: AsyncMock,
    ) -> None:
        """Test getting specific group by ID."""
        client = await aiohttp_client(groups_app)

        thermacell_client = ThermacellClient(
            username="test@example.com",
            password="password",
            base_url=str(client.make_url("")),
        )
        thermacell_client._session = client.session
        thermacell_client._api._session = client.session
        thermacell_client._api._auth_handler = mock_auth
        thermacell_client._owns_session = False
        thermacell_client._auth_handler = mock_auth

        group = await thermacell_client.get_group("group-1")

        assert group is not None
        assert group.group_id == "group-1"
        assert group.group_name == "Backyard"
        assert group.total == 2

    async def test_get_group_not_found(
        self,
        aiohttp_client: TestClient,
        groups_app: Application,
        mock_auth: AsyncMock,
    ) -> None:
        """Test getting nonexistent group."""
        client = await aiohttp_client(groups_app)

        thermacell_client = ThermacellClient(
            username="test@example.com",
            password="password",
            base_url=str(client.make_url("")),
        )
        thermacell_client._session = client.session
        thermacell_client._api._session = client.session
        thermacell_client._api._auth_handler = mock_auth
        thermacell_client._owns_session = False
        thermacell_client._auth_handler = mock_auth

        group = await thermacell_client.get_group("nonexistent")

        assert group is None

    async def test_get_group_nodes_success(
        self,
        aiohttp_client: TestClient,
        groups_app: Application,
        mock_auth: AsyncMock,
    ) -> None:
        """Test getting nodes in a group."""
        client = await aiohttp_client(groups_app)

        thermacell_client = ThermacellClient(
            username="test@example.com",
            password="password",
            base_url=str(client.make_url("")),
        )
        thermacell_client._session = client.session
        thermacell_client._api._session = client.session
        thermacell_client._api._auth_handler = mock_auth
        thermacell_client._owns_session = False
        thermacell_client._auth_handler = mock_auth

        nodes = await thermacell_client.get_group_nodes("group-1")

        assert len(nodes) == 3
        assert "node-1" in nodes
        assert "node-2" in nodes
        assert "node-3" in nodes

    async def test_get_group_nodes_empty(
        self,
        aiohttp_client: TestClient,
        groups_app: Application,
        mock_auth: AsyncMock,
    ) -> None:
        """Test getting nodes from empty group."""
        client = await aiohttp_client(groups_app)

        thermacell_client = ThermacellClient(
            username="test@example.com",
            password="password",
            base_url=str(client.make_url("")),
        )
        thermacell_client._session = client.session
        thermacell_client._api._session = client.session
        thermacell_client._api._auth_handler = mock_auth
        thermacell_client._owns_session = False
        thermacell_client._auth_handler = mock_auth

        nodes = await thermacell_client.get_group_nodes("empty-group")

        assert len(nodes) == 0
        assert nodes == []

    async def test_get_group_devices_success(
        self,
        aiohttp_client: TestClient,
        groups_app: Application,
        mock_auth: AsyncMock,
    ) -> None:
        """Test getting device objects for a group."""

        # Add device endpoints to the app
        async def get_nodes_list(request: web.Request) -> web.Response:
            group_id = request.query.get("group_id")
            if group_id:
                return web.json_response({"nodes": ["node-1", "node-2"], "total": 2})
            return web.json_response({"nodes": ["node-1", "node-2", "node-3"]})

        async def get_params(request: web.Request) -> web.Response:
            return web.json_response(
                {
                    "LIV Hub": {
                        "Enable Repellers": True,
                        "LED Brightness": 80,
                        "LED Hue": 120,
                        "LED Saturation": 100,
                    }
                }
            )

        async def get_status(request: web.Request) -> web.Response:
            return web.json_response({"connectivity": {"connected": True}})

        async def get_config(request: web.Request) -> web.Response:
            node_id = request.query.get("nodeid", "node-1")
            return web.json_response(
                {
                    "node_id": node_id,
                    "info": {
                        "name": f"Device {node_id}",
                        "type": "thermacell-hub",
                        "fw_version": "5.3.2",
                    },
                    "devices": [{"name": "LIV Hub", "serial_num": "SN123"}],
                }
            )

        groups_app.router.add_get("/v1/user/nodes/params", get_params)
        groups_app.router.add_get("/v1/user/nodes/status", get_status)
        groups_app.router.add_get("/v1/user/nodes/config", get_config)

        client = await aiohttp_client(groups_app)

        thermacell_client = ThermacellClient(
            username="test@example.com",
            password="password",
            base_url=str(client.make_url("")),
        )
        thermacell_client._session = client.session
        thermacell_client._api._session = client.session
        thermacell_client._api._auth_handler = mock_auth
        thermacell_client._owns_session = False
        thermacell_client._auth_handler = mock_auth

        devices = await thermacell_client.get_group_devices("group-1")

        assert len(devices) == 3  # SAMPLE_GROUP_NODES_RESPONSE has 3 nodes
        assert all(hasattr(d, "node_id") for d in devices)
        assert all(hasattr(d, "name") for d in devices)

    async def test_get_group_devices_optimized(
        self,
        aiohttp_client: TestClient,
        mock_auth: AsyncMock,
    ) -> None:
        """Test that get_group_devices only fetches devices in the group (optimization)."""
        call_counts = {"nodes": 0, "params": 0, "status": 0, "config": 0}

        # Create custom app to count API calls
        app = web.Application()

        async def get_nodes_with_group(request: web.Request) -> web.Response:
            """Return nodes for specific group."""
            group_id = request.query.get("group_id")
            call_counts["nodes"] += 1
            if group_id == "group-1":
                # Group has 2 devices out of 10 total
                return web.json_response({"nodes": ["node-1", "node-2"], "total": 2})
            # All devices (should NOT be called)
            return web.json_response(
                {"nodes": [f"node-{i}" for i in range(1, 11)], "total": 10}
            )

        async def count_params(request: web.Request) -> web.Response:
            call_counts["params"] += 1
            return web.json_response(
                {
                    "LIV Hub": {
                        "Enable Repellers": True,
                        "LED Brightness": 80,
                        "LED Hue": 120,
                        "LED Saturation": 100,
                    }
                }
            )

        async def count_status(request: web.Request) -> web.Response:
            call_counts["status"] += 1
            return web.json_response({"connectivity": {"connected": True}})

        async def count_config(request: web.Request) -> web.Response:
            call_counts["config"] += 1
            node_id = request.query.get("nodeid", "node-1")
            return web.json_response(
                {
                    "node_id": node_id,
                    "info": {
                        "name": f"Device {node_id}",
                        "type": "thermacell-hub",
                        "fw_version": "5.3.2",
                    },
                    "devices": [{"name": "LIV Hub", "serial_num": "SN123"}],
                }
            )

        app.router.add_get("/v1/user/nodes", get_nodes_with_group)
        app.router.add_get("/v1/user/nodes/params", count_params)
        app.router.add_get("/v1/user/nodes/status", count_status)
        app.router.add_get("/v1/user/nodes/config", count_config)

        client = await aiohttp_client(app)

        thermacell_client = ThermacellClient(
            username="test@example.com",
            password="password",
            base_url=str(client.make_url("")),
        )
        thermacell_client._session = client.session
        thermacell_client._api._session = client.session
        thermacell_client._api._auth_handler = mock_auth
        thermacell_client._owns_session = False
        thermacell_client._auth_handler = mock_auth

        # Get devices for group with 2 devices (out of 10 total)
        devices = await thermacell_client.get_group_devices("group-1")

        # Verify we got the correct devices
        assert len(devices) == 2
        assert devices[0].node_id == "node-1"
        assert devices[1].node_id == "node-2"

        # Verify optimization: only 7 API calls instead of 32
        # 1 (get group nodes) + 2 * 3 (fetch 2 devices) = 7 calls
        # Old behavior would be: 1 (get group nodes) + 1 (get all nodes) + 10 * 3 (fetch all devices) = 32 calls
        assert call_counts["nodes"] == 1  # Only get group nodes
        assert call_counts["params"] == 2  # Only 2 devices fetched
        assert call_counts["status"] == 2
        assert call_counts["config"] == 2

    async def test_create_group_success(
        self,
        aiohttp_client: TestClient,
        groups_app: Application,
        mock_auth: AsyncMock,
    ) -> None:
        """Test creating a new group."""
        client = await aiohttp_client(groups_app)

        thermacell_client = ThermacellClient(
            username="test@example.com",
            password="password",
            base_url=str(client.make_url("")),
        )
        thermacell_client._session = client.session
        thermacell_client._api._session = client.session
        thermacell_client._api._auth_handler = mock_auth
        thermacell_client._owns_session = False
        thermacell_client._auth_handler = mock_auth

        group_id = await thermacell_client.create_group("Test Group")

        assert group_id == "new-group-123"

    async def test_create_group_with_nodes(
        self,
        aiohttp_client: TestClient,
        groups_app: Application,
        mock_auth: AsyncMock,
    ) -> None:
        """Test creating a new group with node list."""
        client = await aiohttp_client(groups_app)

        thermacell_client = ThermacellClient(
            username="test@example.com",
            password="password",
            base_url=str(client.make_url("")),
        )
        thermacell_client._session = client.session
        thermacell_client._api._session = client.session
        thermacell_client._api._auth_handler = mock_auth
        thermacell_client._owns_session = False
        thermacell_client._auth_handler = mock_auth

        group_id = await thermacell_client.create_group("Test Group", node_ids=["node-1", "node-2"])

        assert group_id == "new-group-123"

    async def test_create_group_empty_name(
        self,
        aiohttp_client: TestClient,
        groups_app: Application,
        mock_auth: AsyncMock,
    ) -> None:
        """Test creating a group with empty name raises ValueError."""
        client = await aiohttp_client(groups_app)

        thermacell_client = ThermacellClient(
            username="test@example.com",
            password="password",
            base_url=str(client.make_url("")),
        )
        thermacell_client._session = client.session
        thermacell_client._api._session = client.session
        thermacell_client._api._auth_handler = mock_auth
        thermacell_client._owns_session = False
        thermacell_client._auth_handler = mock_auth

        with pytest.raises(ValueError, match="Group name cannot be empty"):
            await thermacell_client.create_group("")

        with pytest.raises(ValueError, match="Group name cannot be empty"):
            await thermacell_client.create_group("   ")

    async def test_update_group_name(
        self,
        aiohttp_client: TestClient,
        groups_app: Application,
        mock_auth: AsyncMock,
    ) -> None:
        """Test updating group name."""
        client = await aiohttp_client(groups_app)

        thermacell_client = ThermacellClient(
            username="test@example.com",
            password="password",
            base_url=str(client.make_url("")),
        )
        thermacell_client._session = client.session
        thermacell_client._api._session = client.session
        thermacell_client._api._auth_handler = mock_auth
        thermacell_client._owns_session = False
        thermacell_client._auth_handler = mock_auth

        success = await thermacell_client.update_group("group-1", group_name="New Name")

        assert success is True

    async def test_update_group_nodes(
        self,
        aiohttp_client: TestClient,
        groups_app: Application,
        mock_auth: AsyncMock,
    ) -> None:
        """Test updating group nodes."""
        client = await aiohttp_client(groups_app)

        thermacell_client = ThermacellClient(
            username="test@example.com",
            password="password",
            base_url=str(client.make_url("")),
        )
        thermacell_client._session = client.session
        thermacell_client._api._session = client.session
        thermacell_client._api._auth_handler = mock_auth
        thermacell_client._owns_session = False
        thermacell_client._auth_handler = mock_auth

        success = await thermacell_client.update_group("group-1", node_ids=["node-1", "node-2", "node-3"])

        assert success is True

    async def test_update_group_not_found(
        self,
        aiohttp_client: TestClient,
        groups_app: Application,
        mock_auth: AsyncMock,
    ) -> None:
        """Test updating nonexistent group."""
        client = await aiohttp_client(groups_app)

        thermacell_client = ThermacellClient(
            username="test@example.com",
            password="password",
            base_url=str(client.make_url("")),
        )
        thermacell_client._session = client.session
        thermacell_client._api._session = client.session
        thermacell_client._api._auth_handler = mock_auth
        thermacell_client._owns_session = False
        thermacell_client._auth_handler = mock_auth

        success = await thermacell_client.update_group("nonexistent", group_name="New Name")

        assert success is False

    async def test_delete_group_success(
        self,
        aiohttp_client: TestClient,
        groups_app: Application,
        mock_auth: AsyncMock,
    ) -> None:
        """Test deleting a group."""
        client = await aiohttp_client(groups_app)

        thermacell_client = ThermacellClient(
            username="test@example.com",
            password="password",
            base_url=str(client.make_url("")),
        )
        thermacell_client._session = client.session
        thermacell_client._api._session = client.session
        thermacell_client._api._auth_handler = mock_auth
        thermacell_client._owns_session = False
        thermacell_client._auth_handler = mock_auth

        success = await thermacell_client.delete_group("group-1")

        assert success is True

    async def test_delete_group_not_found(
        self,
        aiohttp_client: TestClient,
        groups_app: Application,
        mock_auth: AsyncMock,
    ) -> None:
        """Test deleting nonexistent group."""
        client = await aiohttp_client(groups_app)

        thermacell_client = ThermacellClient(
            username="test@example.com",
            password="password",
            base_url=str(client.make_url("")),
        )
        thermacell_client._session = client.session
        thermacell_client._api._session = client.session
        thermacell_client._api._auth_handler = mock_auth
        thermacell_client._owns_session = False
        thermacell_client._auth_handler = mock_auth

        success = await thermacell_client.delete_group("nonexistent")

        assert success is False
