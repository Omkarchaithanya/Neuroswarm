# Runtime Observability Framework (ROF)

> **Ownership:** ROF belongs **only** to ARMORA (`neuroswarm_arm/armora/telemetry/`). Peers emit via injected ports / process-global `get_rof()` — they never own `TracerProvider` / export lifecycle.

## Mission

OpenTelemetry is the unified telemetry layer for NEXUS-ARM — traces, metrics, logs, and events. ROF is the observability operating system: every runtime stage emits correlated telemetry without slowing inference.

## Quickstart

```bash
export NSA_ROF_ENABLED=1
export NSA_ROF_EXPORTERS=prometheus,json
export NSA_ROF_SAMPLER=always_on
# optional OTLP → Tempo/Jaeger
export NSA_ROF_OTLP_ENDPOINT=http://localhost:4318
export NSA_ROF_EXPORTERS=otlp,prometheus,json
```

```python
from neuroswarm_arm.armora.telemetry import build_rof, SpanNames

rof = build_rof()
with rof.start_request(request_id="r1", agent_id="chat"):
    with rof.span(SpanNames.PLANNER):
        ...
print(rof.export_prometheus())
rof.shutdown()
```

## Placement

```
neuroswarm_arm/armora/telemetry/   # ownership
docs/observability/                # this documentation
tests/armora/telemetry/            # pytest suite
ops/grafana/dashboards/rof-*.json  # dashboards
```

Composition root: `neuroswarm_arm/main.py` calls `build_rof()` **before** budget/rcis/haoe/dipa, registers metric sources, installs `ROFMiddleware`, merges scrape at `GET /metrics`.

## Peer contract

| Peer | Obligation |
|------|------------|
| Gateway | Root request span; admission/policy/budget spans; envelope baggage |
| Budget | `budget_*` via bridge source; violations force-sample |
| RCIS | Cost span + `CostReportGenerated` / `PlannerLearned` |
| HAOE | CorrelationIds ↔ RuntimeTraceContext; no local TracerProvider |
| DIPA | Planner / routing / infer stage spans |
| AROP | `ROFObservationProvider` read-only |

## Docs index

- [architecture.md](architecture.md)
- [trace-flow.md](trace-flow.md)
- [metrics-catalogue.md](metrics-catalogue.md)
- [semantic-conventions.md](semantic-conventions.md)
- [dashboard-guide.md](dashboard-guide.md)
- [instrumentation-guide.md](instrumentation-guide.md)

- [developer.md](developer.md)
- [plugin-guide.md](plugin-guide.md)

## Axion + obs (Compose) — Prometheus / Grafana cheat sheet

Dual-host layout: **axion** serves the API; **neuroswarm-obs** serves Prometheus + Grafana.

| What | URL |
|------|-----|
| Health | `http://<axion>/health` |
| OpenAPI | `http://<axion>/docs` |
| Raw metrics | `http://<axion>/metrics` |
| Prometheus UI | `http://<obs>/prometheus/` |
| Grafana | `http://<obs>/grafana/` (`admin` / `neuroswarm`) |

**API vs Prometheus vs Grafana:** Swagger `/docs` is the HTTP API surface. Prometheus scrapes `GET /metrics` (`nexus_*`, `admit_*`, …). Grafana dashboards visualize those series — APIs do not appear as graphs automatically.

**Why Prometheus shows “No data queried yet”:** the Graph page starts blank. Type a PromQL expression and click **Execute**. Starters: `up`, `nexus_performix_ipc`, `nexus_performix_hotspot_pct`, `{__name__=~"nexus_.*"}`. Check **Status → Targets** for scrape health.

**Why `/` on axion is `{"detail":"Not Found"}`:** FastAPI has no root handler — use `/health` or `/docs`.

**Performix dashboard:** on Axion run `NSA_PERFORMIX_ALLOW_DEMO=0 NSA_AROP_PERFORMIX=1 bash scripts/refresh-performix-snapshot.sh` (cron every 2 min recommended). Expect `work/performix/snapshot.json` with `source=apx` or honest `unavailable` (never silent demo). Gateway reads that file via the compose volume. `PMU available = 0` is honest when hardware counters are unavailable. **Windows Performix GUI is optional** (SSH to Axion for interactive UI); automation uses host `apx` on the VM. Product MCP = `performix-bridge`, not `armlimited/arm-mcp` (IDE-only — see `.cursor/mcp.json.example`).
