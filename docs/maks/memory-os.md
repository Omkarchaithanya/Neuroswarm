"""MAKS Memory Operating System — architecture."""

# MAKS Memory OS (Layer 5)

**MAKS** is NEXUS **Layer 5** — the Global KV Memory Operating System.

It owns the full inference-KV lifecycle: allocation, global page pool, sharing,
reference counting, CoW snapshots, deduplication, tiered migration, scored
eviction, capability discovery, and telemetry.

Plane 2 (`neuroswarm_arm/runtime/kv/`) remains a **compatibility facade**;
pressure and lifecycle policy are owned by MAKS. Cognitive Mem0 / OKF stay
orthogonal (`docs/memory/architecture.md`).

## Layer map

| Layer | Module | Role |
|-------|--------|------|
| L1 Manager | `manager.py`, `handles.py`, `registry.py` | Session/handle/ownership |
| L2 Page Pool | `pool.py` | UUID pages, tier, NUMA, checksum, refs |
| L3 Refcount | `reference_counter.py` | Share, CoW, snapshot/version |
| L4 Dedup | `deduplicator.py` / `dedup.py` | SHA256/BLAKE3, identity-gated |
| L5 Tiers | `providers/`, `tier_manager.py` | RAM→mmap→Redis→NVMe→CXL(stub) |
| L6 Migration | `migration.py`, `pager.py` | Hot/warm/cold, rollback |
| L7 Compression | `compressor.py` | LZ4/Zstd lazy inflate |
| L8 Eviction | `eviction.py`, `policies/scored.py` | Multi-signal score (default) |
| L9 Capability | `capability.py`, `engines/` | `supports_*()` matrix |
| L10 Telemetry | `telemetry.py`, `pressure_monitor.py` | Prometheus + OTel hooks |

## Provider HAL

```text
IKVProvider
  allocate/store/load/share/delete/migrate/exists/stats/pin/unpin/warm/cold/flush
  ├── ram / mmap / redis / nvme
  ├── future_mte   AVAILABLE=False
  └── future_cxl   AVAILABLE=False
```

## Capability detection

Every backend exposes:

- `supports_prefix_reuse()`
- `supports_shared_kv()`
- `supports_paged_kv()`
- `supports_speculative_kv()`
- `supports_cross_session_reuse()`
- `supports_cross_model_reuse()` — **default False**

See [capability-matrix.md](capability-matrix.md).

## Identity (AQR-safe)

`KVIdentity`: model_id, quantization, tokenizer_version, rope_config, context_window.
Different quants **cannot** share blindly.

## Lifecycle

```text
Allocated → Warmed → Shared → Pinned → Migrated → Released → Evicted → Destroyed
```

## Integrations (DI, no cycles)

- **DIPA** — `IKVCacheConnector` / `MAKSConnector` (capability-aware)
- **AWPP** — prefetch
- **AQR** — identity metadata
- **HAOE** — locality hints; pressure from MAKS
- **ARMORA** — admit/budget
- **RTG / Cascade** — `pressure_snapshot()` from MAKS
- **AROP** — live eviction/tier knobs via `MAKSDeploymentAdapter`
- **Mem0 / OKF / ACR** — orthogonal cognitive/institutional memory

## Public API

```python
from neuroswarm_arm.runtime.maks import build_maks, load_maks_config, KVIdentity

maks = build_maks(load_maks_config("work/kv"), enable_scheduler=False)
handle = await maks.create(b"...", agent_id="a1", identity=KVIdentity(...))
await maks.share(handle.kv_id, "a2")
print(maks.capability_matrix())
print(maks.pressure_snapshot())
```

REST: `/maks/status`, `/maks/capabilities`, `/maks/create`, `/maks/share`, `/maks/migrate`, `/maks/lookup/{id}`, `/maks/prefetch`.
