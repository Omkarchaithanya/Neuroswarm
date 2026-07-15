# Dashboard Guide

Grafana boards under `ops/grafana/dashboards/` (auto-provisioned via `ops/grafana/provisioning/dashboards/neuroswarm.yaml`).

| Dashboard | File | Focus |
|-----------|------|-------|
| Runtime Overview | `rof-runtime-overview.json` | Requests, latency, drops, export health |
| Planner | `rof-planner.json` | Planner duration / prediction error |
| Cost | existing `rcis-runtime-cost.json` | `runtime_*` |
| Budget | existing `armora-budget-envelope.json` | `budget_*` |
| KV | existing `kv-memory-runtime.json` | `kv_*` / `maks_*` |
| RTG | existing `rtg-governor.json` | `rtg_*` |

## Datasources

- Prometheus → scrape `gateway:8000/metrics` (ROF-owned merge)
- Tempo/Jaeger → OTLP from `NSA_ROF_OTLP_ENDPOINT`

## Adding a board

1. Create JSON under `ops/grafana/dashboards/rof-*.json`
2. Use Prometheus queries against catalogue series
3. Optionally register an `IDashboardProvider` plugin that returns specs
