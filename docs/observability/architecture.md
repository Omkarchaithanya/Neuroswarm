# ROF Architecture

## Role in NEXUS-ARM

ARMORA owns three OS planes:

| Plane | Package | Job |
|-------|---------|-----|
| Admit / enforce | `armora/budget` | Budget Envelope |
| Cost learning | `armora/cost` | RCIS |
| Observability | `armora/telemetry` | **ROF** |

ROF normalizes all telemetry through OpenTelemetry. Prometheus scrape preserves existing series ABI (`budget_*`, `runtime_*`, `haoe_*`, …) via metric-source bridges.

## Hexagonal modules

| Module | Role |
|--------|------|
| `context.py` | Immutable `RuntimeTraceContext` + contextvars |
| `tracing.py` | Span API over shared TracerProvider |
| `metrics.py` | Cardinality-guarded meter |
| `logging.py` | Structured JSON logs |
| `events.py` | Typed runtime event bus |
| `sampling.py` | AlwaysOn/Off, Head, Tail, Adaptive, Dynamic |
| `lifecycle.py` | Batch export queue + graceful shutdown |
| `exporters/` | OTLP, Prometheus, Jaeger, Tempo, Zipkin, JSON, SQLite, DuckDB |
| `bridges/` | MetricsStore, Budget, RCIS, HAOE, DIPA, Performix, AROP |
| `plugins.py` | Decorator registry |
| `runtime.py` | `build_rof()` facade |

## Integration

```
Client → Gateway (root) → Admission → Policy → Budget
      → HAOE workflow → DIPA planner → routing → infer → stream
      → RCIS cost → ROF export (OTLP/Prom/JSON)
ROF → ROFObservationProvider → AROP (propose-only)
```

## Performance

- Hot path: ContextVar + attribute set only
- Export: background thread, bounded queue, drop counters on backpressure
- Failures never block inference
- Target: telemetry overhead &lt; 1% p99 (see perf tests)

## Config

All knobs via `NSA_ROF_*` — see [developer.md](developer.md).
