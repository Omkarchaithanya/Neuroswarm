"""Compressor facade — Lazy decompress for cold pages."""

from __future__ import annotations

from .compression import (
    LZ4Codec,
    NoneCodec,
    QuantizedKVStub,
    ZSTDCodec,
    build_compression,
)
from .interfaces import ICompression


class LazyCompressor:
    """Compress on cold demote; decompress on load if marked."""

    def __init__(self, codec: ICompression | None = None, *, name: str = "zstd") -> None:
        self.codec = codec or build_compression(name)
        self.bytes_in = 0
        self.bytes_out = 0

    @property
    def name(self) -> str:
        return self.codec.name

    def compress(self, data: bytes) -> bytes:
        out = self.codec.compress(data)
        self.bytes_in += len(data)
        self.bytes_out += len(out)
        return out

    def decompress(self, data: bytes) -> bytes:
        return self.codec.decompress(data)

    @property
    def compression_ratio(self) -> float:
        if self.bytes_out <= 0:
            return 1.0
        return self.bytes_in / float(self.bytes_out)


__all__ = [
    "LazyCompressor",
    "build_compression",
    "NoneCodec",
    "LZ4Codec",
    "ZSTDCodec",
    "QuantizedKVStub",
]
