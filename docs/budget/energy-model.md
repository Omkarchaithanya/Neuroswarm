# Energy Model

## First-class signal

Energy is a peer budget dimension to cost and latency. ARMORA tracks estimated joules, tokens/watt, and future ARM PMU integration.

## Interface

`IEnergyModel.project(cpu_seconds, thread_count, numa_node, hardware) → EnergyProjection`

## Formula (default software model)

```
watts ≈ base_watts + (thread_count × watts_per_thread) × numa_efficiency(node)
joules ≈ cpu_seconds × watts
tokens_per_watt ≈ tokens / max(watts, ε)
```

All coefficients come from `BudgetRuntimeConfig` / plugins.

## ARM Performix / PMU (future provider)

Reuse AROP `PerformixProvider` pattern:

- Observation provider reads Performix / Linux perf / PMU counters
- Maps cycles, instructions, package energy to `EnergyBudget.consumed`
- Does **not** live inside DIPA — injected via `IEnergyModel` plugin

## Integration

| Peer | Use |
|------|-----|
| DIPA | Project energy before tier/quant choice |
| HAOE | Prefer NUMA-local workers when energy residual low |
| MAKS | Cold-page migration cost in joules |
| Telemetry | `budget_tokens_per_watt`, `budget_remaining{dim=energy}` |
| AROP | Tune energy soft/hard thresholds via policy templates |

## Axion notes

On GCP Axion (single NUMA typical), `numa_efficiency` defaults to 1.0. Multi-NUMA Graviton paths apply locality penalties from HAOE topology providers.
