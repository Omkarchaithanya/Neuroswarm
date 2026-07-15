"""KV compression codecs."""

from __future__ import annotations

from ..interfaces.compression import IKVCompression


class NoneCompression(IKVCompression):
    @property
    def name(self) -> str:
        return "none"

    def compress(self, data: bytes) -> bytes:
        return data

    def decompress(self, data: bytes) -> bytes:
        return data


class ZSTDCompression(IKVCompression):
    def __init__(self, level: int = 3) -> None:
        self._level = level
        try:
            import zstandard as zstd

            self._zstd = zstd
            self._cctx = zstd.ZstdCompressor(level=level)
            self._dctx = zstd.ZstdDecompressor()
        except ImportError as exc:  # pragma: no cover
            raise RuntimeError(
                "zstandard package required for ZSTD compression; pip install zstandard"
            ) from exc

    @property
    def name(self) -> str:
        return "zstd"

    def compress(self, data: bytes) -> bytes:
        return self._cctx.compress(data)

    def decompress(self, data: bytes) -> bytes:
        return self._dctx.decompress(data)


class LZ4Compression(IKVCompression):
    def __init__(self) -> None:
        try:
            import lz4.frame

            self._lz4 = lz4.frame
        except ImportError as exc:  # pragma: no cover
            raise RuntimeError(
                "lz4 package required for LZ4 compression; pip install lz4"
            ) from exc

    @property
    def name(self) -> str:
        return "lz4"

    def compress(self, data: bytes) -> bytes:
        return self._lz4.compress(data)

    def decompress(self, data: bytes) -> bytes:
        return self._lz4.decompress(data)


def build_compression(name: str) -> IKVCompression:
    key = (name or "none").strip().lower()
    if key in {"", "none", "null", "identity"}:
        return NoneCompression()
    if key in {"zstd", "zstandard"}:
        try:
            return ZSTDCompression()
        except RuntimeError:
            return NoneCompression()
    if key == "lz4":
        try:
            return LZ4Compression()
        except RuntimeError:
            return NoneCompression()
    raise ValueError(f"unknown compression codec: {name}")


__all__ = [
    "IKVCompression",
    "LZ4Compression",
    "NoneCompression",
    "ZSTDCompression",
    "build_compression",
]
