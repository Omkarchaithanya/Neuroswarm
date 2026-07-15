# Developer Guide

## Local stack

```bash
# Prometheus scrapes gateway /metrics (see ops/prometheus.yml)
# Optional Tempo:
#   OTLP HTTP :4318  → set NSA_ROF_OTLP_ENDPOINT=http://localhost:4318
export NSA_ROF_ENABLED=1
export NSA_ROF_EXPORTERS=prometheus,json,sqlite
export NSA_ROF_SAMPLER=always_on
export NSA_ROF_WORK_DIR=work/rof
```

## Factory

```python
from neuroswarm_arm.armora.telemetry import build_rof, load_rof_config

cfg = load_rof_config()
rof = build_rof(cfg)
assert rof.export_prometheus()
rof.shutdown(timeout_ms=2000)
```

## Env reference

| Var | Default | Meaning |
|-----|---------|---------|
| `NSA_ROF_ENABLED` | `1` | Master switch |
| `NSA_ROF_SERVICE_NAME` | `nexus-arm` | Resource attribute |
| `NSA_ROF_OTLP_ENDPOINT` | empty | OTLP HTTP base |
| `NSA_ROF_SAMPLER` | `always_on` | `always_on\|always_off\|head:0.1\|tail\|adaptive\|dynamic` |
| `NSA_ROF_EXPORTERS` | `prometheus,json` | Comma list |
| `NSA_ROF_BATCH_SIZE` | `512` | Export batch |
| `NSA_ROF_EXPORT_TIMEOUT_MS` | `5000` | Exporter timeout |
| `NSA_ROF_MAX_QUEUE_SIZE` | `2048` | Backpressure queue |
| `NSA_ROF_JSON_PATH` | `work/rof/telemetry.jsonl` | JSONL sink |
| `NSA_ROF_SQLITE_PATH` | `work/rof/telemetry.sqlite` | SQLite sink |
| `NSA_ROF_DUCKDB_PATH` | `work/rof/telemetry.duckdb` | DuckDB sink |
| `NSA_ROF_PLUGINS` | empty | Extra import paths |
| `NSA_ROF_LOG_LEVEL` | `INFO` | JSON log level |

## Tests

```bash
pytest tests/armora/telemetry -q
```
