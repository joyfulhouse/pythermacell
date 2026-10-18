"""Safety and reporting regressions; all peers here are simulators, never live evidence."""

from __future__ import annotations

import argparse
import asyncio
import json
from copy import deepcopy
from typing import TYPE_CHECKING, Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from aiohttp import web

from pythermacell import diagnostics
from pythermacell._proto.local_pb2 import LocalCtrlMessage
from pythermacell.local import LocalTransport
from pythermacell.parsers import parse_device_state
from pythermacell.services import HubServices
from tests.test_local import HubPeer


if TYPE_CHECKING:
    from pathlib import Path


class DiagnosticPeer(HubPeer):
    """Plaintext advertised test peer with mutable LED state and realistic metadata."""

    def __init__(self) -> None:
        super().__init__(0, 0)
        self.config = {
            "node_id": "hub",
            "info": {"fw_version": "test-firmware"},
            "devices": [
                {
                    "name": "LIV Hub",
                    "params": [{"name": name, "properties": ["read", "write"]} for name in diagnostics.LED_NAMES],
                }
            ],
            "services": [
                {
                    "name": "Local Control",
                    "type": "esp.service.local_control",
                    "params": [
                        {"name": name, "type": f"esp.param.local_control_{kind}"}
                        for name, kind in (("Type", "type"), ("PoP", "pop"), ("Username", "username"))
                    ],
                }
            ],
        }
        self.params = {
            "LIV Hub": {"LED Brightness": 75, "LED Hue": 240, "LED Saturation": 100, "LED Power": True},
            "Local Control": {"Type": 0, "PoP": "hidden-pop", "Username": "hidden-username"},
        }

    async def control(self, request: web.Request) -> web.Response:
        assert "Authorization" not in request.headers
        packet = LocalCtrlMessage.FromString(await request.read())
        reply = LocalCtrlMessage()
        if packet.msg == 0:
            reply.msg = 1
            reply.resp_get_prop_count.count = 2
        elif packet.msg == 4:
            reply.msg = 5
            for name, value, flags in (("config", self.config, 1), ("params", self.params, int(self.readonly))):
                prop = reply.resp_get_prop_vals.props.add()
                prop.name, prop.value, prop.flags = name, json.dumps(value).encode(), flags
        else:
            assert packet.msg == 6
            payload = json.loads(packet.cmd_set_prop_vals.props[0].value)
            self.writes.append(payload)
            self.params["LIV Hub"].update(payload["LIV Hub"])
            reply.msg = 7
            reply.resp_set_prop_vals.status = 0
        return web.Response(body=reply.SerializeToString())


@pytest.fixture
async def diagnostic_peer(aiohttp_client: Any) -> Any:
    peer = DiagnosticPeer()
    app = web.Application()
    app.router.add_post("/esp_local_ctrl/session", peer.session)
    app.router.add_post("/esp_local_ctrl/control", peer.control)
    http = await aiohttp_client(app)
    url = http.make_url("/")
    record = {"node_id": "hub", "host": "test.local.", "port": url.port, "addresses": [url.host]}
    state = parse_device_state("hub", peer.params, {}, peer.config)
    services = HubServices(MagicMock(), lambda: state)
    return peer, record, services


async def diagnose(
    peer: DiagnosticPeer, record: dict[str, Any], services: HubServices, *, write: bool
) -> dict[str, Any]:
    return await diagnostics.diagnose_node(
        "hub", peer.config, peer.params, [record], services=services, write_led=write
    )


async def test_readonly_stages_use_direct_transport(diagnostic_peer: Any) -> None:
    peer, record, services = diagnostic_peer
    report = await diagnose(peer, record, services, write=False)
    for name in ("discovery", "handshake", "identity", "properties"):
        assert report["stages"][name]["status"] == "passed"
    assert report["stages"]["metadata"]["security_type"] == 0
    assert report["local_firmware"] == "test-firmware"
    assert report["stages"]["led_write"]["status"] == "not_performed"
    assert not peer.writes


async def test_led_changes_one_value_and_restores_all(diagnostic_peer: Any) -> None:
    peer, record, services = diagnostic_peer
    before = deepcopy(peer.params)
    report = await diagnose(peer, record, services, write=True)
    assert peer.writes == [{"LIV Hub": {"LED Brightness": 74}}, {"LIV Hub": {"LED Brightness": 75}}]
    assert peer.params == before
    assert report["stages"]["led_readback"]["values"]["LED Brightness"] == 74
    assert report["stages"]["restore"] == {"status": "passed", "values": before["LIV Hub"]}


@pytest.mark.parametrize("failure", ["identity", "missing_metadata", "readonly", "unknown_led", "missing_led"])
async def test_unsafe_or_unsupported_nodes_never_write(diagnostic_peer: Any, failure: str) -> None:
    peer, record, services = diagnostic_peer
    if failure == "identity":
        peer.config["node_id"] = "different-node"
    elif failure == "missing_metadata":
        peer.config["services"] = []
    elif failure == "readonly":
        peer.readonly = True
    elif failure == "unknown_led":
        peer.params["LIV Hub"]["LED Unknown"] = 12
    else:
        del peer.params["LIV Hub"]["LED Hue"]
    report = await diagnose(peer, record, services, write=True)
    assert not peer.writes
    assert report["stages"]["led_write"]["status"] != "passed"
    if failure == "identity":
        assert report["stages"]["handshake"]["status"] == "passed"
        assert report["stages"]["identity"]["status"] == "failed"


async def test_no_discovery_does_not_guess_endpoint(diagnostic_peer: Any) -> None:
    peer, _, services = diagnostic_peer
    report = await diagnostics.diagnose_node("hub", peer.config, peer.params, [], services=services, write_led=True)
    assert report["stages"]["discovery"] == {"status": "not_found", "records": []}
    assert report["stages"]["handshake"]["status"] == "not_performed"
    assert not peer.writes


async def test_handshake_failure_has_its_own_stage(diagnostic_peer: Any) -> None:
    peer, record, services = diagnostic_peer
    peer.params["Local Control"]["Type"] = 9
    report = await diagnose(peer, record, services, write=False)
    assert report["stages"]["metadata"]["security_type"] == 9
    assert report["stages"]["handshake"]["status"] == "not_performed"
    peer.params["Local Control"]["Type"] = 1
    report = await diagnose(peer, record, services, write=False)
    assert report["stages"]["handshake"]["status"] == "failed"
    assert report["stages"]["identity"]["status"] == "not_performed"
    assert report["stages"]["properties"]["status"] == "not_performed"
    assert not peer.writes


@pytest.mark.parametrize("failure", ["timeout", "readback", "cancel"])
async def test_finally_restores_uncertain_write_and_cancellation(failure: str) -> None:
    peer = DiagnosticPeer()
    transport = AsyncMock(spec=LocalTransport)
    transport.read.return_value = (peer.config, peer.params)
    if failure == "timeout":
        transport.write.side_effect = [TimeoutError("hidden-session-key"), None]
    elif failure == "cancel":
        transport.write.side_effect = [asyncio.CancelledError(), None]
    else:
        transport.read.side_effect = [
            (peer.config, peer.params),
            ValueError("hidden-cookie"),
            (peer.config, peer.params),
        ]
    report = diagnostics.new_report("hub")
    if failure == "cancel":
        with pytest.raises(asyncio.CancelledError):
            await diagnostics.exercise_led(transport, report)
    else:
        await diagnostics.exercise_led(transport, report)
    assert transport.write.await_count == 2
    assert transport.write.await_args.args == ({"LIV Hub": {"LED Brightness": 75}},)
    assert report["stages"]["restore"]["status"] == "passed"
    assert "hidden-" not in json.dumps(report)


@pytest.mark.parametrize("failure", ["write", "read", "mismatch"])
async def test_restore_failure_is_loud(failure: str, capsys: pytest.CaptureFixture[str]) -> None:
    peer = DiagnosticPeer()
    original = deepcopy(peer.params["LIV Hub"])
    transport = AsyncMock(spec=LocalTransport)
    transport.read.return_value = (peer.config, peer.params)
    if failure == "write":
        transport.write.side_effect = TimeoutError("secret-token")
    elif failure == "read":
        transport.read.side_effect = TimeoutError("secret-token")
    else:
        peer.params["LIV Hub"]["LED Hue"] = 241
    report = diagnostics.new_report("hub")
    await diagnostics.restore_led(transport, original, report)
    assert report["stages"]["restore"]["status"] == "RESTORE_FAILED"
    err = capsys.readouterr().err
    assert "RESTORE_FAILED" in err
    assert json.dumps(original) in err
    assert "secret-token" not in err


async def test_restore_failure_stops_later_hubs_and_exits_nonzero(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(
        diagnostics, "account_nodes", AsyncMock(return_value=[("first", {}, {}, None), ("second", {}, {}, None)])
    )
    monkeypatch.setattr(diagnostics, "discover", AsyncMock(return_value=[]))
    report = diagnostics.new_report("first")
    diagnostics.stage(report, "restore", "RESTORE_FAILED")
    monkeypatch.setattr(diagnostics, "new_report", lambda node: report)
    probe = AsyncMock(return_value=report)
    monkeypatch.setattr(diagnostics, "diagnose_node", probe)
    args = argparse.Namespace(output=tmp_path, discovery_seconds=1, node_id=None, write_led=True, deny_cloud=False)
    assert await diagnostics.run(args) == 3
    assert probe.await_count == 1


async def test_cancellation_during_cleanup_waits_for_verified_restore() -> None:
    peer = DiagnosticPeer()
    entered = asyncio.Event()
    release = asyncio.Event()
    transport = AsyncMock(spec=LocalTransport)
    transport.read.return_value = (peer.config, peer.params)

    async def write(values: dict[str, Any]) -> None:
        if values["LIV Hub"]["LED Brightness"] == 75:
            entered.set()
            await release.wait()

    transport.write.side_effect = write
    report = diagnostics.new_report("hub")
    task = asyncio.create_task(diagnostics.exercise_led(transport, report))
    await asyncio.wait_for(entered.wait(), 1)
    task.cancel()
    await asyncio.sleep(0)
    assert not task.done()
    release.set()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert report["stages"]["restore"]["status"] == "passed"


async def test_cancelled_hub_still_saves_report(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(diagnostics, "account_nodes", AsyncMock(return_value=[("hub", {}, {}, None)]))
    monkeypatch.setattr(diagnostics, "discover", AsyncMock(return_value=[]))
    monkeypatch.setattr(diagnostics, "diagnose_node", AsyncMock(side_effect=asyncio.CancelledError()))
    save = MagicMock()
    monkeypatch.setattr(diagnostics, "save_report", save)
    args = argparse.Namespace(output=tmp_path, discovery_seconds=1, node_id=None, write_led=True, deny_cloud=False)
    with pytest.raises(asyncio.CancelledError):
        await diagnostics.run(args)
    save.assert_called_once()


async def test_artifacts_redact_credentials_and_exceptions(
    diagnostic_peer: Any, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    peer, record, services = diagnostic_peer
    peer.config["password"] = "hidden-password"
    peer.params["LIV Hub"].update({"token": "hidden-token", "cookie": "hidden-cookie", "session_key": "hidden-key"})
    report = await diagnose(peer, record, services, write=False)
    report["source"] = "simulator"
    await asyncio.to_thread(diagnostics.save_report, tmp_path, report)
    output = capsys.readouterr().out

    def read_artifacts() -> str:
        text = ""
        for path in tmp_path.iterdir():
            text += path.read_text()
            assert path.stat().st_mode & 0o777 == 0o600
        assert tmp_path.stat().st_mode & 0o777 == 0o700
        return text

    output += await asyncio.to_thread(read_artifacts)
    assert "hidden-" not in output
    assert report["stages"]["metadata"]["pop_present"] is True
    assert report["stages"]["metadata"]["username_present"] is True


async def test_process_denial_blocks_cloud_but_allows_lan(
    diagnostic_peer: Any, aiohttp_client: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    peer, record, services = diagnostic_peer
    app = web.Application()
    app.router.add_get("/", lambda request: web.Response(text="cloud"))
    cloud = await aiohttp_client(app)
    monkeypatch.setattr(diagnostics, "CLOUD_URL", str(cloud.make_url("/")))
    with diagnostics.deny_cloud({(record["addresses"][0], record["port"])}) as evidence:
        await diagnostics.probe_denial(evidence)
        report = await diagnose(peer, record, services, write=False)
        assert evidence["status"] == "verified"
        assert evidence["blocked_connects"] > 0
        assert report["stages"]["properties"]["status"] == "passed"
    response = await cloud.get("/")
    assert await response.text() == "cloud"


async def test_unverified_denial_disables_writes_and_fails(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(diagnostics, "account_nodes", AsyncMock(return_value=[("hub", {}, {}, None)]))
    monkeypatch.setattr(diagnostics, "discover", AsyncMock(return_value=[]))

    async def probe(evidence: dict[str, Any]) -> None:
        evidence["status"] = "unverified"

    async def successful_read(*args: Any, **kwargs: Any) -> None:
        assert kwargs["write_led"] is False
        for name in ("handshake", "identity", "properties"):
            diagnostics.stage(kwargs["report"], name, "passed")

    monkeypatch.setattr(diagnostics, "probe_denial", probe)
    monkeypatch.setattr(diagnostics, "diagnose_node", successful_read)
    args = argparse.Namespace(output=tmp_path, discovery_seconds=1, node_id=None, write_led=True, deny_cloud=True)
    assert await diagnostics.run(args) == 2


def test_cli_defaults_are_readonly(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    runner = AsyncMock(return_value=0)
    monkeypatch.setattr(diagnostics, "run", runner)
    monkeypatch.setattr("sys.argv", ["lan", "--output", str(tmp_path)])
    assert diagnostics.main() == 0
    assert runner.await_args.args[0].write_led is False
    assert runner.await_args.args[0].deny_cloud is False
