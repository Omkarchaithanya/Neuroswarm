# Plugin Guide

Extend RMF without modifying ARMORA core.

## Registration

```python
from neuroswarm_arm.metrics.plugins import (
    register_exporter,
    register_collector,
    register_aggregator,
    register_alert_rules,
    register_dashboard,
    register_provider,
)

@register_collector("my_hw")
class MyHWCollector:
    def __init__(self, registry, **kwargs): ...
    def collect(self) -> None: ...
    def start(self) -> None: ...
    def stop(self) -> None: ...
```

Load via:

```
NSA_RMF_PLUGINS=my_company.nexus_rmf_plugins
```

## Extension points

| Hook | Role |
|------|------|
| `register_provider` | Custom metric publishers |
| `register_exporter` | New export formats |
| `register_collector` | Pull collectors (PMU, RAPL, …) |
| `register_aggregator` | Window / rollup strategies |
| `register_alert_rules` | Extra Alertmanager groups |
| `register_dashboard` | Extra Grafana JSON builders |

## Built-ins

- Exporters: `prometheus`, `openmetrics`, `otlp`
- Collectors: `psutil`, `performix`
- Aggregator: `window`
- Alerts / dashboards: `default`
