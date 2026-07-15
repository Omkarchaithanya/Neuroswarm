# Plugin / Extension Guide

Add profilers, exporters, reports, metric sources, telemetry, dashboards **without editing ARMORA core**.

## Decorators

```python
from neuroswarm_arm.armora.profiling.plugins import (
    register_profiler,
    register_exporter,
    register_report_builder,
    register_metric_source,
    register_telemetry,
    register_dashboard,
)
```

## Discovery

```bash
export NSA_RPF_PLUGINS=acme.nexus.rpf_plugins
```

Modules are imported at `build_rpf()`; failures log warnings and continue.

## Example exporter

```python
from pathlib import Path
from neuroswarm_arm.armora.profiling.plugins import register_exporter
from neuroswarm_arm.armora.profiling.schemas import RuntimeProfile

class MyExporter:
    def __init__(self, root: Path, **kwargs):
        self.root = root

    def name(self) -> str:
        return "mine"

    def export(self, profile: RuntimeProfile) -> None:
        (self.root / f"{profile.profile_id}.txt").write_text(profile.profiler_used)

@register_exporter("mine")
def build_mine(root, **kwargs):
    return MyExporter(root)
```

Then `NSA_RPF_EXPORTER=mine`.
