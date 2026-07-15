# RMF Architecture

## Ownership

| Layer | Owns |
|-------|------|
| **RMF** | Metric definitions, registry, labels, collectors, aggregators, scrape export, alert/recording/dashboard artifacts |
| **Runtime planes** | When to publish (request lifecycle, scheduler ticks, inference stages) |
| **Prometheus** | Scrape + storage + PromQL evaluation |
| **Grafana / Alertmanager** | Visualization and paging |
| **ROF** | Traces, events, logs (may emit `rof_*` series; does not own business metrics) |
| **RCIS / Budget** | Cost learning / admission semantics; publish numbers into RMF |

Prometheus must **not** compute planner or admit decisions. It only exports what RMF normalizes.

## Integration map

```
Gateway ──► RMFMiddleware (RED)
ARMORA Budget ──► PlaneMetricBridge / export source
RCIS ──► PlaneMetricBridge / export source
HAOE / DIPA / MAKS / AWPP / KV / ACR ──► bridges + metrics_bridge dual-write
Performix / psutil ──► Collectors (interval, never request path)
RMF Registry ──► PrometheusExporter | OpenMetricsExporter | OTLPMetricsExporter
         └──► WindowAggregator ──► RMFObservationProvider ──► AROP feedback loop
```

## Hexagonal layout

- **Domain**: `MetricRegistry`, `MetricDef`, domain catalogue
- **Ports**: `MetricExporter`, `MetricCollector`, `MetricPublisher`
- **Adapters**: `exporters/*`, `collectors.py`, `bridges.py`, `compat.MetricsStore`
- **Plugins**: `plugins.py` (`NSA_RMF_PLUGINS`)

## Self-optimizing feedback loop

1. Planes publish latency/cost/KV/spec signals into RMF.
2. RCIS finalizes `RuntimeCostReport` and also exports `runtime_*` / `nexus_*` cost series.
3. `RMFObservationProvider` exposes aggregated gauges to AROP.
4. AROP proposes knobs (propose-only); it never scrapes Prometheus text for control.

## Compatibility

Legacy `MetricsStore` (`metrics_bridge=`) dual-writes into RMF when bound. Local `export_prometheus()` stays local-only so ROF bridges cannot recurse into RMF scrape.

## Performance

- Hot path: sharded registry updates; optional `AsyncMetricBuffer` batching.
- Collectors run on a timer, not on `/v1/chat/completions`.
- Cardinality hard-capped per metric (`NSA_RMF_CARDINALITY_MAX`).
