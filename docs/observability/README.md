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
- [host-monitoring.md](host-monitoring.md) — htop/btop + Glances/cAdvisor (live host/container metrics)
- [linux-perf-ebpf.md](../profiling/linux-perf-ebpf.md) — host `perf` / bpftrace vs Kleidi PID (open-source; not ProfInfer)
- [llama-native.md](../profiling/llama-native.md) — llama-server timings, llama-bench, tier Prometheus `/metrics`

- [developer.md](developer.md)
- [plugin-guide.md](plugin-guide.md)

## Axion + obs (Compose) — Prometheus / Grafana cheat sheet

Dual-host layout: **axion** serves the API; **neuroswarm-obs** serves Prometheus + Grafana.

| What | URL |
|------|-----|
| Health | `http://<axion>/health` |
| OpenAPI | `http://<axion>/docs` |
| Raw metrics | `http://<axion>/metrics` |
| Prometheus UI | `http://<obs>/prometheus/` (nginx basic auth + Grafana admin password) |
| Grafana | `http://<obs>/grafana/` (same; set `GRAFANA_ADMIN_PASSWORD`, run `bash scripts/gen-obs-htpasswd.sh`) |

**Canonical scrape:** Prometheus on obs scrapes **`neuroswarm-gateway`** → `10.128.0.2:80`, plus **`cadvisor`** → `:8088` and **`glances`** → `:61209` when the Axion `hostmon` profile is up. Do not run Compose and k3s/Helm gateways at the same time (series ×2–3). Do not scrape OTEL `:8889`. See [host-monitoring.md](host-monitoring.md).

**API vs Prometheus vs Grafana:** Swagger `/docs` is the HTTP API surface. Prometheus scrapes `GET /metrics` (`nexus_*`, `admit_*`, …) from Axion gateway **`:8000`** (obs job `neuroswarm-gateway` → `10.128.0.2:8000`). Grafana on **obs** visualizes those series — APIs do not appear as graphs automatically.

**Why Prometheus shows “No data queried yet”:** the Graph page starts blank. Type a PromQL expression and click **Execute**. Starters: `up`, `nexus_performix_ipc{job="neuroswarm-gateway"}`, `nexus_performix_hotspot_pct`, `{__name__=~"nexus_.*"}`. Check **Status → Targets** for scrape health.

**Why `/` on axion is `{"detail":"Not Found"}`:** FastAPI has no root handler — use `/health` or `/docs`.

**Performix dashboard:** on Axion run `NSA_PERFORMIX_ALLOW_DEMO=0 NSA_AROP_PERFORMIX=1 bash scripts/refresh-performix-snapshot.sh` (PID-scoped; refuses idle `--system-wide` unless `PERFORMIX_ALLOW_SYSTEM_WIDE=1`). Expect `work/performix/snapshot.json` with `source=apx` or honest `unavailable` (never silent demo / never leave stale). Gateway collector exports zeros when `source` is `demo|synthetic|unavailable` or `available=0`. `PMU available = 0` is honest when hardware counters are unavailable. Top-down panels are **last snapshot** gauges — see `nexus_performix_snapshot_age_seconds`.

**AROP gauges** (RMF bridge `wire_arop`; zeros when AROP disabled / no policy):

| Metric | Meaning |
|--------|---------|
| `arop_active` | 1 when `NSA_AROP_ENABLED` |
| `arop_draft_len` / `arop_accept_threshold` / `arop_escalate_threshold` | Active policy knobs |
| `arop_canary_percent` | Current canary share |
| `arop_rollback_total` | Successful deployment rollbacks |
| `arop_last_status` | Last `run_once` status code (`0` disabled … `5` rolled_back) |

PromQL starters: `arop_active`, `arop_draft_len`, `rate(arop_rollback_total[1h])` (gauge; use `increase` only if scraped as counter later).

**Windows access to Grafana:** tunnel **obs** (not Axion `:3000`):

```powershell
ssh -L 13000:127.0.0.1:3000 ... neuroswarm-obs
# → http://127.0.0.1:13000/grafana/
```

Full GUI + tunnel steps: [performix-gui-windows.md](../telemetry/performix-gui-windows.md). Automation uses host `apx` on the VM. Product MCP = `performix-bridge`, not `armlimited/arm-mcp` (IDE-only — see `.cursor/mcp.json.example`).
