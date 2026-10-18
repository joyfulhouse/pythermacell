"""HTTP contracts checked against the Android Retrofit interface."""

from typing import Any
from unittest.mock import AsyncMock, MagicMock

from aiohttp import web

from pythermacell.api import ThermacellAPI


async def test_node_queries_and_empty_success(aiohttp_client: Any) -> None:
    """Use the APK's node_id query and accept a bodyless 204 response."""
    received = []

    async def endpoint(request: web.Request) -> web.Response:
        assert dict(request.query) == {"node_id": "test-hub"}
        assert request.headers["Authorization"] == "test-access-token"
        received.append(request.path)
        if request.method == "PUT":
            assert await request.json() == {"LIV Hub": {"Enable Repellers": False}}
            return web.Response(status=204, content_type="application/json")
        return web.json_response({})

    app = web.Application()
    for suffix in ("params", "config", "status"):
        app.router.add_get(f"/v1/user/nodes/{suffix}", endpoint)
    app.router.add_put("/v1/user/nodes/params", endpoint)
    http = await aiohttp_client(app)
    auth = MagicMock()
    auth.ensure_authenticated = AsyncMock()
    auth.should_retry_on_status.return_value = False
    auth.access_token = "test-access-token"
    api = ThermacellAPI(auth_handler=auth, session=http.session, base_url=str(http.make_url("/")))
    for method in (api.get_node_params, api.get_node_config, api.get_node_status):
        assert await method("test-hub") == (200, {})
    assert await api.update_node_params("test-hub", {"LIV Hub": {"Enable Repellers": False}}) == (204, {})
    assert len(received) == 4
