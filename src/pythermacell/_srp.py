# SPDX-FileCopyrightText: 2022 Espressif Systems (Shanghai) CO LTD
# SPDX-License-Identifier: Apache-2.0
"""Typed SRP-6a client adapted from Espressif's RainMaker CLI (SHA512/3072)."""

from __future__ import annotations

import hashlib
import secrets

from pythermacell.exceptions import DeviceError


PRIME = int(
    "FFFFFFFFFFFFFFFFC90FDAA22168C234C4C6628B80DC1CD129024E088A67CC74020BBEA63B139B22514A08798E3404DD"
    "EF9519B3CD3A431B302B0A6DF25F14374FE1356D6D51C245E485B576625E7EC6F44C42E9A637ED6B0BFF5CB6F406B7ED"
    "EE386BFB5A899FA5AE9F24117C4B1FE649286651ECE45B3DC2007CB8A163BF0598DA48361C55D39A69163FA8FD24CF5F"
    "83655D23DCA3AD961C62F356208552BB9ED529077096966D670C354E4ABC9804F1746C08CA18217C32905E462E36CE3B"
    "E39E772C180E86039B2783A2EC07A28FB5C55DF06F4C52C9DE2BCBF6955817183995497CEA956AE515D2261898FA0510"
    "15728E5A8AAAC42DAD33170D04507A33A85521ABDF1CBA64ECFB850458DBEF0A8AEA71575D060C7DB3970F85A6E1E4C7"
    "ABF5AE8CDB0933D71E8C94E04A25619DCEE3D2261AD2EE6BF12FFA06D98A0864D87602733EC86A64521F2B18177B200C"
    "BBE117577A615D6C770988C0BAD946E208E24FA074E5AB3143DB5BFCE0FD108E4B82D120A93AD2CAFFFFFFFFFFFFFFFF",
    16,
)
WIDTH = 384
GENERATOR = 5


def integer_bytes(value: int) -> bytes:
    """Encode the minimal unsigned integer representation used by Espressif."""
    return value.to_bytes(max(1, (value.bit_length() + 7) // 8), "big")


def digest(*parts: bytes) -> bytes:
    """Hash a concatenation without changing integer padding."""
    return hashlib.sha512(b"".join(parts)).digest()


class SRPClient:
    """Calculate SRP client proof and expected server proof."""

    def __init__(self, username: str, password: str) -> None:
        self.username = username.encode()
        self.password = password.encode()
        self.secret = secrets.randbits(256) | (1 << 255)
        self.public = pow(GENERATOR, self.secret, PRIME)
        self.key = b""
        self.server_proof = b""

    def challenge(self, salt: bytes, server_public: bytes) -> bytes:
        """Reject invalid server values and derive the session proof."""
        peer = int.from_bytes(server_public)
        if not 0 < peer < PRIME or not salt:
            msg = "Invalid SRP challenge"
            raise DeviceError(msg)
        padded_prime = PRIME.to_bytes(WIDTH)
        padded_generator = GENERATOR.to_bytes(WIDTH)
        multiplier = int.from_bytes(digest(padded_prime, padded_generator))
        scramble = int.from_bytes(digest(self.public.to_bytes(WIDTH), peer.to_bytes(WIDTH)))
        if not scramble:
            msg = "Invalid SRP scrambling parameter"
            raise DeviceError(msg)
        # Espressif hashes minimal integer encodings for salt and the inner hash.
        inner = integer_bytes(int.from_bytes(digest(self.username + b":" + self.password)))
        salt = integer_bytes(int.from_bytes(salt))
        private = int.from_bytes(digest(salt, inner))
        shared = pow(peer - multiplier * pow(GENERATOR, private, PRIME), self.secret + scramble * private, PRIME)
        self.key = digest(integer_bytes(shared))
        xor = bytes(a ^ b for a, b in zip(digest(padded_prime), digest(padded_generator), strict=True))
        proof = digest(xor, digest(self.username), salt, integer_bytes(self.public), integer_bytes(peer), self.key)
        self.server_proof = digest(integer_bytes(self.public), proof, self.key)
        return proof
