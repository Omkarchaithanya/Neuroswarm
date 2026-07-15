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

## Affinity / NUMA

Axion VMs often report one NUMA node. `ThreadAffinityManager` is best-effort (`sched_setaffinity`). Optional `numactl` via ProcessSupervisor `numa_bind`.

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

