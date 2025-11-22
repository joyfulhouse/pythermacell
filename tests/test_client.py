"""Comprehensive tests for ThermacellClient using pytest-aiohttp."""

from __future__ import annotations

from http import HTTPStatus
from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, MagicMock

import pytest
from aiohttp import web

from pythermacell.client import ThermacellClient
from pythermacell.exceptions import DeviceError


if TYPE_CHECKING:
    from aiohttp.test_utils import TestClient
    from aiohttp.web import Application


# Sample API responses
SAMPLE_NODES_RESPONSE = {"nodes": ["node1", "node2"]}

SAMPLE_PARAMS_RESPONSE = {
    "LIV Hub": {
        "Power": True,
        "LED Power": True,
        "LED Brightness": 80,
        "LED Hue": 120,
        "LED Saturation": 100,
        "Refill Life": 75.5,
        "System Runtime": 120,
        "System Status": 3,
        "Error": 0,
        "Enable Repellers": True,
    }
}

SAMPLE_STATUS_RESPONSE = {"connectivity": {"connected": True}}

SAMPLE_CONFIG_RESPONSE = {
    "node_id": "node1",
    "info": {
        "name": "Test Device",
        "type": "thermacell-hub",
        "fw_version": "5.3.2",
    },
    "devices": [{"name": "LIV Hub", "serial_num": "SN123456"}],
}


@pytest.fixture
def app() -> Application:
    """Create a test aiohttp application."""
    app = web.Application()

    async def get_nodes(request: web.Request) -> web.Response:
        """Mock /v1/user/nodes endpoint."""
        return web.json_response(SAMPLE_NODES_RESPONSE)

    async def get_params(request: web.Request) -> web.Response:
        """Mock /v1/user/nodes/params endpoint."""
        node_id = request.query.get("nodeid")
        if node_id == "nonexistent":
            return web.Response(status=HTTPStatus.NOT_FOUND)
        return web.json_response(SAMPLE_PARAMS_RESPONSE)

    async def get_status(request: web.Request) -> web.Response:
        """Mock /v1/user/nodes/status endpoint."""
        return web.json_response(SAMPLE_STATUS_RESPONSE)

    async def get_config(request: web.Request) -> web.Response:
        """Mock /v1/user/nodes/config endpoint."""
        node_id = request.query.get("nodeid")
        config = SAMPLE_CONFIG_RESPONSE.copy()
        config["node_id"] = node_id or "node1"
        if node_id == "node2":
            config["info"] = {
                "name": "Device 2",
                "type": "thermacell-hub",
                "fw_version": "5.3.2",
            }
        return web.json_response(config)

    async def update_params(request: web.Request) -> web.Response:
        """Mock PUT /v1/user/nodes/params endpoint."""
        return web.Response(status=HTTPStatus.OK)

    async def error_endpoint(request: web.Request) -> web.Response:
        """Mock endpoint that returns error."""
        return web.Response(status=HTTPStatus.INTERNAL_SERVER_ERROR)

    # Register routes
    app.router.add_get("/v1/user/nodes", get_nodes)
    app.router.add_get("/v1/user/nodes/params", get_params)
    app.router.add_get("/v1/user/nodes/status", get_status)
    app.router.add_get("/v1/user/nodes/config", get_config)
    app.router.add_put("/v1/user/nodes/params", update_params)
    app.router.add_get("/v1/error", error_endpoint)

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
    auth.set_session = MagicMock()  # Add set_session method
    auth.__aenter__ = AsyncMock(return_value=auth)
    auth.__aexit__ = AsyncMock()
    return auth


class TestClientGetDevices:
    """Test client.get_devices() method."""

    async def test_get_devices_success(
        self,
        aiohttp_client: TestClient,
        app: Application,
        mock_auth: AsyncMock,
    ) -> None:
        """Test successfully getting device list."""
        client = await aiohttp_client(app)

        # Create Thermacell client with test server
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

        devices = await thermacell_client.get_devices()

        assert len(devices) == 2
        assert devices[0].node_id == "node1"
        assert devices[0].name == "Test Device"
        assert devices[0].is_powered_on is True
        assert devices[0].firmware_version == "5.3.2"
        assert devices[1].node_id == "node2"
        assert devices[1].name == "Device 2"

    async def test_get_devices_empty_list(
        self,
        aiohttp_client: TestClient,
        mock_auth: AsyncMock,
    ) -> None:
        """Test getting devices when none exist."""
        app = web.Application()

        async def get_empty_nodes(request: web.Request) -> web.Response:
            return web.json_response({"nodes": []})

        app.router.add_get("/v1/user/nodes", get_empty_nodes)
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

        devices = await thermacell_client.get_devices()

        assert len(devices) == 0

    async def test_get_devices_api_error(
        self,
        aiohttp_client: TestClient,
        mock_auth: AsyncMock,
    ) -> None:
        """Test get_devices handles API errors."""
        app = web.Application()

        async def get_error(request: web.Request) -> web.Response:
            return web.Response(status=HTTPStatus.INTERNAL_SERVER_ERROR)

        app.router.add_get("/v1/user/nodes", get_error)
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

        with pytest.raises(DeviceError, match="Failed to get devices"):
            await thermacell_client.get_devices()


class TestClientGetDevice:
    """Test client.get_device() method."""

    async def test_get_device_success(
        self,
        aiohttp_client: TestClient,
        app: Application,
        mock_auth: AsyncMock,
    ) -> None:
        """Test successfully getting a single device."""
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

        device = await thermacell_client.get_device("node1")

        assert device is not None
        assert device.node_id == "node1"
        assert device.name == "Test Device"
        assert device.power is True
        assert device.led_brightness == 80

    async def test_get_device_not_found(
        self,
        aiohttp_client: TestClient,
        app: Application,
        mock_auth: AsyncMock,
    ) -> None:
        """Test getting device that doesn't exist."""
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

        device = await thermacell_client.get_device("nonexistent")

        assert device is None

    async def test_get_device_cached_no_refresh(
        self,
        aiohttp_client: TestClient,
        app: Application,
        mock_auth: AsyncMock,
    ) -> None:
        """Test getting cached device without refresh (0 API calls)."""
        call_counts = {"params": 0, "status": 0, "config": 0}

        # Create custom app to count API calls
        app_with_counter = web.Application()

        async def count_params(request: web.Request) -> web.Response:
            call_counts["params"] += 1
            return web.json_response(SAMPLE_PARAMS_RESPONSE)

        async def count_status(request: web.Request) -> web.Response:
            call_counts["status"] += 1
            return web.json_response(SAMPLE_STATUS_RESPONSE)

        async def count_config(request: web.Request) -> web.Response:
            call_counts["config"] += 1
            node_id = request.query.get("nodeid")
            config = SAMPLE_CONFIG_RESPONSE.copy()
            config["node_id"] = node_id or "node1"
            return web.json_response(config)

        app_with_counter.router.add_get("/v1/user/nodes/params", count_params)
        app_with_counter.router.add_get("/v1/user/nodes/status", count_status)
        app_with_counter.router.add_get("/v1/user/nodes/config", count_config)

        test_client = await aiohttp_client(app_with_counter)
        thermacell_client = ThermacellClient(
            username="test@example.com",
            password="password",
            base_url=str(test_client.make_url("")),
        )
        thermacell_client._session = test_client.session
        thermacell_client._api._session = test_client.session
        thermacell_client._api._auth_handler = mock_auth
        thermacell_client._owns_session = False
        thermacell_client._auth_handler = mock_auth

        # First call: fetch device (3 API calls)
        device1 = await thermacell_client.get_device("node1")
        assert device1 is not None
        assert call_counts["params"] == 1
        assert call_counts["status"] == 1
        assert call_counts["config"] == 1

        # Second call: return cached device without refresh (0 API calls)
        device2 = await thermacell_client.get_device("node1", force_refresh=False)
        assert device2 is device1  # Same instance
        assert call_counts["params"] == 1  # No additional calls
        assert call_counts["status"] == 1
        assert call_counts["config"] == 1

    async def test_get_device_force_refresh(
        self,
        aiohttp_client: TestClient,
        app: Application,
        mock_auth: AsyncMock,
    ) -> None:
        """Test force_refresh parameter refreshes cached device."""
        call_counts = {"params": 0, "status": 0, "config": 0}

        # Create custom app to count API calls
        app_with_counter = web.Application()

        async def count_params(request: web.Request) -> web.Response:
            call_counts["params"] += 1
            return web.json_response(SAMPLE_PARAMS_RESPONSE)

        async def count_status(request: web.Request) -> web.Response:
            call_counts["status"] += 1
            return web.json_response(SAMPLE_STATUS_RESPONSE)

        async def count_config(request: web.Request) -> web.Response:
            call_counts["config"] += 1
            node_id = request.query.get("nodeid")
            config = SAMPLE_CONFIG_RESPONSE.copy()
            config["node_id"] = node_id or "node1"
            return web.json_response(config)

        app_with_counter.router.add_get("/v1/user/nodes/params", count_params)
        app_with_counter.router.add_get("/v1/user/nodes/status", count_status)
        app_with_counter.router.add_get("/v1/user/nodes/config", count_config)

        test_client = await aiohttp_client(app_with_counter)
        thermacell_client = ThermacellClient(
            username="test@example.com",
            password="password",
            base_url=str(test_client.make_url("")),
        )
        thermacell_client._session = test_client.session
        thermacell_client._api._session = test_client.session
        thermacell_client._api._auth_handler = mock_auth
        thermacell_client._owns_session = False
        thermacell_client._auth_handler = mock_auth

        # First call: fetch device (3 API calls)
        device1 = await thermacell_client.get_device("node1")
        assert device1 is not None
        assert call_counts["params"] == 1
        assert call_counts["status"] == 1
        assert call_counts["config"] == 1

        # Second call with force_refresh: refresh device (3 more API calls)
        device2 = await thermacell_client.get_device("node1", force_refresh=True)
        assert device2 is device1  # Same instance
        assert call_counts["params"] == 2  # Refreshed
        assert call_counts["status"] == 2  # Refreshed
        assert call_counts["config"] == 2  # Refreshed

    async def test_get_device_max_age_not_stale(
        self,
        aiohttp_client: TestClient,
        app: Application,
        mock_auth: AsyncMock,
    ) -> None:
        """Test max_age_seconds doesn't refresh if state is fresh."""
        call_counts = {"params": 0, "status": 0, "config": 0}

        # Create custom app to count API calls
        app_with_counter = web.Application()

        async def count_params(request: web.Request) -> web.Response:
            call_counts["params"] += 1
            return web.json_response(SAMPLE_PARAMS_RESPONSE)

        async def count_status(request: web.Request) -> web.Response:
            call_counts["status"] += 1
            return web.json_response(SAMPLE_STATUS_RESPONSE)

        async def count_config(request: web.Request) -> web.Response:
            call_counts["config"] += 1
            node_id = request.query.get("nodeid")
            config = SAMPLE_CONFIG_RESPONSE.copy()
            config["node_id"] = node_id or "node1"
            return web.json_response(config)

        app_with_counter.router.add_get("/v1/user/nodes/params", count_params)
        app_with_counter.router.add_get("/v1/user/nodes/status", count_status)
        app_with_counter.router.add_get("/v1/user/nodes/config", count_config)

        test_client = await aiohttp_client(app_with_counter)
        thermacell_client = ThermacellClient(
            username="test@example.com",
            password="password",
            base_url=str(test_client.make_url("")),
        )
        thermacell_client._session = test_client.session
        thermacell_client._api._session = test_client.session
        thermacell_client._api._auth_handler = mock_auth
        thermacell_client._owns_session = False
        thermacell_client._auth_handler = mock_auth

        # First call: fetch device (3 API calls)
        device1 = await thermacell_client.get_device("node1")
        assert device1 is not None
        assert call_counts["params"] == 1

        # Second call with max_age_seconds=60: state is fresh, no refresh (0 API calls)
        device2 = await thermacell_client.get_device("node1", max_age_seconds=60)
        assert device2 is device1
        assert call_counts["params"] == 1  # No refresh
        assert call_counts["status"] == 1
        assert call_counts["config"] == 1

    async def test_get_device_max_age_stale(
        self,
        aiohttp_client: TestClient,
        app: Application,
        mock_auth: AsyncMock,
    ) -> None:
        """Test max_age_seconds refreshes if state is stale."""
        import asyncio

        call_counts = {"params": 0, "status": 0, "config": 0}

        # Create custom app to count API calls
        app_with_counter = web.Application()

        async def count_params(request: web.Request) -> web.Response:
            call_counts["params"] += 1
            return web.json_response(SAMPLE_PARAMS_RESPONSE)

        async def count_status(request: web.Request) -> web.Response:
            call_counts["status"] += 1
            return web.json_response(SAMPLE_STATUS_RESPONSE)

        async def count_config(request: web.Request) -> web.Response:
            call_counts["config"] += 1
            node_id = request.query.get("nodeid")
            config = SAMPLE_CONFIG_RESPONSE.copy()
            config["node_id"] = node_id or "node1"
            return web.json_response(config)

        app_with_counter.router.add_get("/v1/user/nodes/params", count_params)
        app_with_counter.router.add_get("/v1/user/nodes/status", count_status)
        app_with_counter.router.add_get("/v1/user/nodes/config", count_config)

        test_client = await aiohttp_client(app_with_counter)
        thermacell_client = ThermacellClient(
            username="test@example.com",
            password="password",
            base_url=str(test_client.make_url("")),
        )
        thermacell_client._session = test_client.session
        thermacell_client._api._session = test_client.session
        thermacell_client._api._auth_handler = mock_auth
        thermacell_client._owns_session = False
        thermacell_client._auth_handler = mock_auth

        # First call: fetch device (3 API calls)
        device1 = await thermacell_client.get_device("node1")
        assert device1 is not None
        assert call_counts["params"] == 1

        # Wait for state to become stale
        await asyncio.sleep(0.2)

        # Second call with max_age_seconds=0.1: state is stale, refresh (3 API calls)
        device2 = await thermacell_client.get_device("node1", max_age_seconds=0.1)
        assert device2 is device1
        assert call_counts["params"] == 2  # Refreshed
        assert call_counts["status"] == 2  # Refreshed
        assert call_counts["config"] == 2  # Refreshed


class TestClientAuthenticationIntegration:
    """Test authentication integration."""

    async def test_reauthentication_on_401(
        self,
        aiohttp_client: TestClient,
        mock_auth: AsyncMock,
    ) -> None:
        """Test automatic reauthentication on 401."""
        app = web.Application()
        call_count = {"count": 0}

        async def get_nodes_with_auth_retry(request: web.Request) -> web.Response:
            call_count["count"] += 1
            if call_count["count"] == 1:
                # First call returns 401
                return web.Response(status=HTTPStatus.UNAUTHORIZED)
            # Second call succeeds
            return web.json_response({"nodes": []})

        app.router.add_get("/v1/user/nodes", get_nodes_with_auth_retry)
        client = await aiohttp_client(app)

        # Configure mock auth to trigger retry
        mock_auth.should_retry_on_status = MagicMock(side_effect=lambda status: status == HTTPStatus.UNAUTHORIZED)
        mock_auth.handle_auth_retry = AsyncMock()

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

        devices = await thermacell_client.get_devices()

        assert len(devices) == 0
        assert call_count["count"] == 2
        mock_auth.handle_auth_retry.assert_called_once_with(HTTPStatus.UNAUTHORIZED)


class TestClientInitialization:
    """Test client initialization."""

    def test_init_with_credentials(self) -> None:
        """Test initialization with username and password."""
        client = ThermacellClient(
            username="test@example.com",
            password="password123",
        )

        # Credentials are stored in auth handler, base_url in API
        assert client._auth_handler is not None
        assert client._api is not None
        assert client._api._base_url == "https://api.iot.thermacell.com"
        assert client._api._session is None
        assert client._api._owns_session is True

    def test_init_with_custom_base_url(self) -> None:
        """Test initialization with custom base URL."""
        client = ThermacellClient(
            username="test@example.com",
            password="password123",
            base_url="https://custom.api.com/",
        )

        assert client._api._base_url == "https://custom.api.com"

    async def test_init_with_session(self, aiohttp_client: TestClient) -> None:
        """Test initialization with provided session."""
        app = web.Application()
        test_client = await aiohttp_client(app)

        client = ThermacellClient(
            username="test@example.com",
            password="password123",
            session=test_client.session,
        )

        # Session is stored in API layer
        assert client._api._session == test_client.session
        assert client._api._owns_session is False

    def test_init_creates_auth_handler(self) -> None:
        """Test initialization creates auth handler."""
        client = ThermacellClient(
            username="test@example.com",
            password="password123",
        )

        assert client._auth_handler is not None
        assert client._api is not None


class TestClientContextManager:
    """Test client context manager."""

    async def test_context_manager_creates_session(self, mock_auth: AsyncMock) -> None:
        """Test context manager creates session when not provided."""
        client = ThermacellClient(
            username="test@example.com",
            password="password123",
        )
        client._auth_handler = mock_auth
        client._api._auth_handler = mock_auth

        async with client:
            # Session is created in API layer
            assert client._api._session is not None
            assert client._api._owns_session is True

    async def test_context_manager_closes_owned_session(self, mock_auth: AsyncMock) -> None:
        """Test context manager closes session it created."""
        client = ThermacellClient(
            username="test@example.com",
            password="password123",
        )
        client._auth_handler = mock_auth
        client._api._auth_handler = mock_auth

        async with client:
            # Session is created in API layer
            session = client._api._session
            assert session is not None
            assert not session.closed

        assert session.closed

    async def test_context_manager_does_not_close_provided_session(
        self,
        aiohttp_client: TestClient,
        mock_auth: AsyncMock,
    ) -> None:
        """Test context manager doesn't close injected session."""
        app = web.Application()
        test_client = await aiohttp_client(app)

        client = ThermacellClient(
            username="test@example.com",
            password="password123",
            session=test_client.session,
        )
        client._auth_handler = mock_auth
        client._api._auth_handler = mock_auth

        async with client:
            pass

        assert not test_client.session.closed
