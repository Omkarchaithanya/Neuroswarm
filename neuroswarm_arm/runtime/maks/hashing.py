"""Hashing for prefix / identity / dedup."""

from __future__ import annotations

import hashlib
from typing import Callable

from .interfaces import IHasher
from .models import HashAlgo, KVIdentity


class SHA256Hasher(IHasher):
    @property
    def name(self) -> str:
        return HashAlgo.SHA256.value

    def hash(self, data: bytes) -> str:
        return hashlib.sha256(data).hexdigest()

    def hash_identity(self, identity: KVIdentity, *, prompt_prefix: bytes | str = b"") -> str:
        if isinstance(prompt_prefix, str):
            prompt_prefix = prompt_prefix.encode("utf-8")
        material = identity.fingerprint().encode("utf-8") + b"\0" + prompt_prefix
        return self.hash(material)


class Blake3Hasher(IHasher):
    def __init__(self) -> None:
        try:
            import blake3  # type: ignore

            self._blake3 = blake3
        except ImportError:
            self._blake3 = None

    @property
    def name(self) -> str:
        return HashAlgo.BLAKE3.value

    def hash(self, data: bytes) -> str:
        if self._blake3 is None:
            # Graceful Axion fallback when blake3 wheel absent
            return hashlib.sha256(data).hexdigest()
        return self._blake3.blake3(data).hexdigest()

    def hash_identity(self, identity: KVIdentity, *, prompt_prefix: bytes | str = b"") -> str:
        if isinstance(prompt_prefix, str):
            prompt_prefix = prompt_prefix.encode("utf-8")
        material = identity.fingerprint().encode("utf-8") + b"\0" + prompt_prefix
        return self.hash(material)


class RollingHashStub(IHasher):
    """Future rolling / Rabin-style hash — interface only."""

    @property
    def name(self) -> str:
        return HashAlgo.ROLLING.value

    def hash(self, data: bytes) -> str:
        # Deterministic placeholder until rolling hash lands
        return hashlib.sha256(b"rolling:" + data).hexdigest()

    def hash_identity(self, identity: KVIdentity, *, prompt_prefix: bytes | str = b"") -> str:
        if isinstance(prompt_prefix, str):
            prompt_prefix = prompt_prefix.encode("utf-8")
        return self.hash(identity.fingerprint().encode("utf-8") + prompt_prefix)


def build_hasher(algo: HashAlgo | str) -> IHasher:
    key = HashAlgo(algo) if isinstance(algo, str) else algo
    if key is HashAlgo.BLAKE3:
        return Blake3Hasher()
    if key is HashAlgo.ROLLING:
        return RollingHashStub()
    return SHA256Hasher()


def prefix_block_hashes(blocks: list[bytes], hasher: IHasher | None = None) -> list[str]:
    h = hasher or SHA256Hasher()
    out: list[str] = []
    acc = b""
    for block in blocks:
        acc += block
        out.append(h.hash(acc))
    return out


def longest_common_prefix_len(a: list[str], b: list[str]) -> int:
    n = min(len(a), len(b))
    i = 0
    while i < n and a[i] == b[i]:
        i += 1
    return i
