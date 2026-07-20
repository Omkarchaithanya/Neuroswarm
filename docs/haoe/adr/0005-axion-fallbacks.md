# ADR 0005: Axion Software Fallbacks

## Status

Accepted

## Context

Primary deploy target is GCP Axion `c4a-standard-8`: homogeneous CPUs, no exposed MTE/CXL, **single UMA domain (1 NUMA node per Google C4A docs)**. Cross-NUMA access penalties are not applicable on this host. Windows dev hosts lack `sched_setaffinity`.

## Decision

- Affinity: best-effort; `NoOpAffinityProvider` when bind fails
- NUMA: single-node placement via `NumaAdapter` / `collect_numa_status()` → `policy=single_uma`
- **Locality (preferred framing):** `locality_scheduler` selects `numa_aware` when `numa_nodes > 1`, else `cache_aware` core partitions (draft 0–1, verifier 2–7 on c4a-standard-8)
- Multi-NUMA `numactl` + llama `--numa` bind: **topology-gated** — only when guest `numa_nodes > 1` (`NSA_NUMA_POLICY=auto`)
- Never claim “NUMA activated”, “draft on NUMA0 / verifier on NUMA1”, or NUMA-split wins on Axion; metrics export `neuroswarm_cross_numa_applicable=0`
- MTE/CXL: provider stubs returning empty/unavailable
- networkx optional: pure-Python DAG fallback for minimal images
- Never raise because a hardware feature is missing

## Consequences

- Production-correct behavior on Axion today
- Feature detector still surfaces SVE2/etc. when present for future paths
- Docs must not claim hardware acceleration that is not active
- Probe: `scripts/probe-numa.sh` + `/health.numa` for judge-facing topology truth
- Router ANN: default `turbovec` (NEON/SIMD when the wheel provides it) with `exact`/`numpy` fallback. `SveDotIndex` is an API stub (`kernel_path=numpy_stub`). Do **not** set `nexus_hw_sve2_utilization` > 0 until real SVE kernels land. Mem0/Qdrant episodic memory is separate and not SVE-optimized.
