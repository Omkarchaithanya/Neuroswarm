# Layer 5 MAKS — Audit Report

**Date:** 2026-07-27T18:45:00Z

**Auditor:** Cursor Plan Agent

**Verdict:** FAIL

## Executive summary

- Core Memory OS (`KVManager`, `GlobalPagePool`, dedup, migration, eviction, scheduler, Prometheus `maks_*`) is **real and tested** — 38/38 pytest pass on win32.
- Pitch claims for **MTE zero-copy**, **2× concurrent agents**, and **“first MTE application”** are **not shippable** on this host (MTE unavailable; concurrency metric is `ram_budget / avg_kv_size` extrapolation).
- Multi-agent dedup bench reports **87.5%** savings on **synthetic session-metadata blobs**, not GGML inference KV tensors (`benchmarks/maks_multi_agent_dedup_bench.py`).
- **SECURITY_FLAG:** `share()` grants read without `KVIdentity` gate; `release()` does not revoke `SharePermission` tokens — adversarial probes 1 and 4 **FAIL**.
- **MTE honesty OK:** unavailable backends **raise** `KVProviderUnavailableError` (no silent RAM fallback).

## Phase 1 — Static architecture

### File role index (`neuroswarm_arm/runtime/maks/` — 75 files)

| File | Role |
|------|------|
| `__init__.py` | Layer 5 public exports (`build_maks`, `KVManager`, models, pool) |
| `api.py` | Optional FastAPI `/maks/*` router |
| `allocator.py` | NUMA/locality-aware KV allocator facade |
| `capability.py` | `CapabilityRegistry` and backend feature gates |
| `compression.py` | Compression codec builders (Q8/LZ4/ZSTD/stub) |
| `compressor.py` | Lazy decompress facade for cold pages |
| `config.py` | `MAKSConfig` and `NSA_MAKS_*` env loading |
| `dedup.py` | `DeduplicationEngine` keyed by identity + content |
| `deduplicator.py` | Memory OS alias for `DeduplicationEngine` |
| `eviction.py` | `EvictionEngine` with pluggable policies |
| `exceptions.py` | Typed MAKS exception hierarchy |
| `factory.py` | `build_maks()` DI factory |
| `handles.py` | Session/handle binding registry |
| `hashing.py` | SHA256/BLAKE3/xxhash identity and content hashers |
| `lifecycle.py` | KV lifecycle state machine |
| `manager.py` | `KVManager` — create/share/lookup/migrate control plane |
| `metadata.py` | `KVMetadata` builders and timestamps |
| `metrics.py` | `MAKSMetrics` Prometheus bridge |
| `migration.py` | RAM→mmap→Redis→NVMe migration engine |
| `models.py` | Pydantic domain models (`KVIdentity`, `SharePermission`, …) |
| `pager.py` | Page-in/page-out via `MigrationEngine` + `TierManager` |
| `pool.py` | `GlobalPagePool` / `PageMeta` page-table semantics |
| `prefetch.py` | `PrefetchEngine` for AWPP warm paths |
| `pressure_monitor.py` | Unified pressure snapshot for eviction/RTG |
| `provider.py` | `BaseKVProvider` pin/warm/share defaults |
| `q8_codec.py` | Per-block Q8 byte-payload codec |
| `reference_counter.py` | Refcount with orphan/zombie tracking |
| `registry.py` | `KVRegistry` with optional durable store |
| `scheduler.py` | Background `MAKSScheduler` tick loop |
| `sharing.py` | `SharingEngine` token grants and MTE tags |
| `telemetry.py` | `MAKSTelemetry` Prometheus series publisher |
| `tier_manager.py` | Hot/warm/cold provider ladder |
| `utils.py` | `new_kv_id`, `new_token`, timing helpers |
| `docs/README.md` | In-package MAKS documentation |
| `backends/__init__.py` | `build_default_backends()` provider map |
| `backends/_adapter.py` | `Plane2ProviderAdapter` MAKS↔Plane-2 bridge |
| `backends/future_cxl_backend.py` | CXL stub — raises when unavailable |
| `backends/future_mte_backend.py` | MTE stub — raises when unavailable |
| `backends/mmap_backend.py` | mmap warm-tier backend wrapper |
| `backends/mte_backend.py` | Real MTE backend when `native_mte.AVAILABLE` |
| `backends/nvme_backend.py` | NVMe cold-tier backend with optional compression |
| `backends/ram_backend.py` | RAM hot tier; optional `SharedMemoryBackend` share |
| `backends/redis_backend.py` | Redis warm-tier backend wrapper |
| `benchmarks/__init__.py` | In-package benchmarks package marker |
| `benchmarks/__main__.py` | CLI entry → `benchmarks.runner` |
| `benchmarks/runner.py` | In-package multi-agent/provider benchmark runner |
| `engines/__init__.py` | `build_default_engines()` capability adapters |
| `engines/llama_cpp.py` | llama.cpp capability flags adapter |
| `engines/sglang.py` | SGLang capability flags adapter |
| `engines/stubs.py` | TensorRT-LLM / DeepSpeed / TGI stub adapters |
| `engines/vllm.py` | vLLM capability flags adapter |
| `interfaces/__init__.py` | MAKS protocol ABCs (`IKVProvider`, `IHasher`, …) |
| `interfaces/allocator.py` | Allocator interface re-export |
| `interfaces/cache.py` | Cache lookup interface re-export |
| `interfaces/compression.py` | Compression interface re-export |
| `interfaces/migration.py` | Migration interface re-export |
| `interfaces/provider.py` | Provider interface re-export |
| `interfaces/security.py` | Security interface re-export |
| `native/__init__.py` | `feature_matrix()` ARM capability detection |
| `native/compression/__init__.py` | Native compression hooks placeholder |
| `native/mte/__init__.py` | MTE detect, `PROT_MTE` mmap, prctl, SIGSEGV handler |
| `native/numa/__init__.py` | NUMA helpers (degrade to node 0 on Axion) |
| `policies/__init__.py` | `build_policy()` eviction factory |
| `policies/arc.py` | ARC-inspired eviction policy |
| `policies/cost_aware.py` | Cost-aware eviction policy |
| `policies/lfu.py` | LFU eviction policy |
| `policies/lru.py` | LRU eviction policy |
| `policies/s3fifo.py` | S3-FIFO eviction policy |
| `policies/scored.py` | Scored eviction policy (default) |
| `policies/temperature.py` | Temperature-based eviction policy |
| `providers/__init__.py` | Provider HAL re-exports |
| `storage/__init__.py` | Registry storage package |
| `storage/redis_registry.py` | Redis-backed registry persistence |
| `storage/sqlite_registry.py` | SQLite-backed registry persistence |
| `tests/__init__.py` | Package-local tests re-export path |

### Architecture Q&A

| # | Question | Answer | Citation |
|---|----------|--------|----------|
| 1 | Real `KVManager` with all lifecycle methods? | **Yes** | `create` `manager.py:146`; `lookup` `303`; `share` `365`; `release` `391`; `migrate` `407`; `pin` `464`; `warm` `488`; `cold` `502`; `prefetch` `523`; `cleanup` `526`; `relieve_pressure` `544` |
| 2 | `GlobalPagePool` page-table semantics? | **Yes** — `PageMeta` has page_id (UUID via `new_page_id`), tier, refcount, share_count, numa_node, capabilities, content_hash, prefix_hash, version, cow | `pool.py:18-48`, `66` |
| 3 | `DeduplicationEngine` keyed by `KVIdentity.fingerprint()`? | **Yes** — fingerprint joins model_id, quantization, tokenizer_version, rope_config, context_window; used in `make_key` via `hasher.hash_identity` | `models.py:63-71`; `dedup.py:56-66`, `117` |
| 4 | `SharingEngine` + `SharePermission`? | **Yes** — owner, consumer, kv_id, can_read, can_write, token | `sharing.py:20-41`; `models.py:142-148` |
| 5 | `CapabilityRegistry` 6 gates; default `cross_model_reuse=False`? | **Yes** | `capability.py:87-102` |
| 6 | `ReferenceCounter` orphan/zombie; `orphan_grace_s`? | **Yes** — default `300.0` | `reference_counter.py:22-25`, `67-82`; `config.py:57` |
| 7 | `MigrationEngine` + `Pager` RAM→mmap→Redis→NVMe? | **Yes** | `migration.py:11-18`, `84-94`; `pager.py:22-33` |
| 8 | `PressureMonitor` feeds `EvictionEngine`? | **Yes** — `relieve_pressure` snapshots pressure, sets eviction signals | `manager.py:120-127`, `544-558` |
| 9 | `Scheduler` background loop start/stop? | **Yes** | `scheduler.py:47-58`; `manager.py:674-678` |
| 10 | Prometheus `maks_*` metrics? | **Yes** | `telemetry.py:11-33`; counters/gauges also in `manager.py:612-634` |

## Phase 2 — Backend honesty

### Host probes (audit host: win32)

```
/proc/cpuinfo: not present (Windows)
libc: None
getauxval: False
native_mte.AVAILABLE: False
```

Equivalent Linux probe (not runnable here):

```bash
rg -E "mte|mte2" /proc/cpuinfo | head -3 || echo "no mte in cpuinfo"
python3 -c "import ctypes, ctypes.util; libc=ctypes.CDLL(ctypes.util.find_library('c')); print('getauxval:', hasattr(libc,'getauxval'))"
```

### Backend verdicts

| Backend | Verdict | Evidence |
|---------|---------|----------|
| `ram_backend.py` | **FALLBACK-ONLY** | Default `share()` returns token string (`provider.py:27-28`). With `use_shared_memory=True` (`backends/__init__.py:25`), `share()` **copies** via `load`+`store` then shm token (`ram_backend.py:21-26`) — not zero-copy |
| `mmap_backend.py` | **REAL** (read path) | File-backed storage via `MemoryMappedProvider`; read uses `mmap.ACCESS_READ` (`mmap_provider.py:63-71`) — **not** `MAP_SHARED` write sharing |
| `redis_backend.py` | **FALLBACK-ONLY** on audit host | Client init + ping when Redis up (`redis_provider.py:23-38`); `_available=False` and `_require()` raises when down (`55-59`) |
| `nvme_backend.py` | **REAL** | Disk put/get via `NVMeProvider` (`nvme_backend.py:14-28`) |
| `future_mte_backend.py` | **RAISES-ON-ALL-CALLS** | `_raise()` → `KVProviderUnavailableError` on allocate/store/load/delete/migrate (`future_mte_backend.py:19-46`) |
| `mte_backend.py` | **RAISES-ON-ALL-CALLS** when MTE unavailable; **REAL** when `native_mte.AVAILABLE` | `_require_available()` (`mte_backend.py:45-47`); PROT_MTE mmap/prctl/SIGSEGV in `native/mte/__init__.py:103-266` |
| `future_cxl_backend.py` | **RAISES-ON-ALL-CALLS** | Same stub pattern (`future_cxl_backend.py:19-46`) |

## Phase 3 — Control-plane integrity

### Agent chat → `KVManager.create` trace

| Step | File:line | Action |
|------|-----------|--------|
| 1 | `execution_pipeline.py:175-177` | `kv_cache_manager.load(session_id, agent_id)` pre-chat |
| 2 | `kv_cache_manager.py:44-63` | `connector.load(...)` |
| 3 | `maks_connector.py:73-93` | Session→kv_id lookup via manager or fallback |
| 4 | `execution_pipeline.py:204-224` | `kv_cache_manager.save(...)` post-chat with model/quant metadata |
| 5 | `kv_cache_manager.py:65-88` | `connector.save(...)` |
| 6 | `maks_connector.py:108-129` | Build `KVIdentity`, call `_manager.create(...)` |
| 7 | `manager.py:146-301` | `KVManager.create()` |

### Integrity checks

| Check | Result | Citation |
|-------|--------|----------|
| `create()` calls `sharing.grant()` for owner? | **No** — owner implicit reader via `check_read` owner branch | `sharing.py:111-114` |
| `share()` increments refcount, readers, `pool.increment_share()`? | **Yes** | `manager.py:377-384`; `pool.py:166` |
| `lookup()` honors `identity.compatible_with()`? | **Yes** — raises `KVIdentityMismatchError` | `manager.py:322-323` |
| `relieve_pressure()` demote before delete? | **Yes** — `page_out` / `migration.demote` before `delete` | `manager.py:565-578` |
| Identity-incompatible `share()` path? | **SECURITY_FLAG** — `share(kv_id, consumer_id)` has no `KVIdentity` parameter or check | `manager.py:365-389` |
| `delete()` on pinned without `force=True`? | **CORRECTNESS OK** — raises `KVPinnedError` | `manager.py:422-423` |

### SECURITY_FLAGs

1. **`share()` lacks identity gate** — any consumer granted read if they know `kv_id`; `load_payload()` has no agent/token check (`manager.py:511-521`).
2. **`release()` does not revoke share tokens** — `SharePermission` remains in `_perms` after consumer release (`manager.py:391-405`; `sharing.py` has no revoke call from `release`).

### CORRECTNESS_FLAGs

None — pinned delete correctly raises; cleanup uses `force=True` for TTL (`manager.py:532`).

## Phase 4 — Runtime smoke

### pytest (`uv run pytest tests/runtime/maks/ -v --tb=short`)

```
38 passed in 94.73s (0:01:34)
0 failed
```

All 38 tests passed (integration 7, mte 6, q8 7, unit 18).

### Benchmark inventory

```
benchmarks/kv_share.py
benchmarks/maks_multi_agent_dedup_bench.py
```

### `benchmarks/maks_multi_agent_dedup_bench.py` (tail output)

```
dedup_savings=87.5% | sharing=100.0% | agents@budget=127981 | refcount>1=20
{
  "dedup_savings_pct": 87.5,
  "sharing_savings_pct": 100.0,
  "concurrent_agents_supported": 127981,
  "dedup_run": { "provider_used_bytes": 6218, "unique_kv_ids": 20, "total_creates": 160 },
  "control_run": { "provider_used_bytes": 49744, "unique_kv_ids": 160, "total_creates": 160 }
}
```

### `benchmarks/kv_share.py` (Plane-2 KV runtime, not MAKS Layer 5)

```
{'name': 'share', 'iterations': 20, 'latency_ms_avg': 1.55, 'pressure': {'pressure': 0.0, ...}}
```

## Phase 5 — Spec mapping

| # | Spec line | Code location | Verdict | Evidence |
|---|-----------|---------------|---------|----------|
| 1 | Shared KV-Cache pool across all agents in a swarm | `manager.py:78-301`, `pool.py:66-276`, `registry.py:12+` | **A** | `tests/runtime/maks/test_unit.py::test_create_share_release`, `test_page_pool_registers_on_create` |
| 2 | When agents share context … KV caches deduplicated in memory | `dedup.py:46-123`, `manager.py:189-209` | **A** | `test_dedup_reuse`, `test_concurrent_creates` |
| 3 | Implements a shared KV-Cache pool | Same as #1 | **A** | `test_integration.py::test_dipa_connector_roundtrip` |
| 4 | 40-70% memory duplication eliminated | `dedup.py:46+`, `benchmarks/maks_multi_agent_dedup_bench.py` | **C** | `docs/evidence/latest/layer-verify/14-maks-dedup.json` (87.5% on synthetic blobs; not GGML KV tensors) |
| 5 | 2× more concurrent agents per server (ARM pitch) | `benchmarks/maks_multi_agent_dedup_bench.py` L concurrent_agents calc | **F** | `14-maks-dedup.json` `concurrent_agents_supported: 127981` = `ram_budget/avg_kv_size`; no measured 2× vs baseline |
| 6 | ARM MTE secure zero-copy sharing between agents | `backends/mte_backend.py`, `native/mte/__init__.py`, `backends/future_mte_backend.py` | **D** | `test_mte_unavailable_raises`; `native_mte.AVAILABLE=False` on audit host |
| 7 | First application of ARM MTE for AI workload security | No shipping MTE path | **F** | Marketing only; `future_mte_backend.py:19-22` |
| 8 | Problem statement: separate KV caches cause 40-70% duplication | `dedup.py` + bench | **C** | Bench validates synthetic scenario; not production inference KV |

## Phase 6 — Live evidence

| Check | Result |
|-------|--------|
| `LAYER_SCORECARD.md` §8 MAKS | **Yes** — `docs/evidence/latest/LAYER_SCORECARD.md:22-70` |
| `MEASURED.md` `maks_dedup_savings_pct` | **Yes** — 87.5% (`MEASURED.md:20`) |
| `MEASURED.md` `maks_concurrent_agents_supported` | **Yes** — 127981 (`MEASURED.md:22`) |
| `MEASURED.md` `maks_mte_available` | **No row** |
| `layer-verify/12-product-gaps.txt` exercises `/maks/*`? | **No** — no maks matches |
| `layer-verify/13-kleidi.txt` exercises `/maks/*`? | **No** — no maks matches |
| `scripts/layer-live-verify.sh` step 14 MAKS? | **Yes** — `scripts/layer-live-verify.sh:8-19` |
| `layer-verify/14-maks-dedup.json` | **Present** — captured 87.5% dedup savings |

**Stale evidence note:** `LAYER_SCORECARD.md:63` still says `14-maks-dedup.json` PENDING; file now exists.

## Phase 7 — Adversarial probes

Script: `C:\tmp\audit_maks_adversarial.py` (not committed)

```
host=win32 mte_available=False
probe1_cross_model_blind_share: FAIL
  lookup blocks q8 but share()+load_payload allow agent-b read without identity check
probe2_pin_eviction_bypass: PASS
  kv_id=kv_383d9ba210e04154bf7c7cee6ba83cda still pinned refcount=1
probe3_dedup_count_fabrication: PASS
  separate kv_ids; hits=0 inserts=2 ratio=0.0
probe4_share_token_reuse: FAIL
  token still valid after release
probe5_mte_provider_silent_fallback: PASS
  raises KVProviderUnavailableError: ARM MTE not exposed in user-space on GCP Axion; use ram/mmap/redis/nvme
```

| Probe | Result |
|-------|--------|
| probe1_cross_model_blind_share | **FAIL** |
| probe2_pin_eviction_bypass | **PASS** |
| probe3_dedup_count_fabrication | **PASS** |
| probe4_share_token_reuse | **FAIL** |
| probe5_mte_provider_silent_fallback | **PASS** |

MTE does **not** silently delegate to RAM — probe5 PASS.

## Findings

### Critical

- **Share permission model broken after release** — tokens remain valid after `release()`; stale tokens grant read (`sharing.py:104-118`, `manager.py:391-405`). Adversarial probe4 FAIL.

### High

- **`share()` has no `KVIdentity` gate** — cross-quant consumer can read via `share()` + `load_payload()` even when `lookup()` would raise `KVIdentityMismatchError` (`manager.py:322-323` vs `365-389`). Adversarial probe1 FAIL.
- **MTE / 2× agents pitch not evidenced** — spec lines #5–#7 graded F/D/F; no `maks_mte_available` in `MEASURED.md`.
- **Dedup savings bench is synthetic** — 87.5% on session-metadata blobs, not inference KV cache tensors (`benchmarks/maks_multi_agent_dedup_bench.py`).

### Medium

- **RAM `share()` copies bytes** before shm token; not zero-copy (`ram_backend.py:21-26`).
- **mmap tier** uses read-only mmap of files, not `MAP_SHARED` cross-process KV (`mmap_provider.py:70`).
- **Redis backend** unavailable without running Redis (`redis_provider.py:55-59`).
- **`LAYER_SCORECARD.md` stale** — claims step 14 PENDING while artifact exists.
- **`/maks/*` API not in layer-verify steps 12–13** — only step 14 bench; no HTTP endpoint exercise.

### Low

- `benchmarks/kv_share.py` exercises Plane-2 KV runtime, not MAKS Layer 5.
- Owner has no explicit `sharing.grant()` at create — implicit owner read only (`sharing.py:111-114`).

## Recommendations

1. **Revoke tokens on `release()`** — call `sharing.revoke(token)` or revoke by `(kv_id, consumer)` in `KVManager.release()` (`manager.py:391-405`). Effort: ~2h.
2. **Add `KVIdentity` check to `share()`** — require consumer identity compatible with record identity or explicit capability token (`manager.py:365-389`). Effort: ~4h.
3. **Gate `load_payload()` on `sharing.require_read()`** when `agent_id`/`token` supplied (`manager.py:511-521`). Effort: ~3h.
4. **Add `maks_mte_available` row to `MEASURED.md`** from `native_mte.AVAILABLE` / `feature_matrix()`. Effort: ~30m.
5. **Refresh `LAYER_SCORECARD.md` §8** — mark `14-maks-dedup.json` captured; remove PENDING (`LAYER_SCORECARD.md:63`). Effort: ~15m.
6. **Label dedup bench honestly** — document payloads are session metadata, not GGML KV (`benchmarks/maks_multi_agent_dedup_bench.py` header). Effort: ~30m.
7. **Wire `/maks/status` into layer-live-verify** optional HTTP step or document offline-only matrix (`api.py:38-47`, `scripts/layer-live-verify.sh`). Effort: ~2h.

## Honest scorecard line for LAYER_SCORECARD.md

```
| **MAKS / Multi-Agent KV Sharing** | PARTIAL | Memory OS real + 38 tests pass; dedup bench 87.5% on synthetic blobs only |
| ARM MTE zero-copy sharing | Marketing-only | `native_mte.AVAILABLE=False`; backends raise, do not ship on Axion |
| 2× concurrent agents | Marketing-only | No measured 2× baseline; `concurrent_agents_supported` is budget math |
| Share token security | FAIL (audit) | Tokens survive `release()`; `share()` lacks identity gate — fix before multi-tenant |
```
