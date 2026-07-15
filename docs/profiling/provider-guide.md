# Provider Guide

## Built-in providers

| Name | When available | Metrics |
|------|----------------|---------|
| `performix` | `apx` on PATH + `NSA_RPF_ALLOW_PERFORMIX=1` | Recipe hotspots, optional HW |
| `perf` | Linux + `perf` binary | cycles, instructions, cache/branch |
| `psutil` | `psutil` importable | CPU%, RSS/VMS, threads, affinity, ctx switches |
| `mock` | always | Deterministic synthetic |
| `ebpf` | bcc or bpftrace present | Interface ready; empty until instrumented |
| `parca` | `NSA_RPF_PARCA_URL` set | Continuous sink reachability |
| `pyroscope` | `NSA_RPF_PYROSCOPE_URL` set | Continuous sink reachability |

## Auto selection

```
performix → perf → psutil → mock
```

Force: `NSA_RPF_PROVIDER=psutil`.

## Writing a provider

Implement methods matching `IProfilerProvider` (see `ports.py`):

- `name`, `capabilities()`, `initialize()`, `start()`, `sample()`, `stop()`, `shutdown()`, `health()`

Register via plugin:

```python
from neuroswarm_arm.armora.profiling.plugins import register_profiler

@register_profiler("mine")
def build_mine(**kwargs):
    return MineProvider()
```

Load with `NSA_RPF_PLUGINS=my.package.mod` and `NSA_RPF_PROVIDER=mine`.

## Honesty rules (Axion)

- Do not claim SVE2 / I8MM / PMU unless detector says so
- Performix wins require evidence (`apx` + successful recipe)
- Missing hardware → `UNAVAILABLE`, never raise
