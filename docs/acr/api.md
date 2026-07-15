# ACR API

```python
from neuroswarm_arm.runtime.acr import build_acr, load_acr_config, AdaptiveContextRuntime

cfg = load_acr_config("work/acr")
acr = build_acr(config=cfg, memory=neuro, okf=okf)

snap = acr.build_context(
    "cascade policy on Axion",
    owner="agent-1",
    agent_role="architect",
    tool_names=["github-mcp"],
    token_budget=1500,
)

assert snap.prompt
assert snap.version.content_hash
print(snap.stats.compression.token_reduction)
print(snap.stats.compression.information_retained)

recs = acr.evolve(snap, success=True, cost=0.01, latency_ms=120.0, owner="agent-1")
print(acr.health())
print(acr.prometheus_text())
```

## Connectors

```python
from neuroswarm_arm.runtime.acr.connectors import (
    build_context_for_haoe,
    escalate_memory_needed,
    awpp_prefetch_hints,
    record_rtg_outcome,
)
from neuroswarm_arm.runtime.acr.connectors.ascr import ASCRMemoryConnector
from neuroswarm_arm.runtime.acr.connectors.awpp import ACRPrefetchPredictor
```

## IRs

- `ContextRequirementGraph`
- `RetrievalExecutionPlan` / `CompressionPlan` / `AssemblyPlan`
- `MemoryBundle` / `KnowledgeBundle`
- `ContextSnapshot` / `ContextVersion` / `ContextCacheKey`
- `ContextStatistics` / `CompressionMetrics`
