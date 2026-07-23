#!/usr/bin/env python3
"""Q8 codec encode/decode throughput benchmark."""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from neuroswarm_arm.runtime.maks.q8_codec import decode_q8, encode_q8


def _bench(data: bytes, rounds: int = 200) -> dict:
    import random
    import struct

    from neuroswarm_arm.runtime.maks.q8_codec import encode_f32_vector

    t0 = time.perf_counter()
    encoded = encode_q8(data)
    encode_ms = (time.perf_counter() - t0) * 1000.0

    t1 = time.perf_counter()
    for _ in range(rounds):
        decode_q8(encoded)
    decode_ms = (time.perf_counter() - t1) * 1000.0 / rounds

    ratio = len(encoded) / max(1, len(data))
    f32_vals = [random.uniform(-1.0, 1.0) for _ in range(4096)]
    f32_raw = struct.pack(f"<{len(f32_vals)}f", *f32_vals)
    f32_enc = encode_f32_vector(f32_vals)
    f32_ratio = len(f32_enc) / max(1, len(f32_raw))
    mb = len(data) / (1024 * 1024)
    encode_mbps = mb / (encode_ms / 1000.0) if encode_ms else 0.0
    decode_mbps = mb / (decode_ms / 1000.0) if decode_ms else 0.0
    return {
        "original_bytes": len(data),
        "encoded_bytes": len(encoded),
        "compression_ratio": ratio,
        "f32_compression_ratio": f32_ratio,
        "encode_ms": round(encode_ms, 3),
        "decode_ms_p50": round(decode_ms, 3),
        "encode_mbps": round(encode_mbps, 2),
        "decode_mbps": round(decode_mbps, 2),
    }


def main() -> None:
    payload = json.dumps(
        {"session_id": "bench", "completion_preview": "x" * 2048}
    ).encode("utf-8")
    payload *= 64
    report = {
        "status": "ok",
        "q8_bench": _bench(payload),
        "overhead_budget_ms": 5.0,
        "within_budget": _bench(payload)["decode_ms_p50"] < 5.0,
    }
    out = ROOT / "work" / "benchmarks" / "q8_codec_bench.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
