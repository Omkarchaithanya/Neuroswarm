# RCIS Dashboard Guide

## Grafana

Dashboard: [`ops/grafana/dashboards/rcis-runtime-cost.json`](../../ops/grafana/dashboards/rcis-runtime-cost.json)

Panels:

- Live Cost timeline (`runtime_cost_total`)
- Cost per token / Tokens per dollar
- CPU / Memory / Energy
- KV reuse / Spec acceptance
- Tokens per watt
- Planner accuracy + prediction errors
- Backend / Quant / Model cost series

## Prometheus series

| Metric | Type |
|--------|------|
| `runtime_cost_total` | counter |
| `runtime_cost_per_token` | gauge |
| `runtime_cpu_seconds` | gauge |
| `runtime_memory_bytes` | gauge |
| `runtime_energy_estimate` | gauge |
| `runtime_kv_reuse` | gauge |
| `runtime_spec_acceptance` | gauge |
| `runtime_backend_cost` | counter |
| `runtime_model_cost` | counter |
| `runtime_quant_cost` | counter |
| `runtime_planner_prediction_error` | gauge |
| `runtime_tokens_per_dollar` | gauge |
| `runtime_tokens_per_watt` | gauge |

Provisioned automatically with other NeuroSwarm Grafana dashboards.
