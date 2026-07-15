# RPF Architecture

## Ownership

RPF lives only under `neuroswarm_arm/armora/profiling/`.

- **Observes** CPU, memory, NUMA, hardware counters, phase timings
- **Never** admits (Budget) or prices (RCIS) or mutates policy (AROP)
- ARM Performix = optional `IProfilerProvider` only

## Integration map

```
Gateway ──► BudgetEnvelope (admit)
       ├──► RCIS.predict / finalize (learn)
       └──► RPF.open_session / sample / finalize (profile)

DIPA / HAOE / MAKS / AQR / AWPP
    └──► ProfileSignalBus.push_phase (connectors only)

RuntimeProfile ──► Persistence (JSON/SQLite/DuckDB/Parquet)
               ──► Prometheus profile_* / OTel
               ──► IProfilerFeedback (planner)
               ──► ProfilingObservationProvider (AROP / GEPA ASI)
```

## Hexagonal modules

| Module | Role |
|--------|------|
| `schemas.py` | Immutable `RuntimeProfile`, modes, metric blocks |
| `ports.py` | Protocols (`IProfilerProvider`, collectors, exporters, feedback) |
| `registry.py` | Capability detect + cascade + `FailureIsolatingProxy` |
| `providers/` | performix, perf, ebpf, psutil, mock, parca, pyroscope |
| `collector.py` | Session open / phase / sample / finalize |
| `reports.py` | Build frozen `RuntimeProfile` |
| `telemetry.py` | `profile_*` Prometheus + OTel bridge |
| `exporters.py` | JSON / SQLite / DuckDB / Parquet / OTLP |
| `feedback.py` | Planner + RL observation APIs (no RL impl) |
| `plugins.py` | Extension registry |
| `profiler.py` | Facade `build_rpf()` |
| `arop_provider.py` | Read-only ObservationProvider |
| `connectors.py` | Peer phase signal bus |

## Patterns

- Protocols + DI
- Strategy (providers / exporters / telemetry)
- Factory (`build_rpf`)
- Repository (profile store → feedback ranks)
- Plugin-first (`NSA_RPF_PLUGINS`)
- Failure isolation — profiling never kills inference

## Cascade

Performix (if allowed + `apx` present) → Linux perf → psutil → mock.

Override: `NSA_RPF_PROVIDER=<name>`.
