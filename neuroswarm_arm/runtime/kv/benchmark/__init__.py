"""In-package KV benchmark runners."""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any

from ..manager.runtime import KVRuntimeManager


async def bench_prefix(runtime: KVRuntimeManager, iterations: int = 50) -> dict[str, Any]:
    payloads = [f"prefix-block-{i}".encode("utf-8") * 8 for i in range(8)]
    session = f"bench-prefix-{int(time.time())}"
    prefix = ""
    for i, payload in enumerate(payloads):
        block = await runtime.allocate(session, payload, token_start=i * 256, prefix_hash=prefix)
        prefix = block.content_hash
    start = time.monotonic()
    hits = 0
    for _ in range(iterations):
        match = runtime.lookup_prefix(payloads)
        if match.hit:
            hits += 1
    elapsed = (time.monotonic() - start) * 1000.0
    await runtime.release(session)
    return {
        "name": "prefix",
        "iterations": iterations,
        "hits": hits,
        "hit_rate": hits / max(1, iterations),
        "latency_ms_total": elapsed,
        "latency_ms_avg": elapsed / max(1, iterations),
    }


async def bench_restore(runtime: KVRuntimeManager, iterations: int = 10) -> dict[str, Any]:
    latencies: list[float] = []
    for i in range(iterations):
        sid = f"bench-restore-{i}-{int(time.time() * 1000)}"
        await runtime.allocate(sid, b"restore-payload-" + bytes([i % 256]) * 64)
        await runtime.checkpoint(sid)
        await runtime.release(sid)
        t0 = time.monotonic()
        await runtime.restore(sid)
        latencies.append((time.monotonic() - t0) * 1000.0)
        await runtime.release(sid)
    return {
        "name": "restore",
        "iterations": iterations,
        "latency_ms_avg": sum(latencies) / max(1, len(latencies)),
        "latency_ms_p50": sorted(latencies)[len(latencies) // 2] if latencies else 0.0,
    }


async def bench_share(runtime: KVRuntimeManager, iterations: int = 20) -> dict[str, Any]:
    sid = f"bench-share-{int(time.time())}"
    block = await runtime.allocate(sid, b"shared-payload" * 16)
    assert block.physical_id
    t0 = time.monotonic()
    for i in range(iterations):
        await runtime.share(block.physical_id, f"consumer-{i}")
    elapsed = (time.monotonic() - t0) * 1000.0
    await runtime.release(sid)
    return {
        "name": "share",
        "iterations": iterations,
        "latency_ms_avg": elapsed / max(1, iterations),
    }


async def bench_compress(runtime: KVRuntimeManager, iterations: int = 20) -> dict[str, Any]:
    from ..interfaces.types import StorageTier

    sid = f"bench-compress-{int(time.time())}"
    payload = (b"compressible-" * 256)
    block = await runtime.allocate(sid, payload)
    assert block.physical_id
    t0 = time.monotonic()
    for _ in range(iterations):
        await runtime.migrate(block.physical_id, StorageTier.L2_COMPRESSED_RAM)
        await runtime.migrate(block.physical_id, StorageTier.L1_RAM)
    elapsed = (time.monotonic() - t0) * 1000.0
    metrics = runtime.metrics()
    await runtime.release(sid)
    return {
        "name": "compress",
        "iterations": iterations,
        "latency_ms_avg": elapsed / max(1, iterations),
        "compression_ratio": metrics.get("kv_compression_ratio", 1.0),
    }


async def bench_checkpoint(runtime: KVRuntimeManager, iterations: int = 10) -> dict[str, Any]:
    latencies: list[float] = []
    for i in range(iterations):
        sid = f"bench-ckpt-{i}-{int(time.time() * 1000)}"
        await runtime.allocate(sid, b"ckpt" * 128)
        t0 = time.monotonic()
        await runtime.checkpoint(sid)
        latencies.append((time.monotonic() - t0) * 1000.0)
        await runtime.release(sid)
    return {
        "name": "checkpoint",
        "iterations": iterations,
        "latency_ms_avg": sum(latencies) / max(1, len(latencies)),
    }


async def bench_dedup(runtime: KVRuntimeManager, iterations: int = 50) -> dict[str, Any]:
    sid = f"bench-dedup-{int(time.time())}"
    payload = b"identical-block-payload" * 32
    t0 = time.monotonic()
    for _ in range(iterations):
        await runtime.deduplicate(sid, payload)
    elapsed = (time.monotonic() - t0) * 1000.0
    metrics = runtime.metrics()
    await runtime.release(sid)
    return {
        "name": "dedup",
        "iterations": iterations,
        "latency_ms_avg": elapsed / max(1, iterations),
        "dedup_ratio": metrics.get("kv_dedup_ratio", 0.0),
        "blocks_total": metrics.get("kv_blocks_total", 0.0),
    }


async def bench_latency(runtime: KVRuntimeManager, iterations: int = 100) -> dict[str, Any]:
    latencies: list[float] = []
    sid = f"bench-lat-{int(time.time())}"
    for i in range(iterations):
        payload = f"lat-{i}".encode("utf-8") * 16
        t0 = time.monotonic()
        await runtime.allocate(sid, payload, token_start=i * 256)
        latencies.append((time.monotonic() - t0) * 1000.0)
    await runtime.release(sid)
    ordered = sorted(latencies)
    return {
        "name": "latency",
        "iterations": iterations,
        "latency_ms_avg": sum(latencies) / max(1, len(latencies)),
        "latency_ms_p50": ordered[len(ordered) // 2],
        "latency_ms_p95": ordered[int(len(ordered) * 0.95)],
    }


async def bench_scaling(runtime: KVRuntimeManager, iterations: int = 5) -> dict[str, Any]:
    sizes = [10, 50, 100, 200]
    results = []
    for n in sizes:
        sid = f"bench-scale-{n}-{int(time.time() * 1000)}"
        t0 = time.monotonic()
        for i in range(n):
            await runtime.allocate(sid, f"scale-{i}".encode("utf-8") * 8, token_start=i * 256)
        elapsed = (time.monotonic() - t0) * 1000.0
        results.append({"blocks": n, "latency_ms": elapsed, "per_block_ms": elapsed / n})
        await runtime.release(sid)
    return {"name": "scaling", "iterations": iterations, "series": results}


BENCHMARKS = {
    "prefix": bench_prefix,
    "restore": bench_restore,
    "share": bench_share,
    "compress": bench_compress,
    "checkpoint": bench_checkpoint,
    "dedup": bench_dedup,
    "latency": bench_latency,
    "scaling": bench_scaling,
}


async def run_named_benchmark(
    runtime: KVRuntimeManager,
    name: str,
    *,
    iterations: int = 50,
) -> dict[str, Any]:
    fn = BENCHMARKS.get(name)
    if fn is None:
        raise ValueError(f"unknown benchmark: {name}; choose from {sorted(BENCHMARKS)}")
    result = await fn(runtime, iterations=iterations)
    result["pressure"] = runtime.pressure_snapshot().to_dict()
    return result


def write_report(path: Path, results: list[dict[str, Any]]) -> Path:
    import json

    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {"results": results, "generated_at": time.time()}
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    md = path.with_suffix(".md")
    lines = ["# KV Memory Runtime Benchmark Report", ""]
    for r in results:
        lines.append(f"## {r.get('name')}")
        for k, v in r.items():
            if k == "name":
                continue
            lines.append(f"- **{k}**: `{v}`")
        lines.append("")
    md.write_text("\n".join(lines), encoding="utf-8")
    return path


__all__ = [
    "BENCHMARKS",
    "run_named_benchmark",
    "write_report",
]
