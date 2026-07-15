# RPF Lifecycle

```
Initialize (build_rpf)
  → Capability Detection
  → Collect Metrics (open_session → sample / record_phase)
  → Generate RuntimeProfile (finalize)
  → Export Telemetry / Persistence
  → Shutdown
```

## Per-request

1. Gateway `open_session(request_id, agent_id, …)`
2. Optional mid-request `sample` / connector `push_phase`
3. `finalize_sync` → immutable `RuntimeProfile`
4. Telemetry `profile_*` + exporter write (best-effort)

## Failure rules

| Failure | Behavior |
|---------|----------|
| Provider crash | `FailureIsolatingProxy` demotes; log warning |
| Export fail | Drop batch; inference continues |
| Disabled (`NSA_RPF_ENABLED=0`) | No-op sessions; never raise |

Profiling failure **must never** terminate the runtime.
