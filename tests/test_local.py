"""Exercise real HTTP, protobuf, and encrypted local sessions against a hub peer."""

import hashlib
import json
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from aiohttp import web
from cryptography.hazmat.primitives.asymmetric.x25519 import X25519PrivateKey, X25519PublicKey
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from pythermacell._proto.local_pb2 import LocalCtrlMessage, SessionData
from pythermacell._srp import PRIME, WIDTH
from pythermacell.api import ThermacellAPI
from pythermacell.client import ThermacellClient
from pythermacell.exceptions import AuthenticationError, DeviceError
from pythermacell.local import LocalEndpoint, LocalTransport


def _bytes(number: int) -> bytes:
    return number.to_bytes(max(1, (number.bit_length() + 7) // 8), "big")


class HubPeer:
    """Independent server side of the documented protocomm exchange."""

    def __init__(self, scheme: int, patch: int) -> None:
        self.scheme = scheme
        self.patch = patch
        self.cipher: Any = None
        self.aead: AESGCM | None = None
        self.nonce = bytes(range(12))
        self.node = "hub"
        self.readonly = False
        self.reject = False
        self.writes: list[Any] = []
        self.expected_proof = b""
        self.server_proof = b""
        self.session_key = b""
        self.client_pub = b""
        self.device_pub = b""

    async def version(self, request: web.Request) -> web.Response:
        return web.json_response({"local_ctrl": {"sec_ver": self.scheme, "sec_patch_ver": self.patch}})

    async def session(self, request: web.Request) -> web.Response:
        assert "Authorization" not in request.headers
        packet = SessionData.FromString(await request.read())
        assert packet.sec_ver == self.scheme
        response = SessionData(sec_ver=self.scheme)
        if self.scheme == 0:
            response.sec0.msg = 1
            response.sec0.sr.status = 0
        elif self.scheme == 1:
            self._security1(packet, response)
        else:
            self._security2(packet, response)
        result = web.Response(body=response.SerializeToString())
        result.set_cookie("session", "peer")
        return result

    def _security1(self, packet: Any, response: Any) -> None:
        if packet.sec1.msg == 0:
            private = X25519PrivateKey.generate()
            self.device_pub = private.public_key().public_bytes_raw()
            self.client_pub = packet.sec1.sc0.client_pubkey
            shared = private.exchange(X25519PublicKey.from_public_bytes(self.client_pub))
            shared = bytes(a ^ b for a, b in zip(shared, hashlib.sha256(b"proof").digest(), strict=True))
            self.cipher = Cipher(algorithms.AES(shared), modes.CTR(bytes(range(16)))).encryptor()
            response.sec1.msg = 1
            response.sec1.sr0.device_pubkey = self.device_pub
            response.sec1.sr0.device_random = bytes(range(16))
        else:
            assert self.cipher.update(packet.sec1.sc1.client_verify_data) == self.device_pub
            response.sec1.msg = 3
            response.sec1.sr1.device_verify_data = self.cipher.update(self.client_pub)

    def _security2(self, packet: Any, response: Any) -> None:
        if packet.sec2.msg == 0:
            assert packet.sec2.sc0.client_username == b"wifiprov"
            salt = b"1234567890123456"
            identity = hashlib.sha512(b"wifiprov:proof").digest()
            x = int.from_bytes(hashlib.sha512(salt + _bytes(int.from_bytes(identity))).digest())
            verifier = pow(5, x, PRIME)
            multiplier = int.from_bytes(hashlib.sha512(PRIME.to_bytes(WIDTH) + (5).to_bytes(WIDTH)).digest())
            private = 123456789
            server = (multiplier * verifier + pow(5, private, PRIME)) % PRIME
            client = int.from_bytes(packet.sec2.sc0.client_pubkey)
            scramble = int.from_bytes(hashlib.sha512(client.to_bytes(WIDTH) + server.to_bytes(WIDTH)).digest())
            shared = pow(client * pow(verifier, scramble, PRIME), private, PRIME)
            self.session_key = hashlib.sha512(_bytes(shared)).digest()
            xor = bytes(
                a ^ b
                for a, b in zip(
                    hashlib.sha512(PRIME.to_bytes(WIDTH)).digest(),
                    hashlib.sha512((5).to_bytes(WIDTH)).digest(),
                    strict=True,
                )
            )
            self.expected_proof = hashlib.sha512(
                xor + hashlib.sha512(b"wifiprov").digest() + salt + _bytes(client) + _bytes(server) + self.session_key
            ).digest()
            self.server_proof = hashlib.sha512(_bytes(client) + self.expected_proof + self.session_key).digest()
            response.sec2.msg = 1
            response.sec2.sr0.device_pubkey = _bytes(server)
            response.sec2.sr0.device_salt = salt
        else:
            assert packet.sec2.sc1.client_proof == self.expected_proof
            self.aead = AESGCM(self.session_key[:32])
            self.nonce = bytes(range(12))
            response.sec2.msg = 3
            response.sec2.sr1.device_proof = self.server_proof
            response.sec2.sr1.device_nonce = self.nonce

    def _increment(self) -> None:
        if self.patch:
            self.nonce = self.nonce[:8] + (int.from_bytes(self.nonce[8:]) + 1).to_bytes(4)

    async def control(self, request: web.Request) -> web.Response:
        assert "Authorization" not in request.headers
        assert request.cookies["session"] == "peer"
        payload = await request.read()
        if self.cipher:
            payload = self.cipher.update(payload)
        elif self.aead:
            payload = self.aead.decrypt(self.nonce, payload, None)
            self._increment()
        packet = LocalCtrlMessage.FromString(payload)
        response = LocalCtrlMessage()
        if packet.msg == 0:
            response.msg = 1
            response.resp_get_prop_count.count = 2
        elif packet.msg == 4:
            assert list(packet.cmd_get_prop_vals.indices) == [0, 1]
            response.msg = 5
            # Deliberately reorder the properties relative to the app's index 1.
            for name, value, flags in (
                ("params", {"LIV Hub": {"Enable Repellers": False}}, int(self.readonly)),
                ("config", {"node_id": self.node}, 1),
            ):
                prop = response.resp_get_prop_vals.props.add()
                prop.name, prop.value, prop.flags = name, json.dumps(value).encode(), flags
        else:
            assert packet.msg == 6
            prop = packet.cmd_set_prop_vals.props[0]
            assert prop.index == 0
            self.writes.append(json.loads(prop.value))
            response.msg = 7
            response.resp_set_prop_vals.status = 1 if self.reject else 0
        payload = response.SerializeToString()
        if self.cipher:
            payload = self.cipher.update(payload)
        elif self.aead:
            payload = self.aead.encrypt(self.nonce, payload, None)
            self._increment()
        return web.Response(body=payload)


@pytest.fixture
async def local_peer(aiohttp_client: Any) -> Any:
    async def create(scheme: int = 1, patch: int = 1) -> Any:
        peer = HubPeer(scheme, patch)
        app = web.Application()
        app.router.add_post("/esp_local_ctrl/version", peer.version)
        app.router.add_post("/esp_local_ctrl/session", peer.session)
        app.router.add_post("/esp_local_ctrl/control", peer.control)
        http = await aiohttp_client(app)
        url = http.make_url("/")
        endpoint = LocalEndpoint("hub", url.host, url.port, scheme, "proof")
        return peer, LocalTransport(http.session, endpoint), http

    return create


@pytest.mark.parametrize(("scheme", "patch"), [(0, 0), (1, 0), (2, 0), (2, 1)])
async def test_encrypted_property_reads_and_writes(local_peer: Any, scheme: int, patch: int) -> None:
    peer, transport, _ = await local_peer(scheme, patch)
    config, params = await transport.read()
    assert config == {"node_id": "hub"}
    assert params["LIV Hub"]["Enable Repellers"] is False
    await transport.write({"LIV Hub": {"Enable Repellers": False}})
    assert peer.writes == [{"LIV Hub": {"Enable Repellers": False}}]
    assert "proof" not in repr(transport.endpoint)


@pytest.mark.parametrize("failure", ["identity", "readonly", "rejected"])
async def test_local_write_protections(local_peer: Any, failure: str) -> None:
    peer, transport, _ = await local_peer()
    peer.node = "someone-else" if failure == "identity" else "hub"
    peer.readonly = failure == "readonly"
    peer.reject = failure == "rejected"
    with pytest.raises(DeviceError):
        await transport.write({"LIV Hub": {"Refill Reset": 1}})
    assert len(peer.writes) == (1 if failure == "rejected" else 0)


async def test_uncertain_local_write_is_never_replayed_in_cloud(local_peer: Any) -> None:
    _, transport, http = await local_peer()
    api = ThermacellAPI(auth_handler=MagicMock(), session=http.session)
    api.local_transports["hub"] = transport
    transport.write = AsyncMock(side_effect=TimeoutError)
    api.request = AsyncMock()
    with pytest.raises(TimeoutError):
        await api.update_node_params("hub", {"LIV Hub": {"Refill Reset": 1}})
    api.request.assert_not_awaited()
    transport.read = AsyncMock(side_effect=TimeoutError)
    api.request.return_value = (200, {"cloud": True})
    assert await api.get_node_params("hub") == (200, {"cloud": True})
    assert api.last_transport["hub"] == "cloud"


async def test_local_polling_survives_cloud_outage_and_preserves_failed_hub(local_peer: Any) -> None:
    _, transport, http = await local_peer()
    client = ThermacellClient(username="test", password="test", session=http.session)
    client.api.local_transports["hub"] = transport
    client.api.get_nodes = AsyncMock(return_value=(200, {"nodes": ["hub"]}))
    devices = await client.get_devices()
    device = devices[0]
    assert device.is_online
    assert await device.refresh()
    client.api.get_nodes.return_value = (503, None)
    assert (await client.get_devices())[0] is device
    client.api.get_nodes.side_effect = TimeoutError
    assert (await client.get_devices())[0].is_online
    client._fetch_device_state = AsyncMock(return_value=None)
    assert (await client.get_devices())[0] is device
    assert not device.is_online


async def test_failed_reauthentication_never_uses_cached_membership(local_peer: Any) -> None:
    _, transport, http = await local_peer()
    client = ThermacellClient(username="test", password="test", session=http.session)
    client.api.local_transports["hub"] = transport
    client.api.get_nodes = AsyncMock(return_value=(200, {"nodes": ["hub"]}))
    await client.get_devices()
    client.api.get_nodes.side_effect = AuthenticationError("password changed")
    with pytest.raises(AuthenticationError):
        await client.get_devices()


async def test_register_local_requires_active_session(local_peer: Any) -> None:
    _, transport, http = await local_peer()
    api = ThermacellAPI(auth_handler=MagicMock())
    with pytest.raises(RuntimeError):
        api.configure_local(transport.endpoint)
    api = ThermacellAPI(auth_handler=MagicMock(), session=http.session)
    api.configure_local(transport.endpoint)
    assert await api.update_node_params("hub", {"LIV Hub": {"Enable Repellers": False}}) == (200, {})
    assert api.last_transport["hub"] == "local"
