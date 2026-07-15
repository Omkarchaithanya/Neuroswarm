# Developer Guide

## Package map

```
neuroswarm_arm/armora/profiling/
  profiler.py      # build_rpf / RuntimeProfilingFramework
  ports.py         # Protocols
  schemas.py       # RuntimeProfile + modes
  providers/       # performix, perf, psutil, mock, …
  collector.py
  telemetry.py
  exporters.py
  feedback.py
  connectors.py
  arop_provider.py
```

## Public API

```python
from neuroswarm_arm.armora import build_rpf, RuntimeProfilingFramework

rpf = build_rpf()
ctx = rpf.open_session(request_id="…", envelope_id="…")
rpf.record_phase(ctx.session_id, planner_ms=1.0)
rpf.sample(ctx.session_id)
profile = rpf.finalize_sync(ctx.session_id)
text = rpf.export_prometheus()
```

## Planner feedback

```python
ranks = rpf.feedback.hottest_backends_sync()
ipc = rpf.feedback.worst_ipc_workloads_sync()
p90 = rpf.feedback.latency_percentiles_sync(backend="llama.cpp")
asi = rpf.feedback.gepa_asi()  # for GEPA — no RL inside RPF
```

## Composition root

Wired in `neuroswarm_arm/main.py`:

- `rpf = build_rpf()`
- `RPFTelemetrySource` registered on ROF scrape merge
- Gateway session open/finalize around chat
- `ProfilingObservationProvider` added to AROP aggregator
- Optional `DecisionEngine.profiler_feedback = rpf.feedback`

## Tests

```bash
pytest tests/armora/profiling -q
```
