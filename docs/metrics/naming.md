# Metric Naming Guide

## Canonical form

```
nexus_<domain>_<metric>[_unit]
```

Rules:

- Counters end with `_total`.
- Use base units: `seconds`, `bytes`, `joules`, ratios `0..1`.
- Domains: `request`, `admission`, `planner`, `routing`, `haoe`, `dipa`, `budget`, `cost`, `memory`, `hw`, `performix`, `energy`, `rmf`.

## Labels (scrape)

**Allowed:** `agent_type`, `planner`, `backend`, `model`, `model_tier`, `quantization`, `worker`, `thread_pool`, `numa_node`, `request_type`, `streaming`, `reasoning`, `status`, plus bounded helpers (`dim`, `pool`, `tier`, `stage`, `event`, `outcome`, `error_class`).

**Forbidden on scrape series:** `workflow_id`, `request_id`, `trace_id`, `user_id`, prompts, IPs.

`workflow_id` / `request_id` belong on OTel spans and optional histogram **exemplars**, never as Prometheus labels.

## Cardinality

- Enumerate backends/models from catalogues.
- Cap distinct series per metric (`NSA_RMF_CARDINALITY_MAX`, default 2048).
- Prefer recording rules for high-fan-out rollups.

## Legacy aliases

RMF registers aliases so existing Grafana boards keep working:

| Legacy | Canonical |
|--------|-----------|
| `neuroswarm_requests_total` | `nexus_request_total` |
| `haoe_queue_depth` | `nexus_haoe_queue_depth` |
| `budget_remaining` | `nexus_budget_remaining` |
| `runtime_cost_total` | `nexus_runtime_cost_total` |

Dual-write remains enabled via `NSA_RMF_DUAL_WRITE_LEGACY=1`.
