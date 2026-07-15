# Runtime Profiling Framework (RPF)

ARMORA-owned observation plane for CPU / memory / hardware / phase timings.

| Subsystem | Role |
|-----------|------|
| Budget Envelope | Admit / enforce |
| RCIS | Cost learn |
| **RPF** | Profile / sample / `RuntimeProfile` |

ARM Performix is **one optional provider**, never a hard dependency.

## Docs

- [architecture.md](architecture.md)
- [lifecycle.md](lifecycle.md)
- [diagrams.md](diagrams.md)
- [provider-guide.md](provider-guide.md)
- [plugin-guide.md](plugin-guide.md) / [extension.md](extension.md)
- [developer.md](developer.md)
- [telemetry.md](telemetry.md)
- [benchmark.md](benchmark.md)

## Quick start

```python
from neuroswarm_arm.armora import build_rpf

rpf = build_rpf()
ctx = rpf.open_session(request_id="r1", agent_id="a1")
rpf.record_phase(ctx.session_id, planner_ms=10, execution_ms=100)
rpf.sample(ctx.session_id)
profile = rpf.finalize_sync(ctx.session_id)
print(profile.profiler_used, profile.hardware.ipc)
```

## Env

| Var | Default | Meaning |
|-----|---------|---------|
| `NSA_RPF_ENABLED` | `1` | Master switch |
| `NSA_RPF_MODE` | `production` | disabled/sampling/tracing/… |
| `NSA_RPF_PROVIDER` | `auto` | performix\|perf\|psutil\|mock\|… |
| `NSA_RPF_ALLOW_PERFORMIX` | `1` | Allow Performix in auto cascade |
| `NSA_RPF_SAMPLE_HZ` | `1` | Sampling frequency |
| `NSA_RPF_TELEMETRY` | `prometheus` | prometheus\|otel |
| `NSA_RPF_EXPORTER` | `json` | json\|sqlite\|duckdb\|parquet |
| `NSA_RPF_OTEL` | `0` | Enable OTel bridge |
| `NSA_RPF_PLUGINS` | `` | Comma module paths |

## Tests

```bash
pytest tests/armora/profiling -q
```
