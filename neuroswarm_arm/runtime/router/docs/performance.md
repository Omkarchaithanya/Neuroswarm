# Performance guide

- Prefer `turbovec` on ARM64 (NEON kernels in Rust when the package is installed). Default quantization is **4-bit** over **384-dim** vectors.
- Memory rule of thumb: 10k tools × 384 dims × 4-bit ≈ **1.92 MB** for the TurboVec codebook path (plus float32 working set for inserts).
- Use embedding cache warm path after cold start (BGE-small ~33.4M params).
- `candidate_multiplier` trades recall vs latency; keyword expand is capped at `candidate_k`.
- Pin workers with `NSA_ROUTER_AFFINITY_CORES` on dedicated Axion VMs.
- Snapshot indexes to avoid re-embed on restart.
- Honest Axion note: SVE2 only claimed when `/proc/cpuinfo` exposes it; the optional `sve_dot` backend is a numpy stub (`kernel_path=numpy_stub`).
- Lean harness: `uv run python benchmarks/router_mcpga.py` writes `work/benchmarks/router_mcpga.json` (synthetic ~40 tools, top-3 vs naïve-all).
