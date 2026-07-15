# Plugin Guide

ROF is plugin-first — extend without modifying ARMORA core.

## Register exporters

```python
from neuroswarm_arm.armora.telemetry import register_exporter

@register_exporter("my_sink")
def build_my_sink(config=None, **kw):
    return MyExporter(config)

# NSA_ROF_EXPORTERS=prometheus,my_sink
# NSA_ROF_PLUGINS=my_package.rof_plugins
```

Exporter surface: `export_spans`, `export_metrics`, `export_logs`, `sink_event`, `export_prometheus`, `shutdown`.

## Samplers

```python
from neuroswarm_arm.armora.telemetry import register_sampler

@register_sampler("my_sampler")
def build(config=None, **kw):
    return MySampler()
```

## Metric sources

```python
rof.register_metric_source(MySource())  # name + export_prometheus()
```

Or `@register_metric_source("foo")` factory discovered via `NSA_ROF_PLUGINS`.

## Event types

```python
from neuroswarm_arm.armora.telemetry import register_event_type
register_event_type("MyCustomEvent")
rof.emit("MyCustomEvent", payload={"k": 1})
```

## Trace processors / dashboards

`@register_trace_processor` / `@register_dashboard_provider` — same decorator pattern as Budget/RCIS plugins.
