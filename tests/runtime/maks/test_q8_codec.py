"""Q8 codec property and integration tests."""

from __future__ import annotations

import json
import random
import struct

import pytest

from neuroswarm_arm.runtime.maks.q8_codec import (
    cosine_distance,
    decode_f32_vector,
    decode_q8,
    encode_f32_vector,
    encode_q8,
)


@pytest.mark.parametrize("dim", [64, 768, 4096])
def test_f32_roundtrip_cosine(dim: int) -> None:
    rng = random.Random(42)
    vec = [rng.uniform(-1.0, 1.0) for _ in range(dim)]
    encoded = encode_f32_vector(vec)
    decoded = decode_f32_vector(encoded)
    assert len(decoded) == dim
    assert cosine_distance(vec, decoded) <= 0.01


def test_per_block_symmetric_no_zero_point() -> None:
    data = bytes(range(256)) * 4
    encoded = encode_q8(data)
    assert encoded[:4] == b"NSQ8"
    assert encoded[4] == 2
    # each block header scale + int8 payload
    block_size = struct.unpack("<I", encoded[9:13])[0]
    offset = 13
    while offset < len(encoded):
        scale = struct.unpack("<f", encoded[offset : offset + 4])[0]
        offset += 4
        block = encoded[offset : offset + block_size]
        offset += len(block)
        for q in block:
            assert -127 <= (q if q < 128 else q - 256) <= 127
        assert scale >= 0.0


def test_compression_ratio_f32_vectors() -> None:
    rng = random.Random(7)
    values = [rng.uniform(-2.0, 2.0) for _ in range(4096)]
    raw = struct.pack(f"<{len(values)}f", *values)
    encoded = encode_f32_vector(values)
    ratio = len(encoded) / len(raw)
    assert ratio <= 0.27


def test_byte_roundtrip() -> None:
    data = b"neuroswarm " * 512
    assert decode_q8(encode_q8(data)) == data


def test_v1_backward_compat() -> None:
    from neuroswarm_arm.runtime.maks.q8_codec import _VERSION_V1

    data = bytes([10, 20, 30, 40])
    signed = [b if b < 128 else b - 256 for b in data]
    scale = max(abs(v) for v in signed) / 127.0
    quantized = bytes(max(-127, min(127, int(round(v / scale)))) for v in signed)
    v1 = b"NSQ8" + struct.pack("<B", _VERSION_V1) + struct.pack("<If", len(data), scale) + quantized
    assert decode_q8(v1) == data
