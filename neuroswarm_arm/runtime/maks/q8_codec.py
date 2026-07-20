"""Q8 byte-payload compression for MAKS persistent tier."""

from __future__ import annotations

import struct

_MAGIC = b"NSQ8"
_VERSION = 1


def encode_q8(data: bytes) -> bytes:
    if not data:
        return _MAGIC + struct.pack("<B", _VERSION) + struct.pack("<I", 0)
    scale = max(abs(b) for b in data) / 127.0 if data else 1.0
    if scale <= 0:
        scale = 1.0
    quantized = bytes(max(-127, min(127, int(round(b / scale)))) for b in data)
    header = _MAGIC + struct.pack("<B", _VERSION) + struct.pack("<If", len(data), scale)
    return header + quantized


def decode_q8(blob: bytes) -> bytes:
    if len(blob) < 13 or blob[:4] != _MAGIC:
        return blob
    version = blob[4]
    if version != _VERSION:
        return blob
    orig_len, scale = struct.unpack("<If", blob[5:13])
    body = blob[13:]
    out = bytearray()
    for q in body[:orig_len]:
        qv = q if q < 128 else q - 256
        out.append(int(max(0, min(255, round(qv * scale)))))
    return bytes(out)
