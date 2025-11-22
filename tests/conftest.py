"""Pytest configuration and shared fixtures."""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, MagicMock

import pytest
from aiohttp import ClientSession


if TYPE_CHECKING:
    from collections.abc import AsyncGenerator


@pytest.fixture
async def mock_session() -> AsyncGenerator[ClientSession]:
    """Create a mock aiohttp ClientSession.

    Yields:
        Mock ClientSession for testing.
    """
    session = AsyncMock(spec=ClientSession)
    session.closed = False

    async def mock_close() -> None:
        session.closed = True

    session.close = mock_close

    yield session

    if not session.closed:
        await session.close()


@pytest.fixture
def mock_response() -> MagicMock:
    """Create a mock aiohttp ClientResponse.

    Returns:
        Mock ClientResponse for testing.
    """
    response = MagicMock()
    response.status = 200
    response.headers = {}
    return response
