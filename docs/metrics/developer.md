# Developer Guide

## Never import prometheus_client in plane code

```python
# BAD
from prometheus_client import Counter

# GOOD
from neuroswarm_arm.metrics import get_rmf

rmf = get_rmf()
rmf.inc("nexus_routing_backend_usage_total", 1.0, labels={"backend": "sglang", "status": "ok"})
rmf.observe("nexus_dipa_prefill_latency_seconds", 0.12, labels={"backend": "sglang", "status": "ok", "model": "t1", "model_tier": "1", "quantization": "q4"})
```

## Typed handles

```python
from neuroswarm_arm.metrics import get_rmf

pub = get_rmf().publisher
pub.counter("nexus_request_total").inc(labels={"status": "ok", "request_type": "http", "streaming": "false", "reasoning": "false", "agent_type": "coding"})
```

## Legacy metrics_bridge

Existing `metrics_bridge.inc/set/describe` still works. Bind once at process start:

```python
from neuroswarm_arm.metrics import metrics, build_rmf

rmf = build_rmf()
metrics.bind(rmf)
```

## Async buffer (optional hot path)

```python
rmf.buffer.inc("nexus_request_total", 1.0, labels={...})
# background flusher drains into registry
```

## Config

| Env | Default |
|-----|---------|
| `NSA_RMF_ENABLED` | `1` |
| `NSA_RMF_EXPORTERS` | `prometheus,openmetrics` |
| `NSA_RMF_CARDINALITY_MAX` | `2048` |
| `NSA_RMF_BUFFER_MAX` | `65536` |
| `NSA_RMF_FLUSH_MS` | `25` |
| `NSA_RMF_PERFORMIX` | `0` |
| `NSA_RMF_METRICS_TOKEN` | empty (no auth) |
| `NSA_RMF_OTLP_ENDPOINT` | empty |
| `NSA_RMF_PLUGINS` | empty |

## Scrape

`GET /metrics` on the gateway. Optional `Accept: application/openmetrics-text` for OpenMetrics. Bearer token when `NSA_RMF_METRICS_TOKEN` set.
