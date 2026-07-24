# Axion Optimization Guide

Target: GCP C4A (Axion) = Arm Neoverse **V2**.

## Detect

```bash
python build/detect_cpu.py -o work/cpu-profile.json
grep -E 'sve2|i8mm|asimddp|bf16|sme' /proc/cpuinfo | sort -u
```

## CMake

```bash
python build/generate_cmake.py --profile work/cpu-profile.json --print-cli
```

Uses `GGML_NATIVE=ON` (runtime ISA pick). Do **not** force `-mtune=neoverse-v3` on Axion.

## Affinity / locality (not fake NUMA-split)

**GCP C4A (Axion) is a single UMA domain** ([Google machine families](https://docs.cloud.google.com/compute/docs/machine-resource)): the guest reports **1 NUMA node**, so **cross-NUMA memory penalties do not apply**. Do not claim “draft on NUMA0 / verifier on NUMA1” on this SKU.

HAOE / `collect_numa_status()` performs **topology discovery**:

| Topology | Scheduler mode | Mechanism |
|----------|----------------|-----------|
| `numa_nodes > 1` | `numa_aware` | `numactl --cpunodebind/--membind` + llama `--numa isolate` |
| `numa_nodes == 1` (Axion) | `cache_aware` | Compose `cpuset` + `OMP_PROC_BIND=close` + `OMP_PLACES=cores` |

Default Axion 8-core partition (matches `TIER*_THREADS` 2/3/3):

```
tier1 draft:     cpuset 0-1
tier2 verifier:  cpuset 2-4
tier3 verifier:  cpuset 5-7
```

Manual check on the VM:

```bash
lscpu | grep -i numa          # expect: NUMA node(s): 1
numactl --hardware            # expect: available: 1 nodes (0)
bash scripts/probe-numa.sh    # → docs/evidence/latest/numa-status.json
curl -s localhost:8000/health | jq '.numa | {policy,locality_mode,cpuset_strings}'
docker inspect neuroswarm-arm-tier1-1 --format '{{.HostConfig.CpusetCpus}}'
```

Env: `NSA_LOCALITY_MODE`, `NSA_TIER1_CPUSET`, `NSA_TIER2_CPUSET`, `NSA_TIER3_CPUSET` (see `.env.example`).

## SME

Unset `GGML_KLEIDIAI_SME` for auto. Axion without SME → kernels fall back to DotProd/I8MM/SVE2.

## SGLang prefill (soft PD)

Axion CPU path (ADR-0006):

```bash
export SGLANG_USE_CPU_ENGINE=1
export NSA_DIPA_PD_MODE=soft
export NSA_DIPA_SGLANG_URL=http://127.0.0.1:30000
```

- Prefer W8A8 Arm builds for SGLang when available
- Pin OMP/affinity via DIPA `ThreadAffinityManager` (`dipa-prefill` / `dipa-decode` pools)
- Do **not** claim Mooncake/NIXL on Axion — transfer mode stays `recompute`
- Shared agent system prompts: `PrefixCacheManager.warm()` / ARMORA `warmup_prefix`
- RAM budget: avoid co-locating large BF16 SGLang + 3 GGUF tiers on c4a-standard-8 (32GB)

See [docs/dipa/pd-architecture.md](../dipa/pd-architecture.md) and [migration-pd.md](../dipa/migration-pd.md).

