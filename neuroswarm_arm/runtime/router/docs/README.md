# Semantic MCP Tool Router

Production AIM Pillar 2 service for NEXUS-ARM.

## Position

```
ARMORA → HAOE → Semantic MCP Tool Router → DIPA → AQR → Inference
```

Default path:

`BGE-small-en-v1.5 → TurboVec (NEON/SVE2 when present) → Hybrid fusion → Rerank → Top-K → DIPA prompt injection`

FAISS / HNSWlib / USearch / ScaNN remain pluggable via `NSA_ROUTER_ANN_BACKEND`.

## Quick start

```python
from neuroswarm_arm.runtime.router import build_router

router = build_router()
result = router.route("Upload artifact to S3")
print(result.tool_ids, result.confidence_top1)
print(router.prompt_block(result))
```

## API

See [api.md](api.md). Mounted by `create_tool_router(runtime)` in `main.py`.

## Config

See [configuration.md](configuration.md). Prefix: `NSA_ROUTER_*`.

## Docs index

- [architecture.md](architecture.md)
- [sequence.md](sequence.md)
- [data-flow.md](data-flow.md)
- [api.md](api.md)
- [configuration.md](configuration.md)
- [developer.md](developer.md)
- [benchmark.md](benchmark.md)
- [performance.md](performance.md)
- [deployment.md](deployment.md)
- [troubleshooting.md](troubleshooting.md)
