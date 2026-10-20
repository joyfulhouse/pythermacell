"""Safety and reporting regressions; all peers here are simulators, never live evidence."""

from __future__ import annotations

import argparse
import asyncio
import inspect
import json
import socket
from copy import deepcopy
from functools import partial
from typing import TYPE_CHECKING, Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from aiohttp import web

from pythermacell import diagnostics
from pythermacell._proto.local_pb2 import LocalCtrlMessage
from pythermacell.client import ThermacellClient
from pythermacell.exceptions import AuthenticationError, DeviceError, ThermacellConnectionError
from pythermacell.local import LocalTransport
from pythermacell.parsers import parse_device_state
from pythermacell.services import HubServices
from tests.test_local import HubPeer


if TYPE_CHECKING:
    from pathlib import Path


@pytest.fixture(autouse=True)
def isolated_credentials(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(diagnostics, "_CREDENTIALS", set(), raising=False)
    diagnostics._RESTORE_FAILED.clear()
    monkeypatch.delenv("THERMACELL_USERNAME", raising=False)
    monkeypatch.delenv("THERMACELL_PASSWORD", raising=False)


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


async def test_queued_write_and_failed_restore_cannot_pass_stale_read(aiohttp_client: Any) -> None:
    class DelayedPeer(DiagnosticPeer):
        pending = False
        fail_restore = False

        async def control(self, request: web.Request) -> web.Response:
            packet = LocalCtrlMessage.FromString(await request.read())
            if packet.msg == 6:
                self.pending = self.fail_restore = True
                return web.Response(status=500)
            if packet.msg == 4 and self.fail_restore:
                self.fail_restore = False
                return web.Response(status=500)
            response = await super().control(request)
            if packet.msg == 4 and self.pending:
                self.params["LIV Hub"]["LED Brightness"] = 74
                self.pending = False
            return response

    peer = DelayedPeer()
    app = web.Application()
    app.router.add_post("/esp_local_ctrl/session", peer.session)
    app.router.add_post("/esp_local_ctrl/control", peer.control)
    http = await aiohttp_client(app)
    url = http.make_url("/")
    record = {"node_id": "hub", "host": "test.local.", "port": url.port, "addresses": [url.host]}
    state = parse_device_state("hub", peer.params, {}, peer.config)
    report = await diagnose(peer, record, HubServices(MagicMock(), lambda: state), write=True)
    assert report["stages"]["restore"]["values"]["LED Brightness"] == 75
    assert peer.params["LIV Hub"]["LED Brightness"] == 74
    assert report["stages"]["restore"]["status"] == "RESTORE_FAILED"
    assert diagnostics._RESTORE_FAILED.is_set()


async def test_numeric_secret_prevents_mutation_and_is_absent_from_restore_alert(
    diagnostic_peer: Any, capsys: pytest.CaptureFixture[str]
) -> None:
    peer, record, services = diagnostic_peer
    diagnostics.remember_credentials("240")
    report = await diagnose(peer, record, services, write=True)
    assert not peer.writes
    assert report["stages"]["led_write"]["error_type"] == "ReportRefusedError"
    transport = AsyncMock(spec=LocalTransport)
    transport.write.side_effect = TimeoutError
    transport.read.return_value = (peer.config, peer.params)
    await diagnostics.restore_led(transport, peer.params["LIV Hub"], report)
    alert = capsys.readouterr().err
    assert "RESTORE_FAILED" in alert
    assert "240" not in alert


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
    assert report["stages"]["restore"]["status"] == ("passed" if failure == "readonly" else "not_performed")
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

    async def write(values: dict[str, Any]) -> None:
        peer.params["LIV Hub"].update(values["LIV Hub"])
        if values["LIV Hub"]["LED Brightness"] == 74:
            if failure == "timeout":
                raise TimeoutError("hidden-session-key")
            if failure == "cancel":
                raise asyncio.CancelledError

    transport.write.side_effect = write
    if failure == "readback":
        transport.read.side_effect = [
            (peer.config, peer.params),
            ValueError("hidden-cookie"),
            (peer.config, peer.params),
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
    peer.params["LIV Hub"]["LED Brightness"] = 74
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
    transport.read.assert_awaited_once()
    assert report["stages"]["restore"]["status"] == "RESTORE_FAILED"
    assert report["stages"]["restore"]["original_values"] == original
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


@pytest.mark.parametrize("cancellations", [1, 2])
async def test_cancellation_during_cleanup_waits_for_verified_restore(cancellations: int) -> None:
    peer = DiagnosticPeer()
    entered = asyncio.Event()
    release = asyncio.Event()
    transport = AsyncMock(spec=LocalTransport)
    transport.read.return_value = (peer.config, peer.params)

    async def write(values: dict[str, Any]) -> None:
        if values["LIV Hub"]["LED Brightness"] == 75:
            entered.set()
            await release.wait()
        peer.params["LIV Hub"].update(values["LIV Hub"])

    transport.write.side_effect = write
    report = diagnostics.new_report("hub")
    task = asyncio.create_task(diagnostics.exercise_led(transport, report))
    await asyncio.wait_for(entered.wait(), 1)
    for _ in range(cancellations):
        task.cancel()
        await asyncio.sleep(0)
    assert not task.done()
    release.set()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert report["stages"]["restore"]["status"] == "passed"
    assert peer.params["LIV Hub"]["LED Brightness"] == 75


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


async def test_rejected_write_continues_to_next_hub(
    diagnostic_peer: Any, monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    peer, record, services = diagnostic_peer
    peer.readonly = True
    original = deepcopy(peer.params["LIV Hub"])
    monkeypatch.setattr(
        diagnostics,
        "account_nodes",
        AsyncMock(return_value=[("hub", peer.config, peer.params, services)] * 2),
    )
    monkeypatch.setattr(diagnostics, "discover", AsyncMock(return_value=[record]))
    args = argparse.Namespace(output=tmp_path, discovery_seconds=1, node_id=None, write_led=True, deny_cloud=False)
    assert await diagnostics.run(args) == 2
    assert not peer.writes
    assert peer.params["LIV Hub"] == original
    assert "RESTORE_FAILED" not in capsys.readouterr().err

    def reports() -> list[dict[str, Any]]:
        return [json.loads(path.read_text()) for path in tmp_path.glob("*.json")]

    saved = await asyncio.to_thread(reports)
    assert len(saved) == 2
    assert all(
        report["stages"]["restore"]
        == {"status": "passed", "values": original, "write_error_type": "LocalPropertyReadOnlyError"}
        for report in saved
    )


async def test_interrupted_restore_reports_exact_originals(capsys: pytest.CaptureFixture[str]) -> None:
    peer = DiagnosticPeer()
    original = deepcopy(peer.params["LIV Hub"])
    transport = AsyncMock(spec=LocalTransport)
    transport.read.side_effect = asyncio.CancelledError
    report = diagnostics.new_report("hub")
    await diagnostics.restore_led(transport, original, report)
    assert report["stages"]["restore"]["status"] == "RESTORE_FAILED"
    assert report["stages"]["restore"]["original_values"] == original
    assert json.dumps(original) in capsys.readouterr().err


@pytest.mark.parametrize("closed_stderr", [False, True])
def test_cli_reporting_failure_never_exposes_exception_chain(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str], *, closed_stderr: bool
) -> None:
    output = tmp_path / "existing-file"
    output.touch()
    monkeypatch.setattr(diagnostics, "run", AsyncMock(side_effect=ValueError("synthetic-secret-token")))
    monkeypatch.setattr("sys.argv", ["lan", "--output", str(output)])
    if closed_stderr:
        monkeypatch.setattr(diagnostics.sys, "stderr", MagicMock(write=MagicMock(side_effect=ValueError("closed"))))
    assert diagnostics.main() == 2
    captured = capsys.readouterr()
    assert "synthetic-secret-token" not in captured.out + captured.err
    assert "Traceback" not in captured.out + captured.err
    if not closed_stderr:
        assert "unable to write a safe report" in captured.err


def test_output_preflight_prevents_hub_operations(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    output = tmp_path / "existing-file"
    output.touch()
    nodes = AsyncMock(return_value=[])
    discovery = AsyncMock(return_value=[])
    monkeypatch.setattr(diagnostics, "account_nodes", nodes)
    monkeypatch.setattr(diagnostics, "discover", discovery)
    monkeypatch.setattr("sys.argv", ["lan", "--output", str(output), "--write-led"])
    assert diagnostics.main() == 2
    nodes.assert_not_awaited()
    discovery.assert_not_awaited()


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ({"token": "nested-secret-token"}, "<invalid type>"),
        (["nested-secret-token"], "<invalid type>"),
        ("x" * 257, "<invalid type>"),
        (False, "<invalid type>"),
        (54, "54"),
        ("prefix hidden-pop hidden-username suffix", "prefix <redacted> <redacted> suffix"),
    ],
)
async def test_metadata_projection_is_bounded_and_redacted(
    diagnostic_peer: Any, tmp_path: Path, capsys: pytest.CaptureFixture[str], value: Any, expected: str
) -> None:
    peer, record, services = diagnostic_peer
    peer.params["LIV Hub"]["Name"] = value
    peer.config["info"]["fw_version"] = value
    report = await diagnose(peer, record, services, write=False)
    for name in ("name", "cloud_firmware", "local_firmware"):
        assert report[name] == expected
    await asyncio.to_thread(diagnostics.save_report, tmp_path, report)

    def artifacts() -> str:
        assert {path.suffix for path in tmp_path.iterdir()} == {".json", ".txt"}
        return "".join(path.read_text() for path in tmp_path.iterdir())

    output = capsys.readouterr().out + await asyncio.to_thread(artifacts)
    for secret in ("nested-secret-token", "hidden-pop", "hidden-username"):
        assert secret not in output


@pytest.mark.parametrize(
    ("failure", "reason"),
    [
        (None, "Set THERMACELL_USERNAME and THERMACELL_PASSWORD"),
        (ModuleNotFoundError("hidden-secret", name="zeroconf.asyncio"), "Install optional zeroconf dependency"),
        (AuthenticationError("hidden-secret"), "Cloud authentication failed"),
        (ThermacellConnectionError("hidden-secret"), "Cloud network connection failed"),
        (TimeoutError("hidden-secret"), "Prerequisite request timed out"),
        (ValueError("hidden-secret"), "Prerequisite failed; exception details withheld"),
    ],
)
def test_prerequisite_reasons_are_allowlisted(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    failure: Exception | None,
    reason: str,
) -> None:
    if failure is not None:
        monkeypatch.setattr(diagnostics, "account_nodes", AsyncMock(side_effect=failure))
    monkeypatch.setattr("sys.argv", ["lan", "--output", str(tmp_path)])
    assert diagnostics.main() == 2
    report = json.loads(next(tmp_path.glob("*.json")).read_text())
    assert report["reason"] == reason
    captured = capsys.readouterr()
    assert "hidden-secret" not in captured.out + captured.err


def test_unknown_node_id_produces_report(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(diagnostics, "account_nodes", AsyncMock(return_value=[]))
    monkeypatch.setattr(diagnostics, "discover", AsyncMock(return_value=[]))
    monkeypatch.setattr("sys.argv", ["lan", "--output", str(tmp_path), "--node-id", "not-a-node"])
    assert diagnostics.main() == 2
    reports = list(tmp_path.glob("*.json"))
    assert len(reports) == 1
    assert json.loads(reports[0].read_text())["reason"] == "node_id not in account"


@pytest.mark.parametrize("method", ["connect", "connect_ex"])
@pytest.mark.parametrize("scope", ["2", "test-interface"])
def test_cloud_guard_preserves_ipv6_scope(monkeypatch: pytest.MonkeyPatch, method: str, scope: str) -> None:
    connect = MagicMock(return_value=0)
    monkeypatch.setattr(socket.socket, method, connect)
    monkeypatch.setattr(socket, "if_nametoindex", lambda name: 2)
    with diagnostics.deny_cloud({(f"fe80::1234%{scope}", 80)}) as evidence:
        with socket.socket(socket.AF_INET6) as sock:
            getattr(sock, method)(("fe80:0:0:0:0:0:0:1234", 80, 0, 2))
            for address in (
                ("fe80::1234", 80, 0, 3),
                ("fe80::1234", 80, 0, 0),
                ("fe80::1234", 443, 0, 2),
                ("2001:db8::1", 80, 0, 2),
                ("cloud.example", 443),
            ):
                with pytest.raises(PermissionError):
                    getattr(sock, method)(address)
        connect.assert_called_once()
        assert evidence["blocked_connects"] == 5
    assert getattr(socket.socket, method) is connect


async def test_read_falls_back_to_second_address(diagnostic_peer: Any) -> None:
    peer, record, services = diagnostic_peer
    record["addresses"] = ["127.0.0.0", *record["addresses"]]
    with diagnostics.deny_cloud({(ip, record["port"]) for ip in record["addresses"]}):
        report = await diagnose(peer, record, services, write=False)
    for name in ("handshake", "identity", "properties"):
        assert report["stages"][name]["status"] == "passed"
    assert report["selected_endpoint"]["address"] == "127.0.0.1"
    assert not peer.writes


async def test_address_preference_ipv4_global_ipv6_then_link_local(
    diagnostic_peer: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    peer, record, services = diagnostic_peer
    record["addresses"] = ["fe80::1234%2", "2001:db8::1", "203.0.113.1"]
    failed = AsyncMock(spec=LocalTransport)
    failed.read.side_effect = OSError("unreachable")
    factory = MagicMock(return_value=failed)
    monkeypatch.setattr(diagnostics, "DiagnosticTransport", factory)
    await diagnose(peer, record, services, write=False)
    assert [call.args[1].host for call in factory.call_args_list] == ["203.0.113.1", "2001:db8::1", "fe80::1234%2"]


async def test_write_failure_never_tries_another_address(diagnostic_peer: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    peer, record, services = diagnostic_peer
    record["addresses"].append("::1")
    attempted = []
    endpoint = services.local_endpoint

    def track(host: str, port: int) -> Any:
        attempted.append(host)
        return endpoint(host, port)

    monkeypatch.setattr(services, "local_endpoint", track)
    peer.readonly = True
    report = await diagnose(peer, record, services, write=True)
    assert report["stages"]["restore"]["status"] == "passed"
    assert attempted == ["127.0.0.1"]


@pytest.mark.parametrize(
    "credential", ["account-user", "account-password", "access-token", "hidden-pop", "hidden-username"]
)
async def test_save_report_refuses_loaded_credentials(
    diagnostic_peer: Any,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    credential: str,
) -> None:
    peer, record, services = diagnostic_peer
    monkeypatch.setenv("THERMACELL_USERNAME", "account-user")
    monkeypatch.setenv("THERMACELL_PASSWORD", "account-password")
    report = await diagnose(peer, record, services, write=False)
    diagnostics._CREDENTIALS.add("access-token")
    report["unexpected_field"] = f"prefix {credential} suffix"
    with pytest.raises(ValueError, match="Credential detected in report; output refused"):
        await asyncio.to_thread(diagnostics.save_report, tmp_path, report)
    captured = capsys.readouterr()
    assert credential not in captured.out + captured.err
    assert not await asyncio.to_thread(lambda: list(tmp_path.iterdir()))


def test_cloud_guard_restores_socket_methods_after_exception() -> None:
    original = socket.socket.connect, socket.socket.connect_ex
    with pytest.raises(RuntimeError, match="interrupted"), diagnostics.deny_cloud(set()):
        raise RuntimeError("interrupted")
    assert (socket.socket.connect, socket.socket.connect_ex) == original
    assert "unittest.mock" not in inspect.getsource(diagnostics)


def test_text_artifact_summarizes_stages(tmp_path: Path) -> None:
    report = diagnostics.new_report("hub")
    diagnostics.stage(report, "properties", "passed")
    diagnostics.save_report(tmp_path, report)
    text = next(tmp_path.glob("*.txt")).read_text()
    assert "properties: passed\n" in text
    assert "led_write: not_performed\n" in text
    assert "cloud_denial: not_performed\n" in text
    assert text != next(tmp_path.glob("*.json")).read_text()


async def test_account_bootstrap_tracks_public_credentials(
    aiohttp_client: Any, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    access_token = "synthetic-access-token"
    id_token = "header.eyJjdXN0b206dXNlcl9pZCI6InVzZXIxMjMifQ.signature"
    assert "_decode_jwt_payload" not in inspect.getsource(diagnostics)
    peer = DiagnosticPeer()
    app = web.Application()
    app.router.add_post(
        "/v1/login2", lambda request: web.json_response({"accesstoken": access_token, "idtoken": id_token})
    )
    app.router.add_get("/v1/user/nodes", lambda request: web.json_response({"nodes": ["hub"]}))
    app.router.add_get("/v1/user/nodes/config", lambda request: web.json_response(peer.config))
    app.router.add_get("/v1/user/nodes/params", lambda request: web.json_response(peer.params))
    cloud = await aiohttp_client(app)
    url = str(cloud.make_url("/")).rstrip("/")
    monkeypatch.setenv("THERMACELL_USERNAME", "account-user")
    monkeypatch.setenv("THERMACELL_PASSWORD", "account-password")
    monkeypatch.setattr(diagnostics, "ThermacellClient", partial(ThermacellClient, base_url=url))
    monkeypatch.setattr(diagnostics, "AuthenticationHandler", partial(diagnostics.AuthenticationHandler, base_url=url))
    metadata = MagicMock(side_effect=AssertionError("Bootstrap must explicitly collect local credentials"))
    monkeypatch.setattr(diagnostics, "metadata_report", metadata)
    nodes = await diagnostics.account_nodes()
    assert [node for node, *_ in nodes] == ["hub"]
    metadata.assert_not_called()
    assert id_token not in diagnostics._CREDENTIALS
    for token in (access_token, "hidden-pop", "hidden-username"):
        report = diagnostics.new_report("hub")
        report["unexpected"] = token
        with pytest.raises(ValueError, match="Credential detected"):
            await asyncio.to_thread(diagnostics.save_report, tmp_path, report)


def test_second_interrupt_preserves_restore_failure_exit(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    peer = DiagnosticPeer()
    original = deepcopy(peer.params["LIV Hub"])
    restoring = asyncio.Event()
    transport = AsyncMock(spec=LocalTransport)
    transport.read.return_value = (peer.config, peer.params)

    async def write(values: dict[str, Any]) -> None:
        if values["LIV Hub"]["LED Brightness"] == 75:
            restoring.set()
            await asyncio.Event().wait()
        peer.params["LIV Hub"].update(values["LIV Hub"])

    async def diagnose(*args: Any, **kwargs: Any) -> None:
        await diagnostics.exercise_led(transport, kwargs["report"])

    async def first_interrupt(coro: Any) -> None:
        task = asyncio.create_task(coro)
        await asyncio.wait_for(restoring.wait(), 1)
        task.cancel()
        await asyncio.sleep(0)
        assert peer.params["LIV Hub"]["LED Brightness"] == 74

    def second_interrupt(coro: Any) -> None:
        with asyncio.Runner() as runner:
            runner.run(first_interrupt(coro))
            # A second SIGINT raises here; Runner then cancels every remaining task.
            raise KeyboardInterrupt

    transport.write.side_effect = write
    monkeypatch.setattr(diagnostics, "account_nodes", AsyncMock(return_value=[("hub", {}, {}, None)]))
    monkeypatch.setattr(diagnostics, "discover", AsyncMock(return_value=[]))
    monkeypatch.setattr(diagnostics, "diagnose_node", diagnose)
    monkeypatch.setattr(diagnostics.asyncio, "run", second_interrupt)
    monkeypatch.setattr("sys.argv", ["lan", "--output", str(tmp_path), "--write-led"])
    assert diagnostics.main() == 3
    report = json.loads(next(tmp_path.glob("*.json")).read_text())
    assert report["stages"]["restore"]["status"] == "RESTORE_FAILED"
    assert report["stages"]["restore"]["original_values"] == original
    error = capsys.readouterr().err
    assert "RESTORE_FAILED" in error
    assert json.dumps(original) in error


@pytest.mark.parametrize("ending", ["error", "interrupt", "cancel", "success"])
def test_main_exit_precedence_resets_for_next_invocation(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, ending: str
) -> None:
    async def failed_restore(args: argparse.Namespace) -> int:
        diagnostics.stage(diagnostics.new_report("hub"), "restore", "RESTORE_FAILED")
        if ending == "error":
            raise ValueError("hidden-secret")
        if ending == "interrupt":
            raise KeyboardInterrupt
        if ending == "cancel":
            raise asyncio.CancelledError
        return 0

    monkeypatch.setattr(diagnostics, "run", failed_restore)
    monkeypatch.setattr("sys.argv", ["lan", "--output", str(tmp_path)])
    assert diagnostics.main() == 3
    monkeypatch.setattr(diagnostics, "run", AsyncMock(return_value=0))
    assert diagnostics.main() == 0


@pytest.mark.parametrize("restore_failed", [False, True])
@pytest.mark.parametrize("secret", ["first-node", "2026", "not_performed"])
async def test_refused_hub_report_preserves_stages_and_exit_severity(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    secret: str,
    *,
    restore_failed: bool,
) -> None:
    monkeypatch.setattr(
        diagnostics,
        "account_nodes",
        AsyncMock(return_value=[("first-node", {}, {}, None), ("second-node", {}, {}, None)]),
    )
    monkeypatch.setattr(diagnostics, "discover", AsyncMock(return_value=[]))
    diagnostics.remember_credentials(secret)
    visited = []

    async def diagnose(node: str, *args: Any, **kwargs: Any) -> None:
        visited.append(node)
        report = kwargs["report"]
        report["timestamp"] = "2026-10-19T00:00:00Z"
        for name in ("handshake", "identity", "properties"):
            diagnostics.stage(report, name, "passed")
        if restore_failed:
            diagnostics.stage(report, "restore", "RESTORE_FAILED")

    monkeypatch.setattr(diagnostics, "diagnose_node", diagnose)
    args = argparse.Namespace(
        output=tmp_path, discovery_seconds=1, node_id=None, write_led=restore_failed, deny_cloud=False
    )
    assert await diagnostics.run(args) == (3 if restore_failed else 2)
    assert visited == (["first-node"] if restore_failed else ["first-node", "second-node"])

    def artifacts() -> list[dict[str, Any]]:
        paths = list(tmp_path.glob("*.json"))
        assert len(paths) == (0 if secret == "not_performed" else len(visited))
        for path in tmp_path.iterdir():
            assert secret not in path.read_text()
        return [json.loads(path.read_text()) for path in paths]

    reports = await asyncio.to_thread(artifacts)
    stubs = [report for report in reports if "reason" in report]
    if reports:
        assert stubs
    for stub in stubs:
        assert set(stub) == {"stages", "reason"}
        assert stub["reason"] == "Credential detected in report; output refused"
        assert stub["stages"]["properties"] == {"status": "passed"}
        assert stub["stages"]["restore"]["status"] == ("RESTORE_FAILED" if restore_failed else "not_performed")
    captured = capsys.readouterr()
    assert secret not in captured.out + captured.err
    if secret == "not_performed":
        assert "Diagnostic report withheld" in captured.err


@pytest.mark.parametrize("failure", ["rejected", "timeout", "cancel", "readback"])
async def test_write_errors_always_restore_and_verify(failure: str) -> None:
    peer = DiagnosticPeer()
    original = deepcopy(peer.params["LIV Hub"])
    pending: list[dict[str, Any]] = []
    transport = AsyncMock(spec=LocalTransport)

    async def write(values: dict[str, Any]) -> None:
        if values["LIV Hub"]["LED Brightness"] == 75:
            if pending:
                peer.params["LIV Hub"].update(pending.pop())
            peer.params["LIV Hub"].update(values["LIV Hub"])
            return
        if failure == "rejected":
            raise DeviceError("hidden-rejection")
        pending.append(values["LIV Hub"])
        if failure == "cancel":
            raise asyncio.CancelledError
        if failure == "timeout":
            raise TimeoutError("hidden-timeout")

    async def read() -> tuple[dict[str, Any], dict[str, Any]]:
        if failure == "readback" and transport.read.await_count == 2:
            raise DeviceError("hidden-readback-failure")
        snapshot = deepcopy(peer.params)
        if pending:
            peer.params["LIV Hub"].update(pending.pop())
        return peer.config, snapshot

    transport.write.side_effect = write
    transport.read.side_effect = read
    report = diagnostics.new_report("hub")
    if failure == "cancel":
        with pytest.raises(asyncio.CancelledError):
            await diagnostics.exercise_led(transport, report)
    else:
        await diagnostics.exercise_led(transport, report)
    assert peer.params["LIV Hub"] == original
    assert transport.write.await_count == 2
    assert report["stages"]["restore"]["status"] == "passed"


@pytest.mark.parametrize("failure", ["http", "protocol"])
@pytest.mark.parametrize("restore_fails", [False, True])
async def test_post_dispatch_error_restores_after_stale_read(
    aiohttp_client: Any, capsys: pytest.CaptureFixture[str], failure: str, *, restore_fails: bool
) -> None:
    class FailedWritePeer(DiagnosticPeer):
        def __init__(self) -> None:
            super().__init__()
            self.pending: dict[str, Any] | None = None
            self.stale_read_seen = False

        async def control(self, request: web.Request) -> web.Response:
            packet = LocalCtrlMessage.FromString(await request.read())
            if packet.msg == 6:
                payload = json.loads(packet.cmd_set_prop_vals.props[0].value)
                if payload["LIV Hub"]["LED Brightness"] == 74:
                    self.writes.append(payload)
                    self.pending = payload["LIV Hub"]
                    if failure == "http":
                        return web.Response(status=500)
                    return web.Response(body=LocalCtrlMessage(msg=1).SerializeToString())
                if restore_fails:
                    self.writes.append(payload)
                    return web.Response(status=500)
            response = await super().control(request)
            if packet.msg == 4 and self.pending is not None:
                # Apply the queued write only after serializing the old snapshot.
                self.params["LIV Hub"].update(self.pending)
                self.pending = None
                self.stale_read_seen = True
            return response

    peer = FailedWritePeer()
    before = deepcopy(peer.params["LIV Hub"])
    app = web.Application()
    app.router.add_post("/esp_local_ctrl/session", peer.session)
    app.router.add_post("/esp_local_ctrl/control", peer.control)
    http = await aiohttp_client(app)
    url = http.make_url("/")
    record = {"node_id": "hub", "host": "test.local.", "port": url.port, "addresses": [url.host]}
    state = parse_device_state("hub", peer.params, {}, peer.config)
    report = await diagnose(peer, record, HubServices(MagicMock(), lambda: state), write=True)
    assert peer.stale_read_seen
    assert report["stages"]["led_write"] == {"status": "failed_or_uncertain", "error_type": "DeviceError"}
    if restore_fails:
        assert report["stages"]["restore"]["status"] == "RESTORE_FAILED"
        assert report["stages"]["restore"]["original_values"] == before
        assert "RESTORE_FAILED" in capsys.readouterr().err
    else:
        assert peer.params["LIV Hub"] == before
        assert report["stages"]["restore"] == {"status": "passed", "values": before}
        assert "RESTORE_FAILED" not in capsys.readouterr().err
    assert peer.writes == [{"LIV Hub": {"LED Brightness": 74}}, {"LIV Hub": {"LED Brightness": 75}}]


@pytest.mark.parametrize("failure", [DeviceError, TimeoutError, asyncio.CancelledError])
async def test_restore_write_error_cannot_certify_matching_read(
    failure: type[BaseException], capsys: pytest.CaptureFixture[str]
) -> None:
    peer = DiagnosticPeer()
    original = deepcopy(peer.params["LIV Hub"])
    transport = AsyncMock(spec=LocalTransport)
    transport.write.side_effect = failure("hidden-write-error")
    transport.read.return_value = (peer.config, peer.params)
    report = diagnostics.new_report("hub")
    await diagnostics.restore_led(transport, original, report)
    transport.write.assert_awaited_once_with({"LIV Hub": {"LED Brightness": 75}})
    transport.read.assert_awaited_once()
    assert report["stages"]["restore"] == {
        "status": "RESTORE_FAILED",
        "values": original,
        "original_values": original,
        "write_error_type": failure.__name__,
    }
    assert diagnostics._RESTORE_FAILED.is_set()
    assert "RESTORE_FAILED" in capsys.readouterr().err
    assert "hidden-write-error" not in json.dumps(report)
