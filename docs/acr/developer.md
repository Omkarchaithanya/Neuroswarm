# ACR Developer Guide

## Layout

```text
neuroswarm_arm/runtime/acr/
  kernel.py factory.py config.py
  ir/ understanding/ planner/ memory/ knowledge/
  scoring/ compression/ assembly/ cache/ versioning/
  evolution/ hardware/ metrics/ plugins/ connectors/
```

## Rules

1. Never `import mem0ai` here — use `NeuroMemory` adapter.
2. Never treat OKF as vector RAG — keyword/graph/mount only.
3. No circular imports into DIPA/HAOE concretes from engines; use connectors.
4. Justify ARM/NUMA optimizations with comments.
5. Every engine must update `ACRMetrics`.

## Kill switch

`NSA_ACR_ENABLED=0` → HAOE falls back to `merge_mem0_okf`.

## Tests

```bash
pytest tests/runtime/acr -q
python -m benchmarks.acr.bench_acr
```
