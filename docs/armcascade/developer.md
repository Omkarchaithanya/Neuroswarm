# ASCR Developer Guide

## Build

```python
from neuroswarm_arm.runtime.dipa import build_dipa

rt = build_dipa(use_mock=True)  # cascade_engine is ASCREngine
out = rt.infer(req)
```

Direct:

```python
from neuroswarm_arm.runtime.armcascade import build_ascr

engine = build_ascr(backend_registry, dipa_cascade_cfg=cascade_yaml_dict)
```

## Layout

```
neuroswarm_arm/runtime/armcascade/
  engine.py factory.py
  interfaces/ classifier/ proposal/ verification/
  acceptance/ confidence/ thresholds/ escalation/
  policies/ metrics/ arm/ plugins/ config/
```

## Compat

`neuroswarm_arm.runtime.dipa.cascade` still exports legacy types (`CascadeEngine`, `Verifier`, …) and re-exports `ASCREngine` / `build_ascr`. Prefer `armcascade` for new code.

## Tests

```bash
python -m pytest tests/runtime/armcascade/ -q
```

## Hot reload

`reload_ascr_config()` reloads YAML; wire through DIPA `ConfigurationManager` when extending control plane.
