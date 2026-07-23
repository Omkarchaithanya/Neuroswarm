"""Per-block Q8 byte-payload compression for MAKS persistent tier."""

from __future__ import annotations

import os
import struct

_MAGIC = b"NSQ8"
_VERSION_V1 = 1
_VERSION_V2 = 2


def _block_size() -> int:
    return max(1, int(os.getenv("NSA_Q8_BLOCK_SIZE", "256")))


def encode_q8(data: bytes) -> bytes:
    """Encode bytes with per-block symmetric int8 quantization (no zero-point)."""
    if not data:
        return _MAGIC + struct.pack("<BII", _VERSION_V2, 0, _block_size())

    block_size = _block_size()
    blocks: list[bytes] = []
    for i in range(0, len(data), block_size):
        chunk = data[i : i + block_size]
        blocks.append(_encode_block(chunk))

    header = _MAGIC + struct.pack(
        "<BII",
        _VERSION_V2,
        len(data),
        block_size,
    )
    return header + b"".join(blocks)


def _encode_block(chunk: bytes) -> bytes:
    if not chunk:
        return struct.pack("<f", 0.0)
    signed = [b if b < 128 else b - 256 for b in chunk]
    peak = max(abs(v) for v in signed)
    scale = peak / 127.0 if peak > 0 else 1.0
    quantized = bytes(
        (max(-127, min(127, int(round(v / scale)))) & 0xFF) for v in signed
    )
    return struct.pack("<f", scale) + quantized


def decode_q8(blob: bytes) -> bytes:
    if len(blob) < 9 or blob[:4] != _MAGIC:
        return blob
    version = blob[4]
    if version == _VERSION_V1:
        return _decode_v1(blob)
    if version == _VERSION_V2:
        return _decode_v2(blob)
    return blob


def _decode_v1(blob: bytes) -> bytes:
    if len(blob) < 13:
        return blob
    orig_len, scale = struct.unpack("<If", blob[5:13])
    body = blob[13:]
    out = bytearray()
    for q in body[:orig_len]:
        qv = q if q < 128 else q - 256
        out.append(int(max(0, min(255, round(qv * scale)))))
    return bytes(out)


def _decode_v2(blob: bytes) -> bytes:
    if len(blob) < 13:
        return blob
    orig_len, block_size = struct.unpack("<II", blob[5:13])
    if orig_len == 0:
        return b""
    offset = 13
    out = bytearray()
    while offset < len(blob) and len(out) < orig_len:
        if offset + 4 > len(blob):
            break
        scale = struct.unpack("<f", blob[offset : offset + 4])[0]
        offset += 4
        remain = min(block_size, orig_len - len(out))
        block = blob[offset : offset + remain]
        offset += remain
        for q in block:
            qv = q if q < 128 else q - 256
            out.append(int(max(0, min(255, round(qv * scale)))))
    return bytes(out[:orig_len])


def encode_f32_vector(values: list[float]) -> bytes:
    """Quantize f32 vector with per-block symmetric int8 (target ratio ~0.25)."""
    if not values:
        return _MAGIC + struct.pack("<BII", _VERSION_V2, 0, 64)
    block_floats = 64
    parts = [_MAGIC + struct.pack("<BII", _VERSION_V2, len(values), block_floats)]
    for i in range(0, len(values), block_floats):
        chunk = values[i : i + block_floats]
        peak = max(abs(v) for v in chunk) if chunk else 0.0
        scale = peak / 127.0 if peak > 0 else 1.0
        quant = bytes(
            (max(-127, min(127, int(round(v / scale)))) & 0xFF) for v in chunk
        )
        parts.append(struct.pack("<f", scale) + quant)
    return b"".join(parts)


def decode_f32_vector(blob: bytes) -> list[float]:
    if len(blob) < 13 or blob[:4] != _MAGIC:
        return []
    version = blob[4]
    if version != _VERSION_V2:
        raw = decode_q8(blob)
        count = len(raw) // 4
        if count == 0:
            return []
        return list(struct.unpack(f"<{count}f", raw[: count * 4]))
    count, block_floats = struct.unpack("<II", blob[5:13])
    if count == 0:
        return []
    offset = 13
    out: list[float] = []
    while offset < len(blob) and len(out) < count:
        scale = struct.unpack("<f", blob[offset : offset + 4])[0]
        offset += 4
        remain = min(block_floats, count - len(out))
        block = blob[offset : offset + remain]
        offset += remain
        for q in block:
            qv = q if q < 128 else q - 256
            out.append(qv * scale)
    return out[:count]


def cosine_distance(a: list[float], b: list[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 1.0
    dot = sum(x * y for x, y in zip(a, b, strict=True))
    na = sum(x * x for x in a) ** 0.5
    nb = sum(y * y for y in b) ** 0.5
    if na == 0 or nb == 0:
        return 0.0 if na == nb else 1.0
    return 1.0 - (dot / (na * nb))
