# Grafana Guide

Dashboards are generated from `neuroswarm_arm.metrics.dashboards.default_dashboards()` into `ops/grafana/dashboards/rmf-*.json`.

## Boards

| UID | Title |
|-----|-------|
| rmf-runtime-overview | Runtime Overview |
| rmf-planner | Planner |
| rmf-routing | Routing |
| rmf-budget | Budget |
| rmf-inference | Inference |
| rmf-haoe | HAOE |
| rmf-dipa | DIPA |
| rmf-memory | Memory |
| rmf-kv | KV |
| rmf-energy | Energy |
| rmf-cost | Cost |
| rmf-arm-hardware | ARM Hardware |
| rmf-performix | Performix |
| rmf-planner-learning | Planner Learning |

## Provisioning

Datasource: `ops/grafana/provisioning/datasources/prometheus.yaml`  
Dashboard provider: `ops/grafana/provisioning/dashboards/neuroswarm.yaml` (loads JSON from dashboards dir).

## Regenerate

```bash
python -c "from neuroswarm_arm.metrics.dashboards import write_dashboards; write_dashboards('ops/grafana/dashboards')"
```

Existing `armora-budget-envelope` / `rcis-runtime-cost` boards remain for plane-specific deep dives; RMF boards are the cross-runtime view.
