# GCP Axion Compatibility

Target: Google Cloud Axion `c4a-standard-8` (Arm Neoverse V2).

## What Axion exposes today

| Capability | Status on Axion | MAKS behavior |
|------------|-----------------|---------------|
| User-space ARM MTE | Not available | `FutureMTEBackend.AVAILABLE=False` |
| Public CXL memory pools | Not available | `FutureCXLBackend.AVAILABLE=False` |
| NUMA | Effectively single socket | Locality hint node 0 |
| RAM / mmap / NVMe | Available | Default path |
| Redis | Optional | Registry + cold/distributed share |

## Safe defaults

- Default provider: **RAM**
- Cold demotion: **mmap → NVMe**
- Registry: **SQLite** under `work/kv/maks/registry/`
- Sharing for DIPA: wired to `KVManager` (not in-process dict)
- Pressure threshold: **0.70** (aligned with Plane 2)

## Do not claim

Per ADR-0005:

- No MTE zero-copy wins on Axion demos
- No CXL sub-µs migration claims
- Feature detector must report UNAVAILABLE for MTE/CXL

## Config knobs

```text
NSA_MAKS_STORE / NSA_KV_STORE
NSA_MAKS_REGISTRY=sqlite|redis|memory
NSA_MAKS_DEFAULT_PROVIDER=ram
NSA_MAKS_EVICTION=lru|lfu|arc|temperature|cost_aware
NSA_MAKS_COMPRESSION=zstd|lz4|none
NSA_MAKS_RAM_BUDGET
NSA_MAKS_PRESSURE=0.70
```
