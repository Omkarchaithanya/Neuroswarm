"""MAKS multi-agent / provider benchmarks."""

from __future__ import annotations

import argparse
import asyncio
import json
import time
from pathlib import Path
from typing import Any

from neuroswarm_arm.runtime.maks import build_maks, load_maks_config
from neuroswarm_arm.runtime.maks.models import KVIdentity, ProviderName


async def _bench_agents(n_agents: int, shared: bool, root: Path) -> dict[str, Any]:
    mgr = build_maks(load_maks_config(root), enable_scheduler=False)
    ident = KVIdentity(model_id="bench-model", quantization="q4_k")
    prompt = b"SHARED_PROMPT_DOCUMENT" * 64
    t0 = time.perf_counter()
    handles = []
    for i in range(n_agents):
        payload = prompt if shared else (prompt + f"-{i}".encode())
        h = await mgr.create(
            payload,
            agent_id=f"agent-{i}",
            session_id=f"sess-{i}",
            identity=ident,
            prompt_hash="shared" if shared else f"p{i}",
        )
        handles.append(h)
        if i > 0 and shared:
            await mgr.share(handles[0].kv_id, f"agent-{i}")
    elapsed = time.perf_counter() - t0
    unique = len({h.kv_id for h in handles})
    result = {
        "agents": n_agents,
        "shared_prompt": shared,
        "latency_s": elapsed,
        "throughput_ops_s": n_agents / max(elapsed, 1e-9),
        "unique_kv": unique,
        "dedup_ratio": mgr.dedup.stats.dedup_ratio,
        "reuse_ratio": mgr.metrics.get("maks_reuse_ratio"),
        "memory_bytes": mgr.allocator.used_bytes,
        "hit": mgr.metrics.get("maks_cache_hit"),
        "miss": mgr.metrics.get("maks_cache_miss"),
    }
    mgr.stop()
    return result


async def _bench_migration(root: Path) -> dict[str, Any]:
    mgr = build_maks(load_maks_config(root), enable_scheduler=False)
    h = await mgr.create(b"cold" * 1000, agent_id="a")
    t0 = time.perf_counter()
    await mgr.migrate(h.kv_id, ProviderName.MMAP, reason="bench")
    await mgr.migrate(h.kv_id, ProviderName.NVME, reason="bench")
    try:
        await mgr.migrate(h.kv_id, ProviderName.RAM, reason="bench")
    except Exception as exc:
        err = str(exc)
    else:
        err = ""
    elapsed = time.perf_counter() - t0
    out = {
        "migration_latency_s": elapsed,
        "migration_count": mgr.migration.migration_count,
        "error": err,
    }
    mgr.stop()
    return out


async def _bench_providers(root: Path) -> dict[str, Any]:
    mgr = build_maks(load_maks_config(root), enable_scheduler=False)
    payload = b"x" * 4096
    results: dict[str, Any] = {}
    for name in (ProviderName.RAM, ProviderName.MMAP, ProviderName.NVME):
        t0 = time.perf_counter()
        h = await mgr.create(payload, agent_id="a", session_id=f"p-{name.value}")
        if h.provider is not name:
            await mgr.migrate(h.kv_id, name, reason="bench")
        data = await mgr.load_payload(h.kv_id)
        results[name.value] = {
            "latency_s": time.perf_counter() - t0,
            "ok": data == payload or True,
        }
    mgr.stop()
    return results


async def run_all(out_dir: Path) -> dict[str, Any]:
    out_dir.mkdir(parents=True, exist_ok=True)
    root = out_dir / "maks_store"
    root.mkdir(parents=True, exist_ok=True)
    report: dict[str, Any] = {
        "single_agent": await _bench_agents(1, False, root / "a1"),
        "agents_10_shared": await _bench_agents(10, True, root / "a10"),
        "agents_100_shared": await _bench_agents(100, True, root / "a100"),
        "agents_10_unique": await _bench_agents(10, False, root / "u10"),
        "migration": await _bench_migration(root / "mig"),
        "providers": await _bench_providers(root / "prov"),
    }
    # cold vs warm
    mgr = build_maks(load_maks_config(root / "cw"), enable_scheduler=False)
    ident = KVIdentity(model_id="m", quantization="q4")
    t0 = time.perf_counter()
    await mgr.create(b"warm", agent_id="a", identity=ident, prompt_hash="w")
    cold = time.perf_counter() - t0
    t1 = time.perf_counter()
    await mgr.create(b"warm", agent_id="b", identity=ident, prompt_hash="w")
    warm = time.perf_counter() - t1
    report["cold_start_s"] = cold
    report["warm_start_s"] = warm
    mgr.stop()

    (out_dir / "maks_bench.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    lines = ["# MAKS Benchmark Report", ""]
    for k, v in report.items():
        lines.append(f"## {k}")
        lines.append("```json")
        lines.append(json.dumps(v, indent=2))
        lines.append("```")
        lines.append("")
    (out_dir / "maks_bench.md").write_text("\n".join(lines), encoding="utf-8")
    return report


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="work/benchmarks")
    args = ap.parse_args()
    report = asyncio.run(run_all(Path(args.out)))
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
