# Instrumentation Guide

## Gateway

```python
with rof.start_request(request_id=..., agent_id=...):
    with rof.span(SpanNames.ADMISSION):
        ...
```

`AgentGateway` already wraps chat + budget + HAOE + RCIS when `rof=` is injected.

## DIPA

`ExecutionPipeline.run` uses `get_rof()` for planner/routing/infer spans. Connectors may use:

```python
from neuroswarm_arm.armora.telemetry import get_rof, SpanNames

rof = get_rof()
if rof:
    with rof.span(SpanNames.QUANT, attributes={"nexus.quantization": q}):
        ...
```

Or inject `DIPAObservabilityAdapter(rof)`.

## HAOE

Do **not** call `trace.set_tracer_provider`. Use shared provider:

```python
from neuroswarm_arm.armora.telemetry import HAOEObservabilityAdapter
adapter = HAOEObservabilityAdapter(rof)
with adapter.workflow_span(ids):
    ...
```

## Events + logs

```python
rof.emit_builtin(EventType.INFERENCE_STARTED, payload={"backend": "llama.cpp"})
rof.log("INFO", "infer done", latency_ms=12.3, cost_estimate=0.001)
```

Every log merges active `RuntimeTraceContext`.

## Metrics

```python
rof.counter("nexus_backend_selected_total", labels={"backend": "llama.cpp", "model_tier": "tier1"})
rof.histogram("nexus_inference_duration_seconds", 0.12)
```

Forbidden labels are dropped and counted on `rof_metric_label_drops_total`.
