"""Compression layer — wraps Plane-2 codecs + future quantized KV stub."""

from __future__ import annotations

from neuroswarm_arm.runtime.kv.compression import (
    LZ4Compression as _LZ4,
    NoneCompression as _None,
    ZSTDCompression as _ZSTD,
    build_compression as _build_kv,
)

from .interfaces import ICompression


class NoneCodec(ICompression):
    @property
    def name(self) -> str:
        return "none"

    def compress(self, data: bytes) -> bytes:
        return data

    def decompress(self, data: bytes) -> bytes:
        return data


class LZ4Codec(ICompression):
    def __init__(self) -> None:
        self._inner = _LZ4()

    @property
    def name(self) -> str:
        return "lz4"

    def compress(self, data: bytes) -> bytes:
        return self._inner.compress(data)

    def decompress(self, data: bytes) -> bytes:
        return self._inner.decompress(data)


class ZSTDCodec(ICompression):
    def __init__(self, level: int = 3) -> None:
        self._inner = _ZSTD(level=level)

    @property
    def name(self) -> str:
        return "zstd"

    def compress(self, data: bytes) -> bytes:
        return self._inner.compress(data)

    def decompress(self, data: bytes) -> bytes:
        return self._inner.decompress(data)


class QuantizedKVStub(ICompression):
    """Future quantized KV compression — interface only."""

    @property
    def name(self) -> str:
        return "quantized_kv"

    def compress(self, data: bytes) -> bytes:
        raise NotImplementedError("quantized KV compression not available yet")

    def decompress(self, data: bytes) -> bytes:
        raise NotImplementedError("quantized KV compression not available yet")


def build_compression(name: str) -> ICompression:
    key = (name or "none").strip().lower()
    if key in {"", "none", "null", "identity"}:
        return NoneCodec()
    if key == "lz4":
        try:
            return LZ4Codec()
        except RuntimeError:
            return NoneCodec()
    if key in {"zstd", "zstandard"}:
        try:
            return ZSTDCodec()
        except RuntimeError:
            return NoneCodec()
    if key in {"quantized", "quantized_kv"}:
        return QuantizedKVStub()
    # Fall back through Plane-2 builder then wrap
    inner = _build_kv(key)
    if inner.name == "none":
        return NoneCodec()

    class _Wrap(ICompression):
        @property
        def name(self) -> str:
            return inner.name

        def compress(self, data: bytes) -> bytes:
            return inner.compress(data)

        def decompress(self, data: bytes) -> bytes:
            return inner.decompress(data)

    return _Wrap()
