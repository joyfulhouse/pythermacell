"""Pytest configuration and fixtures for integration tests."""

from __future__ import annotations

import asyncio
import os
from pathlib import Path
from typing import TYPE_CHECKING

import pytest
from dotenv import load_dotenv


if TYPE_CHECKING:
    from collections.abc import AsyncGenerator

    from pythermacell import ThermacellClient


# Load .env file from project root
env_path = Path(__file__).parents[2] / ".env"
load_dotenv(env_path)


@pytest.fixture(scope="session")
def integration_config() -> dict[str, str]:
    """Load integration test configuration from environment.

    Returns:
        Dictionary with API credentials and configuration.

    Raises:
        ValueError: If required environment variables are missing.
    """
    username = os.getenv("THERMACELL_USERNAME")
    password = os.getenv("THERMACELL_PASSWORD")
    base_url = os.getenv("THERMACELL_API_BASE_URL", "https://api.iot.thermacell.com")

    if not username or not password:
        msg = (
            "Missing required environment variables. "
            "Please create .env file with THERMACELL_USERNAME and THERMACELL_PASSWORD"
        )
        raise ValueError(msg)

    return {
        "username": username,
        "password": password,
        "base_url": base_url,
    }


@pytest.fixture(scope="session")
def test_node_id() -> str | None:
    """Get test node ID from environment if available.

    Returns:
        Node ID for testing, or None to use first discovered device.
    """
    return os.getenv("THERMACELL_TEST_NODE_ID")


# Shared client cache (module-scoped to avoid pytest-asyncio scope issues)
_client_cache: dict[str, ThermacellClient] = {}


@pytest.fixture
async def shared_integration_client(integration_config: dict[str, str]) -> AsyncGenerator:
    """Get or create a shared authenticated client for integration tests.

    Uses caching to reuse the same client across tests without session scope issues.
    This dramatically reduces API calls by authenticating once and reusing the client.

    Note: Each test invocation will enter/exit the client context manager, but the
    client and its auth token are cached so we don't re-authenticate. The session
    will be recreated for each test to avoid event loop closure issues, but the
    authentication token is reused.
    """
    from pythermacell import ThermacellClient

    cache_key = f"{integration_config['username']}@{integration_config['base_url']}"

    # Return or create cached client
    if cache_key not in _client_cache:
        # Create new client (will create session on first __aenter__)
        client = ThermacellClient(
            username=integration_config["username"],
            password=integration_config["password"],
            base_url=integration_config["base_url"],
        )
        _client_cache[cache_key] = client

    client = _client_cache[cache_key]

    # Clear session reference if it exists and is closed, so a new one gets created
    if client._session is not None and client._session.closed:
        client._session = None
        client._auth_handler._session = None

    # Enter context manager - creates session if needed, uses cached auth
    async with client:
        # Ensure we're authenticated (will use cached token if still valid)
        await client._auth_handler.ensure_authenticated()
        yield client
    # Session closes here, but client and auth token are cached


def pytest_configure(config: pytest.Config) -> None:
    """Register custom markers for integration tests."""
    config.addinivalue_line("markers", "integration: Integration tests requiring real API access")
    config.addinivalue_line("markers", "slow: Slow tests that may take several seconds")


@pytest.fixture(autouse=True)
async def rate_limit_delay(request: pytest.FixtureRequest) -> None:
    """Add delay between integration tests to prevent API rate limiting.

    This fixture automatically runs after each integration test to add a small
    delay, preventing the API from being overwhelmed when running the full test suite.

    The delay helps avoid:
    - API rate limiting (429 responses)
    - Device firmware overload
    - Devices going offline due to too many rapid commands
    """
    # Only apply to integration tests
    if "integration" in request.keywords:
        yield
        # Add 2-second delay after each integration test
        await asyncio.sleep(2.0)
    else:
        yield
