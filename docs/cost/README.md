# Runtime Cost Intelligence System (RCIS)

> **Ownership:** RCIS belongs **only** to ARMORA (`neuroswarm_arm/armora/cost/`).
> Peers consult repositories / metrics — they never own cost intelligence storage.

## Mission

Every inference produces two outputs:

1. **ExecutionResult** (DIPA / gateway response)
2. **RuntimeCostReport** (immutable learning signal)

Cost is an **optimization signal**, not billing. Budget Envelope remains the admit/enforce contract.

## Placement

```
neuroswarm_arm/armora/cost/   # ownership
docs/cost/                    # this documentation
tests/armora/cost/            # pytest suite
work/rcis/                    # persistence root
ops/grafana/dashboards/rcis-runtime-cost.json
```

## Boundary vs Budget Envelope

| Concern | Owner |
|---------|--------|
| Admit / freeze / reserve / degrade | `armora/budget` |
| Predict / estimate / analyze / feedback | **RCIS** |
| Planner routing decisions | DIPA / HAOE via `IPlannerFeedback` only |
| Policy evolution | AROP observes RCIS (propose-only) |

## Anti-LiteLLM

LiteLLM tracks `tokens × hosted price map` for API spend.
RCIS estimates multi-resource runtime cost (CPU, memory, energy, KV, speculation, planner, queue) for ARM-native routing improvement.

## Core loop

```
predict → open session → execute → observe → estimate → analyze → persist → feedback
```

## Related docs

- [lifecycle.md](lifecycle.md)
- [cost-model.md](cost-model.md)
- [prediction.md](prediction.md)
- [developer.md](developer.md)
- [plugin-guide.md](plugin-guide.md)
- [dashboard-guide.md](dashboard-guide.md)
- [diagrams.md](diagrams.md)
