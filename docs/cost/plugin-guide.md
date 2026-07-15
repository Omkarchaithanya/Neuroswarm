# RCIS Plugin Guide

Register without modifying ARMORA core:

```python
from neuroswarm_arm.armora.cost import register_cost_model, register_storage

@register_cost_model("axion_committed")
class AxionCommittedEstimator:
    def __init__(self, cfg): ...
    def estimate(self, observed, *, hardware=None): ...
    def estimate_energy_joules(self, **kwargs): ...

@register_storage("s3_parquet")
def build_s3(root, **kw): ...
```

Then set:

```
NSA_RCIS_COST_MODEL=axion_committed
NSA_RCIS_PLUGINS=myorg.rcis_plugins
```

## Extension points

| Decorator | Purpose |
|-----------|---------|
| `register_cost_model` | Live cost estimator |
| `register_energy_model` | Energy strategy alias |
| `register_predictor` | Prediction strategy |
| `register_accounting` | Unit economics |
| `register_storage` | Persistence backend |
| `register_telemetry` | Metrics exporter |
| `register_dashboard` | Dashboard panel provider |
