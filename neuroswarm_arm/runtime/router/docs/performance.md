# Performance guide

- Prefer `turbovec` on ARM64 (NEON kernels in Rust).
- Use embedding cache warm path after cold start.
- `candidate_multiplier` trades recall vs latency.
- Pin workers with `NSA_ROUTER_AFFINITY_CORES` on dedicated Axion VMs.
- Snapshot indexes to avoid re-embed on restart.
- Honest Axion note: SVE2 only claimed when `/proc/cpuinfo` exposes it.
