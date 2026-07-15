# Benchmark guide

```bash
python benchmarks/router_accuracy.py
python benchmarks/router_full.py
python -m neuroswarm_arm.runtime.router.benchmarks.runner
```

Artifacts land in `work/benchmarks/router_*.json`.

Targets (MCPGA-aligned suite):

- top-3 accuracy ≥ 0.95 on seed templates
- schema reduction ~40 → 3
- routing P50 low-ms once BGE+TurboVec warm on Axion
