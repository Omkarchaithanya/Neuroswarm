# Telemetry Guide

## Prometheus series (`profile_*`)

| Series | Type | Meaning |
|--------|------|---------|
| `profile_sessions_total` | counter | Finalized sessions |
| `profile_failures_total` | counter | Non-fatal profiling failures |
| `profile_cpu_usage_percent` | gauge | Last CPU % |
| `profile_ipc` | gauge | Last IPC |
| `profile_memory_peak_bytes` | gauge | Peak RSS |
| `profile_execution_ms` | gauge | Execution phase |
| `profile_planner_ms` | gauge | Planner phase |
| `profile_sample_hz` | gauge | Configured sample rate |

Scraped via ROF `/metrics` merge (`RPFTelemetrySource`).

## OpenTelemetry

Set `NSA_RPF_OTEL=1` or `NSA_RPF_TELEMETRY=otel`.

Spans: `rpf.profile`, `rpf.export` (best-effort; no-op if SDK absent).

## Persistence exporters

| `NSA_RPF_EXPORTER` | Sink |
|--------------------|------|
| `json` | `work/profiling/*.json` + `profiles.jsonl` |
| `sqlite` | `profiles.sqlite` (+ JSON fallback) |
| `duckdb` | `profiles.duckdb` (degrades to JSON) |
| `parquet` | `profiles.parquet` (degrades to JSON) |

## Grafana

Dashboard: `ops/grafana/dashboards/rpf-runtime-profiling.json`.
