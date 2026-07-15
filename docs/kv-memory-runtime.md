# KV Memory Runtime (Plane 2)

Production KV Memory Runtime for NEXUS-ARM / NeuroSwarm-ARM on Google Cloud Axion (Arm Neoverse V2).

This is **Plane 2** of the architecture: fixed-size block virtual memory, prefix caching, multi-backend storage tiering, sharing, checkpoint/recovery, NUMA-aware placement, and telemetry — without CUDA, MTE, or CXL implementations.

**Layer 5 MAKS** (`neuroswarm_arm/runtime/maks/`) is the multi-agent control plane that sits on top of this substrate. See [`docs/maks/architecture.md`](maks/architecture.md).

## Package map

```text
neuroswarm_arm/runtime/kv/
  interfaces/     ABC contracts (provider, sharing, compression, allocator, …)
  allocator/      NUMA policy + local RAM allocator (single-node Axion fallback)
  block/          Block model, Logical/Physical tables, CoW
  manager/        KVBlockManager + KVRuntimeManager
  providers/      RAM → CompressedRAM → mmap → NVMe → LMDB → Redis (+ CXL/MTE stubs)
  sharing/        shm / mmap / LMDB / Redis sharing backends (Plane 2 substrate for Layer 5 MAKS)
  compression/    none / zstd / lz4
  migration/      tiering policy engine
  scheduler/      hot/warm/cold background migration
  checkpoint/     metadata + payload separation
  recovery/       journal + hash validation
  telemetry/      Prometheus metrics
  security/       capability tokens (no MTE)
  benchmark/      in-process bench runners
  api.py          FastAPI /kv/* router
  factory.py      build_kv_runtime() DI factory
```

## Storage tiers

```text
L1 RAM  →  L2 Compressed RAM  →  L3 MemoryMapped / NVMe  →  L4 LMDB  →  L5 Redis
                                                                    ↘ FUTURE CXL / MTE (stubs)
```

Migration is driven by access frequency, last access, temperature, reference count, priority, and memory pressure (default threshold **0.70**).

## Public API

```python
from neuroswarm_arm.runtime.kv import build_kv_runtime, load_kv_config

runtime = build_kv_runtime(load_kv_config("work/kv"), enable_background=False)
session = runtime.create_session("s1", agent_id="agent-a")
block = await runtime.allocate("s1", b"opaque-kv-tensor-bytes")
await runtime.checkpoint("s1")
await runtime.restore("s1")
snap = runtime.pressure_snapshot()  # used by ReasoningGovernor / Cost Router
```

## REST endpoints

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/kv/status` | Health, pressure, providers |
| GET | `/kv/metrics` | JSON KV metrics |
| POST/GET | `/kv/session` | Create / inspect session |
| POST | `/kv/allocate` | Allocate a block |
| POST | `/kv/share` | Cross-agent share |
| POST | `/kv/checkpoint` | Checkpoint session |
| POST | `/kv/restore` | Restore / resume |
| GET/POST | `/kv/provider` | List / select providers |
| POST | `/kv/benchmark` | Run named benchmark |
| GET | `/kv/pressure` | Governor pressure snapshot |

Gateway `/metrics` merges Plane-2 Prometheus series (`kv_*`). Grafana dashboard: [`ops/grafana/dashboards/kv-memory-runtime.json`](../ops/grafana/dashboards/kv-memory-runtime.json).

## Axion / NUMA notes

`c4a-standard-8` is effectively single-socket. The NUMA policy detects `/sys/devices/system/node` when present and **falls back to node 0** otherwise. Cross-node allocation is avoided when multi-node topology exists.

## Future backends

`CXLProvider` and `MTEProvider` are registered as stubs and raise `NotImplementedError`. Do not select them in production.

## Config (`NSA_KV_*`)

| Variable | Default | Meaning |
|----------|---------|---------|
| `NSA_KV_STORE` | `work/kv` | Root for mmap/nvme/lmdb/checkpoints |
| `NSA_KV_BLOCK_SIZE` | `256` | Tokens per logical block |
| `NSA_KV_RAM_BUDGET` | `512MiB` | L1/L2 budget for pressure |
| `NSA_KV_PRESSURE_THRESHOLD` | `0.70` | Migration trigger |
| `NSA_KV_COMPRESSION` | `zstd` | Cold-tier codec (`none`/`zstd`/`lz4`) |
| `NSA_KV_SHARING_BACKEND` | `mmap` | `mmap`/`shm`/`lmdb`/`redis` |
| `NSA_KV_REDIS_URL` | `redis://localhost:6379/0` | Redis provider/share |
| `NSA_KV_BG_MIGRATION` | `1` | Background scheduler |

## Benchmarks

```bash
python benchmarks/kv_run_all.py
# or individually: kv_prefix.py, kv_restore.py, kv_share.py, …
```

Reports land in `work/benchmarks/kv_*.json` (+ `.md`).

## Tests

```bash
pytest tests/runtime/kv -q
```
