"""Async ESP local-control transport (the LIV app's property protocol)."""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
from dataclasses import dataclass, field
from http import HTTPStatus
from typing import TYPE_CHECKING, Any

from aiohttp import ClientTimeout
from cryptography.hazmat.primitives.asymmetric.x25519 import X25519PrivateKey, X25519PublicKey
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from yarl import URL

from pythermacell._proto.local_pb2 import LocalCtrlMessage, SessionData
from pythermacell._srp import SRPClient, integer_bytes
from pythermacell.exceptions import DeviceError


if TYPE_CHECKING:
    from aiohttp import ClientSession
    from cryptography.hazmat.primitives.ciphers import CipherContext

SERVICE_TYPE = "_esp_local_ctrl._tcp.local."
MAX_PROPERTIES = 128
MAX_RESPONSE_BYTES = 1024 * 1024
SECURITY_SRP = 2
NONCE_BYTES = 12


class LocalPropertyReadOnlyError(DeviceError):
    """The params property refused a write before any mutation was dispatched."""


@dataclass(frozen=True)
class LocalEndpoint:
    """A discovered address paired with credentials from authenticated config."""

    node_id: str
    host: str
    port: int
    security: int
    pop: str = field(default="", repr=False)
    username: str = field(default="wifiprov", repr=False)


class LocalTransport:
    """Serialize encrypted exchanges and never replay an uncertain write.

    Each operation establishes a fresh session, then discovers properties by
    name and checks the node identity. This avoids stale cipher counters after
    a reboot, a timeout, or another controller opening a session.
    """

    def __init__(self, session: ClientSession, endpoint: LocalEndpoint) -> None:
        """Use an existing session without sending cloud authorization headers."""
        self._session = session
        self.endpoint = endpoint
        self._lock = asyncio.Lock()
        self._cipher: CipherContext | None = None
        self._aead: AESGCM | None = None
        self._nonce = b""
        self._patch_version = 0
        self._cookies: dict[str, str] = {}
        self._base = URL.build(scheme="http", host=endpoint.host, port=endpoint.port)

    async def _post(self, path: str, payload: bytes) -> bytes:
        async with self._session.post(
            self._base / "esp_local_ctrl" / path,
            data=payload,
            headers={"Content-Type": "application/octet-stream"},
            cookies=self._cookies,
            timeout=ClientTimeout(total=10),
            allow_redirects=False,
        ) as response:
            if response.status != HTTPStatus.OK:
                msg = f"Local control failed: HTTP {response.status}"
                raise DeviceError(msg)
            self._cookies.update({name: cookie.value for name, cookie in response.cookies.items()})
            data = bytearray()
            async for chunk in response.content.iter_chunked(65536):
                data.extend(chunk)
                if len(data) > MAX_RESPONSE_BYTES:
                    msg = "Local control response exceeds size limit"
                    raise DeviceError(msg)
            return bytes(data)

    async def _exchange(self, request: SessionData, reply: str, security: int) -> SessionData:
        response = SessionData.FromString(await self._post("session", request.SerializeToString()))
        payload = getattr(response, f"sec{security}")
        if (
            response.sec_ver != security
            or response.WhichOneof("proto") != f"sec{security}"
            or payload.WhichOneof("payload") != reply
            or getattr(payload, reply).status != 0
        ):
            msg = "Local session authentication failed"
            raise DeviceError(msg)
        return response

    async def _connect(self) -> None:
        self._cipher = None
        self._aead = None
        self._cookies = {}
        security = self.endpoint.security
        if security == 0:
            request = SessionData(sec_ver=0)
            request.sec0.sc.SetInParent()
            await self._exchange(request, "sr", 0)
        elif security == 1:
            await self._connect_security1()
        elif security == SECURITY_SRP:
            await self._connect_security2()
        else:
            msg = "Unsupported advertised local security scheme"
            raise DeviceError(msg)

    async def _connect_security1(self) -> None:
        private = X25519PrivateKey.generate()
        public = private.public_key().public_bytes_raw()
        request = SessionData(sec_ver=1)
        request.sec1.sc0.client_pubkey = public
        response = (await self._exchange(request, "sr0", 1)).sec1.sr0
        shared = private.exchange(X25519PublicKey.from_public_bytes(response.device_pubkey))
        if self.endpoint.pop:
            pop_hash = hashlib.sha256(self.endpoint.pop.encode()).digest()
            shared = bytes(a ^ b for a, b in zip(shared, pop_hash, strict=True))
        self._cipher = Cipher(algorithms.AES(shared), modes.CTR(response.device_random)).encryptor()
        request = SessionData(sec_ver=1)
        request.sec1.msg = 2
        request.sec1.sc1.client_verify_data = self._cipher.update(response.device_pubkey)
        proof = (await self._exchange(request, "sr1", 1)).sec1.sr1.device_verify_data
        if not hmac.compare_digest(self._cipher.update(proof), public):
            msg = "Local device proof is invalid"
            raise DeviceError(msg)

    async def _connect_security2(self) -> None:
        info = json.loads(await self._post("version", b"---"))
        metadata = info.get("local_ctrl", info.get("prov", {}))
        self._patch_version = metadata.get("sec_patch_ver", 0)
        if self._patch_version not in (0, 1):
            msg = "Unsupported local security patch version"
            raise DeviceError(msg)
        srp = await asyncio.to_thread(SRPClient, self.endpoint.username, self.endpoint.pop)
        request = SessionData(sec_ver=2)
        request.sec2.sc0.client_username = self.endpoint.username.encode()
        request.sec2.sc0.client_pubkey = integer_bytes(srp.public)
        response = (await self._exchange(request, "sr0", 2)).sec2.sr0
        proof = await asyncio.to_thread(srp.challenge, response.device_salt, response.device_pubkey)
        request = SessionData(sec_ver=2)
        request.sec2.msg = 2
        request.sec2.sc1.client_proof = proof
        response1 = (await self._exchange(request, "sr1", 2)).sec2.sr1
        if (
            not hmac.compare_digest(response1.device_proof, srp.server_proof)
            or len(response1.device_nonce) != NONCE_BYTES
        ):
            msg = "Local device proof or nonce is invalid"
            raise DeviceError(msg)
        self._aead = AESGCM(srp.key[:32])
        self._nonce = response1.device_nonce

    def _advance_nonce(self) -> None:
        if self._patch_version == 1:
            counter = int.from_bytes(self._nonce[8:]) + 1
            self._nonce = self._nonce[:8] + counter.to_bytes(4)

    async def _control(self, request: LocalCtrlMessage, expected: str, message_type: int) -> LocalCtrlMessage:
        payload = request.SerializeToString()
        if self._cipher:
            payload = self._cipher.update(payload)
        elif self._aead:
            payload = self._aead.encrypt(self._nonce, payload, None)
            self._advance_nonce()
        result = await self._post("control", payload)
        if self._cipher:
            result = self._cipher.update(result)
        elif self._aead:
            result = self._aead.decrypt(self._nonce, result, None)
            self._advance_nonce()
        response = LocalCtrlMessage.FromString(result)
        if (
            response.msg != message_type
            or response.WhichOneof("payload") != expected
            or getattr(response, expected).status != 0
        ):
            msg = "Local property operation was rejected"
            raise DeviceError(msg)
        return response

    async def _properties(self) -> tuple[dict[str, Any], dict[str, Any], int]:
        await self._connect()
        request = LocalCtrlMessage(msg=0)
        request.cmd_get_prop_count.SetInParent()
        count = (await self._control(request, "resp_get_prop_count", 1)).resp_get_prop_count.count
        if not 1 <= count <= MAX_PROPERTIES:
            msg = "Invalid local property count"
            raise DeviceError(msg)
        request = LocalCtrlMessage(msg=4)
        request.cmd_get_prop_vals.indices.extend(range(count))
        props = (await self._control(request, "resp_get_prop_vals", 5)).resp_get_prop_vals.props
        if len(props) != count or any(prop.status != 0 for prop in props):
            msg = "Incomplete local property response"
            raise DeviceError(msg)
        values = {p.name: json.loads(p.value) for p in props if p.name in ("config", "params")}
        config = values.get("config")
        params = values.get("params")
        if (
            not isinstance(config, dict)
            or config.get("node_id") != self.endpoint.node_id
            or not isinstance(params, dict)
        ):
            msg = "Local node identity or properties do not match the account"
            raise DeviceError(msg)
        index = next((i for i, p in enumerate(props) if p.name == "params" and not p.flags & 1), -1)
        return config, params, index

    async def read(self) -> tuple[dict[str, Any], dict[str, Any]]:
        """Fetch authenticated config and params from the hub."""
        async with self._lock:
            config, params, _ = await self._properties()
            return config, params

    async def write(self, params: dict[str, Any]) -> None:
        """Write once after authenticating and checking identity/read-only flags."""
        async with self._lock:
            _, _, index = await self._properties()
            if index < 0:
                msg = "Local params property is not writable"
                raise LocalPropertyReadOnlyError(msg)
            request = LocalCtrlMessage(msg=6)
            prop = request.cmd_set_prop_vals.props.add()
            prop.index = index
            prop.value = json.dumps(params, separators=(",", ":")).encode()
            await self._control(request, "resp_set_prop_vals", 7)
