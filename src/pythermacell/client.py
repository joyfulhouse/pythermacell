"""Device manager and coordinator for Thermacell devices.

This module provides high-level device management, coordinating between
the low-level API layer and stateful device objects.
"""

from __future__ import annotations

import asyncio
import logging
from http import HTTPStatus
from typing import TYPE_CHECKING

from aiohttp import ClientSession  # noqa: TC002 - Used at runtime for isinstance checks

from pythermacell.api import ThermacellAPI
from pythermacell.auth import AuthenticationHandler
from pythermacell.const import DEFAULT_BASE_URL
from pythermacell.devices import ThermacellDevice
from pythermacell.exceptions import DeviceError
from pythermacell.models import DeviceState, Group
from pythermacell.serializers import deserialize_device_state


if TYPE_CHECKING:
    from types import TracebackType

    from pythermacell.resilience import CircuitBreaker, ExponentialBackoff, RateLimiter

_LOGGER = logging.getLogger(__name__)


class ThermacellClient:
    """Device manager and coordinator for Thermacell devices.

    This class manages the lifecycle of Thermacell device objects, coordinates
    state updates, and provides high-level operations for device discovery
    and group management.

    The client uses a low-level ThermacellAPI for HTTP communication and creates
    stateful ThermacellDevice objects that maintain their own state and provide
    optimistic updates.

    Example:
        Basic usage with automatic session management:

        ```python
        from pythermacell import ThermacellClient

        async with ThermacellClient(username="user@example.com", password="password") as client:
            # Discover devices
            devices = await client.get_devices()

            # Control devices (with optimistic updates)
            for device in devices:
                await device.turn_on()
                await device.set_led_color(hue=120, brightness=80)

            # Access cached state
            print(f"Refill life: {device.refill_life}%")
        ```

        Advanced usage with session injection and resilience patterns:

        ```python
        from aiohttp import ClientSession
        from pythermacell import ThermacellClient
        from pythermacell.resilience import CircuitBreaker, ExponentialBackoff

        async with ClientSession() as session:
            breaker = CircuitBreaker(failure_threshold=5)
            backoff = ExponentialBackoff(max_retries=3)

            client = ThermacellClient(
                username="user@example.com",
                password="password",
                session=session,
                circuit_breaker=breaker,
                backoff=backoff,
            )

            async with client:
                devices = await client.get_devices()

                # Start auto-refresh for all devices
                for device in devices:
                    await device.start_auto_refresh(interval=60)
        ```

    Attributes:
        api: Low-level ThermacellAPI instance for HTTP communication.
    """

    def __init__(
        self,
        username: str,
        password: str,
        base_url: str = DEFAULT_BASE_URL,
        *,
        session: ClientSession | None = None,
        auth_handler: AuthenticationHandler | None = None,
        circuit_breaker: CircuitBreaker | None = None,
        backoff: ExponentialBackoff | None = None,
        rate_limiter: RateLimiter | None = None,
    ) -> None:
        """Initialize the Thermacell client.

        Args:
            username: User's email address for authentication.
            password: User's password for authentication.
            base_url: Base URL for the API. Defaults to Thermacell production API.
            session: Optional aiohttp ClientSession. If not provided, one will be
                created when entering the context manager.
            auth_handler: Optional pre-configured AuthenticationHandler. If not provided,
                one will be created with the given credentials.
            circuit_breaker: Optional CircuitBreaker for fault tolerance.
            backoff: Optional ExponentialBackoff for retry logic.
            rate_limiter: Optional RateLimiter for handling 429 responses.
        """
        # Create or use provided auth handler
        if auth_handler is not None:
            self._auth_handler = auth_handler
        else:
            self._auth_handler = AuthenticationHandler(
                username=username,
                password=password,
                base_url=base_url,
                session=session,
                circuit_breaker=circuit_breaker,
                backoff=backoff,
                rate_limiter=rate_limiter,
            )

        # Create API client
        self._api = ThermacellAPI(
            auth_handler=self._auth_handler,
            session=session,
            base_url=base_url,
            circuit_breaker=circuit_breaker,
            backoff=backoff,
            rate_limiter=rate_limiter,
        )

        # Device cache for coordinated management
        self._devices: dict[str, ThermacellDevice] = {}

    @property
    def api(self) -> ThermacellAPI:
        """Get the underlying API client.

        This provides direct access to low-level API methods for advanced use cases.

        Returns:
            ThermacellAPI instance.
        """
        return self._api

    async def __aenter__(self) -> ThermacellClient:
        """Enter the context manager.

        Creates session if needed and authenticates with the API.

        Returns:
            Self for use in async with statements.
        """
        await self._api.__aenter__()
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        """Exit the context manager.

        Stops auto-refresh on all devices and closes the API client.

        Args:
            exc_type: Exception type if an exception occurred.
            exc_val: Exception value if an exception occurred.
            exc_tb: Exception traceback if an exception occurred.
        """
        # Stop auto-refresh on all devices
        for device in self._devices.values():
            await device.stop_auto_refresh()

        # Exit API context
        await self._api.__aexit__(exc_type, exc_val, exc_tb)

    async def get_devices(self) -> list[ThermacellDevice]:
        """Get all devices for the authenticated user.

        Fetches device states concurrently for improved performance.
        Returns cached device objects if they already exist.

        Returns:
            List of ThermacellDevice instances with cached state.

        Raises:
            DeviceError: If device discovery fails.
            ThermacellConnectionError: If connection fails.
        """
        # Get list of node IDs
        status, data = await self._api.get_nodes()

        if status != HTTPStatus.OK or data is None:
            msg = f"Failed to get devices: HTTP {status}"
            raise DeviceError(msg)

        node_ids = data.get("nodes", [])
        if not node_ids:
            return []

        # Fetch full state for all devices concurrently
        states = await asyncio.gather(
            *[self._fetch_device_state(node_id) for node_id in node_ids],
            return_exceptions=False,
        )

        # Create or update device objects
        devices: list[ThermacellDevice] = []
        for state in states:
            if state is not None:
                # Use cached device if available, otherwise create new
                if state.node_id in self._devices:
                    device = self._devices[state.node_id]
                    # Update state on existing device
                    await device._update_state(state)
                else:
                    # Create new device
                    device = ThermacellDevice(api=self._api, state=state)
                    self._devices[state.node_id] = device

                devices.append(device)

        return devices

    async def get_device(self, node_id: str) -> ThermacellDevice | None:
        """Get a specific device by node ID.

        Returns cached device object if available, otherwise creates a new one.

        Args:
            node_id: The device's node ID.

        Returns:
            ThermacellDevice instance if found, None otherwise.

        Raises:
            ThermacellConnectionError: If connection fails.
        """
        # Return cached device if available
        if node_id in self._devices:
            device = self._devices[node_id]
            # Refresh state
            await device.refresh()
            return device

        # Fetch state for new device
        state = await self._fetch_device_state(node_id)
        if state is None:
            return None

        # Create and cache device
        device = ThermacellDevice(api=self._api, state=state)
        self._devices[node_id] = device
        return device

    async def refresh_all(self) -> None:
        """Refresh state for all cached devices.

        This is useful for periodic polling when not using auto-refresh.
        """
        if not self._devices:
            return

        await asyncio.gather(
            *[device.refresh() for device in self._devices.values()],
            return_exceptions=True,
        )

    async def _fetch_device_state(self, node_id: str) -> DeviceState | None:
        """Fetch complete device state from API.

        This method fetches three separate API endpoints to build complete device state:
        1. /user/nodes/params - Device parameters (power, LED, refill, runtime, etc.)
        2. /user/nodes/status - Connectivity status (online/offline)
        3. /user/nodes/config - Device info (model, firmware, serial number)

        Args:
            node_id: The device's node ID.

        Returns:
            DeviceState instance if successful, None if device not found.
        """
        # Fetch all endpoints concurrently
        params_result, status_result, config_result = await asyncio.gather(
            self._api.get_node_params(node_id),
            self._api.get_node_status(node_id),
            self._api.get_node_config(node_id),
            return_exceptions=False,
        )

        params_status, params_data = params_result
        status_status, status_data = status_result
        config_status, config_data = config_result

        # Check for 404 Not Found
        if params_status == HTTPStatus.NOT_FOUND:
            _LOGGER.debug("Device %s not found", node_id)
            return None

        # Validate all requests succeeded
        if params_status != HTTPStatus.OK or params_data is None:
            _LOGGER.warning("Failed to fetch params for device %s: HTTP %d", node_id, params_status)
            return None

        if status_status != HTTPStatus.OK or status_data is None:
            _LOGGER.warning("Failed to fetch status for device %s: HTTP %d", node_id, status_status)
            return None

        if config_status != HTTPStatus.OK or config_data is None:
            _LOGGER.warning("Failed to fetch config for device %s: HTTP %d", node_id, config_status)
            return None

        # Parse responses into models using serializers
        return deserialize_device_state(
            node_id=node_id,
            params_data=params_data,
            status_data=status_data,
            config_data=config_data,
        )

    # -------------------------------------------------------------------------
    # Group Management
    # -------------------------------------------------------------------------

    async def get_groups(self) -> list[Group]:
        """Get all groups for the authenticated user.

        Returns:
            List of Group instances. Returns empty list if no groups exist.

        Raises:
            ThermacellConnectionError: If connection fails.
            AuthenticationError: If authentication fails.
        """
        status, data = await self._api.get_groups()

        if status != HTTPStatus.OK or data is None:
            _LOGGER.warning("Failed to get groups: HTTP %d", status)
            return []

        groups_data = data.get("groups", [])
        groups: list[Group] = []

        for group_data in groups_data:
            group = Group(
                group_id=group_data["group_id"],
                group_name=group_data["group_name"],
                is_matter=group_data.get("is_matter", False),
                primary=group_data.get("primary", False),
                total=group_data.get("total", 0),
            )
            groups.append(group)

        _LOGGER.debug("Found %d group(s)", len(groups))
        return groups

    async def get_group(self, group_id: str) -> Group | None:
        """Get a specific group by ID.

        Args:
            group_id: The group's unique identifier.

        Returns:
            Group instance if found, None otherwise.

        Raises:
            ThermacellConnectionError: If connection fails.
            AuthenticationError: If authentication fails.
        """
        status, data = await self._api.get_group(group_id)

        if status != HTTPStatus.OK or data is None:
            _LOGGER.warning("Failed to get group %s: HTTP %d", group_id, status)
            return None

        groups_data = data.get("groups", [])
        if not groups_data:
            _LOGGER.debug("Group %s not found", group_id)
            return None

        # API returns single-element array
        group_data = groups_data[0]
        return Group(
            group_id=group_data["group_id"],
            group_name=group_data["group_name"],
            is_matter=group_data.get("is_matter", False),
            primary=group_data.get("primary", False),
            total=group_data.get("total", 0),
        )

    async def get_group_nodes(self, group_id: str) -> list[str]:
        """Get node IDs belonging to a group.

        Args:
            group_id: The group's unique identifier.

        Returns:
            List of node IDs in the group. Returns empty list if group is empty or doesn't exist.

        Raises:
            ThermacellConnectionError: If connection fails.
            AuthenticationError: If authentication fails.
        """
        status, data = await self._api.get_group_nodes(group_id)

        if status != HTTPStatus.OK or data is None:
            _LOGGER.warning("Failed to get nodes for group %s: HTTP %d", group_id, status)
            return []

        nodes: list[str] = data.get("nodes", [])
        _LOGGER.debug("Group %s has %d node(s)", group_id, len(nodes))
        return nodes

    async def get_group_devices(self, group_id: str) -> list[ThermacellDevice]:
        """Get full device objects for all devices in a group.

        This is a convenience method that combines get_group_nodes() with get_devices()
        to return ThermacellDevice instances instead of just node IDs.

        Args:
            group_id: The group's unique identifier.

        Returns:
            List of ThermacellDevice instances in the group.

        Raises:
            ThermacellConnectionError: If connection fails.
            AuthenticationError: If authentication fails.
        """
        # Get node IDs in the group
        node_ids = await self.get_group_nodes(group_id)

        if not node_ids:
            return []

        # Get all devices
        all_devices = await self.get_devices()

        # Filter devices by group membership
        group_devices = [device for device in all_devices if device.node_id in node_ids]

        _LOGGER.debug("Group %s has %d device(s)", group_id, len(group_devices))
        return group_devices

    async def create_group(self, group_name: str, node_ids: list[str] | None = None) -> str:
        """Create a new group.

        Args:
            group_name: Name for the new group.
            node_ids: Optional list of node IDs to add to the group.

        Returns:
            The newly created group ID.

        Raises:
            ValueError: If group_name is empty.
            DeviceError: If creation fails.
            ThermacellConnectionError: If connection fails.
            AuthenticationError: If authentication fails.
        """
        if not group_name or not group_name.strip():
            msg = "Group name cannot be empty"
            raise ValueError(msg)

        _LOGGER.debug("Creating group '%s' with %d nodes", group_name, len(node_ids) if node_ids else 0)

        status, data = await self._api.create_group(group_name.strip(), node_ids)

        if status != HTTPStatus.OK or data is None:
            msg = f"Failed to create group: HTTP {status}"
            _LOGGER.error(msg)
            raise DeviceError(msg)

        group_id: str | None = data.get("group_id")
        if not group_id:
            msg = "No group_id returned from create group API"
            raise DeviceError(msg)

        _LOGGER.info("Successfully created group '%s' with ID %s", group_name, group_id)
        return group_id

    async def update_group(
        self,
        group_id: str,
        group_name: str | None = None,
        node_ids: list[str] | None = None,
    ) -> bool:
        """Update an existing group.

        Args:
            group_id: The group's unique identifier.
            group_name: Optional new name for the group.
            node_ids: Optional new list of node IDs (replaces existing nodes).

        Returns:
            True if successful, False otherwise.

        Raises:
            ValueError: If neither group_name nor node_ids is provided.
            ThermacellConnectionError: If connection fails.
            AuthenticationError: If authentication fails.
        """
        if not group_name and node_ids is None:
            msg = "Must provide either group_name or node_ids to update"
            raise ValueError(msg)

        # Get current group info to preserve unmodified fields
        current_group = await self.get_group(group_id)
        if not current_group:
            _LOGGER.warning("Group %s not found", group_id)
            return False

        # Use current name if not updating
        final_name = group_name.strip() if group_name else current_group.group_name

        _LOGGER.debug("Updating group %s", group_id)

        status, _ = await self._api.update_group(group_id, final_name, node_ids)

        success = status == HTTPStatus.OK
        if success:
            _LOGGER.info("Successfully updated group %s", group_id)
        else:
            _LOGGER.warning("Failed to update group %s: HTTP %d", group_id, status)

        return success

    async def delete_group(self, group_id: str) -> bool:
        """Delete a group.

        Args:
            group_id: The group's unique identifier.

        Returns:
            True if successful, False otherwise.

        Raises:
            ThermacellConnectionError: If connection fails.
            AuthenticationError: If authentication fails.
        """
        _LOGGER.debug("Deleting group %s", group_id)

        status, _ = await self._api.delete_group(group_id)

        success = status == HTTPStatus.OK
        if success:
            _LOGGER.info("Successfully deleted group %s", group_id)
        else:
            _LOGGER.warning("Failed to delete group %s: HTTP %d", group_id, status)

        return success
