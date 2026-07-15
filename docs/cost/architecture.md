# RCIS Architecture

## Integration map

```
Gateway ──► BudgetEnvelope (admit)
       └──► RCIS.predict / finalize (learn)

DIPA ExecutionResult ──► ObservedRuntimeSignals ──► RuntimeCostReport
MAKS KV hits/misses  ──┘
AQR quantization     ──┘
ASCR speculation     ──┘
Performix / psutil   ──┘

RuntimeCostReport ──► Persistence (SQLite/DuckDB/Postgres/Parquet/JSON)
                  ──► Prometheus runtime_* / OTel
                  ──► IPlannerFeedback repositories
                  ──► AROP RCISObservationProvider (GEPA ASI)
```

## Hexagonal modules

| Module | Role |
|--------|------|
| `schemas.py` | Immutable `RuntimeCostReport`, predictions, errors |
| `estimator.py` | Live multi-component cost |
| `predictor.py` | Pre-execution expectations |
| `analyzer.py` | Predicted vs actual |
| `tracker.py` | Mutable in-flight sessions |
| `feedback.py` | Planner query API |
| `repositories.py` | Backend/quant/tier/spec ranking |
| `persistence.py` | Multi-backend store |
| `telemetry.py` | `runtime_*` metrics |
| `plugins.py` | Extension registry |
| `runtime_cost.py` | Facade `build_rcis()` |
| `arop_provider.py` | Read-only ObservationProvider |

## Patterns

- Protocols + dependency injection
- Strategy (cost/energy/storage/telemetry)
- Repository (planner feedback)
- Factory (`build_rcis`)
- Plugin-first (`NSA_RCIS_PLUGINS`)

## Config

All rates via `NSA_RCIS_*` — see [cost-model.md](cost-model.md). Zero hardcoded prices in estimator logic beyond configurable defaults loaded from env.
