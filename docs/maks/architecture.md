# MAKS Architecture (Layer 5) — Memory OS

**MAKS (Multi-Agent KV-Cache Sharing)** is NEXUS **Layer 5** — the Global KV
**Memory Operating System**.

Plane 2 (`neuroswarm_arm/runtime/kv/`) is a compatibility substrate / facade.
MAKS owns lifecycle, global page pool, registry, dedup identity, sharing policy,
scored eviction, migration/paging, capability discovery, prefetch, and peer
integrations. See also [memory-os.md](memory-os.md) and
[capability-matrix.md](capability-matrix.md).

## Layer vs plane

| Concept | Role |
|---------|------|
| Layer 5 MAKS | Memory OS: create/share/lookup/release/migrate/pin/prefetch + pages |
| Plane 2 KV | Facade + block helpers; pressure delegated to MAKS when bound |
| DIPA `IKVCacheConnector` | Port only — DIPA asks, never owns storage (ADR-0003) |

## Provider HAL

```text
KVProvider ABC
  allocate/store/load/share/delete/migrate/exists/stats/pin/unpin/warm/cold/flush
  ├── ram_backend      (multiprocessing.shared_memory capable)
  ├── mmap_backend
  ├── redis_backend
  ├── nvme_backend     (cold + compression)
  ├── future_mte_backend   AVAILABLE=False
  └── future_cxl_backend   AVAILABLE=False
```

Runtime logic never imports hardware syscalls for MTE/CXL. Future ARM boards
plug in by implementing `IKVProvider`. Native stubs live under `maks/native/`.

## Global page pool

Logical handles map to ordered `PageMeta` entries (UUID, tier, checksum,
refcount, share_count, NUMA, backend caps, identity fingerprint). CoW and
snapshot/version tracking supported.

## Identity (AQR-safe)

KV entries keyed by `KVIdentity`:

- model_id
- quantization
- tokenizer_version
- rope_config
- context_window

Different quantizations **cannot** share blindly. Cross-model reuse requires
`supports_cross_model_reuse()` (default **False**).

## Eviction

Default policy is **scored** (recency × frequency × sharing × importance ×
prediction × cascade stage × reasoning depth − pressure). LRU/LFU/ARC remain
pluggable.

## Lifecycle

```text
Allocated → Warmed → Shared → Pinned → Migrated → Released → Evicted → Destroyed
```

Pinned entries are never evicted.

## Integrations

- **DIPA** — `MAKSConnector(sharing=maks_runtime)` — capability-aware
- **AWPP** — `HeuristicWarmConnector.bind_maks` → `prefetch()`
- **AQR** — quant/model → `KVIdentity`
- **HAOE** — locality hints; **pressure from MAKS**
- **ARMORA** — `ArmoraBudgetPolicy.admit()`
- **RTG / Cascade** — `pressure_snapshot()` from MAKS
- **AROP** — live `maks_eviction_weight` / `maks_tier_threshold` knobs

## Config

`NSA_MAKS_*` composes with `NSA_KV_*`. Defaults: scored eviction,
`NSA_MAKS_BACKEND=opaque`, `NSA_MAKS_PAGE_BYTES`.

## Public API

```python
from neuroswarm_arm.runtime.maks import build_maks, load_maks_config

maks = build_maks(load_maks_config("work/kv"), enable_scheduler=False)
handle = await maks.create(b"...", agent_id="a1", identity=KVIdentity(...))
await maks.share(handle.kv_id, "a2")
```

REST: `/maks/status`, `/maks/capabilities`, `/maks/create`, `/maks/share`,
`/maks/migrate`, `/maks/lookup/{id}`, `/maks/prefetch`.
